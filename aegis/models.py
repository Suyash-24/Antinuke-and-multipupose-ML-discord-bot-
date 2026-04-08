from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LogType(StrEnum):
    MOD = "mod_log_channel_id"
    MESSAGE = "message_log_channel_id"
    SERVER = "server_log_channel_id"
    VOICE = "voice_log_channel_id"
    ANTINUKE = "antinuke_log_channel_id"


class PunishmentAction(StrEnum):
    NONE = "none"
    WARN = "warn"
    MUTE = "mute"
    KICK = "kick"
    BAN = "ban"
    SOFTBAN = "softban"
    SILENTBAN = "silentban"


class AntiNukeMode(StrEnum):
    CONTAIN = "contain"
    BAN = "ban"
    ALERT = "alert"


class AntiNukeEventType(StrEnum):
    BOT_ADD = "bot_add"
    ADMIN_PERMISSION_GRANT = "admin_permission_grant"
    CHANNEL_CREATE = "channel_create"
    CHANNEL_DELETE = "channel_delete"
    CHANNEL_UPDATE = "channel_update"
    ROLE_CREATE = "role_create"
    ROLE_DELETE = "role_delete"
    ROLE_UPDATE = "role_update"
    WEBHOOK_CREATE = "webhook_create"
    WEBHOOK_DELETE = "webhook_delete"
    WEBHOOK_UPDATE = "webhook_update"
    GUILD_UPDATE = "guild_update"


class TrustSubjectType(StrEnum):
    USER = "user"
    ROLE = "role"


@dataclass(slots=True, frozen=True)
class GuildSettings:
    guild_id: int
    mod_role_id: int | None = None
    muted_role_id: int | None = None
    mod_log_channel_id: int | None = None
    message_log_channel_id: int | None = None
    server_log_channel_id: int | None = None
    voice_log_channel_id: int | None = None
    antinuke_log_channel_id: int | None = None
    anti_invite_strikes: int = 0
    anti_referral_strikes: int = 0
    anti_copypasta_strikes: int = 0
    anti_everyone_strikes: int = 1
    resolve_urls: bool = False
    max_mentions: int | None = None
    max_role_mentions: int | None = None
    max_lines: int | None = None
    dehoist_char: str | None = None
    duplicate_strike_threshold: int | None = None
    duplicate_delete_threshold: int | None = None
    duplicate_strikes: int = 1
    anti_raid_joins: int | None = None
    anti_raid_seconds: int | None = None
    raid_mode_enabled: bool = False
    raid_mode_previous_verification: int | None = None
    antinuke_enabled: bool = False
    antinuke_mode: AntiNukeMode = AntiNukeMode.CONTAIN
    antinuke_freeze_minutes: int = 10


@dataclass(slots=True, frozen=True)
class PunishmentConfig:
    guild_id: int
    strike_count: int
    action: PunishmentAction
    duration_seconds: int | None = None


class FilterItemType(StrEnum):
    GLOB = "glob"
    QUOTE = "quote"
    REGEX = "regex"


@dataclass(slots=True, frozen=True)
class AutoModFilterItem:
    item_type: FilterItemType
    value: str


@dataclass(slots=True, frozen=True)
class AutoModFilter:
    guild_id: int
    name: str
    strikes: int
    items: tuple[AutoModFilterItem, ...]


@dataclass(slots=True, frozen=True)
class AntiNukeThresholdConfig:
    guild_id: int
    event_type: AntiNukeEventType
    count: int
    window_seconds: int
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class AntiNukeTrustEntry:
    guild_id: int
    subject_id: int
    subject_type: TrustSubjectType


@dataclass(slots=True, frozen=True)
class AntiNukeIncident:
    incident_id: int
    guild_id: int
    actor_id: int | None
    actor_name: str | None
    event_type: AntiNukeEventType
    audit_log_id: int | None
    target_id: int | None
    target_name: str | None
    mode: AntiNukeMode
    summary: str
    response_action: str | None
    response_result: str | None
    rollback_action: str | None
    rollback_result: str | None
    trusted: bool
    freeze_expires_at: str | None
    created_at: str
    evidence: dict[str, Any]
