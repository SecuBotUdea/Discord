from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas.common import ActionWebhookPayload, HealthResponse, NotifyWebhookPayload


def create_app(settings, database_manager, webhook_service, bot) -> FastAPI:
    app = FastAPI(title="Discord Microservice", version="1.0.0")

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["POST", "GET"],
            allow_headers=["Content-Type", "Authorization"],
        )

    @app.post("/webhook/notify")
    async def webhook_notify(payload: NotifyWebhookPayload) -> dict:
        try:
            return await webhook_service.process_notify(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to deliver webhook: {exc}") from exc

    @app.post("/webhook/action")
    async def webhook_action(payload: ActionWebhookPayload) -> dict:
        try:
            return await webhook_service.process_action(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to route action: {exc}") from exc

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        bot_connected = bool(bot.is_gateway_connected)
        db_connected = bool(database_manager.database_connected)
        status = "healthy" if bot_connected and db_connected else "degraded"
        return HealthResponse(
            status=status,
            bot_connected=bot_connected,
            database_connected=db_connected,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    return app
