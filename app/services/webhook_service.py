from __future__ import annotations

from app.schemas.common import ActionWebhookPayload, NotifyWebhookPayload


class WebhookService:
    def __init__(self, server_repository, webhook_log_repository, bot, routing_service) -> None:
        self.server_repository = server_repository
        self.webhook_log_repository = webhook_log_repository
        self.bot = bot
        self.routing_service = routing_service

    async def process_notify(self, payload: NotifyWebhookPayload) -> dict:
        payload_dict = payload.model_dump()
        try:
            await self.bot.send_message_to_guild(
                guild_id=payload.guild_id,
                message_content=payload.message_content,
                embed_data=payload.embed_data,
            )
            await self.webhook_log_repository.add_log(
                server_id=payload.guild_id,
                action="notify",
                payload=payload_dict,
                status="delivered",
            )
            return {"status": "delivered"}
        except Exception as exc:
            await self.webhook_log_repository.add_log(
                server_id=payload.guild_id,
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
