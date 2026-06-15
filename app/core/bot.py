from __future__ import annotations

import asyncio
import logging

import aiohttp
import discord
from discord import app_commands

from app.models.server import ServerRecord
from app.schemas.common import ActionWebhookPayload

logger = logging.getLogger(__name__)

RESCAN_EMOJI = "🔄"
RESCAN_EMOJI_NAME = "rescan"


class DiscordGatewayBot(discord.Client):
    def __init__(self, server_repository, routing_service, alert_message_repository) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.server_repository = server_repository
        self.routing_service = routing_service
        self.alert_message_repository = alert_message_repository

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
            interaction_open = not interaction.response.is_done()

            if interaction_open:
                try:
                    await interaction.response.defer(thinking=True)
                except (discord.NotFound, discord.HTTPException) as exc:
                    logger.warning("Unable to acknowledge rescan interaction for %s: %s", alert_id, exc)
                    interaction_open = False

            try:
                payload = ActionWebhookPayload(
                    action="rescan",
                    alert_id=alert_id,
                    guild_id=str(interaction.guild_id or ""),
                    user_id=str(user_id or interaction.user.id),
                )

                routed = await self.routing_service.route_user_action(payload.model_dump())
                if not routed:
                    if interaction_open:
                        await interaction.followup.send(f"❌ No se pudo enviar el rescan para `{alert_id}`")
                    return

                if interaction_open:
                    await interaction.followup.send(f"🔄 Reescaneo solicitado para `{alert_id}`")
            except Exception as e:
                logger.error(f"Error en rescan: {e}")
                if interaction_open:
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

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        # Ignore bot's own reactions
        try:
            if payload.user_id == (self.user.id if self.user else None):
                return
        except Exception:
            pass

        message_id = str(payload.message_id)
        try:
            mapping = await self.alert_message_repository.get_by_message_id(message_id)
        except Exception:
            mapping = None

        if not mapping:
            return

        # Accept rescan by unicode or by emoji name (server custom emoji)
        emoji_obj = payload.emoji
        emoji_str = str(emoji_obj)
        emoji_name = getattr(emoji_obj, "name", None)
        if not (emoji_str == RESCAN_EMOJI or emoji_name == RESCAN_EMOJI_NAME):
            return

        # Build action payload and route
        try:
            action_payload = ActionWebhookPayload(
                action="rescan",
                alert_id=mapping.get("alert_id"),
                guild_id=mapping.get("guild_id"),
                user_id=str(payload.user_id),
            )

            routed = await self.routing_service.route_user_action(action_payload.model_dump())
            if not routed:
                return

            # mark mapping as actioned to avoid duplicates
            try:
                # mark_actioned returns True only for the first actor
                marked = await self.alert_message_repository.mark_actioned(message_id, status="actioned", acted_by_user_id=str(payload.user_id))
                if not marked:
                    # already handled by someone else
                    return
            except Exception:
                # if marking fails, continue but avoid duplicate routing risk
                return

            try:
                # try removing user's reaction by name first, then by unicode
                await self.remove_user_reaction_from_message(
                    channel_id=mapping.get("channel_id"),
                    message_id=message_id,
                    emoji=f":{RESCAN_EMOJI_NAME}:",
                    user_id=str(payload.user_id),
                )
            except Exception:
                try:
                    await self.remove_user_reaction_from_message(
                        channel_id=mapping.get("channel_id"),
                        message_id=message_id,
                        emoji=RESCAN_EMOJI,
                        user_id=str(payload.user_id),
                    )
                except Exception:
                    pass

            # Optionally acknowledge via DM
            try:
                discord_user = await self.fetch_user(int(payload.user_id))
                await discord_user.send(f"🔄 Reescaneo solicitado para `{action_payload.alert_id}`")
            except Exception:
                # ignore failures to DM
                pass
        except Exception as exc:  # pragma: no cover - best-effort handler
            logger.exception("Error handling reaction for message %s: %s", message_id, exc)

    async def send_message_to_guild(self, guild_id: str, message_content: str, embed_data: dict | None = None) -> str | None:
        server = await self.server_repository.get_server(guild_id)
        if not server:
            raise ValueError(f"No webhook configuration for guild {guild_id}")

        webhook_url = f"https://discord.com/api/webhooks/{server['webhook_id']}/{server['webhook_token']}"
        embed = self._build_embed(message_content, embed_data)
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            result = await webhook.send(content=message_content, embed=embed, wait=True)
            # `result` is a WebhookMessage when `wait=True`. Return its id if available.
            try:
                message_id = getattr(result, "id", None)
                if message_id is not None:
                    message_id_str = str(message_id)
                    channel_id = server.get("channel_id")
                    if channel_id:
                        logger.info("Attempting to add rescan reaction to webhook message %s in channel %s", message_id_str, channel_id)
                        added = await self.add_reaction_to_message(str(channel_id), message_id_str, RESCAN_EMOJI)
                        if added:
                            logger.info("Added rescan reaction to webhook message %s", message_id_str)
                        else:
                            logger.error("Failed to add rescan reaction to webhook message %s in channel %s", message_id_str, channel_id)
                    return message_id_str
                return None
            except Exception:
                return None

    async def add_reaction_to_message(self, channel_id: str, message_id: str, emoji: str = RESCAN_EMOJI) -> bool:
        try:
            chan = self.get_channel(int(channel_id))
            if not chan:
                chan = await self.fetch_channel(int(channel_id))

            message = await chan.fetch_message(int(message_id))
            await message.add_reaction(emoji)
            return True
        except Exception as exc:  # pragma: no cover - best-effort
            logger.exception("Failed to add reaction %s to message %s", emoji, message_id)
            return False

    async def send_message_to_user(self, user_id: str, message_content: str, embed_data: dict | None = None) -> None:
        try:
            discord_user_id = int(user_id)
        except ValueError as exc:
            raise ValueError(f"Invalid Discord user ID: {user_id}") from exc

        user = await self.fetch_user(discord_user_id)
        embed = self._build_embed(message_content, embed_data)
        await user.send(content=message_content, embed=embed)

    async def remove_user_reaction_from_message(self, channel_id: str, message_id: str, emoji: str = RESCAN_EMOJI, user_id: str | None = None) -> bool:
        """Remove a specific user's reaction from a message. Returns True on success."""
        try:
            chan = self.get_channel(int(channel_id))
            if not chan:
                chan = await self.fetch_channel(int(channel_id))

            message = await chan.fetch_message(int(message_id))
            if user_id is None:
                await message.clear_reaction(emoji)
            else:
                try:
                    user = await self.fetch_user(int(user_id))
                    await message.remove_reaction(emoji, user)
                except Exception:
                    await message.clear_reaction(emoji)
            return True
        except Exception as exc:  # pragma: no cover - best-effort
            logger.debug("Failed to remove user reaction %s from message %s: %s", emoji, message_id, exc)
            return False

    @staticmethod
    def _build_embed(message_content: str, embed_data: dict | None) -> discord.Embed | None:
        if not embed_data:
            return None

        normalized_embed_data = dict(embed_data)
        return discord.Embed.from_dict(normalized_embed_data)


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
