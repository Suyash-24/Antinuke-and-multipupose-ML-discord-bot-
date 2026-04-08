from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from aegis.bot import AegisBot
from aegis.checks import require_manage_guild
from aegis.models import LogType
from aegis.ui import build_panel


class SettingsCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot

    async def _resolve_log_channel(
        self,
        ctx: commands.Context[AegisBot],
        target: str | None,
    ) -> discord.TextChannel | None:
        if target is None:
            if isinstance(ctx.channel, discord.TextChannel):
                return ctx.channel
            raise commands.BadArgument("Run this in a text channel or pass a `#channel` explicitly.")

        if target.lower() == "off":
            return None

        return await commands.TextChannelConverter().convert(ctx, target)

    async def _set_log_channel(
        self,
        ctx: commands.Context[AegisBot],
        log_type: LogType,
        target: str | None,
        label: str,
    ) -> None:
        channel = await self._resolve_log_channel(ctx, target)
        await self.bot.db.set_log_channel(ctx.guild.id, log_type, channel.id if channel else None)
        await ctx.send(
            view=build_panel(
                f"{label} Updated",
                "Aegis saved the new logging destination.",
                tone="success",
                fields=[("Channel", channel.mention if channel else "Disabled")],
            )
        )

    @commands.group(invoke_without_command=True)
    @require_manage_guild()
    async def setup(self, ctx: commands.Context[AegisBot]) -> None:
        await ctx.send(
            view=build_panel(
                "Setup Commands",
                f"Use `{ctx.clean_prefix}setup muted` to create or register the muted role used by Aegis.",
                tone="info",
            )
        )

    @setup.command(name="muted")
    @require_manage_guild()
    async def setup_muted(self, ctx: commands.Context[AegisBot]) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        existing_role = ctx.guild.get_role(settings.muted_role_id or 0) if settings.muted_role_id else None
        if existing_role is not None:
            await ctx.send(
                view=build_panel(
                    "Muted Role Ready",
                    "Aegis already has a muted role configured for this server.",
                    tone="info",
                    fields=[("Role", existing_role.mention)],
                )
            )
            return

        role = discord.utils.get(ctx.guild.roles, name="Aegis Muted")
        if role is None:
            role = await ctx.guild.create_role(
                name="Aegis Muted",
                reason="Aegis muted role setup",
            )

        overwrite = discord.PermissionOverwrite(
            send_messages=False,
            add_reactions=False,
            speak=False,
            connect=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
        )

        updated_channels = 0
        for channel in ctx.guild.channels:
            try:
                await channel.set_permissions(role, overwrite=overwrite, reason="Aegis muted role setup")
                updated_channels += 1
            except discord.HTTPException:
                continue

        await self.bot.db.update_guild_settings(ctx.guild.id, muted_role_id=role.id)
        await ctx.send(
            view=build_panel(
                "Muted Role Configured",
                "Aegis created the muted role and pushed channel overwrites where possible.",
                tone="success",
                fields=[
                    ("Role", role.mention),
                    ("Channels Updated", str(updated_channels)),
                ],
            )
        )

    @commands.command()
    @require_manage_guild()
    async def prefix(self, ctx: commands.Context[AegisBot], *, value: str | None = None) -> None:
        current_prefix = await self.bot.get_guild_prefix(ctx.guild.id)

        if value is None:
            await ctx.send(
                view=build_panel(
                    "Prefix",
                    "Aegis command prefix for this server.",
                    tone="info",
                    fields=[
                        ("Current", f"`{current_prefix}`"),
                        ("Change", f"`{ctx.clean_prefix}prefix <new-prefix>`"),
                        ("Reset", f"`{ctx.clean_prefix}prefix default`"),
                    ],
                )
            )
            return

        normalized = value.strip()
        if normalized.lower() in {"default", "reset"}:
            normalized = self.bot.config.prefix

        if not normalized:
            raise commands.BadArgument("Prefix cannot be empty.")

        if any(char.isspace() for char in normalized):
            raise commands.BadArgument("Prefix cannot contain spaces.")

        if len(normalized) > 5:
            raise commands.BadArgument("Prefix must be between 1 and 5 characters.")

        if normalized == current_prefix:
            await ctx.send(
                view=build_panel(
                    "Prefix Unchanged",
                    "That prefix is already active for this server.",
                    tone="info",
                    fields=[("Prefix", f"`{current_prefix}`")],
                )
            )
            return

        await self.bot.db.update_guild_settings(ctx.guild.id, prefix=normalized)
        self.bot.set_guild_prefix(ctx.guild.id, normalized)
        await ctx.send(
            view=build_panel(
                "Prefix Updated",
                "Aegis saved the new command prefix for this server.",
                tone="success",
                fields=[
                    ("Old", f"`{current_prefix}`"),
                    ("New", f"`{normalized}`"),
                    ("Example", f"`{normalized}help`"),
                ],
            )
        )

    @commands.command()
    @require_manage_guild()
    async def modrole(
        self,
        ctx: commands.Context[AegisBot],
        *,
        role: Optional[discord.Role] = None,
    ) -> None:
        await self.bot.db.update_guild_settings(ctx.guild.id, mod_role_id=role.id if role else None)
        await ctx.send(
            view=build_panel(
                "Mod Role Updated",
                "Aegis saved the moderation role override.",
                tone="success",
                fields=[("Role", role.mention if role else "Disabled")],
            )
        )

    @commands.command()
    @require_manage_guild()
    async def modlog(self, ctx: commands.Context[AegisBot], *, target: str | None = None) -> None:
        await self._set_log_channel(ctx, LogType.MOD, target, "Mod Log")

    @commands.command()
    @require_manage_guild()
    async def messagelog(self, ctx: commands.Context[AegisBot], *, target: str | None = None) -> None:
        await self._set_log_channel(ctx, LogType.MESSAGE, target, "Message Log")

    @commands.command()
    @require_manage_guild()
    async def serverlog(self, ctx: commands.Context[AegisBot], *, target: str | None = None) -> None:
        await self._set_log_channel(ctx, LogType.SERVER, target, "Server Log")

    @commands.command()
    @require_manage_guild()
    async def voicelog(self, ctx: commands.Context[AegisBot], *, target: str | None = None) -> None:
        await self._set_log_channel(ctx, LogType.VOICE, target, "Voice Log")

    @commands.command()
    @require_manage_guild()
    async def settings(self, ctx: commands.Context[AegisBot]) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        punishments = await self.bot.db.get_punishments(ctx.guild.id)
        ignored = await self.bot.db.list_ignored_targets(ctx.guild.id)
        antinuke_freeze = await self.bot.get_antinuke_freeze_until(ctx.guild.id)

        def render_role(role_id: int | None) -> str:
            if not role_id:
                return "Not set"
            role = ctx.guild.get_role(role_id)
            return role.mention if role else f"`{role_id}`"

        def render_channel(channel_id: int | None) -> str:
            if not channel_id:
                return "Not set"
            channel = ctx.guild.get_channel(channel_id)
            return channel.mention if channel else f"`{channel_id}`"

        ignored_preview = []
        for row in ignored[:8]:
            target = ctx.guild.get_role(row["target_id"]) if row["target_type"] == "role" else ctx.guild.get_channel(row["target_id"])
            ignored_preview.append(target.mention if target else f"`{row['target_id']}`")

        punishment_preview = []
        for threshold, config in sorted(punishments.items()):
            if config.duration_seconds:
                punishment_preview.append(f"`{threshold}` -> `{config.action.value}` ({config.duration_seconds}s)")
            else:
                punishment_preview.append(f"`{threshold}` -> `{config.action.value}`")

        await ctx.send(
            view=build_panel(
                "Aegis Settings",
                "Current moderation, logging, and AutoMod configuration for this server.",
                tone="info",
                fields=[
                    ("Prefix", f"`{settings.prefix}`"),
                    ("Mod Role", render_role(settings.mod_role_id)),
                    ("Muted Role", render_role(settings.muted_role_id)),
                    ("Mod Log", render_channel(settings.mod_log_channel_id)),
                    ("Message Log", render_channel(settings.message_log_channel_id)),
                    ("Server Log", render_channel(settings.server_log_channel_id)),
                    ("Voice Log", render_channel(settings.voice_log_channel_id)),
                    ("Anti-Nuke Log", render_channel(settings.antinuke_log_channel_id)),
                    ("Raid Mode", "Enabled" if settings.raid_mode_enabled else "Disabled"),
                    ("Anti-Nuke", "Enabled" if settings.antinuke_enabled else "Disabled"),
                    ("Anti-Nuke Mode", settings.antinuke_mode.value),
                    (
                        "Anti-Nuke Freeze",
                        discord.utils.format_dt(antinuke_freeze, style="R") if antinuke_freeze else "Inactive",
                    ),
                    ("Punishment Ladder", "\n".join(punishment_preview) if punishment_preview else "Not configured"),
                    ("Ignored Targets", "\n".join(ignored_preview) if ignored_preview else "None"),
                ],
            )
        )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(SettingsCog(bot))
