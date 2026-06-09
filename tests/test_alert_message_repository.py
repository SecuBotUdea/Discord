import pytest

from app.models.alert_mapping import AlertMessageMapping
from app.database.connection import InMemoryAlertMessageRepository


@pytest.mark.asyncio
async def test_alert_message_repository_upsert_and_get():
    repo = InMemoryAlertMessageRepository()
    mapping = AlertMessageMapping(alert_id="alert1", guild_id="g1", channel_id="c1", message_id="m1")
    await repo.upsert_mapping(mapping)

    by_msg = await repo.get_by_message_id("m1")
    assert by_msg is not None
    assert by_msg["alert_id"] == "alert1"

    by_alert = await repo.get_by_alert_id("alert1")
    assert by_alert is not None
    assert by_alert["message_id"] == "m1"


@pytest.mark.asyncio
async def test_mark_actioned_idempotent():
    repo = InMemoryAlertMessageRepository()
    mapping = AlertMessageMapping(alert_id="alert2", guild_id="g1", channel_id="c1", message_id="m2")
    await repo.upsert_mapping(mapping)

    first = await repo.mark_actioned("m2", status="actioned", acted_by_user_id="u1")
    assert first is True

    second = await repo.mark_actioned("m2", status="actioned", acted_by_user_id="u2")
    assert second is False
