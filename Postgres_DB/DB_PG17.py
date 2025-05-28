
# PostgreSQL 17

from __future__ import annotations # Allows forward references in type hints without quotes
import asyncpg # Async PostgreSQL client library
import logfire  # Add logfire for telemetry and tracing
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter # Pydantic models for chat messages
from typing import List


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
                        message_list TEXT NOT NULL, 
                        inserted_at TIMESTAMP DEFAULT now()
                    );"""
                )

            # Return an instance of ChatDB using the connection pool
            return cls(pool)

    async def add_messages(self, messages: bytes):
        """
        Insert a new set of messages into the database.
        The messages can be bytes or string, and will be stored as a JSON string.
        """
        
        msg_str = messages.decode("utf-8") if isinstance(messages, bytes) else str(messages)

        with logfire.span('Add new messages to DB: INSERT INTO messages (message_list)...'):
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO messages (message_list) VALUES ($1);",
                    # $1 is a positional placeholder for the first parameter (msg_str)
                    # Using placeholders protects against SQL injection
                    msg_str
                )

    async def get_messages(self) -> List[ModelMessage]:
        """
        Retrieve all stored chat messages, parse them from JSON, and return as a list of ModelMessage objects.
        """
        with logfire.span('Get chat messages from DB: SELECT message_list FROM messages...'):
            # Use a connection to fetch all message rows, ordered by ID (insertion order)

            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT message_list FROM messages ORDER BY id;")

            messages: List[ModelMessage] = []
            # Each row contains a JSON string — parse and extend the messages list

            for row in rows:
                # Use Pydantic to validate and parse the JSON string
                messages.extend(ModelMessagesTypeAdapter.validate_json(row["message_list"]))
            return messages

    async def close(self):
        """Close the connection pool."""
        await self.pool.close()
