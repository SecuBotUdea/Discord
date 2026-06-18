from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AlertMessageMapping(BaseModel):
    alert_id: str
    guild_id: str
    channel_id: str
    message_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actioned_at: datetime | None = None
    action_status: str | None = None
    acted_by_user_id: str | None = None

    def to_document(self) -> dict[str, Any]:
        return self.model_dump()
