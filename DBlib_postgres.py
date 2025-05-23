# DBlib_postgres.py - PostgreSQL 17 version, async, no logfire, simple and clean
import asyncpg
from typing import List
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

# Database connection settings (adjust as needed)
POSTGRES_DSN = "postgresql://postgres:password@localhost:5555/chat_hist_db"

class ChatDB:
    """
    Async PostgreSQL database for chat messages.
    Stores and retrieves chat history as JSON strings.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls) -> 'ChatDB':
        """Create a connection pool and ensure the table exists."""
        pool = await asyncpg.create_pool(dsn=POSTGRES_DSN, min_size=1, max_size=5)
        #MAX sieze??

        async with pool.acquire() as conn:
            await conn.execute(
                '''CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    message_list TEXT NOT NULL
                );'''
            )
        return cls(pool)

    async def add_messages(self, messages: bytes):
        """Insert a new message (as bytes or str) into the database."""

        msg_str = messages.decode("utf-8") if isinstance(messages, bytes) else str(messages)

        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO messages (message_list) VALUES ($1);",
                msg_str
            )

    async def get_messages(self) -> List[ModelMessage]:
        """Retrieve all messages from the database, parsed as ModelMessage objects."""

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT message_list FROM messages ORDER BY id;")
        
        messages: List[ModelMessage] = []

        for row in rows:
            messages.extend(ModelMessagesTypeAdapter.validate_json(row["message_list"]))
        return messages

    async def close(self):
        """Close the connection pool."""
        await self.pool.close()
