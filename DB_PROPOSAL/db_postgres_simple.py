# main_postgres_simple.py
"""
FastAPI chat app using PostgreSQL for chat history storage (async, plain SQL, no logfire, no SQLAlchemy).
Replace DATABASE_URL with your actual PostgreSQL credentials.
Install dependencies:
    pip install fastapi uvicorn databases asyncpg pydantic_ai
"""

from __future__ import annotations as _annotations
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Depends, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from typing import Annotated

from schemas import ChatMessage
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
import databases

# Configure your PostgreSQL connection here
DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/chatdb"
database = databases.Database(DATABASE_URL)

CREATE_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    message_list TEXT NOT NULL
);
"""

async def create_messages_table():
    # Use a direct connection for table creation
    import asyncpg
    conn = await asyncpg.connect(DATABASE_URL.replace('+asyncpg', ''))
    await conn.execute(CREATE_TABLE_QUERY)
    await conn.close()

class Database:
    """Async PostgreSQL database for chat messages."""
    def __init__(self, db):
        self.db = db

    async def add_messages(self, messages: bytes):
        await self.db.execute(
            "INSERT INTO messages (message_list) VALUES (:messages)",
            {"messages": messages.decode("utf-8") if isinstance(messages, bytes) else messages},
        )

    async def get_messages(self) -> list[ModelMessage]:
        rows = await self.db.fetch_all("SELECT message_list FROM messages ORDER BY id")
        messages: list[ModelMessage] = []
        for row in rows:
            messages.extend(ModelMessagesTypeAdapter.validate_json(row["message_list"]))
        return messages

THIS_DIR = Path(__file__).parent

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await database.connect()
    await create_messages_table()
    db = Database(database)
    try:
        yield {'db': db}
    finally:
        await database.disconnect()

app = FastAPI(lifespan=lifespan)

@app.get('/')
async def index() -> FileResponse:
    return FileResponse((THIS_DIR / 'Mock_UI/chat_app.html'), media_type='text/html')

@app.get('/Mock_UI/chat_app.ts')
async def main_ts() -> FileResponse:
    """Get the raw typescript code."""
    return FileResponse((THIS_DIR / 'Mock_UI/chat_app.ts'), media_type='text/plain')

async def get_db(request: Request) -> Database:
    return request.state.db

@app.get('/chat/')
async def get_chat(database: Database = Depends(get_db)) -> Response:
    msgs = await database.get_messages()
    return Response(
        b'\n'.join(json.dumps(to_chat_message(m)).encode('utf-8') for m in msgs),
        media_type='text/plain',
    )

def to_chat_message(m: ModelMessage) -> ChatMessage:
    first_part = m.parts[0]
    if isinstance(m, ModelRequest):
        if isinstance(first_part, UserPromptPart):
            assert isinstance(first_part.content, str)
            return {
                'role': 'user',
                'timestamp': first_part.timestamp.isoformat(),
                'content': first_part.content,
            }
    elif isinstance(m, ModelResponse):
        if isinstance(first_part, TextPart):
            return {
                'role': 'model',
                'timestamp': m.timestamp.isoformat(),
                'content': first_part.content,
            }
    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {m}')

@app.post('/chat/')
async def post_chat(
    prompt: Annotated[str, Form()], database: Database = Depends(get_db)
) -> StreamingResponse:
    async def stream_messages():
        """Streams new line delimited JSON `Message`s to the client."""
        yield (
            json.dumps(
                {
                    'role': 'user',
                    'timestamp': datetime.now(tz=timezone.utc).isoformat(),
                    'content': prompt,
                }
            ).encode('utf-8') + b'\n'
        )
        messages = await database.get_messages()
        # Uncomment and configure your agent below
        # async with agent.run_stream(prompt, message_history=messages) as result:
        #     async for text in result.stream(debounce_by=0.01):
        #         m = ModelResponse(parts=[TextPart(text)], timestamp=result.timestamp())
        #         yield json.dumps(to_chat_message(m)).encode('utf-8') + b'\n'
        #     await database.add_messages(result.new_messages_json())
    return StreamingResponse(stream_messages(), media_type='text/plain')

@app.post("/logs/ingest")
async def log_receiver(request: Request):
    raw_body = await request.body()
    log_text = raw_body.decode("utf-8")
    print(f"Received log: {log_text}")
    return {"status": "ok", "message": "Log received"}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main_postgres_simple:app", host="127.0.0.1", port=8000, reload=True)
    # In cmd: uvicorn main_postgres_simple:app --host 127.0.0.1 --port 8000 --reload
