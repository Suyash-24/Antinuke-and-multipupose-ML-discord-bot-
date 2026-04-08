from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import discord
from discord.ext import commands, tasks

from aegis.config import AppConfig
from aegis.db import Database
from aegis.models import LogType, PunishmentAction, TrustSubjectType
from aegis.ui import build_panel
from aegis.utils import (
    format_identity,
    format_timestamp,
    normalize_message_content,
    truncate,
    utcnow,
)


@dataclass(slots=True)
class MessageLogSnapshot:
    guild_id: int
    channel_id: int
    author_id: int
    author_display: str
    content: str


class AegisBot(commands.Bot):
    HIGH_RISK_COMMANDS = frozenset({"kick", "ban", "softban", "silentban", "clean", "voicemove"})
    HIGH_RISK_MULTI_TARGET_CAP = 3
    HIGH_RISK_CLEAN_CAP = 100
    HIGH_RISK_RATE_WINDOW_SECONDS = 20
    HIGH_RISK_RATE_LIMIT_UNITS = 6
    PRESENCE_REFRESH_MINUTES = 2
    DANGEROUS_PERMISSION_NAMES = (
        "administrator",
        "manage_guild",
        "manage_roles",
        "manage_channels",
        "manage_webhooks",
        "kick_members",
        "ban_members",
        "moderate_members",
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.db = Database(config.database_path)
        self.guild_prefix_cache: dict[int, str] = {}

        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.bans = True
        intents.messages = True
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix=self.resolve_prefix,
            intents=intents,
            help_command=None,
            max_messages=5000,
            allowed_mentions=discord.AllowedMentions.none(),
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="Aegis Security Grid",
                details="Invite to Join",
                state="Shield Network",
            ),
        )
        self.message_cache: dict[tuple[int, int], deque[tuple[str, datetime]]] = defaultdict(
            lambda: deque(maxlen=20)
        )
        self.message_log_snapshots: dict[int, MessageLogSnapshot] = {}
        self.message_log_snapshot_order: deque[int] = deque()
        self.message_log_snapshot_limit = 5000
        self.join_cache: dict[int, deque[datetime]] = defaultdict(lambda: deque(maxlen=50))
        self.voicemove_sessions: dict[int, dict] = {}
        self.antinuke_freezes: dict[int, datetime] = {}
        self.high_risk_command_usage: dict[tuple[int, int], deque[tuple[datetime, int]]] = defaultdict(deque)
        self.presence_started_at_ms = int(utcnow().timestamp() * 1000)

    async def resolve_prefix(
        self,
        bot: commands.Bot,
        message: discord.Message,
    ) -> list[str]:
        prefix = self.config.prefix
        if message.guild is not None and self.db.connection is not None:
            prefix = await self.get_guild_prefix(message.guild.id)
        return commands.when_mentioned_or(prefix)(bot, message)

    async def get_guild_prefix(self, guild_id: int) -> str:
        cached = self.guild_prefix_cache.get(guild_id)
        if cached is not None:
            return cached

        settings = await self.db.fetch_guild_settings(guild_id)
        prefix = settings.prefix or self.config.prefix
        self.guild_prefix_cache[guild_id] = prefix
        return prefix

    def set_guild_prefix(self, guild_id: int, prefix: str) -> None:
        self.guild_prefix_cache[guild_id] = prefix

    def _build_invite_url(self) -> str | None:
        if self.config.client_id is None:
            return None

        permissions = discord.Permissions(
            view_audit_log=True,
            manage_guild=True,
            manage_roles=True,
            manage_channels=True,
            manage_webhooks=True,
            manage_messages=True,
            kick_members=True,
            ban_members=True,
            moderate_members=True,
            read_message_history=True,
            send_messages=True,
            move_members=True,
        )
        return discord.utils.oauth_url(self.config.client_id, permissions=permissions)

    def _build_rich_presence(self) -> discord.Activity:
        guild_count = len(self.guilds)
        party_current = max(1, min(guild_count, 6))
        party_max = 6 if guild_count <= 6 else min(guild_count, 99)
        server_text = f"{guild_count} server" if guild_count == 1 else f"{guild_count} servers"

        payload: dict[str, Any] = {
            "type": discord.ActivityType.competing,
            "name": "Aura Shield Mode",
            "details": "Main Character Security",
            "state": f"Vibes protected in {server_text}",
            "timestamps": {"start": self.presence_started_at_ms},
            "party": {
                "id": "aegis-guard-network",
                "size": [party_current, party_max],
            },
        }

        if self.config.client_id is not None:
            payload["application_id"] = self.config.client_id

        invite_url = self._build_invite_url()
        if invite_url is not None:
            payload["details_url"] = invite_url
        if self.config.docs_base_url:
            payload["state_url"] = self.config.docs_base_url

        assets: dict[str, str] = {}
        if self.config.presence_large_image:
            assets["large_image"] = self.config.presence_large_image
        if self.config.presence_large_text:
            assets["large_text"] = self.config.presence_large_text
        if self.config.presence_small_image:
            assets["small_image"] = self.config.presence_small_image
        if self.config.presence_small_text:
            assets["small_text"] = self.config.presence_small_text
        if assets:
            payload["assets"] = assets

        return discord.Activity(**payload)

    async def refresh_presence(self) -> None:
        activity = self._build_rich_presence()
        try:
            await self.change_presence(status=discord.Status.online, activity=activity)
        except discord.HTTPException:
            return

    async def setup_hook(self) -> None:
        await self.db.connect()
        for extension in (
            "aegis.cogs.general",
            "aegis.cogs.help",
            "aegis.cogs.settings",
            "aegis.cogs.moderation",
            "aegis.cogs.automod",
            "aegis.cogs.antinuke",
            "aegis.cogs.events",
        ):
            await self.load_extension(extension)
        self.scheduler.start()
        self.presence_updater.start()

    async def close(self) -> None:
        if self.scheduler.is_running():
            self.scheduler.cancel()
        if self.presence_updater.is_running():
            self.presence_updater.cancel()
        await self.db.close()
        await super().close()

    async def notify_user(
        self,
        target: discord.abc.Messageable,
        title: str,
        description: str,
        *,
        tone: str = "info",
        fields: list[tuple[str, str]] | None = None,
    ) -> None:
        try:
            await target.send(
                view=build_panel(
                    title,
                    description,
                    tone=tone,
                    fields=fields or [],
                )
            )
        except discord.HTTPException:
            return

    async def send_log(
        self,
        guild: discord.Guild,
        log_type: LogType,
        title: str,
        description: str,
        *,
        tone: str = "info",
        fields: list[tuple[str, str]] | None = None,
        actions: list[tuple[str, str]] | None = None,
        files: list[discord.File] | None = None,
        include_timestamp: bool = True,
        return_message: bool = False,
    ) -> discord.Message | None:
        settings = await self.db.fetch_guild_settings(guild.id)
        channel_id = getattr(settings, log_type.value)
        if channel_id is None and log_type is LogType.ANTINUKE:
            channel_id = settings.mod_log_channel_id or settings.server_log_channel_id
        if channel_id is None:
            return None

        channel = guild.get_channel_or_thread(channel_id)
        if channel is None:
            return None

        payload_fields = list(fields or [])
        if include_timestamp:
            payload_fields.append(("Timestamp", format_timestamp(utcnow())))

        try:
            sent_message = await channel.send(
                view=build_panel(
                    title,
                    description,
                    tone=tone,
                    fields=payload_fields,
                    actions=actions or [],
                ),
                files=files or [],
            )
        except discord.HTTPException:
            return None

        if return_message:
            return sent_message
        return None

    async def record_case(
        self,
        guild: discord.Guild,
        target: discord.abc.Snowflake,
        moderator: discord.abc.Snowflake | None,
        action: str,
        reason: str,
        *,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        case_id = await self.db.add_case(
            guild.id,
            target.id,
            moderator.id if moderator else None,
            action,
            reason,
            utcnow(),
            expires_at=expires_at,
            metadata=metadata,
        )

        fields = [
            ("Target", format_identity(target)),
            ("Moderator", format_identity(moderator)),
            ("Reason", truncate(reason)),
        ]
        if expires_at is not None:
            fields.append(("Expires", format_timestamp(expires_at, "R")))
        if metadata:
            for key, value in metadata.items():
                fields.append((key, str(value)))

        tone_map = {
            "warn": "warning",
            "strike": "warning",
            "mute": "warning",
            "unmute": "success",
            "kick": "danger",
            "ban": "danger",
            "softban": "danger",
            "silentban": "danger",
            "unban": "success",
            "pardon": "success",
            "antinuke_alert": "danger",
            "antinuke_contain": "danger",
            "antinuke_ban": "danger",
            "antinuke_rollback": "warning",
        }

        await self.send_log(
            guild,
            LogType.MOD,
            f"Case #{case_id} - {action.title()}",
            f"Aegis recorded a `{action}` action.",
            tone=tone_map.get(action, "info"),
            fields=fields,
        )
        return case_id

    @staticmethod
    def permissions_are_dangerous(permissions: discord.Permissions) -> bool:
        return any(getattr(permissions, name, False) for name in AegisBot.DANGEROUS_PERMISSION_NAMES)

    async def is_antinuke_trusted(
        self,
        guild: discord.Guild,
        subject: discord.abc.Snowflake | None,
    ) -> bool:
        if subject is None:
            return False

        if self.user is not None and subject.id == self.user.id:
            return True

        if subject.id == guild.owner_id:
            return True

        entries = await self.db.list_antinuke_trust_entries(guild.id)
        trusted_users = {
            entry.subject_id for entry in entries if entry.subject_type is TrustSubjectType.USER
        }
        if subject.id in trusted_users:
            return True

        if isinstance(subject, discord.Member):
            trusted_roles = {
                entry.subject_id for entry in entries if entry.subject_type is TrustSubjectType.ROLE
            }
            if any(role.id in trusted_roles for role in subject.roles):
                return True

        return False

    async def get_antinuke_freeze_until(self, guild_id: int) -> datetime | None:
        cached = self.antinuke_freezes.get(guild_id)
        now = utcnow()
        if cached is not None:
            if cached > now:
                return cached
            self.antinuke_freezes.pop(guild_id, None)

        active = await self.db.get_active_antinuke_freeze(guild_id, now=now)
        if active is not None and active > now:
            self.antinuke_freezes[guild_id] = active
            return active
        return None

    async def activate_antinuke_freeze(self, guild_id: int, *, minutes: int) -> datetime:
        expires_at = utcnow() + timedelta(minutes=max(minutes, 1))
        self.antinuke_freezes[guild_id] = expires_at
        return expires_at

    async def clear_antinuke_freeze(self, guild_id: int) -> bool:
        self.antinuke_freezes.pop(guild_id, None)
        return await self.db.clear_active_antinuke_freeze(guild_id, now=utcnow())

    async def enforce_high_risk_command_policy(
        self,
        ctx: commands.Context["AegisBot"],
        *,
        target_count: int | None = None,
        clean_amount: int | None = None,
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member) or ctx.command is None:
            return

        command_name = ctx.command.qualified_name.split()[0].lower()
        if command_name not in self.HIGH_RISK_COMMANDS:
            return

        if await self.is_antinuke_trusted(ctx.guild, ctx.author):
            return

        freeze_until = await self.get_antinuke_freeze_until(ctx.guild.id)
        if freeze_until is not None:
            raise commands.CheckFailure(
                "Emergency freeze is active. Only the server owner and anti-nuke trusted entries can use high-risk commands right now."
            )

        if command_name in {"kick", "ban", "softban", "silentban"}:
            count = max(target_count or 0, 0)
            if count > self.HIGH_RISK_MULTI_TARGET_CAP:
                raise commands.BadArgument(
                    f"Non-trusted staff can target at most {self.HIGH_RISK_MULTI_TARGET_CAP} users per high-risk command."
                )

        if command_name == "clean" and clean_amount is not None and clean_amount > self.HIGH_RISK_CLEAN_CAP:
            raise commands.BadArgument(
                f"Non-trusted staff can clean at most {self.HIGH_RISK_CLEAN_CAP} messages per command."
            )

        if command_name == "clean":
            units = 1
        elif command_name == "voicemove":
            units = 1
        else:
            units = max(target_count or 1, 1)

        now = utcnow()
        usage_key = (ctx.guild.id, ctx.author.id)
        queue = self.high_risk_command_usage[usage_key]

        while queue and (now - queue[0][0]).total_seconds() > self.HIGH_RISK_RATE_WINDOW_SECONDS:
            queue.popleft()

        used_units = sum(cost for _, cost in queue)
        if used_units + units > self.HIGH_RISK_RATE_LIMIT_UNITS:
            raise commands.CheckFailure(
                "High-risk moderation rate limit reached for this moderator. Pause for a moment before using more destructive commands."
            )

        queue.append((now, units))

    async def apply_strikes(
        self,
        guild: discord.Guild,
        target: discord.User | discord.Member,
        amount: int,
        reason: str,
        *,
        moderator: discord.abc.Snowflake | None,
        source: str,
    ) -> tuple[int, int]:
        old_total, new_total = await self.db.change_strikes(guild.id, target.id, amount)
        metadata = {
            "Change": f"{amount:+d}",
            "Total": str(new_total),
            "Source": source,
        }
        action = "strike" if amount > 0 else "pardon"
        await self.record_case(guild, target, moderator, action, reason, metadata=metadata)

        if amount > 0:
            await self.notify_user(
                target,
                "Strikes Added",
                f"You now have **{new_total}** strike(s) in **{guild.name}**.",
                tone="warning",
                fields=[("Reason", reason), ("Source", source)],
            )
            await self.enforce_strike_punishment(guild, target, old_total, new_total)
        else:
            await self.notify_user(
                target,
                "Strike Pardon",
                f"Your active strike total in **{guild.name}** is now **{new_total}**.",
                tone="success",
                fields=[("Reason", reason), ("Source", source)],
            )

        return old_total, new_total

    async def enforce_strike_punishment(
        self,
        guild: discord.Guild,
        target: discord.User | discord.Member,
        old_total: int,
        new_total: int,
    ) -> None:
        punishments = await self.db.get_punishments(guild.id)
        reached = [config for threshold, config in punishments.items() if old_total < threshold <= new_total]
        if not reached:
            return

        actionable = [config for config in reached if config.action is not PunishmentAction.NONE]
        if not actionable:
            return

        def _pick_most_severe(configs: list) -> PunishmentConfig:
            return max(
                configs,
                key=lambda item: (
                    item.duration_seconds is None,
                    item.duration_seconds or 0,
                    item.strike_count,
                ),
            )

        warn_configs = [cfg for cfg in actionable if cfg.action is PunishmentAction.WARN]
        mute_configs = [cfg for cfg in actionable if cfg.action is PunishmentAction.MUTE]
        kick_configs = [cfg for cfg in actionable if cfg.action is PunishmentAction.KICK]
        softban_configs = [cfg for cfg in actionable if cfg.action is PunishmentAction.SOFTBAN]
        ban_configs = [
            cfg
            for cfg in actionable
            if cfg.action in {PunishmentAction.BAN, PunishmentAction.SILENTBAN}
        ]

        selected: PunishmentConfig
        if ban_configs:
            selected = _pick_most_severe(ban_configs)
        elif softban_configs:
            selected = _pick_most_severe(softban_configs)
        elif kick_configs:
            selected = _pick_most_severe(kick_configs)
        elif mute_configs:
            selected = _pick_most_severe(mute_configs)
        else:
            selected = _pick_most_severe(warn_configs)

        action_reason = f"Strike threshold reached at {selected.strike_count} strike(s)."
        expires_at = (
            utcnow() + timedelta(seconds=selected.duration_seconds)
            if selected.duration_seconds
            else None
        )

        if selected.action is PunishmentAction.WARN:
            await self.notify_user(
                target,
                "Automatic Warning",
                f"Aegis triggered the **{selected.strike_count} strike** warning threshold in **{guild.name}**.",
                tone="warning",
                fields=[("Threshold", str(selected.strike_count))],
            )
            await self.record_case(
                guild,
                target,
                self.user,
                "warn",
                action_reason,
                metadata={"Threshold": str(selected.strike_count)},
            )
            return

        member = guild.get_member(target.id)
        settings = await self.db.fetch_guild_settings(guild.id)

        if selected.action is PunishmentAction.MUTE:
            muted_role = guild.get_role(settings.muted_role_id or 0) if settings.muted_role_id else None
            if member is None or muted_role is None:
                await self.send_log(
                    guild,
                    LogType.MOD,
                    "Auto punishment skipped",
                    "Aegis could not apply the configured mute threshold.",
                    tone="danger",
                    fields=[
                        ("Target", format_identity(target)),
                        ("Reason", "Muted role is missing or the member already left."),
                    ],
                )
                return

            await member.add_roles(muted_role, reason=action_reason)
            case_id = await self.record_case(
                guild,
                target,
                self.user,
                "mute",
                action_reason,
                expires_at=expires_at,
                metadata={"Threshold": str(selected.strike_count)},
            )
            if expires_at:
                await self.db.schedule_action(guild.id, target.id, "unmute", expires_at, case_id)
            return

        if selected.action is PunishmentAction.KICK:
            if member is None:
                return
            await member.kick(reason=action_reason)
            await self.record_case(
                guild,
                target,
                self.user,
                "kick",
                action_reason,
                metadata={"Threshold": str(selected.strike_count)},
            )
            return

        if selected.action in {PunishmentAction.BAN, PunishmentAction.SILENTBAN}:
            delete_window = 0 if selected.action is PunishmentAction.SILENTBAN else 86400
            await guild.ban(target, delete_message_seconds=delete_window, reason=action_reason)
            case_id = await self.record_case(
                guild,
                target,
                self.user,
                selected.action.value,
                action_reason,
                expires_at=expires_at,
                metadata={"Threshold": str(selected.strike_count)},
            )
            if expires_at:
                await self.db.schedule_action(guild.id, target.id, "unban", expires_at, case_id)
            return

        if selected.action is PunishmentAction.SOFTBAN:
            if member is None:
                return
            await guild.ban(target, delete_message_seconds=86400, reason=action_reason)
            await guild.unban(target, reason="Aegis softban completion.")
            await self.record_case(
                guild,
                target,
                self.user,
                "softban",
                action_reason,
                metadata={"Threshold": str(selected.strike_count)},
            )

    async def toggle_raid_mode(
        self,
        guild: discord.Guild,
        enabled: bool,
        *,
        reason: str,
        moderator: discord.abc.Snowflake | None = None,
        automatic: bool = False,
    ) -> None:
        settings = await self.db.fetch_guild_settings(guild.id)
        if settings.raid_mode_enabled == enabled:
            return

        if enabled:
            previous_level = int(guild.verification_level)
            try:
                if guild.verification_level < discord.VerificationLevel.highest:
                    await guild.edit(
                        verification_level=discord.VerificationLevel.highest,
                        reason=f"Aegis raid mode enabled | {reason}",
                    )
            except discord.HTTPException:
                pass

            await self.db.update_guild_settings(
                guild.id,
                raid_mode_enabled=1,
                raid_mode_previous_verification=previous_level,
            )
            await self.send_log(
                guild,
                LogType.SERVER,
                "Raid Mode Enabled",
                "New joins are now treated as suspicious until staff disables raid mode.",
                tone="danger",
                fields=[
                    ("Reason", reason),
                    ("Activated By", "Automatic detection" if automatic else format_identity(moderator)),
                ],
            )
            return

        previous_level = settings.raid_mode_previous_verification
        if previous_level is not None:
            try:
                await guild.edit(
                    verification_level=discord.VerificationLevel(previous_level),
                    reason=f"Aegis raid mode disabled | {reason}",
                )
            except discord.HTTPException:
                pass

        await self.db.update_guild_settings(
            guild.id,
            raid_mode_enabled=0,
            raid_mode_previous_verification=None,
        )
        await self.send_log(
            guild,
            LogType.SERVER,
            "Raid Mode Disabled",
            "Aegis has reopened normal joins for the server.",
            tone="success",
            fields=[
                ("Reason", reason),
                ("Disabled By", format_identity(moderator)),
            ],
        )

    async def is_automod_exempt(
        self,
        member: discord.Member,
        channel: discord.abc.GuildChannel | discord.Thread,
    ) -> bool:
        permissions = member.guild_permissions
        if member.bot:
            return True

        if permissions.administrator or permissions.manage_guild:
            return True

        if permissions.kick_members or permissions.ban_members:
            return True

        me = member.guild.me
        if me is not None and member.id != member.guild.owner_id and member.top_role >= me.top_role:
            return True

        ignored = await self.db.list_ignored_targets(member.guild.id)
        ignored_channels = {row["target_id"] for row in ignored if row["target_type"] == "channel"}
        ignored_roles = {row["target_id"] for row in ignored if row["target_type"] == "role"}

        if channel.id in ignored_channels:
            return True
        if getattr(channel, "category_id", None) in ignored_channels:
            return True
        if getattr(channel, "parent_id", None) in ignored_channels:
            return True
        if any(role.id in ignored_roles for role in member.roles):
            return True
        return False

    def register_duplicate_message(self, message: discord.Message, *, window_seconds: int = 120) -> int:
        normalized = normalize_message_content(message.content)
        if not normalized:
            return 1

        key = (message.guild.id, message.author.id)
        now = utcnow()
        queue = self.message_cache[key]

        while queue and (now - queue[0][1]).total_seconds() > window_seconds:
            queue.popleft()

        occurrences = 1 + sum(1 for content, _ in queue if content == normalized)
        queue.append((normalized, now))
        return occurrences

    def cache_message_snapshot(self, message: discord.Message) -> None:
        if message.guild is None:
            return

        self.cache_message_snapshot_data(
            message_id=message.id,
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            author_display=format_identity(message.author),
            content=message.content,
        )

    def cache_message_snapshot_data(
        self,
        *,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        author_display: str,
        content: str,
    ) -> None:
        snapshot = MessageLogSnapshot(
            guild_id=guild_id,
            channel_id=channel_id,
            author_id=author_id,
            author_display=author_display,
            content=content or "[no text]",
        )

        if message_id not in self.message_log_snapshots:
            if len(self.message_log_snapshot_order) >= self.message_log_snapshot_limit:
                oldest_message_id = self.message_log_snapshot_order.popleft()
                self.message_log_snapshots.pop(oldest_message_id, None)
            self.message_log_snapshot_order.append(message_id)

        self.message_log_snapshots[message_id] = snapshot

    def get_message_snapshot(self, message_id: int) -> MessageLogSnapshot | None:
        return self.message_log_snapshots.get(message_id)

    def update_message_snapshot_content(self, message_id: int, content: str) -> MessageLogSnapshot | None:
        snapshot = self.message_log_snapshots.get(message_id)
        if snapshot is None:
            return None
        snapshot.content = content or "[no text]"
        return snapshot

    def pop_message_snapshot(self, message_id: int) -> MessageLogSnapshot | None:
        snapshot = self.message_log_snapshots.pop(message_id, None)
        if snapshot is None:
            return None

        try:
            self.message_log_snapshot_order.remove(message_id)
        except ValueError:
            pass
        return snapshot

    async def persist_message_snapshot_data(
        self,
        *,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        author_display: str,
        content: str,
    ) -> None:
        await self.db.upsert_message_snapshot(
            message_id=message_id,
            guild_id=guild_id,
            channel_id=channel_id,
            author_id=author_id,
            author_display=author_display,
            content=content or "[no text]",
            updated_at=utcnow(),
        )

    async def fetch_persisted_message_snapshot(self, message_id: int) -> MessageLogSnapshot | None:
        row = await self.db.fetch_message_snapshot(message_id)
        if row is None:
            return None

        return MessageLogSnapshot(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            author_id=row["author_id"],
            author_display=row["author_display"],
            content=row["content"],
        )

    async def fetch_persisted_message_snapshots(self, message_ids: list[int]) -> dict[int, MessageLogSnapshot]:
        rows = await self.db.fetch_message_snapshots(message_ids)
        snapshots: dict[int, MessageLogSnapshot] = {}

        for message_id, row in rows.items():
            snapshots[message_id] = MessageLogSnapshot(
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                author_id=row["author_id"],
                author_display=row["author_display"],
                content=row["content"],
            )

        return snapshots

    async def drop_persisted_message_snapshot(self, message_id: int) -> None:
        await self.db.delete_message_snapshot(message_id)

    async def drop_persisted_message_snapshots(self, message_ids: list[int]) -> None:
        await self.db.delete_message_snapshots(message_ids)

    def register_join(self, guild_id: int, *, window_seconds: int) -> int:
        now = utcnow()
        queue = self.join_cache[guild_id]

        while queue and (now - queue[0]).total_seconds() > window_seconds:
            queue.popleft()

        queue.append(now)
        return len(queue)

    @tasks.loop(seconds=20)
    async def scheduler(self) -> None:
        for row in await self.db.get_due_scheduled_actions(utcnow()):
            guild = self.get_guild(row["guild_id"])
            if guild is None:
                continue

            action = row["action"]
            user_id = row["user_id"]
            try:
                if action == "unban":
                    await guild.unban(discord.Object(id=user_id), reason="Aegis temporary ban expired.")
                    await self.send_log(
                        guild,
                        LogType.MOD,
                        "Timed Ban Expired",
                        "Aegis automatically removed a temporary ban.",
                        tone="success",
                        fields=[("Target ID", f"`{user_id}`")],
                    )
                elif action == "unmute":
                    settings = await self.db.fetch_guild_settings(guild.id)
                    muted_role = guild.get_role(settings.muted_role_id or 0) if settings.muted_role_id else None
                    member = guild.get_member(user_id)
                    if member and muted_role and muted_role in member.roles:
                        await member.remove_roles(muted_role, reason="Aegis temporary mute expired.")
                        await self.send_log(
                            guild,
                            LogType.MOD,
                            "Timed Mute Expired",
                            "Aegis automatically removed a temporary mute.",
                            tone="success",
                            fields=[("Target", format_identity(member))],
                        )
            except discord.HTTPException:
                pass
            finally:
                await self.db.delete_scheduled_action(row["schedule_id"])

    @scheduler.before_loop
    async def before_scheduler(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(minutes=PRESENCE_REFRESH_MINUTES)
    async def presence_updater(self) -> None:
        await self.refresh_presence()

    @presence_updater.before_loop
    async def before_presence_updater(self) -> None:
        await self.wait_until_ready()
        await self.refresh_presence()
