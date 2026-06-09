from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.common import ActionWebhookPayload, NotifyWebhookPayload
from app.models.alert_mapping import AlertMessageMapping

from app.config.team_guild_map import load_team_guild_map

_TEAM_GUILD_MAP = load_team_guild_map()
_NOTIFY_DEDUP_WINDOW_SECONDS = 30

class WebhookService:
    def __init__(self, server_repository, webhook_log_repository, bot, routing_service, alert_message_repository=None) -> None:
        self.server_repository = server_repository
        self.webhook_log_repository = webhook_log_repository
        self.bot = bot
        self.routing_service = routing_service
        self.alert_message_repository = alert_message_repository
        self._recent_notify_fingerprints: dict[str, datetime] = {}

    @staticmethod
    def _get_points_awarded(payload: NotifyWebhookPayload) -> bool | None:
        if payload.points_awarded is not None:
            return payload.points_awarded

        if isinstance(payload.embed_data, dict):
            points_awarded = payload.embed_data.get("points_awarded")
            if isinstance(points_awarded, bool):
                return points_awarded

        return None

    def _notify_fingerprint(self, payload: NotifyWebhookPayload, guild_id: str) -> str:
        embed_data = payload.embed_data or {}
        fingerprint_parts = (
            guild_id,
            payload.user_id or "",
            payload.alert_id or "",
            payload.title or "",
            payload.severity or "",
            payload.status or "",
            payload.component or "",
            payload.location or "",
            payload.source_type or "",
            payload.source_id or "",
            payload.team_id or "",
            payload.team_name or "",
            payload.message_content or "",
            str(payload.points_awarded),
            repr(sorted(embed_data.items())),
        )
        return "|".join(fingerprint_parts)

    def _is_recent_notify_duplicate(self, fingerprint: str) -> bool:
        now = datetime.now(timezone.utc)

        expired_fingerprints = [
            stored_fingerprint
            for stored_fingerprint, stored_at in self._recent_notify_fingerprints.items()
            if (now - stored_at).total_seconds() > _NOTIFY_DEDUP_WINDOW_SECONDS
        ]
        for stored_fingerprint in expired_fingerprints:
            self._recent_notify_fingerprints.pop(stored_fingerprint, None)

        if fingerprint in self._recent_notify_fingerprints:
            return True

        self._recent_notify_fingerprints[fingerprint] = now
        return False

    async def process_notify(self, payload: NotifyWebhookPayload) -> dict:
        mapped_guild_id = _TEAM_GUILD_MAP.get(payload.team_id) if payload.team_id else None
        guild_id = payload.guild_id or mapped_guild_id
        if not guild_id:
            raise ValueError(
                "NotifyWebhookPayload requires guild_id or a valid team_id mapping"
            )

        payload_dict = payload.model_dump()
        points_awarded = self._get_points_awarded(payload)
        fingerprint = self._notify_fingerprint(payload, guild_id)
        try:
            if self._is_recent_notify_duplicate(fingerprint):
                await self.webhook_log_repository.add_log(
                    server_id=guild_id,
                    action="notify",
                    payload=payload_dict,
                    status="deduplicated",
                )
                return {"status": "duplicate_ignored"}

            if points_awarded is False:
                if not payload.user_id:
                    raise ValueError("NotifyWebhookPayload requires user_id when points_awarded is false")

                # send private DM to the user
                await self.bot.send_message_to_user(
                    user_id=payload.user_id,
                    message_content=payload.get_message_content(),
                    embed_data=payload.build_embed_data(),
                )

                # attempt to remove the reaction from the original alert message if mapping exists
                try:
                    if self.alert_message_repository and payload.alert_id:
                        mapping = await self.alert_message_repository.get_by_alert_id(payload.alert_id)
                    else:
                        mapping = None
                except Exception:
                    mapping = None

                if mapping:
                    # try common rescan emojis
                    for emoji in ("🔄", "🔁"):
                        try:
                            if hasattr(self.bot, "remove_reaction_from_message"):
                                await self.bot.remove_reaction_from_message(
                                    guild_id=mapping.get("guild_id"),
                                    channel_id=mapping.get("channel_id"),
                                    message_id=mapping.get("message_id"),
                                    emoji=emoji,
                                )
                        except Exception:
                            pass

                    try:
                        await self.alert_message_repository.mark_actioned(mapping.get("message_id"), status="points_lost", acted_by_user_id=payload.user_id)
                    except Exception:
                        pass
            else:
                # send message to guild and record message_id -> alert mapping when possible
                message_id = await self.bot.send_message_to_guild(
                    guild_id=guild_id,
                    message_content=payload.get_message_content(),
                    embed_data=payload.build_embed_data(),
                )
                if message_id and payload.alert_id:
                    mapping = AlertMessageMapping(
                        alert_id=payload.alert_id,
                        guild_id=guild_id,
                        channel_id=payload.channel_id or "",
                        message_id=message_id,
                    )
                    try:
                        await self.alert_message_repository.upsert_mapping(mapping)
                    except Exception:
                        # non-fatal: log elsewhere via webhook_log
                        pass

            await self.webhook_log_repository.add_log(
                server_id=guild_id,
                action="notify",
                payload=payload_dict,
                status="delivered",
            )
            return {"status": "delivered"}
        except Exception as exc:
            await self.webhook_log_repository.add_log(
                server_id=guild_id,
                action="notify",
                payload=payload_dict,
                status="failed",
                error=str(exc),
            )
            raise

    async def process_action(self, payload: ActionWebhookPayload) -> dict:
        payload_dict = payload.model_dump()
        routed = await self.routing_service.route_user_action(payload_dict)
        await self.webhook_log_repository.add_log(
            server_id=payload.guild_id,
            action="action",
            payload=payload_dict,
            status="delivered" if routed else "failed",
            error=None if routed else "ROUTING_SERVICE_URL not configured",
        )
        return {"status": "delivered" if routed else "queued"}
