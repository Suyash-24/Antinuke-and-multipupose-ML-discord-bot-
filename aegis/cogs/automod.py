from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

import discord
from discord.ext import commands

from aegis.bot import AegisBot
from aegis.checks import require_manage_guild, require_moderation
from aegis.converters import DurationConverter, IgnoreTargetConverter, MemberOrUserConverter
from aegis.models import AutoModFilterItem, FilterItemType, PunishmentAction
from aegis.ui import build_panel
from aegis.utils import format_identity, format_timestamp, humanize_duration, parse_ratio, truncate, unique_by_id, utcnow

MENTION_MINIMUM = 4
ROLE_MENTION_MINIMUM = 2
MAX_STRIKES = 100
MAX_FILTER_NAME_LENGTH = 32
MAX_FILTER_CONTENT_LENGTH = 255
MAX_PUNISHMENTS = 20
_DEHOIST_CHAR_RE = re.compile(r"^[^a-zA-Z0-9]$")


class AutoModCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot

    def _check_manual_target(self, ctx: commands.Context[AegisBot], member: discord.Member) -> str | None:
        if member.id == ctx.author.id:
            return "You cannot change your own strike total."
        if member.id == ctx.guild.owner_id:
            return "You cannot moderate the server owner."
        if ctx.guild.owner_id != ctx.author.id and member.top_role >= ctx.author.top_role:
            return "That member is at or above your top role."
        if ctx.me is not None and member.top_role >= ctx.me.top_role:
            return "Aegis is not high enough in the role hierarchy for that target."
        return None

    async def _send_snapshot(self, ctx: commands.Context[AegisBot]) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        ignored = await self.bot.db.list_ignored_targets(ctx.guild.id)
        punishments = await self.bot.db.get_punishments(ctx.guild.id)
        whitelist = await self.bot.db.list_invite_whitelist_targets(ctx.guild.id)
        filters = await self.bot.db.list_automod_filters(ctx.guild.id)

        ignored_preview = []
        for row in ignored[:8]:
            if row["target_type"] == "role":
                target = ctx.guild.get_role(row["target_id"])
            else:
                target = ctx.guild.get_channel(row["target_id"])
            ignored_preview.append(target.mention if target else f"`{row['target_id']}`")

        ladder = []
        for threshold, config in sorted(punishments.items()):
            label = f"`{threshold}` -> `{config.action.value}`"
            if config.duration_seconds:
                label = f"{label} ({humanize_duration(config.duration_seconds)})"
            ladder.append(label)

        filter_preview = [f"`{flt.name}` ({flt.strikes})" for flt in filters[:8]]
        whitelist_preview = [f"`{guild_id}`" for guild_id in whitelist[:8]]

        await ctx.send(
            view=build_panel(
                "AutoMod Overview",
                "Current Aegis AutoMod and strike configuration.",
                tone="info",
                fields=[
                    ("Anti Invite", self._format_rule_setting(settings.anti_invite_strikes)),
                    ("Anti Referral", self._format_rule_setting(settings.anti_referral_strikes)),
                    ("Anti Copypasta", self._format_rule_setting(settings.anti_copypasta_strikes)),
                    ("Anti Everyone", self._format_rule_setting(settings.anti_everyone_strikes)),
                    ("Resolve Links", "On" if settings.resolve_urls else "Off"),
                    ("Auto Dehoist", settings.dehoist_char or "Off"),
                    ("Max Mentions", str(settings.max_mentions) if settings.max_mentions else "Off"),
                    ("Max Role Mentions", str(settings.max_role_mentions) if settings.max_role_mentions else "Off"),
                    ("Max Lines", str(settings.max_lines) if settings.max_lines else "Off"),
                    (
                        "Duplicate Filter",
                        (
                            f"strike at {settings.duplicate_strike_threshold}, "
                            f"delete at {settings.duplicate_delete_threshold}, "
                            f"apply {self._format_rule_setting(settings.duplicate_strikes)}"
                        )
                        if settings.duplicate_strike_threshold
                        else "Off"
                    ),
                    (
                        "Anti Raid",
                        f"{settings.anti_raid_joins}/{settings.anti_raid_seconds}"
                        if settings.anti_raid_joins and settings.anti_raid_seconds
                        else "Off"
                    ),
                    ("Invite Whitelist", "\n".join(whitelist_preview) if whitelist_preview else "None"),
                    ("Word Filters", "\n".join(filter_preview) if filter_preview else "None"),
                    ("Ignored Targets", "\n".join(ignored_preview) if ignored_preview else "None"),
                    ("Punishment Ladder", "\n".join(ladder) if ladder else "Not configured"),
                ],
            )
        )

    def _parse_int_or_off(self, value: str, *, minimum: int = 1) -> int | None:
        if value.lower() in {"off", "none"}:
            return None
        parsed = int(value)
        if parsed < minimum:
            raise commands.BadArgument(f"Value must be at least {minimum}.")
        return parsed

    def _parse_rule_strikes(self, value: str) -> int | None:
        lowered = value.lower()
        if lowered in {"off", "none"}:
            return None
        if lowered in {"delete", "delete-only", "delete_only"}:
            return -1

        parsed = int(value)
        if parsed < 1:
            raise commands.BadArgument("Strike amount must be at least 1, or use `delete`.")
        if parsed > MAX_STRIKES:
            raise commands.BadArgument(f"Strike amount must be at most {MAX_STRIKES}.")
        return parsed

    def _format_rule_setting(self, value: int) -> str:
        if value == 0:
            return "Off"
        if value < 0:
            return "Delete only"
        return f"{value} strike(s)"

    async def _ensure_punishments_ready(
        self,
        ctx: commands.Context[AegisBot],
        *,
        enabled: bool,
        feature_name: str,
    ) -> None:
        if not enabled:
            return
        if await self.bot.db.has_punishments(ctx.guild.id):
            return
        raise commands.BadArgument(
            f"{feature_name} cannot be enabled before at least one punishment threshold is configured."
        )

    def _normalize_dehoist_char(self, value: str) -> str | None:
        if value.lower() in {"off", "none"}:
            return None
        if len(value) != 1 or _DEHOIST_CHAR_RE.match(value) is None:
            raise commands.BadArgument("Provide a single non-alphanumeric character or `off`.")
        return value

    def _parse_filter_items(self, raw_content: str) -> tuple[AutoModFilterItem, ...]:
        if len(raw_content) > MAX_FILTER_CONTENT_LENGTH + 64:
            raise commands.BadArgument(
                f"Filter content must be at most {MAX_FILTER_CONTENT_LENGTH} characters."
            )

        items: list[AutoModFilterItem] = []
        current = raw_content.strip()
        while current:
            if current[0] == '"':
                end_index = current.find('"', 1)
                if end_index == -1:
                    raise commands.BadArgument("Missing closing quote in filter content.")
                value = current[1:end_index].strip().lower()
                if value:
                    items.append(AutoModFilterItem(FilterItemType.QUOTE, value))
                current = current[end_index + 1 :].strip()
                continue

            if current[0] == "`":
                end_index = current.find("`", 1)
                if end_index == -1:
                    raise commands.BadArgument("Missing closing grave accent in regex content.")
                value = current[1:end_index].strip()
                if not value:
                    raise commands.BadArgument("Regex filter content cannot be empty.")
                try:
                    re.compile(value, re.IGNORECASE)
                except re.error as exc:
                    raise commands.BadArgument(f"Invalid regex pattern: {exc}") from exc
                items.append(AutoModFilterItem(FilterItemType.REGEX, value))
                current = current[end_index + 1 :].strip()
                continue

            parts = current.split(maxsplit=1)
            token = parts[0].strip().lower()
            if token:
                items.append(AutoModFilterItem(FilterItemType.GLOB, token))
            current = parts[1] if len(parts) > 1 else ""

        if not items:
            raise commands.BadArgument("Filter must include at least one pattern.")

        rendered = self._render_filter_items(tuple(items))
        if len(rendered) > MAX_FILTER_CONTENT_LENGTH:
            raise commands.BadArgument(
                f"Filter content must be at most {MAX_FILTER_CONTENT_LENGTH} characters."
            )
        return tuple(items)

    def _render_filter_items(self, items: tuple[AutoModFilterItem, ...]) -> str:
        rendered: list[str] = []
        for item in items:
            if item.item_type is FilterItemType.QUOTE:
                rendered.append(f'"{item.value}"')
            elif item.item_type is FilterItemType.REGEX:
                rendered.append(f"`{item.value}`")
            else:
                rendered.append(item.value)
        return " ".join(rendered)

    def _escape_inline_code(self, value: str) -> str:
        return value.replace("`", "\\`")

    def _render_filter_items_verbose(self, items: tuple[AutoModFilterItem, ...]) -> str:
        labels = {
            FilterItemType.QUOTE: "Quote",
            FilterItemType.REGEX: "Regex",
            FilterItemType.GLOB: "Glob",
        }
        return "\n".join(
            f"{labels[item.item_type]}: `{self._escape_inline_code(item.value)}`"
            for item in items
        )

    async def _format_invite_whitelist_target(
        self,
        ctx: commands.Context[AegisBot],
        target_id: int,
    ) -> str:
        if target_id == ctx.guild.id:
            return f"{ctx.guild.name} (`{target_id}`) - this server"

        guild = self.bot.get_guild(target_id)
        if guild is not None:
            return f"{guild.name} (`{target_id}`)"

        try:
            fetched_guild = await self.bot.fetch_guild(target_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            fetched_guild = None

        if fetched_guild is not None:
            return f"{fetched_guild.name} (`{target_id}`)"

        user = self.bot.get_user(target_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(target_id)
            except (discord.NotFound, discord.HTTPException):
                user = None

        if user is not None:
            return f"{user} (`{target_id}`) - user ID (invite whitelist expects guild IDs)"

        return f"Unknown guild (`{target_id}`)"

    async def _parse_strike_payload(
        self,
        ctx: commands.Context[AegisBot],
        payload: str,
    ) -> tuple[int, list[discord.Member], str]:
        parts = payload.split()
        if not parts:
            raise commands.BadArgument("Provide members and a reason.")

        amount = 1
        if parts[0].isdigit():
            amount = int(parts[0])
            parts = parts[1:]

        members: list[discord.Member] = []
        converter = commands.MemberConverter()
        while parts:
            token = parts[0]
            try:
                member = await converter.convert(ctx, token)
            except commands.BadArgument:
                break
            members.append(member)
            parts = parts[1:]

        members = unique_by_id(members)
        if not members:
            raise commands.BadArgument("Provide at least one member.")
        if not parts:
            raise commands.BadArgument("Provide a reason after the member list.")
        return amount, members, " ".join(parts)

    @commands.group(invoke_without_command=True)
    @require_manage_guild()
    async def automod(self, ctx: commands.Context[AegisBot]) -> None:
        await self._send_snapshot(ctx)

    @automod.command(name="show")
    @require_manage_guild()
    async def automod_show(self, ctx: commands.Context[AegisBot]) -> None:
        await self._send_snapshot(ctx)

    @automod.command(name="antiinvite")
    @require_manage_guild()
    async def automod_antiinvite(self, ctx: commands.Context[AegisBot], strikes: str) -> None:
        value = self._parse_rule_strikes(strikes)
        stored_value = 0 if value is None else value
        await self._ensure_punishments_ready(ctx, enabled=(stored_value > 0), feature_name="Anti Invite")
        await self.bot.db.update_guild_settings(ctx.guild.id, anti_invite_strikes=stored_value)
        await ctx.send(
            view=build_panel(
                "Anti Invite Updated",
                "Aegis saved the invite filter rule.",
                tone="success",
                fields=[("Setting", self._format_rule_setting(stored_value))],
            )
        )

    @automod.command(name="antireferral")
    @require_manage_guild()
    async def automod_antireferral(self, ctx: commands.Context[AegisBot], strikes: str) -> None:
        value = self._parse_rule_strikes(strikes)
        stored_value = 0 if value is None else value
        await self._ensure_punishments_ready(ctx, enabled=(stored_value > 0), feature_name="Anti Referral")
        await self.bot.db.update_guild_settings(ctx.guild.id, anti_referral_strikes=stored_value)
        await ctx.send(
            view=build_panel(
                "Anti Referral Updated",
                "Aegis saved the referral-link filter rule.",
                tone="success",
                fields=[("Setting", self._format_rule_setting(stored_value))],
            )
        )

    @automod.command(name="anticopypasta", aliases=["antipasta", "anti-copypasta"])
    @require_manage_guild()
    async def automod_anticopypasta(self, ctx: commands.Context[AegisBot], strikes: str) -> None:
        value = self._parse_rule_strikes(strikes)
        stored_value = 0 if value is None else value
        await self._ensure_punishments_ready(ctx, enabled=(stored_value > 0), feature_name="Anti Copypasta")
        await self.bot.db.update_guild_settings(ctx.guild.id, anti_copypasta_strikes=stored_value)
        await ctx.send(
            view=build_panel(
                "Anti Copypasta Updated",
                "Aegis saved the copypasta rule.",
                tone="success",
                fields=[("Setting", self._format_rule_setting(stored_value))],
            )
        )

    @automod.command(name="antieveryone")
    @require_manage_guild()
    async def automod_antieveryone(self, ctx: commands.Context[AegisBot], strikes: str) -> None:
        value = self._parse_rule_strikes(strikes)
        stored_value = 0 if value is None else value
        await self._ensure_punishments_ready(ctx, enabled=(stored_value > 0), feature_name="Anti Everyone")
        await self.bot.db.update_guild_settings(ctx.guild.id, anti_everyone_strikes=stored_value)
        await ctx.send(
            view=build_panel(
                "Anti Everyone Updated",
                "Aegis saved the everyone/here mention rule.",
                tone="success",
                fields=[("Setting", self._format_rule_setting(stored_value))],
            )
        )

    @automod.command(name="maxmentions")
    @require_manage_guild()
    async def automod_maxmentions(self, ctx: commands.Context[AegisBot], value: str) -> None:
        parsed = self._parse_int_or_off(value, minimum=MENTION_MINIMUM)
        await self._ensure_punishments_ready(ctx, enabled=parsed is not None, feature_name="Max Mentions")
        await self.bot.db.update_guild_settings(ctx.guild.id, max_mentions=parsed)
        await ctx.send(
            view=build_panel(
                "Max Mentions Updated",
                "Aegis saved the mention threshold.",
                tone="success",
                fields=[("Limit", str(parsed) if parsed else "Off")],
            )
        )

    @automod.command(name="maxrolementions")
    @require_manage_guild()
    async def automod_maxrolementions(self, ctx: commands.Context[AegisBot], value: str) -> None:
        parsed = self._parse_int_or_off(value, minimum=ROLE_MENTION_MINIMUM)
        await self._ensure_punishments_ready(
            ctx,
            enabled=parsed is not None,
            feature_name="Max Role Mentions",
        )
        await self.bot.db.update_guild_settings(ctx.guild.id, max_role_mentions=parsed)
        await ctx.send(
            view=build_panel(
                "Max Role Mentions Updated",
                "Aegis saved the role mention threshold.",
                tone="success",
                fields=[("Limit", str(parsed) if parsed else "Off")],
            )
        )

    @automod.command(name="maxlines")
    @require_manage_guild()
    async def automod_maxlines(self, ctx: commands.Context[AegisBot], value: str) -> None:
        parsed = self._parse_int_or_off(value)
        await self._ensure_punishments_ready(ctx, enabled=parsed is not None, feature_name="Max Lines")
        await self.bot.db.update_guild_settings(ctx.guild.id, max_lines=parsed)
        await ctx.send(
            view=build_panel(
                "Max Lines Updated",
                "Aegis saved the line-count threshold.",
                tone="success",
                fields=[("Limit", str(parsed) if parsed else "Off")],
            )
        )

    @automod.command(name="antiduplicate", aliases=["antispam"])
    @require_manage_guild()
    async def automod_antiduplicate(
        self,
        ctx: commands.Context[AegisBot],
        strike_threshold: str,
        delete_threshold: int | None = None,
        strikes: int = 1,
    ) -> None:
        parsed = self._parse_int_or_off(strike_threshold)
        if parsed is None:
            await self.bot.db.update_guild_settings(
                ctx.guild.id,
                duplicate_strike_threshold=None,
                duplicate_delete_threshold=None,
                duplicate_strikes=1,
            )
            await ctx.send(
                view=build_panel(
                    "Duplicate Filter Disabled",
                    "Aegis will stop flagging repeated message spam.",
                    tone="success",
                )
            )
            return

        delete_value = delete_threshold if delete_threshold is not None else parsed
        if delete_value < 1:
            raise commands.BadArgument("Delete threshold must be at least 1.")
        if delete_value > parsed:
            raise commands.BadArgument("Delete threshold cannot be higher than the strike threshold.")
        if strikes < 0 or strikes > MAX_STRIKES:
            raise commands.BadArgument(f"Strike amount must be between 0 and {MAX_STRIKES}.")
        await self._ensure_punishments_ready(ctx, enabled=(strikes > 0), feature_name="Anti Duplicate")

        await self.bot.db.update_guild_settings(
            ctx.guild.id,
            duplicate_strike_threshold=parsed,
            duplicate_delete_threshold=delete_value,
            duplicate_strikes=strikes,
        )
        await ctx.send(
            view=build_panel(
                "Duplicate Filter Updated",
                "Aegis saved the duplicate-message spam rule.",
                tone="success",
                fields=[
                    ("Strike Threshold", str(parsed)),
                    ("Delete Threshold", str(delete_value)),
                    ("Strike Amount", self._format_rule_setting(strikes)),
                ],
            )
        )

    @automod.command(name="resolvelinks")
    @require_manage_guild()
    async def automod_resolvelinks(self, ctx: commands.Context[AegisBot], mode: str) -> None:
        normalized = mode.lower()
        if normalized not in {"on", "off"}:
            raise commands.BadArgument("Value must be `on` or `off`.")

        enabled = normalized == "on"
        await self.bot.db.update_guild_settings(ctx.guild.id, resolve_urls=1 if enabled else 0)
        await ctx.send(
            view=build_panel(
                "Resolve Links Updated",
                "Aegis saved the redirect-link resolution setting.",
                tone="success",
                fields=[("Setting", "On" if enabled else "Off")],
            )
        )

    @automod.command(name="autodehoist", aliases=["dehoist"])
    @require_manage_guild()
    async def automod_autodehoist(self, ctx: commands.Context[AegisBot], character: str) -> None:
        dehoist_char = self._normalize_dehoist_char(character)
        await self.bot.db.update_guild_settings(ctx.guild.id, dehoist_char=dehoist_char)
        await ctx.send(
            view=build_panel(
                "Auto Dehoist Updated",
                "Aegis saved the dehoist threshold.",
                tone="success",
                fields=[("Setting", dehoist_char if dehoist_char else "Off")],
            )
        )

    @automod.command(name="whitelist", aliases=["whitelistinvites"])
    @require_manage_guild()
    async def automod_invite_whitelist(
        self,
        ctx: commands.Context[AegisBot],
        action: str,
        *target_guild_ids: int,
    ) -> None:
        mode = action.lower()
        if mode == "show":
            targets = await self.bot.db.list_invite_whitelist_targets(ctx.guild.id)
            if targets:
                formatted_targets = [
                    await self._format_invite_whitelist_target(ctx, target)
                    for target in targets[:25]
                ]
                preview = "\n".join(formatted_targets)
            else:
                preview = "None"
            await ctx.send(
                view=build_panel(
                    "Invite Whitelist",
                    "Guild IDs that bypass Anti Invite checks.",
                    tone="info",
                    fields=[
                        ("Targets", preview),
                        ("Note", "Invite whitelist entries are guild IDs, not users."),
                    ],
                )
            )
            return

        if mode not in {"add", "remove"}:
            raise commands.BadArgument("Action must be one of `add`, `remove`, or `show`.")

        if not target_guild_ids:
            raise commands.BadArgument("Provide at least one guild ID.")

        if mode == "add":
            for target_id in target_guild_ids:
                await self.bot.db.add_invite_whitelist_target(ctx.guild.id, target_id)
            title = "Invite Whitelist Updated"
            desc = "Aegis added guild IDs to the invite whitelist."
        else:
            for target_id in target_guild_ids:
                await self.bot.db.remove_invite_whitelist_target(ctx.guild.id, target_id)
            title = "Invite Whitelist Updated"
            desc = "Aegis removed guild IDs from the invite whitelist."

        resolved = [
            await self._format_invite_whitelist_target(ctx, target)
            for target in target_guild_ids[:25]
        ]

        await ctx.send(
            view=build_panel(
                title,
                desc,
                tone="success",
                fields=[("Targets", "\n".join(resolved))],
            )
        )

    @automod.group(name="filter", aliases=["filters"], invoke_without_command=True)
    @require_manage_guild()
    async def automod_filter(self, ctx: commands.Context[AegisBot]) -> None:
        await self.automod_filter_list(ctx)

    @automod_filter.command(name="add", aliases=["create"])
    @require_manage_guild()
    async def automod_filter_add(
        self,
        ctx: commands.Context[AegisBot],
        name: str,
        strikes: int,
        *,
        content: str,
    ) -> None:
        if len(name) > MAX_FILTER_NAME_LENGTH:
            raise commands.BadArgument(f"Filter name must be at most {MAX_FILTER_NAME_LENGTH} characters.")
        if not any(char.isalnum() for char in name):
            raise commands.BadArgument("Filter name must include at least one alphanumeric character.")
        if strikes < 1 or strikes > MAX_STRIKES:
            raise commands.BadArgument(f"Strikes must be between 1 and {MAX_STRIKES}.")

        await self._ensure_punishments_ready(ctx, enabled=True, feature_name="Filters")
        items = self._parse_filter_items(content)
        await self.bot.db.upsert_automod_filter(
            ctx.guild.id,
            name,
            strikes,
            items,
        )

        await ctx.send(
            view=build_panel(
                "Filter Updated",
                "Aegis saved the AutoMod filter.",
                tone="success",
                fields=[
                    ("Name", name.lower()),
                    ("Strikes", str(strikes)),
                    ("Patterns", self._render_filter_items_verbose(items)),
                ],
            )
        )

    @automod_filter.command(name="remove", aliases=["delete"])
    @require_manage_guild()
    async def automod_filter_remove(self, ctx: commands.Context[AegisBot], *, name: str) -> None:
        removed = await self.bot.db.delete_automod_filter(ctx.guild.id, name)
        if not removed:
            raise commands.BadArgument(f"No filter named `{name}` exists.")

        await ctx.send(
            view=build_panel(
                "Filter Removed",
                "Aegis removed the AutoMod filter.",
                tone="success",
                fields=[("Name", name.lower())],
            )
        )

    @automod_filter.command(name="list", aliases=["show"])
    @require_manage_guild()
    async def automod_filter_list(self, ctx: commands.Context[AegisBot]) -> None:
        filters = await self.bot.db.list_automod_filters(ctx.guild.id)
        if not filters:
            await ctx.send(
                view=build_panel(
                    "Filters",
                    "No AutoMod filters are configured.",
                    tone="info",
                )
            )
            return

        lines = [
            f"`{flt.name}` -> `{flt.strikes}` strike(s)\n{self._render_filter_items_verbose(flt.items)}"
            for flt in filters[:12]
        ]
        await ctx.send(
            view=build_panel(
                "Filters",
                "Current AutoMod filters.",
                tone="info",
                fields=[("Entries", "\n\n".join(lines))],
            )
        )

    @automod.command(name="antiraid", aliases=["autoraidmode", "autoraid", "autoantiraid"])
    @require_manage_guild()
    async def automod_antiraid(self, ctx: commands.Context[AegisBot], value: str) -> None:
        if value.lower() == "off":
            await self.bot.db.update_guild_settings(
                ctx.guild.id,
                anti_raid_joins=None,
                anti_raid_seconds=None,
            )
            await ctx.send(
                view=build_panel(
                    "Anti Raid Disabled",
                    "Aegis will stop auto-enabling raid mode on join bursts.",
                    tone="success",
                )
            )
            return

        if value.lower() == "on":
            joins, seconds = 10, 10
            await self.bot.db.update_guild_settings(
                ctx.guild.id,
                anti_raid_joins=joins,
                anti_raid_seconds=seconds,
            )
            await ctx.send(
                view=build_panel(
                    "Anti Raid Updated",
                    "Aegis enabled automatic raid mode with the recommended threshold.",
                    tone="success",
                    fields=[("Threshold", f"{joins} joins in {seconds}s")],
                )
            )
            return

        ratio = parse_ratio(value)
        if ratio is None:
            raise commands.BadArgument("Anti raid must look like `10/8` for joins/seconds.")

        joins, seconds = ratio
        await self.bot.db.update_guild_settings(
            ctx.guild.id,
            anti_raid_joins=joins,
            anti_raid_seconds=seconds,
        )
        await ctx.send(
            view=build_panel(
                "Anti Raid Updated",
                "Aegis saved the join-burst threshold.",
                tone="success",
                fields=[("Threshold", f"{joins} joins in {seconds}s")],
            )
        )

    @automod.command(name="ignore")
    @require_manage_guild()
    async def automod_ignore(
        self,
        ctx: commands.Context[AegisBot],
        *,
        target: IgnoreTargetConverter,
    ) -> None:
        target_type = "role" if isinstance(target, discord.Role) else "channel"
        await self.bot.db.add_ignored_target(ctx.guild.id, target.id, target_type)
        await ctx.send(
            view=build_panel(
                "AutoMod Ignore Added",
                "Aegis will skip AutoMod for this target.",
                tone="success",
                fields=[("Target", target.mention if hasattr(target, "mention") else str(target))],
            )
        )

    @automod.command(name="unignore")
    @require_manage_guild()
    async def automod_unignore(
        self,
        ctx: commands.Context[AegisBot],
        *,
        target: IgnoreTargetConverter,
    ) -> None:
        target_type = "role" if isinstance(target, discord.Role) else "channel"
        await self.bot.db.remove_ignored_target(ctx.guild.id, target.id, target_type)
        await ctx.send(
            view=build_panel(
                "AutoMod Ignore Removed",
                "Aegis will process this target again.",
                tone="success",
                fields=[("Target", target.mention if hasattr(target, "mention") else str(target))],
            )
        )

    @commands.command()
    @require_manage_guild()
    async def punishment(
        self,
        ctx: commands.Context[AegisBot],
        strikes: commands.Range[int, 1, 100],
        action: str,
        duration: Optional[DurationConverter] = None,
    ) -> None:
        action_name = action.lower()
        if action_name in {"off", "none"}:
            await self.bot.db.remove_punishment(ctx.guild.id, strikes)
            await ctx.send(
                view=build_panel(
                    "Punishment Removed",
                    "Aegis cleared that strike threshold.",
                    tone="success",
                    fields=[("Threshold", str(strikes))],
                )
            )
            return

        action_aliases = {
            "tempmute": "mute",
            "temp-mute": "mute",
            "tempban": "ban",
            "temp-ban": "ban",
        }
        action_name = action_aliases.get(action_name, action_name)

        punishments = await self.bot.db.get_punishments(ctx.guild.id)
        if strikes not in punishments and len(punishments) >= MAX_PUNISHMENTS:
            raise commands.BadArgument(
                f"A maximum of {MAX_PUNISHMENTS} punishments can be configured at once."
            )

        try:
            punishment = PunishmentAction(action_name)
        except ValueError as error:
            raise commands.BadArgument(
                "Punishment must be one of `warn`, `mute`, `kick`, `ban`, `softban`, `silentban`, or `none`."
            ) from error

        if duration and punishment not in {
            PunishmentAction.MUTE,
            PunishmentAction.BAN,
            PunishmentAction.SILENTBAN,
        }:
            raise commands.BadArgument("Only `mute`, `ban`, and `silentban` support durations.")

        await self.bot.db.set_punishment(
            ctx.guild.id,
            strikes,
            punishment,
            int(duration.total_seconds()) if duration else None,
        )
        await ctx.send(
            view=build_panel(
                "Punishment Updated",
                "Aegis saved the strike threshold action.",
                tone="success",
                fields=[
                    ("Threshold", str(strikes)),
                    ("Action", punishment.value),
                    ("Duration", humanize_duration(duration) if duration else "Permanent"),
                ],
            )
        )

    @commands.command()
    @require_moderation("moderate_members")
    async def strike(self, ctx: commands.Context[AegisBot], *, payload: str) -> None:
        amount, members, reason = await self._parse_strike_payload(ctx, payload)
        successes: list[str] = []
        failures: list[str] = []

        for member in members:
            failure = self._check_manual_target(ctx, member)
            if failure:
                failures.append(f"{member}: {failure}")
                continue

            old_total, new_total = await self.bot.apply_strikes(
                ctx.guild,
                member,
                amount,
                reason,
                moderator=ctx.author,
                source="Manual moderation",
            )
            successes.append(f"{member}: {old_total} -> {new_total}")

        await ctx.send(
            view=build_panel(
                "Strikes Applied",
                "Aegis updated strike counts for the selected members.",
                tone="success" if successes else "warning",
                fields=[
                    ("Succeeded", "\n".join(successes[:10]) if successes else "None"),
                    ("Skipped", "\n".join(failures[:10]) if failures else "None"),
                ],
            )
        )

    @commands.command()
    @require_moderation("moderate_members")
    async def pardon(self, ctx: commands.Context[AegisBot], *, payload: str) -> None:
        amount, members, reason = await self._parse_strike_payload(ctx, payload)
        successes: list[str] = []
        failures: list[str] = []

        for member in members:
            failure = self._check_manual_target(ctx, member)
            if failure:
                failures.append(f"{member}: {failure}")
                continue

            old_total, new_total = await self.bot.apply_strikes(
                ctx.guild,
                member,
                -amount,
                reason,
                moderator=ctx.author,
                source="Manual moderation",
            )
            successes.append(f"{member}: {old_total} -> {new_total}")

        await ctx.send(
            view=build_panel(
                "Pardon Applied",
                "Aegis reduced strike counts for the selected members.",
                tone="success" if successes else "warning",
                fields=[
                    ("Succeeded", "\n".join(successes[:10]) if successes else "None"),
                    ("Skipped", "\n".join(failures[:10]) if failures else "None"),
                ],
            )
        )

    @commands.command()
    @require_moderation("moderate_members")
    async def check(
        self,
        ctx: commands.Context[AegisBot],
        *,
        user: Optional[MemberOrUserConverter] = None,
    ) -> None:
        target = user or ctx.author
        strikes = await self.bot.db.get_strikes(ctx.guild.id, target.id)
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        now = utcnow()

        muted = "No"
        mute_remaining = "N/A"
        member = ctx.guild.get_member(target.id)
        muted_role = ctx.guild.get_role(settings.muted_role_id or 0) if settings.muted_role_id else None
        if member and muted_role and muted_role in member.roles:
            muted = "Yes"

        unmute_row = await self.bot.db.get_next_scheduled_action(ctx.guild.id, target.id, "unmute")
        if unmute_row is not None:
            try:
                execute_at = datetime.fromisoformat(unmute_row["execute_at"])
                if execute_at > now:
                    mute_remaining = f"{format_timestamp(execute_at, 'R')} ({format_timestamp(execute_at)})"
                else:
                    mute_remaining = "Expiring soon"
            except (TypeError, ValueError):
                mute_remaining = "Unknown"

        banned = "No"
        ban_remaining = "N/A"
        ban_reason = "N/A"
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=target.id))
            banned = "Yes"
            ban_reason = ban_entry.reason or "No reason provided"
        except discord.NotFound:
            banned = "No"
        except discord.Forbidden:
            banned = "Unknown"

        unban_row = await self.bot.db.get_next_scheduled_action(ctx.guild.id, target.id, "unban")
        if unban_row is not None:
            try:
                execute_at = datetime.fromisoformat(unban_row["execute_at"])
                if execute_at > now:
                    ban_remaining = f"{format_timestamp(execute_at, 'R')} ({format_timestamp(execute_at)})"
                else:
                    ban_remaining = "Expiring soon"
            except (TypeError, ValueError):
                ban_remaining = "Unknown"

        if banned == "Yes" and ban_reason == "No reason provided":
            me = ctx.guild.me
            if me and me.guild_permissions.view_audit_log:
                try:
                    async for entry in ctx.guild.audit_logs(action=discord.AuditLogAction.ban, limit=25):
                        target_obj = getattr(entry, "target", None)
                        if target_obj is None or target_obj.id != target.id:
                            continue
                        if entry.reason:
                            ban_reason = entry.reason
                        break
                except discord.Forbidden:
                    pass

        title_name = getattr(target, "name", str(target))
        avatar_url = str(target.display_avatar.url) if hasattr(target, "display_avatar") else None

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## Moderation info of {title_name}"),
            discord.ui.Separator(
                visible=True,
                spacing=discord.SeparatorSpacing.small,
            ),
        ]

        details_block = "\n\n".join(
            [
                f"**User**\n{format_identity(target)}",
                f"**Strikes**\n{strikes}",
                f"**Muted**\n{muted}",
                f"**Mute Time Remaining**\n{mute_remaining}",
                f"**Banned**\n{banned}",
                f"**Ban Time Remaining**\n{ban_remaining}",
                f"**Ban Reason**\n{truncate(ban_reason, 250)}",
            ]
        )

        if avatar_url:
            items.append(
                discord.ui.Section(
                    details_block,
                    accessory=discord.ui.Thumbnail(avatar_url),
                )
            )
        else:
            items.append(discord.ui.TextDisplay(details_block))

        container = discord.ui.Container(*items)
        check_view = discord.ui.LayoutView(timeout=None)
        check_view.add_item(container)

        await ctx.send(
            view=check_view,
        )

    @commands.command()
    @require_manage_guild()
    async def raidmode(
        self,
        ctx: commands.Context[AegisBot],
        mode: str,
        *,
        reason: str = "Manual security override",
    ) -> None:
        if mode.lower() not in {"on", "off"}:
            raise commands.BadArgument("Raid mode must be `on` or `off`.")

        enabled = mode.lower() == "on"
        await self.bot.toggle_raid_mode(
            ctx.guild,
            enabled,
            reason=reason,
            moderator=ctx.author,
            automatic=False,
        )
        await ctx.send(
            view=build_panel(
                "Raid Mode Updated",
                "Aegis changed the raid mode state for this server.",
                tone="danger" if enabled else "success",
                fields=[
                    ("State", "Enabled" if enabled else "Disabled"),
                    ("Reason", reason),
                ],
            )
        )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(AutoModCog(bot))
