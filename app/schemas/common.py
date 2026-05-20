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


class NotificationWebhookPayload(BaseModel):
    guild_id: str
    channel_id: str | None = None
    message_content: str
    embed_data: dict[str, Any] | None = None
    source: str | None = Field(default=None, description="Origin service, for example gloria or secubot")
    event_type: str | None = Field(default=None, description="Logical event name, for example rescan_valid or rescan_invalid")


class RescanActionResultPayload(BaseModel):
    guild_id: str
    alert_id: str
    user_id: str
    status: str = Field(description="valid or invalid")
    message_content: str
    embed_data: dict[str, Any] | None = None
    source: str = "gloria"


class HealthResponse(BaseModel):
    status: str = Field(description="healthy/degraded")
    bot_connected: bool
    database_connected: bool
    timestamp: str
