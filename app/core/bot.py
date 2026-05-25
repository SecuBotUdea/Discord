from __future__ import annotations

import asyncio
import logging

import aiohttp
import discord
from discord import app_commands

from app.models.server import ServerRecord

logger = logging.getLogger(__name__)


class DiscordGatewayBot(discord.Client):
    def __init__(self, server_repository, routing_service) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.server_repository = server_repository
        self.routing_service = routing_service

    @property
    def is_gateway_connected(self) -> bool:
        return self.is_ready() and not self.is_closed()

    async def setup_hook(self) -> None:
        self._register_slash_commands()
        await self.tree.sync()

    def _register_slash_commands(self) -> None:
        @self.tree.command(name="status", description="Estado del bot")
        async def status(interaction: discord.Interaction) -> None:
            await interaction.response.send_message("✅ Discord microservice operativo", ephemeral=True)

        @self.tree.command(name="rescan", description="Reintentar escaneo de alerta")
        @app_commands.describe(alert_id="ID de la alerta", user_id="ID de usuario opcional")
        async def rescan(interaction: discord.Interaction, alert_id: str, user_id: str | None = None) -> None:
            await interaction.response.defer(thinking=True)  # ← AÑADE ESTO
            
            try:
                # Payload EXACTO que Gloria espera (SIN "event")
                payload = {
                    "action": "rescan",
                    "alert_id": alert_id,
                    "guild_id": str(interaction.guild_id or ""),
                    "user_id": str(user_id or interaction.user.id),
                }
                
                await self.routing_service.route_user_action(payload)
                
                await interaction.followup.send(
                    f"🔄 Reescaneo solicitado para `{alert_id}`"
                )
            except Exception as e:
                logger.error(f"Error en rescan: {e}")
                await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    async def on_ready(self) -> None:
        logger.info("Discord gateway connected as %s", self.user)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        logger.info("Joined guild %s", guild.id)
        if not guild.me:
            return

        for channel in guild.text_channels:
            permissions = channel.permissions_for(guild.me)
            if permissions.manage_webhooks:
                webhook = await channel.create_webhook(name="SecuBot Notifications")
                server = ServerRecord(
                    server_id=str(guild.id),
                    guild_id=str(guild.id),
                    webhook_id=str(webhook.id),
                    webhook_token=webhook.token or "",
                    channel_id=str(channel.id),
                    active=True,
                )
                await self.server_repository.upsert_server(server)
                return

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        logger.info("Removed from guild %s", guild.id)
        await self.server_repository.deactivate_server(str(guild.id))

    async def send_message_to_guild(self, guild_id: str, message_content: str, embed_data: dict | None = None) -> None:
        server = await self.server_repository.get_server(guild_id)
        if not server:
            raise ValueError(f"No webhook configuration for guild {guild_id}")

        webhook_url = f"https://discord.com/api/webhooks/{server['webhook_id']}/{server['webhook_token']}"
        embed = discord.Embed.from_dict(embed_data) if embed_data else None
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            await webhook.send(content=message_content, embed=embed, wait=True)


async def run_bot_with_backoff(bot: DiscordGatewayBot, token: str) -> None:
    retry_wait = 1
    while True:
        try:
            await bot.start(token)
            return
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover
            logger.exception("Gateway disconnected unexpectedly, reconnecting in %ss", retry_wait)
            await asyncio.sleep(retry_wait)
            retry_wait = min(retry_wait * 2, 60)
