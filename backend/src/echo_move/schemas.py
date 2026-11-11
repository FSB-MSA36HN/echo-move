"""Pydantic models for the WebSocket protocol."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FrameMessage(BaseModel):
    """Client → server: one base64 JPEG/PNG data-URL plus a timestamp in seconds."""

    image: str = ""
    timestamp: float | None = Field(default=None)
