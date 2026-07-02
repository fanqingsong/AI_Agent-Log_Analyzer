"""Shared FastAPI dependencies.

DB connections and the LLM agent are attached to ``app.state`` during the
lifespan startup and yielded to routes via these helpers.
"""

from fastapi import Request

from app.chat.repository import ChatDB
from app.llm.agent import LogAgent
from app.logs.repository import Redis


async def get_db(request: Request) -> ChatDB:
    return request.state.db


async def get_redis_db(request: Request) -> Redis:
    return request.state.redis_db


def get_log_agent(request: Request) -> LogAgent:
    return request.state.log_agent
