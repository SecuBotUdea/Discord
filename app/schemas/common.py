from typing import Any

from pydantic import BaseModel, Field


class NotifyWebhookPayload(BaseModel):
    guild_id: str
    channel_id: str
    message_content: str
    embed_data: dict[str, Any] | None = None


class ActionWebhookPayload(BaseModel):
    action: str
    alert_id: str
    guild_id: str
    user_id: str


class HealthResponse(BaseModel):
    status: str = Field(description="healthy/degraded")
    bot_connected: bool
    database_connected: bool
    timestamp: str
