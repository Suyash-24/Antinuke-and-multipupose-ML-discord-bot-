from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import discord
from discord.ext import commands

from aegis.bot import AegisBot
from aegis.checks import require_antinuke_control
from aegis.models import (
    AntiNukeCanaryAssetType,
    AntiNukeEventType,
    AntiNukeMode,
    AntiNukeThresholdConfig,
    LogType,
    TrustSubjectType,
)
from aegis.ui import build_panel
from aegis.utils import format_identity, format_timestamp, truncate, utcnow


@dataclass(slots=True)
class NormalizedAntiNukeEvent:
    guild: discord.Guild
    actor: discord.User | discord.Member | None
    actor_id: int | None
    actor_name: str
    event_type: AntiNukeEventType
    audit_entry: discord.AuditLogEntry
    target: object | None
    target_id: int | None
    target_name: str
    summary: str
    weight: int
    evidence: dict[str, Any]
    rollback_hint: dict[str, Any]


DEFAULT_THRESHOLDS: dict[AntiNukeEventType, tuple[int, int, bool, int]] = {
    AntiNukeEventType.BOT_ADD: (1, 60, True, 4),
    AntiNukeEventType.ADMIN_PERMISSION_GRANT: (1, 60, True, 4),
    AntiNukeEventType.CHANNEL_DELETE: (2, 10, True, 2),
    AntiNukeEventType.ROLE_DELETE: (2, 10, True, 2),
    AntiNukeEventType.WEBHOOK_CREATE: (2, 10, True, 2),
    AntiNukeEventType.WEBHOOK_DELETE: (2, 10, True, 2),
    AntiNukeEventType.CHANNEL_CREATE: (5, 10, True, 1),
    AntiNukeEventType.ROLE_CREATE: (5, 10, True, 1),
    AntiNukeEventType.CHANNEL_UPDATE: (5, 10, True, 1),
    AntiNukeEventType.ROLE_UPDATE: (5, 10, True, 1),
    AntiNukeEventType.WEBHOOK_UPDATE: (5, 10, True, 1),
    AntiNukeEventType.GUILD_UPDATE: (2, 60, True, 1),
}

MIXED_SCORE_LIMIT = 4
MIXED_SCORE_WINDOW_SECONDS = 10

EVENT_LABELS: dict[AntiNukeEventType, str] = {
    AntiNukeEventType.BOT_ADD: "Bot Add",
    AntiNukeEventType.ADMIN_PERMISSION_GRANT: "Admin Permission Grant",
    AntiNukeEventType.CHANNEL_CREATE: "Channel Create",
    AntiNukeEventType.CHANNEL_DELETE: "Channel Delete",
    AntiNukeEventType.CHANNEL_UPDATE: "Channel Update",
    AntiNukeEventType.ROLE_CREATE: "Role Create",
    AntiNukeEventType.ROLE_DELETE: "Role Delete",
    AntiNukeEventType.ROLE_UPDATE: "Role Update",
    AntiNukeEventType.WEBHOOK_CREATE: "Webhook Create",
    AntiNukeEventType.WEBHOOK_DELETE: "Webhook Delete",
    AntiNukeEventType.WEBHOOK_UPDATE: "Webhook Update",
    AntiNukeEventType.GUILD_UPDATE: "Guild Update",
}

EVENT_ALIASES: dict[str, AntiNukeEventType] = {
    event_type.value: event_type for event_type in AntiNukeEventType
}
EVENT_ALIASES.update(
    {
        "botadd": AntiNukeEventType.BOT_ADD,
        "admingrant": AntiNukeEventType.ADMIN_PERMISSION_GRANT,
        "permgrant": AntiNukeEventType.ADMIN_PERMISSION_GRANT,
        "permissiongrant": AntiNukeEventType.ADMIN_PERMISSION_GRANT,
        "channelcreate": AntiNukeEventType.CHANNEL_CREATE,
        "channeldelete": AntiNukeEventType.CHANNEL_DELETE,
        "channelupdate": AntiNukeEventType.CHANNEL_UPDATE,
        "rolecreate": AntiNukeEventType.ROLE_CREATE,
        "roledelete": AntiNukeEventType.ROLE_DELETE,
        "roleupdate": AntiNukeEventType.ROLE_UPDATE,
        "webhookcreate": AntiNukeEventType.WEBHOOK_CREATE,
        "webhookdelete": AntiNukeEventType.WEBHOOK_DELETE,
        "webhookupdate": AntiNukeEventType.WEBHOOK_UPDATE,
        "guildupdate": AntiNukeEventType.GUILD_UPDATE,
    }
)

CANARY_TRIP_EVENTS = frozenset(
    {
        AntiNukeEventType.CHANNEL_DELETE,
        AntiNukeEventType.CHANNEL_UPDATE,
        AntiNukeEventType.ROLE_DELETE,
        AntiNukeEventType.ROLE_UPDATE,
        AntiNukeEventType.WEBHOOK_DELETE,
        AntiNukeEventType.WEBHOOK_UPDATE,
    }
)


class AntiNukeCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot
        self._event_windows: dict[tuple[int, int, AntiNukeEventType], deque[datetime]] = defaultdict(deque)
        self._score_windows: dict[tuple[int, int], deque[tuple[datetime, int]]] = defaultdict(deque)
        self._seen_entry_order: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=250))
        self._seen_entry_lookup: dict[int, set[int]] = defaultdict(set)
        self._pending_reconciles: set[tuple[int, str, int | None]] = set()

    def _mark_seen(self, guild_id: int, entry_id: int) -> bool:
        seen = self._seen_entry_lookup[guild_id]
        if entry_id in seen:
            return False

        order = self._seen_entry_order[guild_id]
        if len(order) == order.maxlen:
            evicted = order.popleft()
            seen.discard(evicted)

        order.append(entry_id)
        seen.add(entry_id)
        return True

    def _parse_event_type(self, argument: str) -> AntiNukeEventType:
        normalized = argument.strip().lower().replace("-", "_").replace(" ", "_")
        normalized = normalized.replace("__", "_")
        event_type = EVENT_ALIASES.get(normalized)
        if event_type is None:
            valid = ", ".join(f"`{item.value}`" for item in AntiNukeEventType)
            raise commands.BadArgument(f"Unknown anti-nuke event. Valid values: {valid}")
        return event_type

    async def _resolve_thresholds(
        self,
        guild_id: int,
    ) -> dict[AntiNukeEventType, AntiNukeThresholdConfig]:
        stored = await self.bot.db.get_antinuke_thresholds(guild_id)
        resolved: dict[AntiNukeEventType, AntiNukeThresholdConfig] = {}

        for event_type, (count, seconds, enabled, _) in DEFAULT_THRESHOLDS.items():
            resolved[event_type] = stored.get(
                event_type,
                AntiNukeThresholdConfig(
                    guild_id=guild_id,
                    event_type=event_type,
                    count=count,
                    window_seconds=seconds,
                    enabled=enabled,
                ),
            )

        return resolved

    async def _resolve_trust_subject(
        self,
        ctx: commands.Context[AegisBot],
        raw_target: str,
    ) -> tuple[discord.Role | discord.Member | discord.User, TrustSubjectType]:
        try:
            role = await commands.RoleConverter().convert(ctx, raw_target)
        except commands.BadArgument:
            role = None

        if role is not None:
            return role, TrustSubjectType.ROLE

        for converter in (commands.MemberConverter(), commands.UserConverter()):
            try:
                subject = await converter.convert(ctx, raw_target)
                return subject, TrustSubjectType.USER
            except commands.BadArgument:
                continue

        raise commands.BadArgument("Trust target must be a role, member, or user.")

    def _describe_log_channel(self, guild: discord.Guild, channel_id: int | None) -> str:
        if not channel_id:
            return "Inherited fallback"
        channel = guild.get_channel(channel_id)
        return channel.mention if channel else f"`{channel_id}`"

    def _serialize_change_value(self, value: Any) -> str:
        if value is None:
            return "None"
        if isinstance(value, discord.Permissions):
            enabled = [name for name, allowed in value if allowed]
            return ", ".join(enabled[:8]) + (", ..." if len(enabled) > 8 else "") if enabled else "None"
        if isinstance(value, discord.Asset):
            return value.url
        if isinstance(value, (discord.Object, discord.Role, discord.User, discord.Member)):
            return format_identity(value)
        if isinstance(value, list):
            return ", ".join(self._serialize_change_value(item) for item in value) or "None"
        return truncate(str(value), 200)

    def _extract_change_snapshot(self, entry: discord.AuditLogEntry) -> dict[str, dict[str, str]]:
        fields: dict[str, dict[str, str]] = {}
        candidate_names = (
            "name",
            "permissions",
            "roles",
            "nick",
            "mentionable",
            "hoist",
            "color",
            "topic",
            "nsfw",
            "slowmode_delay",
            "verification_level",
            "default_notifications",
            "explicit_content_filter",
            "system_channel",
            "afk_channel",
            "vanity_url_code",
            "channel",
        )

        for field_name in candidate_names:
            before_value = getattr(entry.before, field_name, None)
            after_value = getattr(entry.after, field_name, None)
            if before_value == after_value:
                continue
            if before_value is None and after_value is None:
                continue
            fields[field_name] = {
                "before": self._serialize_change_value(before_value),
                "after": self._serialize_change_value(after_value),
            }

        return fields

    def _has_dangerous_role_upgrade(self, entry: discord.AuditLogEntry) -> bool:
        before_permissions = getattr(entry.before, "permissions", None)
        after_permissions = getattr(entry.after, "permissions", None)
        if not isinstance(before_permissions, discord.Permissions):
            return False
        if not isinstance(after_permissions, discord.Permissions):
            return False
        if not self.bot.permissions_are_dangerous(after_permissions):
            return False

        return any(
            not getattr(before_permissions, permission_name, False)
            and getattr(after_permissions, permission_name, False)
            for permission_name in self.bot.DANGEROUS_PERMISSION_NAMES
        )

    def _dangerous_roles_added(
        self,
        guild: discord.Guild,
        entry: discord.AuditLogEntry,
    ) -> list[discord.Role]:
        before_roles = {
            getattr(role, "id", None) for role in (getattr(entry.before, "roles", None) or [])
        }
        after_roles = {
            getattr(role, "id", None) for role in (getattr(entry.after, "roles", None) or [])
        }
        added_role_ids = {role_id for role_id in after_roles - before_roles if role_id is not None}

        dangerous_roles: list[discord.Role] = []
        for role_id in added_role_ids:
            role = guild.get_role(role_id)
            if role and self.bot.permissions_are_dangerous(role.permissions):
                dangerous_roles.append(role)
        return dangerous_roles

    def _normalize_entry(self, entry: discord.AuditLogEntry) -> NormalizedAntiNukeEvent | None:
        guild = entry.guild
        actor = entry.user
        actor_id = actor.id if actor else None
        actor_name = format_identity(actor)
        target = entry.target
        target_id = getattr(target, "id", None)
        target_name = format_identity(target)
        evidence: dict[str, Any] = {
            "source": "audit_log",
            "changes": self._extract_change_snapshot(entry),
        }
        rollback_hint: dict[str, Any] = {}

        action = entry.action
        if action is discord.AuditLogAction.bot_add:
            return NormalizedAntiNukeEvent(
                guild=guild,
                actor=actor,
                actor_id=actor_id,
                actor_name=actor_name,
                event_type=AntiNukeEventType.BOT_ADD,
                audit_entry=entry,
                target=target,
                target_id=target_id,
                target_name=target_name,
                summary=f"Added bot {target_name}.",
                weight=DEFAULT_THRESHOLDS[AntiNukeEventType.BOT_ADD][3],
                evidence=evidence,
                rollback_hint={"kind": "bot_add", "target_id": target_id},
            )

        if action is discord.AuditLogAction.channel_create:
            event_type = AntiNukeEventType.CHANNEL_CREATE
            summary = f"Created channel {target_name}."
        elif action is discord.AuditLogAction.channel_delete:
            event_type = AntiNukeEventType.CHANNEL_DELETE
            summary = f"Deleted channel {target_name}."
        elif action is discord.AuditLogAction.channel_update:
            event_type = AntiNukeEventType.CHANNEL_UPDATE
            summary = f"Updated channel {target_name}."
        elif action is discord.AuditLogAction.role_create:
            event_type = AntiNukeEventType.ROLE_CREATE
            summary = f"Created role {target_name}."
        elif action is discord.AuditLogAction.role_delete:
            event_type = AntiNukeEventType.ROLE_DELETE
            summary = f"Deleted role {target_name}."
        elif action is discord.AuditLogAction.role_update:
            if self._has_dangerous_role_upgrade(entry):
                before_permissions = getattr(entry.before, "permissions", None)
                if isinstance(before_permissions, discord.Permissions):
                    rollback_hint = {
                        "kind": "role_permissions",
                        "target_id": target_id,
                        "before_permissions": before_permissions.value,
                    }
                event_type = AntiNukeEventType.ADMIN_PERMISSION_GRANT
                summary = f"Granted dangerous permissions to role {target_name}."
            else:
                event_type = AntiNukeEventType.ROLE_UPDATE
                summary = f"Updated role {target_name}."
        elif action is discord.AuditLogAction.member_role_update:
            dangerous_roles = self._dangerous_roles_added(guild, entry)
            if not dangerous_roles:
                return None
            evidence["dangerous_roles_added"] = [format_identity(role) for role in dangerous_roles]
            rollback_hint = {
                "kind": "member_roles",
                "target_id": target_id,
                "role_ids": [role.id for role in dangerous_roles],
            }
            event_type = AntiNukeEventType.ADMIN_PERMISSION_GRANT
            summary = f"Granted dangerous role(s) to {target_name}."
        elif action is discord.AuditLogAction.guild_update:
            event_type = AntiNukeEventType.GUILD_UPDATE
            summary = "Updated server security-relevant settings."
        elif action is discord.AuditLogAction.webhook_create:
            event_type = AntiNukeEventType.WEBHOOK_CREATE
            summary = f"Created webhook {target_name}."
            rollback_hint = {"kind": "webhook_create", "target_id": target_id}
        elif action is discord.AuditLogAction.webhook_delete:
            event_type = AntiNukeEventType.WEBHOOK_DELETE
            summary = f"Deleted webhook {target_name}."
        elif action is discord.AuditLogAction.webhook_update:
            event_type = AntiNukeEventType.WEBHOOK_UPDATE
            summary = f"Updated webhook {target_name}."
        else:
            return None

        _, _, _, weight = DEFAULT_THRESHOLDS[event_type]
        return NormalizedAntiNukeEvent(
            guild=guild,
            actor=actor,
            actor_id=actor_id,
            actor_name=actor_name,
            event_type=event_type,
            audit_entry=entry,
            target=target,
            target_id=target_id,
            target_name=target_name,
            summary=summary,
            weight=weight,
            evidence=evidence,
            rollback_hint=rollback_hint,
        )

    def _register_event(
        self,
        event: NormalizedAntiNukeEvent,
        threshold: AntiNukeThresholdConfig,
    ) -> tuple[int, int, str | None]:
        if event.actor_id is None:
            return 0, 0, "Actor attribution is missing from the audit log."

        now = utcnow()
        event_key = (event.guild.id, event.actor_id, event.event_type)
        event_queue = self._event_windows[event_key]
        while event_queue and (now - event_queue[0]).total_seconds() > threshold.window_seconds:
            event_queue.popleft()
        event_queue.append(now)

        score_key = (event.guild.id, event.actor_id)
        score_queue = self._score_windows[score_key]
        while score_queue and (now - score_queue[0][0]).total_seconds() > MIXED_SCORE_WINDOW_SECONDS:
            score_queue.popleft()
        score_queue.append((now, event.weight))

        event_count = len(event_queue)
        mixed_score = sum(weight for _, weight in score_queue)

        if event_count >= threshold.count:
            return (
                event_count,
                mixed_score,
                f"{EVENT_LABELS[event.event_type]} threshold reached: {event_count} event(s) in {threshold.window_seconds}s.",
            )

        if mixed_score >= MIXED_SCORE_LIMIT:
            return (
                event_count,
                mixed_score,
                f"Mixed destructive score reached {mixed_score} in {MIXED_SCORE_WINDOW_SECONDS}s.",
            )

        return event_count, mixed_score, None

    def _dangerous_manageable_roles(self, member: discord.Member) -> list[discord.Role]:
        me = member.guild.me
        if me is None:
            return []
        return [
            role
            for role in member.roles
            if role != member.guild.default_role
            and self.bot.permissions_are_dangerous(role.permissions)
            and role < me.top_role
        ]

    def _canary_capability_gaps(self, guild: discord.Guild) -> list[str]:
        me = guild.me
        if me is None:
            return ["Aegis could not resolve its server member state."]

        permissions = me.guild_permissions
        gaps: list[str] = []
        if not permissions.manage_roles:
            gaps.append("Missing Manage Roles.")
        if not permissions.manage_channels:
            gaps.append("Missing Manage Channels.")
        if not permissions.manage_webhooks:
            gaps.append("Missing Manage Webhooks.")
        return gaps

    def _canary_suffix(self, guild: discord.Guild) -> str:
        return f"{guild.id % 10000:04d}-{utcnow().strftime('%H%M%S')}"

    async def _delete_canary_assets(
        self,
        guild: discord.Guild,
        assets: list,
        *,
        reason: str,
    ) -> tuple[list[str], list[str]]:
        notes: list[str] = []
        errors: list[str] = []

        webhook_assets = [
            asset for asset in assets if asset.asset_type is AntiNukeCanaryAssetType.WEBHOOK
        ]
        if webhook_assets:
            try:
                webhooks = await guild.webhooks()
            except discord.HTTPException as error:
                errors.append(f"Failed to load webhooks for canary cleanup: {error}")
                webhooks = []

            for asset in webhook_assets:
                webhook = discord.utils.get(webhooks, id=asset.target_id)
                if webhook is None:
                    notes.append("Webhook canary was already absent.")
                    continue
                try:
                    await webhook.delete(reason=reason)
                    notes.append("Removed webhook canary.")
                except discord.HTTPException as error:
                    errors.append(f"Failed to remove webhook canary: {error}")

        channel_assets = [
            asset for asset in assets if asset.asset_type is AntiNukeCanaryAssetType.CHANNEL
        ]
        for asset in channel_assets:
            channel = guild.get_channel(asset.target_id)
            if channel is None:
                notes.append("Channel canary was already absent.")
                continue
            try:
                await channel.delete(reason=reason)
                notes.append("Removed channel canary.")
            except discord.HTTPException as error:
                errors.append(f"Failed to remove channel canary: {error}")

        role_assets = [asset for asset in assets if asset.asset_type is AntiNukeCanaryAssetType.ROLE]
        for asset in role_assets:
            role = guild.get_role(asset.target_id)
            if role is None:
                notes.append("Role canary was already absent.")
                continue
            try:
                await role.delete(reason=reason)
                notes.append("Removed role canary.")
            except discord.HTTPException as error:
                errors.append(f"Failed to remove role canary: {error}")

        return notes, errors

    async def _provision_canary_assets(
        self,
        guild: discord.Guild,
        *,
        reason: str,
    ) -> tuple[list[str], list[str]]:
        gaps = self._canary_capability_gaps(guild)
        if gaps:
            return [], gaps

        suffix = self._canary_suffix(guild)
        now = utcnow()
        created_notes: list[str] = []

        role: discord.Role | None = None
        channel: discord.TextChannel | None = None
        webhook: discord.Webhook | None = None

        async def rollback_partial() -> None:
            if webhook is not None:
                try:
                    await webhook.delete(reason=reason)
                except discord.HTTPException:
                    pass
            if channel is not None:
                try:
                    await channel.delete(reason=reason)
                except discord.HTTPException:
                    pass
            if role is not None:
                try:
                    await role.delete(reason=reason)
                except discord.HTTPException:
                    pass

        try:
            role_permissions = discord.Permissions(
                manage_guild=True,
                manage_roles=True,
                manage_channels=True,
                manage_webhooks=True,
                ban_members=True,
                kick_members=True,
            )
            role = await guild.create_role(
                name=f"Aegis Canary Role {suffix}",
                permissions=role_permissions,
                hoist=False,
                mentionable=False,
                reason=reason,
            )

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
            }
            if guild.me is not None:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_message_history=True,
                    send_messages=True,
                    manage_webhooks=True,
                )

            channel = await guild.create_text_channel(
                name=f"aegis-canary-{suffix}",
                topic="Aegis anti-nuke canary trap. Do not modify.",
                overwrites=overwrites,
                reason=reason,
            )

            webhook = await channel.create_webhook(
                name=f"Aegis Canary Webhook {suffix}",
                reason=reason,
            )
        except discord.HTTPException as error:
            await rollback_partial()
            return [], [f"Failed to provision canary assets: {error}"]

        await self.bot.db.upsert_antinuke_canary_asset(
            guild.id,
            AntiNukeCanaryAssetType.ROLE,
            role.id,
            parent_channel_id=None,
            created_at=now,
        )
        await self.bot.db.upsert_antinuke_canary_asset(
            guild.id,
            AntiNukeCanaryAssetType.CHANNEL,
            channel.id,
            parent_channel_id=None,
            created_at=now,
        )
        await self.bot.db.upsert_antinuke_canary_asset(
            guild.id,
            AntiNukeCanaryAssetType.WEBHOOK,
            webhook.id,
            parent_channel_id=channel.id,
            created_at=now,
        )

        created_notes.append(f"Role canary: {role.mention}")
        created_notes.append(f"Channel canary: {channel.mention}")
        created_notes.append(f"Webhook canary: `{webhook.id}`")
        return created_notes, []

    async def _rotate_canary_assets(
        self,
        guild: discord.Guild,
        *,
        reason: str,
    ) -> tuple[list[str], list[str]]:
        assets = await self.bot.db.list_antinuke_canary_assets(guild.id)
        teardown_notes, teardown_errors = await self._delete_canary_assets(guild, assets, reason=reason)
        await self.bot.db.clear_antinuke_canary_assets(guild.id)
        provision_notes, provision_errors = await self._provision_canary_assets(guild, reason=reason)
        return teardown_notes + provision_notes, teardown_errors + provision_errors

    def _canary_asset_type_for_event(
        self,
        event_type: AntiNukeEventType,
    ) -> AntiNukeCanaryAssetType | None:
        mapping = {
            AntiNukeEventType.ROLE_UPDATE: AntiNukeCanaryAssetType.ROLE,
            AntiNukeEventType.ROLE_DELETE: AntiNukeCanaryAssetType.ROLE,
            AntiNukeEventType.CHANNEL_UPDATE: AntiNukeCanaryAssetType.CHANNEL,
            AntiNukeEventType.CHANNEL_DELETE: AntiNukeCanaryAssetType.CHANNEL,
            AntiNukeEventType.WEBHOOK_UPDATE: AntiNukeCanaryAssetType.WEBHOOK,
            AntiNukeEventType.WEBHOOK_DELETE: AntiNukeCanaryAssetType.WEBHOOK,
        }
        return mapping.get(event_type)

    async def _apply_contain(
        self,
        guild: discord.Guild,
        event: NormalizedAntiNukeEvent,
    ) -> tuple[str, str]:
        if event.actor_id is None:
            return "contain", "Actor could not be resolved from the audit log."

        actor_member = guild.get_member(event.actor_id)
        if actor_member is None:
            return "contain", "Actor already left the server, so Aegis could not quarantine the account."

        me = guild.me
        if me is None:
            return "contain", "Aegis could not resolve its member state."

        if actor_member.top_role >= me.top_role and actor_member.id != guild.owner_id:
            return "contain", "Actor is above or equal to Aegis in role hierarchy."

        if actor_member.bot:
            try:
                await actor_member.kick(reason="Aegis anti-nuke containment")
                return "contain", "Malicious bot was removed from the server."
            except discord.HTTPException as error:
                return "contain", f"Failed to remove the bot actor: {error}"

        dangerous_roles = self._dangerous_manageable_roles(actor_member)
        if not dangerous_roles:
            return "contain", "Actor has no dangerous roles that Aegis can safely remove."

        try:
            await actor_member.remove_roles(*dangerous_roles, reason="Aegis anti-nuke containment")
        except discord.HTTPException as error:
            return "contain", f"Failed to strip dangerous roles: {error}"

        removed = ", ".join(role.name for role in dangerous_roles)
        return "contain", f"Removed dangerous role(s): {removed}."

    async def _apply_ban(
        self,
        guild: discord.Guild,
        event: NormalizedAntiNukeEvent,
    ) -> tuple[str, str]:
        if event.actor_id is None:
            return "ban", "Actor could not be resolved from the audit log."

        actor_member = guild.get_member(event.actor_id)
        me = guild.me
        if actor_member is not None and me is not None and actor_member.top_role >= me.top_role:
            return "ban", "Actor is above or equal to Aegis in role hierarchy."

        target = actor_member or discord.Object(id=event.actor_id)
        try:
            await guild.ban(target, delete_message_seconds=0, reason="Aegis anti-nuke emergency ban")
        except discord.HTTPException as error:
            return "ban", f"Failed to ban the actor: {error}"

        return "ban", "Actor was banned by anti-nuke."

    async def _safe_rollback(
        self,
        event: NormalizedAntiNukeEvent,
    ) -> tuple[str | None, str | None]:
        kind = event.rollback_hint.get("kind")
        guild = event.guild

        if kind == "bot_add":
            target_id = event.rollback_hint.get("target_id")
            if not isinstance(target_id, int):
                return None, None

            member = guild.get_member(target_id)
            me = guild.me
            if member is None:
                return "remove_bot", "Added bot already left before rollback."
            if me is None or member.top_role >= me.top_role:
                return "remove_bot", "Added bot is above or equal to Aegis in role hierarchy."

            try:
                await member.kick(reason="Aegis anti-nuke removed unauthorized bot")
            except discord.HTTPException as error:
                return "remove_bot", f"Failed to remove added bot: {error}"
            return "remove_bot", "Removed the newly added bot."

        if kind == "webhook_create":
            target_id = event.rollback_hint.get("target_id")
            if not isinstance(target_id, int):
                return None, None

            try:
                webhooks = await guild.webhooks()
            except discord.HTTPException as error:
                return "delete_webhook", f"Failed to load guild webhooks: {error}"

            webhook = discord.utils.get(webhooks, id=target_id)
            if webhook is None:
                return "delete_webhook", "Webhook was already gone before rollback."

            try:
                await webhook.delete(reason="Aegis anti-nuke rollback")
            except discord.HTTPException as error:
                return "delete_webhook", f"Failed to delete webhook: {error}"
            return "delete_webhook", "Deleted the newly created webhook."

        if kind == "role_permissions":
            target_id = event.rollback_hint.get("target_id")
            before_permissions = event.rollback_hint.get("before_permissions")
            role = guild.get_role(target_id) if isinstance(target_id, int) else None
            if role is None or not isinstance(before_permissions, int):
                return "role_permissions", "Role no longer exists or permissions snapshot was missing."

            try:
                await role.edit(
                    permissions=discord.Permissions(before_permissions),
                    reason="Aegis anti-nuke rollback",
                )
            except discord.HTTPException as error:
                return "role_permissions", f"Failed to restore role permissions: {error}"
            return "role_permissions", "Restored the role's previous permissions."

        if kind == "member_roles":
            target_id = event.rollback_hint.get("target_id")
            role_ids = event.rollback_hint.get("role_ids") or []
            if not isinstance(target_id, int):
                return "member_roles", "Target member could not be resolved."

            member = guild.get_member(target_id)
            me = guild.me
            if member is None:
                return "member_roles", "Target member already left before rollback."
            if me is None or member.top_role >= me.top_role:
                return "member_roles", "Target member is above or equal to Aegis in role hierarchy."

            roles_to_remove = [
                role
                for role_id in role_ids
                if isinstance(role_id, int)
                for role in [guild.get_role(role_id)]
                if role is not None and role in member.roles and role < me.top_role
            ]
            if not roles_to_remove:
                return "member_roles", "No dangerous granted roles could be safely removed."

            try:
                await member.remove_roles(*roles_to_remove, reason="Aegis anti-nuke rollback")
            except discord.HTTPException as error:
                return "member_roles", f"Failed to remove dangerous role grant: {error}"
            return "member_roles", "Removed the dangerous granted role(s) from the member."

        return None, None

    async def _record_case(
        self,
        event: NormalizedAntiNukeEvent,
        *,
        action: str,
        reason: str,
        metadata: dict[str, str],
    ) -> None:
        if event.actor_id is None:
            return

        target = event.guild.get_member(event.actor_id) or discord.Object(id=event.actor_id)
        await self.bot.record_case(
            event.guild,
            target,
            self.bot.user,
            action,
            reason,
            metadata=metadata,
        )

    async def _send_incident_log(
        self,
        incident_id: int,
        event: NormalizedAntiNukeEvent,
        *,
        trusted: bool,
        trigger_reason: str,
        response_result: str | None,
        rollback_result: str | None,
        freeze_expires_at: datetime | None,
        mixed_score: int,
        event_count: int,
    ) -> None:
        fields = [
            ("Incident", f"`{incident_id}`"),
            ("Actor", event.actor_name),
            ("Event", EVENT_LABELS[event.event_type]),
            ("Target", event.target_name),
            ("Audit Log ID", f"`{event.audit_entry.id}`"),
            ("Trigger", trigger_reason),
            ("Event Count", str(event_count)),
            ("Mixed Score", str(mixed_score)),
            ("Response", response_result or "None"),
            ("Rollback", rollback_result or "None"),
            ("Snapshots", "Yes" if event.evidence.get("changes") else "No"),
        ]
        if freeze_expires_at is not None:
            fields.append(("Freeze", format_timestamp(freeze_expires_at, "R")))

        await self.bot.send_log(
            event.guild,
            LogType.ANTINUKE,
            "Anti-Nuke Incident",
            "Aegis detected destructive administrative behavior and created an incident.",
            tone="warning" if trusted else "danger",
            fields=fields,
        )

    async def _create_incident(
        self,
        event: NormalizedAntiNukeEvent,
        *,
        settings_mode: AntiNukeMode,
        trusted: bool,
        trigger_reason: str,
        response_action: str | None,
        response_result: str | None,
        rollback_action: str | None,
        rollback_result: str | None,
        freeze_expires_at: datetime | None,
        mixed_score: int,
        event_count: int,
    ) -> int:
        evidence = dict(event.evidence)
        evidence["trigger_reason"] = trigger_reason
        evidence["event_count"] = event_count
        evidence["mixed_score"] = mixed_score

        incident_id = await self.bot.db.add_antinuke_incident(
            event.guild.id,
            actor_id=event.actor_id,
            actor_name=event.actor_name,
            event_type=event.event_type,
            audit_log_id=event.audit_entry.id,
            target_id=event.target_id,
            target_name=event.target_name,
            mode=settings_mode,
            summary=event.summary,
            response_action=response_action,
            response_result=response_result,
            rollback_action=rollback_action,
            rollback_result=rollback_result,
            trusted=trusted,
            freeze_expires_at=freeze_expires_at,
            created_at=utcnow(),
            evidence=evidence,
        )

        await self._send_incident_log(
            incident_id,
            event,
            trusted=trusted,
            trigger_reason=trigger_reason,
            response_result=response_result,
            rollback_result=rollback_result,
            freeze_expires_at=freeze_expires_at,
            mixed_score=mixed_score,
            event_count=event_count,
        )
        return incident_id

    async def _handle_trigger(
        self,
        event: NormalizedAntiNukeEvent,
        *,
        mode: AntiNukeMode,
        trigger_reason: str,
        event_count: int,
        mixed_score: int,
    ) -> None:
        if event.actor_id is None:
            incident_id = await self._create_incident(
                event,
                settings_mode=mode,
                trusted=False,
                trigger_reason="Anti-nuke could not attribute the action to an actor, so it only logged the event.",
                response_action="alert",
                response_result="No punishment applied because actor attribution was missing.",
                rollback_action=None,
                rollback_result=None,
                freeze_expires_at=None,
                mixed_score=mixed_score,
                event_count=event_count,
            )
            await self._record_case(
                event,
                action="antinuke_alert",
                reason="Anti-nuke logged a destructive action with missing actor attribution.",
                metadata={"Incident": str(incident_id), "Event": event.event_type.value},
            )
            return

        if await self.bot.is_antinuke_trusted(event.guild, event.actor):
            await self._create_incident(
                event,
                settings_mode=mode,
                trusted=True,
                trigger_reason=trigger_reason,
                response_action="trusted_bypass",
                response_result="Trusted actor bypassed anti-nuke enforcement.",
                rollback_action=None,
                rollback_result=None,
                freeze_expires_at=None,
                mixed_score=mixed_score,
                event_count=event_count,
            )
            return

        settings = await self.bot.db.fetch_guild_settings(event.guild.id)
        freeze_expires_at = await self.bot.activate_antinuke_freeze(
            event.guild.id,
            minutes=settings.antinuke_freeze_minutes,
        )

        if mode is AntiNukeMode.CONTAIN:
            response_action, response_result = await self._apply_contain(event.guild, event)
            case_action = "antinuke_contain"
        elif mode is AntiNukeMode.BAN:
            response_action, response_result = await self._apply_ban(event.guild, event)
            case_action = "antinuke_ban"
        else:
            response_action, response_result = "alert", "Alert-only mode is enabled. No punishment was applied."
            case_action = "antinuke_alert"

        rollback_action, rollback_result = await self._safe_rollback(event)
        incident_id = await self._create_incident(
            event,
            settings_mode=mode,
            trusted=False,
            trigger_reason=trigger_reason,
            response_action=response_action,
            response_result=response_result,
            rollback_action=rollback_action,
            rollback_result=rollback_result,
            freeze_expires_at=freeze_expires_at,
            mixed_score=mixed_score,
            event_count=event_count,
        )
        await self._record_case(
            event,
            action=case_action,
            reason=f"Anti-nuke triggered: {trigger_reason}",
            metadata={
                "Incident": str(incident_id),
                "Event": event.event_type.value,
                "Response": response_result or "None",
                "Rollback": rollback_result or "None",
            },
        )

    async def _process_audit_entry(self, entry: discord.AuditLogEntry) -> None:
        if not self._mark_seen(entry.guild.id, entry.id):
            return

        settings = await self.bot.db.fetch_guild_settings(entry.guild.id)
        if not settings.antinuke_enabled:
            return

        event = self._normalize_entry(entry)
        if event is None:
            return

        if self.bot.user is not None and event.actor_id == self.bot.user.id:
            return

        if (
            settings.antinuke_canary_enabled
            and event.target_id is not None
            and event.event_type in CANARY_TRIP_EVENTS
        ):
            canary_asset = await self.bot.db.find_antinuke_canary_asset(entry.guild.id, event.target_id)
            if canary_asset is not None:
                event.evidence["canary"] = {
                    "asset_type": canary_asset.asset_type.value,
                    "target_id": canary_asset.target_id,
                    "event_type": event.event_type.value,
                }
                event.summary = (
                    f"Canary trap tripped: {canary_asset.asset_type.value} canary touched "
                    f"by `{event.event_type.value}`."
                )
                await self._handle_trigger(
                    event,
                    mode=settings.antinuke_mode,
                    trigger_reason=(
                        f"Canary {canary_asset.asset_type.value} was touched, so Aegis treated this as a "
                        "high-confidence hostile signal."
                    ),
                    event_count=1,
                    mixed_score=max(MIXED_SCORE_LIMIT, event.weight),
                )

                _, rotation_errors = await self._rotate_canary_assets(
                    entry.guild,
                    reason="Aegis anti-nuke canary re-arm after trigger",
                )
                if rotation_errors:
                    await self.bot.send_log(
                        entry.guild,
                        LogType.ANTINUKE,
                        "Canary Re-Arm Failed",
                        "Aegis handled a canary incident but could not fully re-arm canary assets.",
                        tone="warning",
                        fields=[("Details", "\n".join(rotation_errors[:6]))],
                    )
                return

        thresholds = await self._resolve_thresholds(entry.guild.id)
        threshold = thresholds[event.event_type]
        if not threshold.enabled:
            return

        event_count, mixed_score, trigger_reason = self._register_event(event, threshold)
        if trigger_reason is None:
            return

        await self._handle_trigger(
            event,
            mode=settings.antinuke_mode,
            trigger_reason=trigger_reason,
            event_count=event_count,
            mixed_score=mixed_score,
        )

    async def _reconcile_recent_entries(
        self,
        guild: discord.Guild,
        *,
        actions: tuple[discord.AuditLogAction, ...],
        target_id: int | None = None,
    ) -> None:
        me = guild.me
        if me is None or not me.guild_permissions.view_audit_log:
            return

        cutoff = utcnow().timestamp() - 15
        for action in actions:
            try:
                async for entry in guild.audit_logs(action=action, limit=8):
                    if entry.created_at.timestamp() < cutoff:
                        continue
                    entry_target_id = getattr(entry.target, "id", None)
                    if target_id is not None and entry_target_id != target_id:
                        continue
                    await self._process_audit_entry(entry)
            except discord.HTTPException:
                continue

    def _schedule_reconcile(
        self,
        guild: discord.Guild,
        *,
        actions: tuple[discord.AuditLogAction, ...],
        target_id: int | None = None,
    ) -> None:
        key = (guild.id, ",".join(action.name for action in actions), target_id)
        if key in self._pending_reconciles:
            return
        self._pending_reconciles.add(key)

        async def runner() -> None:
            try:
                await asyncio.sleep(2.0)
                await self._reconcile_recent_entries(guild, actions=actions, target_id=target_id)
            finally:
                self._pending_reconciles.discard(key)

        asyncio.create_task(runner())

    def _degraded_reasons(self, guild: discord.Guild) -> list[str]:
        me = guild.me
        if me is None:
            return ["Aegis could not resolve its server member state."]

        reasons: list[str] = []
        permissions = me.guild_permissions
        if not permissions.view_audit_log:
            reasons.append("Missing View Audit Log.")
        if not permissions.manage_roles:
            reasons.append("Missing Manage Roles.")
        if not permissions.ban_members:
            reasons.append("Missing Ban Members.")
        if not permissions.manage_webhooks:
            reasons.append("Missing Manage Webhooks.")

        dangerous_roles = [
            role
            for role in guild.roles
            if role != guild.default_role
            and not role.managed
            and self.bot.permissions_are_dangerous(role.permissions)
        ]
        if dangerous_roles and any(role.position >= me.top_role.position for role in dangerous_roles):
            reasons.append("At least one dangerous role is above or equal to Aegis in hierarchy.")

        return reasons

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        await self._process_audit_entry(entry)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            self._schedule_reconcile(
                member.guild,
                actions=(discord.AuditLogAction.bot_add,),
                target_id=member.id,
            )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if set(before.roles) != set(after.roles):
            self._schedule_reconcile(
                after.guild,
                actions=(discord.AuditLogAction.member_role_update,),
                target_id=after.id,
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        self._schedule_reconcile(
            channel.guild,
            actions=(discord.AuditLogAction.channel_create,),
            target_id=channel.id,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        self._schedule_reconcile(
            channel.guild,
            actions=(discord.AuditLogAction.channel_delete,),
            target_id=channel.id,
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        self._schedule_reconcile(
            after.guild,
            actions=(discord.AuditLogAction.channel_update,),
            target_id=after.id,
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        self._schedule_reconcile(
            role.guild,
            actions=(discord.AuditLogAction.role_create,),
            target_id=role.id,
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        self._schedule_reconcile(
            role.guild,
            actions=(discord.AuditLogAction.role_delete,),
            target_id=role.id,
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        self._schedule_reconcile(
            after.guild,
            actions=(discord.AuditLogAction.role_update,),
            target_id=after.id,
        )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        self._schedule_reconcile(
            after,
            actions=(discord.AuditLogAction.guild_update,),
            target_id=after.id,
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        self._schedule_reconcile(
            channel.guild,
            actions=(
                discord.AuditLogAction.webhook_create,
                discord.AuditLogAction.webhook_delete,
                discord.AuditLogAction.webhook_update,
            ),
            target_id=None,
        )

    @commands.group(invoke_without_command=True)
    @require_antinuke_control()
    async def antinuke(self, ctx: commands.Context[AegisBot]) -> None:
        await self.antinuke_status(ctx)

    @antinuke.command(name="status")
    @require_antinuke_control()
    async def antinuke_status(self, ctx: commands.Context[AegisBot]) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        thresholds = await self._resolve_thresholds(ctx.guild.id)
        trust_entries = await self.bot.db.list_antinuke_trust_entries(ctx.guild.id)
        canary_assets = await self.bot.db.list_antinuke_canary_assets(ctx.guild.id)
        freeze_until = await self.bot.get_antinuke_freeze_until(ctx.guild.id)
        degraded_reasons = self._degraded_reasons(ctx.guild)

        threshold_lines = [
            f"`{event_type.value}`: {'on' if config.enabled else 'off'} | {config.count}/{config.window_seconds}s"
            for event_type, config in thresholds.items()
        ]

        trust_preview: list[str] = []
        for entry in trust_entries[:8]:
            if entry.subject_type is TrustSubjectType.ROLE:
                role = ctx.guild.get_role(entry.subject_id)
                trust_preview.append(role.mention if role else f"`{entry.subject_id}` (role)")
            else:
                member = ctx.guild.get_member(entry.subject_id)
                user = member or self.bot.get_user(entry.subject_id)
                trust_preview.append(format_identity(user) if user else f"`{entry.subject_id}` (user)")

        health_line = "Degraded" if degraded_reasons else "Ready"
        health_detail = "\n".join(degraded_reasons[:5]) if degraded_reasons else "All required capabilities look available."
        if len(degraded_reasons) > 5:
            health_detail = f"{health_detail}\n...and {len(degraded_reasons) - 5} more."

        canary_by_type = {asset.asset_type: asset for asset in canary_assets}
        canary_lines: list[str] = []
        role_asset = canary_by_type.get(AntiNukeCanaryAssetType.ROLE)
        channel_asset = canary_by_type.get(AntiNukeCanaryAssetType.CHANNEL)
        webhook_asset = canary_by_type.get(AntiNukeCanaryAssetType.WEBHOOK)

        if role_asset is not None:
            role = ctx.guild.get_role(role_asset.target_id)
            canary_lines.append(
                f"Role: {role.mention if role else f'`{role_asset.target_id}` (missing)'}"
            )
        else:
            canary_lines.append("Role: missing")

        if channel_asset is not None:
            channel = ctx.guild.get_channel(channel_asset.target_id)
            canary_lines.append(
                f"Channel: {channel.mention if channel else f'`{channel_asset.target_id}` (missing)'}"
            )
        else:
            canary_lines.append("Channel: missing")

        if webhook_asset is not None:
            canary_lines.append(f"Webhook: `{webhook_asset.target_id}`")
        else:
            canary_lines.append("Webhook: missing")

        canary_ready = len(canary_assets) == 3
        canary_state = "Enabled (armed)" if settings.antinuke_canary_enabled and canary_ready else "Enabled (degraded)"
        if not settings.antinuke_canary_enabled:
            canary_state = "Disabled"

        await ctx.send(
            view=build_panel(
                "Anti-Nuke Status",
                "Current anti-nuke readiness, trust, freeze state, and thresholds.",
                tone="warning" if degraded_reasons else "success",
                fields=[
                    ("Enabled", "Yes" if settings.antinuke_enabled else "No"),
                    ("Mode", f"`{settings.antinuke_mode.value}`"),
                    ("Freeze", format_timestamp(freeze_until, "R") if freeze_until else "Inactive"),
                    ("Freeze Duration", f"{settings.antinuke_freeze_minutes} minute(s)"),
                    ("Log Channel", self._describe_log_channel(ctx.guild, settings.antinuke_log_channel_id)),
                    ("Health", health_line),
                    ("Health Detail", health_detail),
                    ("Canary Trap", canary_state),
                    ("Canary Assets", "\n".join(canary_lines)),
                    ("Trusted Entries", "\n".join(trust_preview) if trust_preview else "Owner only"),
                    ("Thresholds", "\n".join(threshold_lines)),
                ],
            )
        )

    @antinuke.command(name="enable")
    @require_antinuke_control()
    async def antinuke_enable(self, ctx: commands.Context[AegisBot]) -> None:
        await self.bot.db.update_guild_settings(ctx.guild.id, antinuke_enabled=1)
        await ctx.send(
            view=build_panel(
                "Anti-Nuke Enabled",
                "Aegis will now monitor destructive administrative actions in real time.",
                tone="success",
            )
        )

    @antinuke.command(name="disable")
    @require_antinuke_control()
    async def antinuke_disable(self, ctx: commands.Context[AegisBot]) -> None:
        await self.bot.db.update_guild_settings(ctx.guild.id, antinuke_enabled=0)
        await ctx.send(
            view=build_panel(
                "Anti-Nuke Disabled",
                "Aegis stopped anti-nuke enforcement for this server.",
                tone="warning",
            )
        )

    @antinuke.command(name="mode")
    @require_antinuke_control()
    async def antinuke_mode(self, ctx: commands.Context[AegisBot], mode: str) -> None:
        normalized = mode.strip().lower()
        try:
            antinuke_mode = AntiNukeMode(normalized)
        except ValueError as error:
            raise commands.BadArgument("Mode must be `contain`, `ban`, or `alert`.") from error

        await self.bot.db.update_guild_settings(ctx.guild.id, antinuke_mode=antinuke_mode)
        await ctx.send(
            view=build_panel(
                "Anti-Nuke Mode Updated",
                "Aegis saved the new anti-nuke response mode.",
                tone="success",
                fields=[("Mode", f"`{antinuke_mode.value}`")],
            )
        )

    @antinuke.command(name="log")
    @require_antinuke_control()
    async def antinuke_log(self, ctx: commands.Context[AegisBot], *, target: str | None = None) -> None:
        if target is None:
            if isinstance(ctx.channel, discord.TextChannel):
                channel = ctx.channel
            else:
                raise commands.BadArgument("Run this in a text channel or pass a `#channel` explicitly.")
        elif target.lower() == "off":
            channel = None
        else:
            channel = await commands.TextChannelConverter().convert(ctx, target)

        await self.bot.db.update_guild_settings(
            ctx.guild.id,
            antinuke_log_channel_id=channel.id if channel else None,
        )
        await ctx.send(
            view=build_panel(
                "Anti-Nuke Log Updated",
                "Aegis saved the anti-nuke log destination.",
                tone="success",
                fields=[("Channel", channel.mention if channel else "Inherited fallback")],
            )
        )

    @antinuke.group(name="canary", invoke_without_command=True)
    @require_antinuke_control()
    async def antinuke_canary(self, ctx: commands.Context[AegisBot]) -> None:
        await self.antinuke_canary_status(ctx)

    @antinuke_canary.command(name="status")
    @require_antinuke_control()
    async def antinuke_canary_status(self, ctx: commands.Context[AegisBot]) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        assets = await self.bot.db.list_antinuke_canary_assets(ctx.guild.id)
        capability_gaps = self._canary_capability_gaps(ctx.guild)

        assets_by_type = {asset.asset_type: asset for asset in assets}
        role_asset = assets_by_type.get(AntiNukeCanaryAssetType.ROLE)
        channel_asset = assets_by_type.get(AntiNukeCanaryAssetType.CHANNEL)
        webhook_asset = assets_by_type.get(AntiNukeCanaryAssetType.WEBHOOK)

        role_line = "missing"
        if role_asset is not None:
            role = ctx.guild.get_role(role_asset.target_id)
            role_line = role.mention if role else f"`{role_asset.target_id}` (missing)"

        channel_line = "missing"
        if channel_asset is not None:
            channel = ctx.guild.get_channel(channel_asset.target_id)
            channel_line = channel.mention if channel else f"`{channel_asset.target_id}` (missing)"

        webhook_line = f"`{webhook_asset.target_id}`" if webhook_asset is not None else "missing"
        armed = len(assets_by_type) == 3
        status_line = "Enabled (armed)" if settings.antinuke_canary_enabled and armed else "Enabled (degraded)"
        if not settings.antinuke_canary_enabled:
            status_line = "Disabled"

        created_at = None
        if assets:
            created_at = min(datetime.fromisoformat(asset.created_at) for asset in assets)

        await ctx.send(
            view=build_panel(
                "Anti-Nuke Canary",
                "Canary trap state and decoy asset health.",
                tone="success" if settings.antinuke_canary_enabled and armed else "warning",
                fields=[
                    ("Status", status_line),
                    ("Anti-Nuke Enabled", "Yes" if settings.antinuke_enabled else "No"),
                    ("Role Canary", role_line),
                    ("Channel Canary", channel_line),
                    ("Webhook Canary", webhook_line),
                    ("Last Armed", format_timestamp(created_at, "R") if created_at else "Not armed"),
                    (
                        "Capability Gaps",
                        "\n".join(capability_gaps) if capability_gaps else "All required permissions available.",
                    ),
                ],
            )
        )

    @antinuke_canary.command(name="enable")
    @require_antinuke_control()
    async def antinuke_canary_enable(self, ctx: commands.Context[AegisBot]) -> None:
        notes, errors = await self._rotate_canary_assets(
            ctx.guild,
            reason="Aegis anti-nuke canary enable",
        )
        if errors:
            await self.bot.db.update_guild_settings(ctx.guild.id, antinuke_canary_enabled=0)
            await ctx.send(
                view=build_panel(
                    "Canary Enable Failed",
                    "Aegis could not fully provision canary trap assets.",
                    tone="danger",
                    fields=[("Errors", "\n".join(errors[:8]))],
                )
            )
            return

        await self.bot.db.update_guild_settings(ctx.guild.id, antinuke_canary_enabled=1)
        await ctx.send(
            view=build_panel(
                "Canary Trap Enabled",
                "Aegis armed decoy assets and will treat any canary touch as a high-confidence hostile signal.",
                tone="success",
                fields=[("Assets", "\n".join(notes))],
            )
        )

    @antinuke_canary.command(name="disable")
    @require_antinuke_control()
    async def antinuke_canary_disable(self, ctx: commands.Context[AegisBot]) -> None:
        assets = await self.bot.db.list_antinuke_canary_assets(ctx.guild.id)
        notes, errors = await self._delete_canary_assets(
            ctx.guild,
            assets,
            reason="Aegis anti-nuke canary disable",
        )
        await self.bot.db.clear_antinuke_canary_assets(ctx.guild.id)
        await self.bot.db.update_guild_settings(ctx.guild.id, antinuke_canary_enabled=0)

        tone = "success" if not errors else "warning"
        fields: list[tuple[str, str]] = []
        if notes:
            fields.append(("Cleanup", "\n".join(notes[:8])))
        if errors:
            fields.append(("Errors", "\n".join(errors[:8])))

        await ctx.send(
            view=build_panel(
                "Canary Trap Disabled",
                "Aegis disabled canary enforcement for this server.",
                tone=tone,
                fields=fields,
            )
        )

    @antinuke_canary.command(name="rotate")
    @require_antinuke_control()
    async def antinuke_canary_rotate(self, ctx: commands.Context[AegisBot]) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        if not settings.antinuke_canary_enabled:
            raise commands.BadArgument("Canary trap is disabled. Run `^antinuke canary enable` first.")

        notes, errors = await self._rotate_canary_assets(
            ctx.guild,
            reason="Aegis anti-nuke canary rotate",
        )
        if errors:
            await ctx.send(
                view=build_panel(
                    "Canary Rotate Incomplete",
                    "Aegis rotated canary assets with warnings.",
                    tone="warning",
                    fields=[
                        ("Details", "\n".join(notes[:6])) if notes else ("Details", "No cleanup details."),
                        ("Errors", "\n".join(errors[:8])),
                    ],
                )
            )
            return

        await ctx.send(
            view=build_panel(
                "Canary Trap Rotated",
                "Aegis replaced all canary assets with fresh decoys.",
                tone="success",
                fields=[("Assets", "\n".join(notes))],
            )
        )

    @antinuke.group(name="trust", invoke_without_command=True)
    @require_antinuke_control(owner_only=True)
    async def antinuke_trust(self, ctx: commands.Context[AegisBot]) -> None:
        entries = await self.bot.db.list_antinuke_trust_entries(ctx.guild.id)
        lines: list[str] = []
        for entry in entries[:10]:
            if entry.subject_type is TrustSubjectType.ROLE:
                role = ctx.guild.get_role(entry.subject_id)
                lines.append(role.mention if role else f"`{entry.subject_id}` (role)")
            else:
                member = ctx.guild.get_member(entry.subject_id)
                user = member or self.bot.get_user(entry.subject_id)
                lines.append(format_identity(user) if user else f"`{entry.subject_id}` (user)")

        await ctx.send(
            view=build_panel(
                "Anti-Nuke Trust",
                "Trusted users and roles bypass anti-nuke enforcement.",
                tone="info",
                fields=[("Entries", "\n".join(lines) if lines else "Owner only")],
            )
        )

    @antinuke_trust.command(name="add")
    @require_antinuke_control(owner_only=True)
    async def antinuke_trust_add(self, ctx: commands.Context[AegisBot], *, target: str) -> None:
        subject, subject_type = await self._resolve_trust_subject(ctx, target)
        await self.bot.db.add_antinuke_trust_entry(ctx.guild.id, subject.id, subject_type)
        await ctx.send(
            view=build_panel(
                "Trusted Entry Added",
                "Aegis will bypass anti-nuke enforcement for this subject.",
                tone="success",
                fields=[
                    ("Target", format_identity(subject)),
                    ("Type", subject_type.value),
                ],
            )
        )

    @antinuke_trust.command(name="remove")
    @require_antinuke_control(owner_only=True)
    async def antinuke_trust_remove(self, ctx: commands.Context[AegisBot], *, target: str) -> None:
        subject, subject_type = await self._resolve_trust_subject(ctx, target)
        removed = await self.bot.db.remove_antinuke_trust_entry(ctx.guild.id, subject.id, subject_type)
        if not removed:
            raise commands.BadArgument("That target is not currently in the anti-nuke trust list.")

        await ctx.send(
            view=build_panel(
                "Trusted Entry Removed",
                "Aegis removed the anti-nuke trust bypass for this subject.",
                tone="success",
                fields=[
                    ("Target", format_identity(subject)),
                    ("Type", subject_type.value),
                ],
            )
        )

    @antinuke.command(name="threshold")
    @require_antinuke_control()
    async def antinuke_threshold(
        self,
        ctx: commands.Context[AegisBot],
        event_name: str,
        count: int,
        seconds: int,
    ) -> None:
        if count < 1:
            raise commands.BadArgument("Threshold count must be at least 1.")
        if seconds < 1:
            raise commands.BadArgument("Threshold window must be at least 1 second.")

        event_type = self._parse_event_type(event_name)
        current = (await self._resolve_thresholds(ctx.guild.id))[event_type]
        await self.bot.db.upsert_antinuke_threshold(
            ctx.guild.id,
            event_type,
            count=count,
            window_seconds=seconds,
            enabled=current.enabled,
        )
        await ctx.send(
            view=build_panel(
                "Threshold Updated",
                "Aegis saved the anti-nuke threshold override.",
                tone="success",
                fields=[
                    ("Event", f"`{event_type.value}`"),
                    ("Threshold", f"{count} in {seconds}s"),
                    ("Enabled", "Yes" if current.enabled else "No"),
                ],
            )
        )

    @antinuke.command(name="protect")
    @require_antinuke_control()
    async def antinuke_protect(
        self,
        ctx: commands.Context[AegisBot],
        event_name: str,
        state: str,
    ) -> None:
        normalized = state.strip().lower()
        if normalized not in {"on", "off"}:
            raise commands.BadArgument("Protection state must be `on` or `off`.")

        event_type = self._parse_event_type(event_name)
        current = (await self._resolve_thresholds(ctx.guild.id))[event_type]
        enabled = normalized == "on"
        await self.bot.db.upsert_antinuke_threshold(
            ctx.guild.id,
            event_type,
            count=current.count,
            window_seconds=current.window_seconds,
            enabled=enabled,
        )
        await ctx.send(
            view=build_panel(
                "Protection Updated",
                "Aegis saved the anti-nuke protection toggle.",
                tone="success",
                fields=[
                    ("Event", f"`{event_type.value}`"),
                    ("Enabled", "Yes" if enabled else "No"),
                ],
            )
        )

    @antinuke.command(name="incidents")
    @require_antinuke_control()
    async def antinuke_incidents(
        self,
        ctx: commands.Context[AegisBot],
        limit: int = 5,
    ) -> None:
        limit = max(1, min(limit, 10))
        incidents = await self.bot.db.list_antinuke_incidents(ctx.guild.id, limit=limit)

        lines: list[str] = []
        for incident in incidents:
            created_at = datetime.fromisoformat(incident.created_at)
            freeze_text = ""
            if incident.freeze_expires_at:
                freeze_text = f" | freeze {format_timestamp(datetime.fromisoformat(incident.freeze_expires_at), 'R')}"
            lines.append(
                f"`{incident.incident_id}` {EVENT_LABELS[incident.event_type]} | "
                f"{incident.actor_name or 'Unknown actor'} | "
                f"{format_timestamp(created_at, 'R')} | "
                f"{incident.response_result or 'No response'}{freeze_text}"
            )

        await ctx.send(
            view=build_panel(
                "Anti-Nuke Incidents",
                "Recent anti-nuke incidents recorded for this server.",
                tone="info",
                fields=[("Incidents", "\n".join(lines) if lines else "No incidents recorded yet.")],
            )
        )

    @antinuke.command(name="resetfreeze")
    @require_antinuke_control()
    async def antinuke_resetfreeze(self, ctx: commands.Context[AegisBot]) -> None:
        cleared = await self.bot.clear_antinuke_freeze(ctx.guild.id)
        await ctx.send(
            view=build_panel(
                "Emergency Freeze Reset",
                "Aegis cleared the active anti-nuke freeze window." if cleared else "No active anti-nuke freeze was set.",
                tone="success" if cleared else "info",
            )
        )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(AntiNukeCog(bot))
