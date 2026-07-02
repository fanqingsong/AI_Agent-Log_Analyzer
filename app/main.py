"""FastAPI application entry point.

This module only wires things together: logfire setup, lifespan
(DB/Redis/agent connections), static files, and router includes.
All business logic lives in the ``app.chat`` and ``app.logs`` packages.
"""

import os
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.chat.repository import ChatDB
from app.chat.routes import router as chat_router
from app.llm.agent import LogAgent
from app.logs.repository import redis_init
from app.logs.routes import router as logs_router
from app.logs.service import register_system_prompt


# --- Logfire telemetry ----------------------------------------------------
logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()
logfire.instrument_redis()


# --- Application lifespan -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await ChatDB.connect()
    redis_db = await redis_init()

    log_agent = LogAgent()
    register_system_prompt(log_agent)

    # Attach resources to app.state so dependencies can read them.
    app.state.db = db
    app.state.redis_db = redis_db
    app.state.log_agent = log_agent

    try:
        yield
    finally:
        await db.close()
        if redis_db is not None:
            await redis_db.close()


app = FastAPI(lifespan=lifespan)

# Frontend assets live at the project root under Mock_UI/.
app.mount("/static", StaticFiles(directory="../Mock_UI"), name="static")

logfire.instrument_fastapi(app)

# Register service routers.
app.include_router(chat_router)
app.include_router(logs_router)


# --- Browser entry points -------------------------------------------------
@app.get('/')
async def index() -> RedirectResponse:
    """Redirect root to the chat UI."""
    return RedirectResponse(url="/static/chat_app.html")


@app.get('/chat_app.ts')
async def main_ts() -> RedirectResponse:
    """Redirect to the TypeScript frontend file."""
    return RedirectResponse(url="/static/chat_app.ts")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )
