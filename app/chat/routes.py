"""HTTP routes for the chat service (conversation + model switching)."""

import json

import logfire
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from typing import Annotated

from app.chat.repository import ChatDB
from app.chat.schemas import ChatDeleteRequest
from app.chat.service import stream_chat_response, to_chat_message
from app.deps import get_db, get_log_agent

router = APIRouter()


@router.get('/chat/')
async def get_chat(db: ChatDB = Depends(get_db)) -> Response:
    msgs = await db.get_messages()
    return Response(
        json.dumps([to_chat_message(msg) for msg in msgs]),
        media_type='application/json',
    )


@router.post('/chat/')
async def post_chat(
    prompt: Annotated[str, Form()],
    db: ChatDB = Depends(get_db),
    log_agent=Depends(get_log_agent),
) -> StreamingResponse:
    """Stream a chat response. Available models: openai, anthropic, deepseek, ollama(local)."""
    return StreamingResponse(
        stream_chat_response(prompt, db, log_agent), media_type='text/plain'
    )


@router.delete("/chat/delete")
async def delete_chats(
    request: ChatDeleteRequest,
    db: ChatDB = Depends(get_db),
) -> JSONResponse:
    """Delete a chat and its messages by chat ID."""
    result = await db.delete_messages(request.chatId)
    return JSONResponse(status_code=200, content=result)


@router.post('/set_model/')
async def set_model(request: Request, log_agent=Depends(get_log_agent)):
    """Change the active LLM model at runtime."""
    data = await request.json()
    model_name = data.get('model')

    if model_name:
        log_agent.change_model(model_name)
        logfire.info(f"You are using: {log_agent.agent.model}")
        return {"status": "ok", "model": model_name}
    return {"status": "error", "reason": "No model specified"}
