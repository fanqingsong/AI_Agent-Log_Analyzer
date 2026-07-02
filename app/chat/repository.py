"""Async PostgreSQL repository for chat message persistence.

Stores PydanticAI message lists as JSONB rows keyed by chat_id.
"""

from __future__ import annotations

import asyncio
import json
from typing import List

import asyncpg
import logfire
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app import config


class ChatDB:
    """Asynchronous PostgreSQL interface for chat messages."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls) -> ChatDB:
        """Create a connection pool (with retries) and ensure the table exists."""
        with logfire.span('Connect to PostgreSQL DB: CREATE TABLE IF NOT EXISTS...'):
            pool = None
            last_error: Exception | None = None
            for attempt in range(1, config.DB_CONNECT_RETRIES + 1):
                try:
                    pool = await asyncpg.create_pool(
                        dsn=config.POSTGRES_DSN, min_size=1, max_size=10
                    )
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """CREATE TABLE IF NOT EXISTS messages (
                                id SERIAL PRIMARY KEY,
                                message_list JSONB NOT NULL,
                                chat_id TEXT,
                                inserted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            );"""
                        )
                    break
                except (OSError, asyncpg.PostgresError,
                        asyncpg.ConnectionDoesNotExistError,
                        asyncpg.ConnectionFailureError) as e:
                    last_error = e
                    if pool is not None:
                        await pool.close()
                        pool = None
                    logfire.warn(
                        f"Postgres not ready (attempt {attempt}/{config.DB_CONNECT_RETRIES}): {e}"
                    )
                    await asyncio.sleep(config.DB_CONNECT_RETRY_DELAY)

            if pool is None:
                raise RuntimeError(
                    f"Could not connect to PostgreSQL at {config.DB_HOST}:{config.DB_PORT} "
                    f"after {config.DB_CONNECT_RETRIES} attempts"
                ) from last_error

            return cls(pool)

    async def add_messages(self, messages_json: str) -> None:
        with logfire.span('Adding messages to DB: INSERT INTO messages...'):
            async with self.pool.acquire() as conn:
                messages_data = json.loads(messages_json)
                chat_id = None
                if isinstance(messages_data, list) and messages_data:
                    chat_id = messages_data[0].get('chatId')

                await conn.execute(
                    """
                    INSERT INTO messages (message_list, chat_id)
                    VALUES ($1, $2)
                    """,
                    messages_json,
                    chat_id
                )

    async def get_messages(self) -> List[ModelMessage]:
        with logfire.span('Get chat messages from DB: SELECT message_list FROM messages...'):
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT message_list, chat_id
                    FROM messages
                    ORDER BY chat_id, inserted_at;
                """)

            messages: List[ModelMessage] = []
            for row in rows:
                parsed_messages = ModelMessagesTypeAdapter.validate_json(row["message_list"])
                for msg in parsed_messages:
                    if hasattr(msg, 'parts') and msg.parts:
                        for part in msg.parts:
                            if not hasattr(part, 'chat_id'):
                                part.chat_id = row["chat_id"]
                messages.extend(parsed_messages)
            return messages

    async def delete_messages(self, chat_id: str) -> dict:
        with logfire.span(f'Deleting messages for chat {chat_id} from DB'):
            async with self.pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM messages WHERE chat_id = $1",
                    chat_id
                )
                await conn.execute(
                    "DELETE FROM messages WHERE chat_id = $1",
                    chat_id
                )
                return {
                    "deleted_messages_count": count,
                    "success": True,
                    "chat_id": chat_id
                }

    async def close(self):
        await self.pool.close()
