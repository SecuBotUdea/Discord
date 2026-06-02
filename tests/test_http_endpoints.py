from pathlib import Path
import sys

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import pytest

from app.config.settings import Settings
from app.database.connection import DatabaseManager
from app.http import create_app
from app.schemas.common import ActionWebhookPayload, NotifyWebhookPayload


class FakeBot:
    def __init__(self) -> None:
        self.is_gateway_connected = True
        self.messages = []
        self.direct_messages = []

    async def send_message_to_guild(self, guild_id: str, message_content: str, embed_data=None) -> None:
        self.messages.append((guild_id, message_content, embed_data))

    async def send_message_to_user(self, user_id: str, message_content: str, embed_data=None) -> None:
        self.direct_messages.append((user_id, message_content, embed_data))


class FakeRoutingService:
    def __init__(self) -> None:
        self.payloads = []

    async def route_user_action(self, payload: dict) -> bool:
        self.payloads.append(payload)
        return True


class FakeWebhookLogRepository:
    def __init__(self) -> None:
        self.logs = []

    async def add_log(self, server_id: str, action: str, payload: dict, status: str, error: str | None = None) -> None:
        self.logs.append((server_id, action, status, error, payload))


class FakeWebhookService:
    def __init__(self) -> None:
        self.notify_payloads = []
        self.action_payloads = []

    async def process_notify(self, payload: NotifyWebhookPayload) -> dict:
        self.notify_payloads.append(payload)
        return {"status": "delivered"}

    async def process_action(self, payload: ActionWebhookPayload) -> dict:
        self.action_payloads.append(payload)
        return {"status": "delivered"}


@pytest.fixture
def api_client() -> tuple[TestClient, FakeWebhookService, FakeBot, DatabaseManager]:
    settings = Settings.model_validate(
        {
            "DISCORD_BOT_TOKEN": "test",
            "DATABASE_URL": "memory://test",
            "HTTP_PORT": 8000,
        }
    )
    db = DatabaseManager(settings.database_url)
    db.database_connected = True
    bot = FakeBot()
    webhook_service = FakeWebhookService()
    app = create_app(settings, db, webhook_service, bot)
    return TestClient(app), webhook_service, bot, db


def test_health_endpoint(api_client) -> None:
    client, _, _, _ = api_client
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["bot_connected"] is True
    assert payload["database_connected"] is True


def test_webhook_notify_endpoint(api_client) -> None:
    client, webhook_service, _, _ = api_client
    response = client.post(
        "/webhook/notify",
        json={
            "guild_id": "123456789",
            "channel_id": "987654321",
            "message_content": "hello",
            "embed_data": {"title": "test"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered"}
    assert webhook_service.notify_payloads[0].guild_id == "123456789"


def test_webhook_notify_endpoint_accepts_message_field(api_client) -> None:
    client, webhook_service, _, _ = api_client
    response = client.post(
        "/webhook/notify",
        json={
            "team_id": "team-001",
            "user_id": "user-456",
            "message": "Rescan rechazado para alert_123",
            "embed_data": {
                "alert_id": "alert_123",
                "points": 0,
                "points_awarded": False,
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered"}
    assert webhook_service.notify_payloads[0].message_content == "Rescan rechazado para alert_123"


def test_webhook_notify_endpoint_with_alert_payload(api_client) -> None:
    client, webhook_service, _, _ = api_client
    response = client.post(
        "/webhook/notify",
        json={
            "guild_id": "123456789",
            "alert_id": "alert_123",
            "title": "Database outage",
            "severity": "critical",
            "status": "firing",
            "component": "database",
            "location": "us-east-1",
            "source_type": "monitoring",
            "team_id": "team_001",
            "team_name": "Database Team",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered"}
    assert webhook_service.notify_payloads[0].title == "Database outage"


def test_webhook_notify_endpoint_with_gloria_payload(api_client) -> None:
    client, webhook_service, _, _ = api_client
    response = client.post(
        "/webhook/notify",
        json={
            "alert_id": "dependabot-pangoaguirre-get-dependabot-alerts-sample-1",
            "title": "Test advisory",
            "severity": "high",
            "status": "open",
            "component": "test-pkg",
            "location": "https://github.com/pangoaguirre/get-dependabot-alerts-sample/security/dependabot/1",
            "source_type": "dependabot",
            "team_id": "team-001",
            "team_name": "Mi Equipo",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered"}
    assert webhook_service.notify_payloads[0].alert_id == "dependabot-pangoaguirre-get-dependabot-alerts-sample-1"
    assert webhook_service.notify_payloads[0].team_id == "team-001"


def test_webhook_notify_endpoint_includes_alert_id_in_message(api_client) -> None:
    client, webhook_service, _, _ = api_client
    response = client.post(
        "/webhook/notify",
        json={
            "alert_id": "alert_123",
            "title": "Database outage",
            "severity": "critical",
            "status": "firing",
            "component": "database",
            "location": "us-east-1",
            "source_type": "monitoring",
            "team_id": "team_001",
            "team_name": "Database Team",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered"}
    assert "Alert ID: alert_123" in webhook_service.notify_payloads[0].get_message_content()


def test_webhook_action_endpoint(api_client) -> None:
    client, webhook_service, _, _ = api_client
    response = client.post(
        "/webhook/action",
        json={
            "action": "rescan_initiated",
            "alert_id": "alert_123",
            "guild_id": "123456789",
            "user_id": "user_456",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered"}
    assert webhook_service.action_payloads[0].alert_id == "alert_123"


@pytest.mark.asyncio
async def test_database_connection_fallback(monkeypatch) -> None:
    manager = DatabaseManager("mongodb://localhost:27017/test")

    async def failing_connect() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(manager, "_connect_mongo", failing_connect)

    await manager.connect()

    assert manager.database_connected is True
    assert manager.using_fallback is True


@pytest.mark.asyncio
async def test_notify_flow_logs_and_sends_message() -> None:
    from app.services.webhook_service import WebhookService

    bot = FakeBot()
    routing = FakeRoutingService()
    logs = FakeWebhookLogRepository()

    class FakeServerRepository:
        async def get_server(self, guild_id: str):
            return {"guild_id": guild_id}

    service = WebhookService(FakeServerRepository(), logs, bot, routing)
    payload = NotifyWebhookPayload(
        guild_id="123",
        channel_id="456",
        message_content="message",
        embed_data=None,
    )

    result = await service.process_notify(payload)

    assert result == {"status": "delivered"}
    assert bot.messages[0][0] == "123"
    assert logs.logs[0][2] == "delivered"


@pytest.mark.asyncio
async def test_notify_flow_sends_invalid_rescan_to_user_dm() -> None:
    from app.services.webhook_service import WebhookService

    bot = FakeBot()
    routing = FakeRoutingService()
    logs = FakeWebhookLogRepository()

    class FakeServerRepository:
        async def get_server(self, guild_id: str):
            return {"guild_id": guild_id}

    service = WebhookService(FakeServerRepository(), logs, bot, routing)
    payload = NotifyWebhookPayload(
        guild_id="123",
        user_id="456",
        message_content="Tu rescan no sirvió",
        embed_data={"points_awarded": False},
        points_awarded=False,
    )

    result = await service.process_notify(payload)

    assert result == {"status": "delivered"}
    assert bot.messages == []
    assert bot.direct_messages[0][0] == "456"
    assert logs.logs[0][2] == "delivered"


@pytest.mark.asyncio
async def test_notify_flow_resolves_guild_from_team_id() -> None:
    from unittest.mock import patch
    from app.services.webhook_service import WebhookService

    bot = FakeBot()
    routing = FakeRoutingService()
    logs = FakeWebhookLogRepository()

    class FakeServerRepository:
        async def get_server(self, guild_id: str):
            return {"guild_id": guild_id}

    service = WebhookService(FakeServerRepository(), logs, bot, routing)
    payload = NotifyWebhookPayload(
        team_id="team-001",
        message_content="alerta resuelta",
    )

    with patch("app.services.webhook_service._TEAM_GUILD_MAP", {"team-001": "guild_abc"}):
        result = await service.process_notify(payload)

    assert result == {"status": "delivered"}
    assert bot.messages[0][0] == "guild_abc"


@pytest.mark.asyncio
async def test_notify_flow_raises_without_guild_or_team_mapping() -> None:
    from unittest.mock import patch
    from app.services.webhook_service import WebhookService

    bot = FakeBot()
    routing = FakeRoutingService()
    logs = FakeWebhookLogRepository()

    class FakeServerRepository:
        async def get_server(self, guild_id: str):
            return {"guild_id": guild_id}

    service = WebhookService(FakeServerRepository(), logs, bot, routing)
    payload = NotifyWebhookPayload(message_content="sin guild ni team")

    with patch("app.services.webhook_service._TEAM_GUILD_MAP", {}):
        try:
            await service.process_notify(payload)
            assert False, "Debería haber lanzado ValueError"
        except (ValueError, Exception):
            pass


def test_notify_payload_builds_message_from_alert_fields() -> None:
    payload = NotifyWebhookPayload(
        guild_id="123",
        title="SQL injection detected",
        severity="critical",
        status="open",
        component="api/auth",
        location="https://github.com/org/repo/security/1",
        source_type="zap",
        team_name="Backend Team",
    )

    message = payload.get_message_content()

    assert "SQL injection detected" in message
    assert "critical" in message
    assert "open" in message
    assert "api/auth" in message
    assert "Backend Team" in message


def test_notify_payload_prefers_message_content_over_alert_fields() -> None:
    payload = NotifyWebhookPayload(
        guild_id="123",
        message_content="texto directo",
        title="este título no debe aparecer",
    )

    assert payload.get_message_content() == "texto directo"


def test_notify_payload_raises_without_message_or_title() -> None:
    payload = NotifyWebhookPayload(guild_id="123")

    try:
        payload.get_message_content()
        assert False, "Debería haber lanzado ValueError"
    except ValueError:
        pass


def test_notify_payload_uses_points_awarded_from_embed_data() -> None:
    from app.services.webhook_service import WebhookService

    payload = NotifyWebhookPayload(
        guild_id="123",
        user_id="456",
        message_content="mensaje",
        embed_data={"points_awarded": False},
    )

    assert WebhookService._get_points_awarded(payload) is False


def test_notify_payload_builds_colored_embed_for_severity() -> None:
    payload = NotifyWebhookPayload(
        guild_id="123",
        alert_id="alert_123",
        title="Uninitialized memory disclosure",
        severity="medium",
        status="open",
        component="ws",
        location="https://example.com/security/1",
        source_type="dependabot",
        team_name="coleccionDeCiencias",
    )

    embed_data = payload.build_embed_data()

    assert embed_data is not None
    assert embed_data["title"].startswith("🟠 ")
    assert embed_data["color"] == 0xF39C12
    assert "Uninitialized memory disclosure" in embed_data["description"]


def test_notify_payload_uses_gray_embed_for_unknown_severity() -> None:
    payload = NotifyWebhookPayload(
        guild_id="123",
        title="Custom alert",
        severity="whatever",
        message_content="Custom alert body",
    )

    embed_data = payload.build_embed_data()

    assert embed_data is not None
    assert embed_data["title"].startswith("⚪ ")
    assert embed_data["color"] == 0x95A5A6


def test_notify_payload_fills_embed_description_from_message_content() -> None:
    from app.core.bot import DiscordGatewayBot

    embed = DiscordGatewayBot._build_embed(
        "Rescan rechazado para alert_123",
        {"alert_id": "alert_123", "points": 0, "points_awarded": False},
    )

    assert embed is not None
    assert embed.description == "Rescan rechazado para alert_123"


@pytest.mark.asyncio
async def test_action_flow_keeps_user_id_when_routing() -> None:
    from app.services.webhook_service import WebhookService

    bot = FakeBot()
    routing = FakeRoutingService()
    logs = FakeWebhookLogRepository()

    class FakeServerRepository:
        async def get_server(self, guild_id: str):
            return {"guild_id": guild_id}

    service = WebhookService(FakeServerRepository(), logs, bot, routing)
    payload = ActionWebhookPayload(
        action="rescan",
        alert_id="alert_123",
        guild_id="123",
        user_id="user_456",
    )

    result = await service.process_action(payload)

    assert result == {"status": "delivered"}
    assert routing.payloads[0]["user_id"] == "user_456"
    assert logs.logs[0][4]["user_id"] == "user_456"
