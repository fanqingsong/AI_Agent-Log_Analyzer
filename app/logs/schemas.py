"""Pydantic model for inbound log entries."""

from typing import Optional

from pydantic import BaseModel


class MockKafkaLogEntry(BaseModel):
    """Format of the mock logs sent to the ingest endpoint."""

    timestamp: str
    level: str
    component: Optional[str] = None
    message: str
    source: Optional[str] = None
