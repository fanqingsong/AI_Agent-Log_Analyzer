"""Pydantic models for the chat service."""

from typing import Literal

from pydantic import BaseModel
from typing_extensions import TypedDict


class ChatMessage(TypedDict):
    """Format of messages sent to the browser."""

    role: Literal['user', 'model']
    timestamp: str
    content: str


class ChatDeleteRequest(BaseModel):
    chatId: str
