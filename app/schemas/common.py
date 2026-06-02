from typing import Any

from pydantic import BaseModel, Field, AliasChoices


class NotifyWebhookPayload(BaseModel):
    guild_id: str | None = None
    channel_id: str | None = None
    user_id: str | None = None
    message_content: str | None = Field(default=None, validation_alias=AliasChoices("message_content", "message"))
    embed_data: dict[str, Any] | None = None
    points_awarded: bool | None = None
    alert_id: str | None = None
    title: str | None = None
    severity: str | None = None
    status: str | None = None
    component: str | None = None
    location: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    team_id: str | None = None
    team_name: str | None = None

    _SEVERITY_COLORS: dict[str, int] = {
        "low": 0x2ECC71,
        "medium": 0xF39C12,
        "high": 0xE74C3C,
        "informational": 0x95A5A6,
        "info": 0x95A5A6,
    }
    _SEVERITY_ICONS: dict[str, str] = {
        "low": "🟢",
        "medium": "🟠",
        "high": "🔴",
        "informational": "ℹ️",
        "info": "ℹ️",
    }

    def get_message_content(self) -> str:
        if self.message_content:
            return self.message_content

        if not self.title:
            raise ValueError(
                "NotifyWebhookPayload requires either message_content or title to build a notification"
            )

        severity = self.severity or "INFO"
        status = self.status or "unknown"
        component = self.component or "unknown component"
        location = self.location or "unknown location"
        team = self.team_name or self.team_id or "unknown team"
        source_type = self.source_type or "unknown source"
        alert_id_line = f"Alert ID: {self.alert_id}\n" if self.alert_id else ""

        return (
            f"[{severity}] {self.title}\n"
            f"{alert_id_line}"
            f"Status: {status}\n"
            f"Component: {component}\n"
            f"Location: {location}\n"
            f"Source: {source_type}\n"
            f"Team: {team}"
        )

    def get_severity_key(self) -> str:
        return (self.severity or "").strip().lower()

    def get_severity_icon(self) -> str:
        return self._SEVERITY_ICONS.get(self.get_severity_key(), "⚪")

    def get_severity_color(self) -> int:
        return self._SEVERITY_COLORS.get(self.get_severity_key(), 0x95A5A6)

    def build_embed_data(self) -> dict[str, Any] | None:
        embed_data = dict(self.embed_data or {})
        message_content = self.get_message_content()

        if self.title and "title" not in embed_data:
            embed_data["title"] = f"{self.get_severity_icon()} {self.title}"

        if "description" not in embed_data:
            embed_data["description"] = message_content

        if "color" not in embed_data:
            embed_data["color"] = self.get_severity_color()

        return embed_data or None


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
