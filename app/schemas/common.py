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
    event_type: str | None = Field(default=None, description="Logical event name, for example rescan_valid")

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

    def is_points_awarded(self) -> bool:
        if self.points_awarded is not None:
            return self.points_awarded
        if isinstance(self.embed_data, dict):
            points_awarded = self.embed_data.get("points_awarded")
            if isinstance(points_awarded, bool):
                return points_awarded
        return False

    def is_rescan_valid_event(self) -> bool:
        if self.event_type == "rescan_valid":
            return True
        return self.is_points_awarded()

    def is_rescan_result_event(self) -> bool:
        if self.event_type in ("rescan_valid", "rescan_invalid"):
            return True
        if self.points_awarded is not None:
            return True
        if isinstance(self.embed_data, dict) and "points_awarded" in self.embed_data:
            return True
        return False

    def get_message_content(self) -> str:
        if self.is_rescan_result_event():
            return ""

        if self.message_content:
            return self.message_content

        if not self.title:
            raise ValueError(
                "NotifyWebhookPayload requires either message_content or title to build a notification"
            )

        # CORRECCIÓN: Normalizamos la severidad. 
        # .capitalize() transformará "medium" en "Medium". Si prefieres todo en mayúsculas, usa .upper()
        severity = (self.severity or "INFO").strip().capitalize() 
        
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

        if self.title and "title" not in embed_data:
            embed_data["title"] = f"{self.get_severity_icon()} {self.title}"

        if "description" not in embed_data:
            description_lines = []
            
            if self.is_rescan_result_event() and self.message_content:
                description_lines.append(self.message_content)
                description_lines.append("")

            if self.alert_id:
                description_lines.append(f"Alert ID: {self.alert_id}")
            if self.status:
                description_lines.append(f"Status: {self.status}")
            if self.component:
                description_lines.append(f"Component: {self.component}")
            if self.location:
                description_lines.append(f"Location: {self.location}")
            if self.source_type:
                description_lines.append(f"Source: {self.source_type}")
            if self.team_name or self.team_id:
                description_lines.append(f"Team: {self.team_name or self.team_id}")

            if description_lines:
                embed_data["description"] = "\n".join(description_lines).strip()

        if "color" not in embed_data:
            color = self.get_severity_color()
            if self.message_content:
                if "not resolved yet" in self.message_content:
                    color = 0xF39C12  # Orange/Warning
                elif "marked as invalid" in self.message_content:
                    color = 0xE74C3C  # Red/Error
            embed_data["color"] = color

        if not self.is_rescan_result_event():
            footer = embed_data.get("footer")
            if isinstance(footer, dict):
                footer.setdefault("text", "Reacciona con 🔄 para solicitar rescan")
            else:
                embed_data["footer"] = {"text": "Reacciona con 🔄 para solicitar rescan"}

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
