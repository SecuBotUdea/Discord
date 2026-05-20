from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv
import uvicorn

from app.config.settings import Settings
from app.core.bot import DiscordGatewayBot, run_bot_with_backoff
from app.database.connection import DatabaseManager
from app.http import create_app
from app.services.routing_service import RoutingService
from app.services.webhook_service import WebhookService


async def main() -> None:
    load_dotenv()
    settings = Settings()

    logging.basicConfig(
        level=getattr(logging, settings.discord_log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    database_manager = DatabaseManager(settings.database_url)
    await database_manager.connect()

    routing_service = RoutingService(settings.routing_service_url)
    bot = DiscordGatewayBot(database_manager.server_repository, routing_service)
    webhook_service = WebhookService(
        server_repository=database_manager.server_repository,
        webhook_log_repository=database_manager.webhook_log_repository,
        bot=bot,
        routing_service=routing_service,
    )

    app = create_app(settings, database_manager, webhook_service, bot)
    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=settings.http_port, log_level=settings.discord_log_level.lower())
    server = uvicorn.Server(uvicorn_config)

    await asyncio.gather(
        server.serve(),
        run_bot_with_backoff(bot, settings.discord_bot_token),
    )


if __name__ == "__main__":
    asyncio.run(main())
