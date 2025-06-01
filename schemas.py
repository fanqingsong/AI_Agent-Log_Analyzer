from pydantic import BaseModel
from typing_extensions import TypedDict
from typing import Literal, Optional


class ChatMessage(TypedDict):
    """Format of messages sent to the browser."""

    role: Literal['user', 'model']
    timestamp: str
    content: str


class MockKafkaLogEntry(BaseModel):
    """Format of the mock logs to endpoint."""

    timestamp: str
    level: str
    component: Optional[str] = None
    message: str
    source: Optional[str] = None
