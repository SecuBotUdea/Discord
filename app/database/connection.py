from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from app.models.server import ServerRecord
from app.models.alert_mapping import AlertMessageMapping

logger = logging.getLogger(__name__)


class InMemoryServerRepository:
    def __init__(self) -> None:
        self._servers: dict[str, dict[str, Any]] = {}

    async def upsert_server(self, server: ServerRecord) -> None:
        now = datetime.now(timezone.utc)
        existing = self._servers.get(server.guild_id)
        document = server.to_document()
        if existing:
            document["created_at"] = existing["created_at"]
        document["updated_at"] = now
        self._servers[server.guild_id] = document

    async def get_server(self, guild_id: str) -> dict[str, Any] | None:
        return self._servers.get(guild_id)

    async def deactivate_server(self, guild_id: str) -> None:
        current = self._servers.get(guild_id)
        if current:
            current["active"] = False
            current["updated_at"] = datetime.now(timezone.utc)


class InMemoryWebhookLogRepository:
    def __init__(self) -> None:
        self._logs: list[dict[str, Any]] = []

    async def add_log(
        self,
        server_id: str,
        action: str,
        payload: dict[str, Any],
        status: str,
        error: str | None = None,
    ) -> None:
        self._logs.append(
            {
                "server_id": server_id,
                "action": action,
                "payload": payload,
                "status": status,
                "error": error,
                "created_at": datetime.now(timezone.utc),
            }
        )


class InMemoryAlertMessageRepository:
    def __init__(self) -> None:
        # message_id -> document
        self._by_message: dict[str, dict[str, Any]] = {}
        # alert_id -> document
        self._by_alert: dict[str, dict[str, Any]] = {}

    async def upsert_mapping(self, mapping: AlertMessageMapping) -> None:
        doc = mapping.to_document()
        self._by_message[mapping.message_id] = doc
        self._by_alert[mapping.alert_id] = doc

    async def get_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        return self._by_message.get(message_id)

    async def get_by_alert_id(self, alert_id: str) -> dict[str, Any] | None:
        return self._by_alert.get(alert_id)

    async def mark_actioned(self, message_id: str, status: str, acted_by_user_id: str | None = None) -> None:
        doc = self._by_message.get(message_id)
        if not doc:
            return False
        if doc.get("action_status"):
            # already actioned
            return False
        doc["actioned_at"] = datetime.now(timezone.utc)
        doc["action_status"] = status
        doc["acted_by_user_id"] = acted_by_user_id
        # mirror to alert index
        self._by_alert[doc.get("alert_id")] = doc
        return True


class MongoServerRepository:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def upsert_server(self, server: ServerRecord) -> None:
        document = server.to_document()
        await self._collection.update_one(
            {"guild_id": server.guild_id},
            {
                "$set": {
                    "server_id": server.server_id,
                    "guild_id": server.guild_id,
                    "webhook_id": server.webhook_id,
                    "webhook_token": server.webhook_token,
                    "channel_id": server.channel_id,
                    "active": server.active,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {"created_at": document["created_at"]},
            },
            upsert=True,
        )

    async def get_server(self, guild_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"guild_id": guild_id, "active": True})

    async def deactivate_server(self, guild_id: str) -> None:
        await self._collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
        )


class MongoWebhookLogRepository:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def add_log(
        self,
        server_id: str,
        action: str,
        payload: dict[str, Any],
        status: str,
        error: str | None = None,
    ) -> None:
        await self._collection.insert_one(
            {
                "server_id": server_id,
                "action": action,
                "payload": payload,
                "status": status,
                "error": error,
                "created_at": datetime.now(timezone.utc),
            }
        )


class MongoAlertMessageRepository:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def upsert_mapping(self, mapping: AlertMessageMapping) -> None:
        doc = mapping.to_document()
        await self._collection.update_one(
            {"message_id": mapping.message_id},
            {"$set": doc},
            upsert=True,
        )

    async def get_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"message_id": message_id})

    async def get_by_alert_id(self, alert_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"alert_id": alert_id})

    async def mark_actioned(self, message_id: str, status: str, acted_by_user_id: str | None = None) -> None:
        result = await self._collection.update_one(
            {"message_id": message_id, "action_status": {"$exists": False}},
            {
                "$set": {
                    "actioned_at": datetime.now(timezone.utc),
                    "action_status": status,
                    "acted_by_user_id": acted_by_user_id,
                }
            },
        )
        return bool(getattr(result, "modified_count", 0))


class DatabaseManager:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.client: AsyncIOMotorClient | None = None
        self.server_repository: InMemoryServerRepository | MongoServerRepository = InMemoryServerRepository()
        self.webhook_log_repository: InMemoryWebhookLogRepository | MongoWebhookLogRepository = InMemoryWebhookLogRepository()
        self.alert_message_repository: InMemoryAlertMessageRepository | MongoAlertMessageRepository = InMemoryAlertMessageRepository()
        self.database_connected: bool = False
        self.using_fallback: bool = True

    async def _connect_mongo(self) -> None:
        self.client = AsyncIOMotorClient(self.database_url, serverSelectionTimeoutMS=3000)
        await self.client.admin.command("ping")

    async def connect(self) -> None:
        if self.database_url.startswith("memory://"):
            logger.warning("Using in-memory database backend")
            self.database_connected = True
            self.using_fallback = True
            return

        try:
            await self._connect_mongo()
            db = self.client.get_default_database()
            self.server_repository = MongoServerRepository(db["servers"])
            self.webhook_log_repository = MongoWebhookLogRepository(db["webhooks_log"])
            self.alert_message_repository = MongoAlertMessageRepository(db["alert_message_mappings"])
            self.database_connected = True
            self.using_fallback = False
        except Exception as exc:  # pragma: no cover
            logger.exception("Database connection failed, switching to fallback backend: %s", exc)
            self.server_repository = InMemoryServerRepository()
            self.webhook_log_repository = InMemoryWebhookLogRepository()
            self.database_connected = True
            self.using_fallback = True
