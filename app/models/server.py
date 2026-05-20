from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ServerRecord(BaseModel):
    server_id: str
    guild_id: str
    webhook_id: str
    webhook_token: str
    channel_id: str
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_document(self) -> dict[str, Any]:
        return self.model_dump()
