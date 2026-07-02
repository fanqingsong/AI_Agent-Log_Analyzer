# PostgreSQL 17

from __future__ import annotations # Allows forward references in type hints without quotes
import asyncpg # Async PostgreSQL client library
import logfire  # Add logfire for telemetry and tracing
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter # Pydantic models for chat messages
from typing import List
import json


# Database configuration parameters
DB_SCHEME = "postgresql"
DB_USERNAME = "postgres"
DB_PASSWORD = "password"
DB_HOST = "localhost"
DB_PORT = 5555
DB_NAME = "chat_hist_db"

# Construct the PostgreSQL connection string (DSN) from the above parameters
POSTGRES_DSN = f"{DB_SCHEME}://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

class ChatDB:
    """
    Asynchronous PostgreSQL database interface for chat messages.
    This class stores and retrieves chat history using JSON strings in a table.
    """

    def __init__(self, pool: asyncpg.Pool):
        # Initializes the asyncpg connection pool for reuse
        self.pool = pool

    @classmethod
    async def connect(cls) -> ChatDB:
        """
        Asynchronously create a connection pool and ensure the 'messages' table exists.
        This method is called to initialize the ChatDB.
        """

        # Use logfire span for tracing DB connection setup
        with logfire.span('Connect to PGSQ17 DB: CREATE TABLE IF NOT EXISTS...'):

            pool = await asyncpg.create_pool(dsn=POSTGRES_DSN, min_size=1, max_size=10)
            # max_size = maximum number of concurrent open connections in the pool

            # Acquire a connection from the pool and create the table if it doesn't exist:
            async with pool.acquire() as conn:
                await conn.execute(
                    """CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        message_list JSONB NOT NULL,
                        chat_id TEXT,
                        inserted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );"""
                )

            # Return an instance of ChatDB using the connection pool
            return cls(pool)


    async def add_messages(self, messages_json: str) -> None:
        """
        Add new messages to the database.
        """
        with logfire.span('Adding messages to DB: INSERT INTO messages...'):
            async with self.pool.acquire() as conn:
                messages_data = json.loads(messages_json)
                # Get chat_id from the first message
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
        """
        Retrieve all stored chat messages, parse them from JSON, and return as a list of ModelMessage objects.
        Messages are ordered by chat_id and creation time.
        """
        with logfire.span('Get chat messages from DB: SELECT message_list FROM messages...'):
            async with self.pool.acquire() as conn:
                # Create table if not exists
                await conn.execute(
                    """CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        message_list JSONB NOT NULL,
                        chat_id TEXT,
                        inserted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );"""
                )
                
                # Get messages ordered by chat_id and creation time
                rows = await conn.fetch("""
                    SELECT message_list, chat_id 
                    FROM messages 
                    ORDER BY chat_id, inserted_at;
                """)

            messages: List[ModelMessage] = []
            for row in rows:
                # Parse messages and add chat_id to each message
                parsed_messages = ModelMessagesTypeAdapter.validate_json(row["message_list"])
                for msg in parsed_messages:
                    # Add chat_id to each message if it's not already present
                    if hasattr(msg, 'parts') and msg.parts:
                        for part in msg.parts:
                            if not hasattr(part, 'chat_id'):
                                part.chat_id = row["chat_id"]
                messages.extend(parsed_messages)
            return messages

    async def delete_messages(self, chat_id: str) -> dict:
        """
        Delete messages from the database based on chat_id.
        Returns information about deleted messages.
        """
        with logfire.span(f'Deleting messages for chat {chat_id} from DB'):
            async with self.pool.acquire() as conn:
                # Get the number of messages before deletion
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM messages WHERE chat_id = $1",
                    chat_id
                )
                
                # Delete messages
                result = await conn.execute(
                    "DELETE FROM messages WHERE chat_id = $1",
                    chat_id
                )
                
                return {
                    "deleted_messages_count": count,
                    "success": True,
                    "chat_id": chat_id
                }


    async def close(self):
        """Close the connection pool."""
        await self.pool.close()
