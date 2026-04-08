from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from aegis.models import (
    AntiNukeEventType,
    AntiNukeIncident,
    AntiNukeMode,
    AntiNukeThresholdConfig,
    AntiNukeTrustEntry,
    AutoModFilter,
    AutoModFilterItem,
    FilterItemType,
    GuildSettings,
    LogType,
    PunishmentAction,
    PunishmentConfig,
    TrustSubjectType,
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA foreign_keys = ON;")
        await self._initialize_schema()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def _conn(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("Database connection has not been initialized.")
        return self.connection

    async def _initialize_schema(self) -> None:
        conn = self._conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                mod_role_id INTEGER,
                muted_role_id INTEGER,
                mod_log_channel_id INTEGER,
                message_log_channel_id INTEGER,
                server_log_channel_id INTEGER,
                voice_log_channel_id INTEGER,
                antinuke_log_channel_id INTEGER,
                anti_invite_strikes INTEGER NOT NULL DEFAULT 0,
                anti_referral_strikes INTEGER NOT NULL DEFAULT 0,
                anti_copypasta_strikes INTEGER NOT NULL DEFAULT 0,
                anti_everyone_strikes INTEGER NOT NULL DEFAULT 1,
                resolve_urls INTEGER NOT NULL DEFAULT 0,
                max_mentions INTEGER,
                max_role_mentions INTEGER,
                max_lines INTEGER,
                dehoist_char TEXT,
                duplicate_strike_threshold INTEGER,
                duplicate_delete_threshold INTEGER,
                duplicate_strikes INTEGER NOT NULL DEFAULT 1,
                anti_raid_joins INTEGER,
                anti_raid_seconds INTEGER,
                raid_mode_enabled INTEGER NOT NULL DEFAULT 0,
                raid_mode_previous_verification INTEGER,
                antinuke_enabled INTEGER NOT NULL DEFAULT 0,
                antinuke_mode TEXT NOT NULL DEFAULT 'contain',
                antinuke_freeze_minutes INTEGER NOT NULL DEFAULT 10
            );

            CREATE TABLE IF NOT EXISTS strike_punishments (
                guild_id INTEGER NOT NULL,
                strike_count INTEGER NOT NULL,
                action TEXT NOT NULL,
                duration_seconds INTEGER,
                PRIMARY KEY (guild_id, strike_count)
            );

            CREATE TABLE IF NOT EXISTS member_strikes (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                strikes INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS moderation_cases (
                case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS scheduled_actions (
                schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                execute_at TEXT NOT NULL,
                case_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS ignored_targets (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, target_id, target_type)
            );

            CREATE TABLE IF NOT EXISTS invite_whitelist (
                guild_id INTEGER NOT NULL,
                target_guild_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, target_guild_id)
            );

            CREATE TABLE IF NOT EXISTS automod_filters (
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                strikes INTEGER NOT NULL,
                items_json TEXT NOT NULL,
                PRIMARY KEY (guild_id, name)
            );

            CREATE TABLE IF NOT EXISTS message_snapshots (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_display TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_message_snapshots_updated_at
            ON message_snapshots (updated_at);

            CREATE TABLE IF NOT EXISTS antinuke_thresholds (
                guild_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                count INTEGER NOT NULL,
                window_seconds INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, event_type)
            );

            CREATE TABLE IF NOT EXISTS antinuke_trust_entries (
                guild_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                subject_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, subject_id, subject_type)
            );

            CREATE TABLE IF NOT EXISTS antinuke_incidents (
                incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                actor_id INTEGER,
                actor_name TEXT,
                event_type TEXT NOT NULL,
                audit_log_id INTEGER,
                target_id INTEGER,
                target_name TEXT,
                mode TEXT NOT NULL,
                summary TEXT NOT NULL,
                response_action TEXT,
                response_result TEXT,
                rollback_action TEXT,
                rollback_result TEXT,
                trusted INTEGER NOT NULL DEFAULT 0,
                freeze_expires_at TEXT,
                created_at TEXT NOT NULL,
                evidence_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_antinuke_incidents_guild_created
            ON antinuke_incidents (guild_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_antinuke_incidents_freeze
            ON antinuke_incidents (guild_id, freeze_expires_at);
            """
        )
        await self._migrate_guild_settings_columns()
        await conn.commit()

    async def _migrate_guild_settings_columns(self) -> None:
        conn = self._conn()
        cursor = await conn.execute("PRAGMA table_info(guild_settings);")
        rows = await cursor.fetchall()
        await cursor.close()
        existing = {str(row["name"]) for row in rows}

        missing_columns = {
            "anti_copypasta_strikes": "INTEGER NOT NULL DEFAULT 0",
            "resolve_urls": "INTEGER NOT NULL DEFAULT 0",
            "dehoist_char": "TEXT",
            "antinuke_log_channel_id": "INTEGER",
            "antinuke_enabled": "INTEGER NOT NULL DEFAULT 0",
            "antinuke_mode": "TEXT NOT NULL DEFAULT 'contain'",
            "antinuke_freeze_minutes": "INTEGER NOT NULL DEFAULT 10",
        }

        for column_name, definition in missing_columns.items():
            if column_name in existing:
                continue
            await conn.execute(f"ALTER TABLE guild_settings ADD COLUMN {column_name} {definition};")

    async def ensure_guild(self, guild_id: int) -> None:
        conn = self._conn()
        await conn.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?);",
            (guild_id,),
        )
        await conn.commit()

    async def fetch_guild_settings(self, guild_id: int) -> GuildSettings:
        await self.ensure_guild(guild_id)
        cursor = await self._conn().execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?;",
            (guild_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return GuildSettings(guild_id=guild_id)

        payload = dict(row)
        payload["raid_mode_enabled"] = bool(payload["raid_mode_enabled"])
        payload["resolve_urls"] = bool(payload.get("resolve_urls", 0))
        payload["antinuke_enabled"] = bool(payload.get("antinuke_enabled", 0))
        payload["antinuke_mode"] = AntiNukeMode(payload.get("antinuke_mode", AntiNukeMode.CONTAIN.value))
        if payload.get("dehoist_char") == "":
            payload["dehoist_char"] = None
        return GuildSettings(**payload)

    async def update_guild_settings(self, guild_id: int, **fields: Any) -> None:
        if not fields:
            return

        await self.ensure_guild(guild_id)
        allowed = {
            "mod_role_id",
            "muted_role_id",
            "mod_log_channel_id",
            "message_log_channel_id",
            "server_log_channel_id",
            "voice_log_channel_id",
            "antinuke_log_channel_id",
            "anti_invite_strikes",
            "anti_referral_strikes",
            "anti_copypasta_strikes",
            "anti_everyone_strikes",
            "resolve_urls",
            "max_mentions",
            "max_role_mentions",
            "max_lines",
            "dehoist_char",
            "duplicate_strike_threshold",
            "duplicate_delete_threshold",
            "duplicate_strikes",
            "anti_raid_joins",
            "anti_raid_seconds",
            "raid_mode_enabled",
            "raid_mode_previous_verification",
            "antinuke_enabled",
            "antinuke_mode",
            "antinuke_freeze_minutes",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Unsupported guild setting columns: {', '.join(sorted(invalid))}")

        normalized_fields = {
            name: value.value if isinstance(value, (LogType, PunishmentAction, AntiNukeMode)) else value
            for name, value in fields.items()
        }

        columns = ", ".join(f"{name} = ?" for name in normalized_fields)
        values = list(normalized_fields.values()) + [guild_id]
        await self._conn().execute(
            f"UPDATE guild_settings SET {columns} WHERE guild_id = ?;",
            values,
        )
        await self._conn().commit()

    async def set_log_channel(self, guild_id: int, log_type: LogType, channel_id: int | None) -> None:
        await self.update_guild_settings(guild_id, **{log_type.value: channel_id})

    async def get_punishments(self, guild_id: int) -> dict[int, PunishmentConfig]:
        cursor = await self._conn().execute(
            """
            SELECT guild_id, strike_count, action, duration_seconds
            FROM strike_punishments
            WHERE guild_id = ?
            ORDER BY strike_count ASC;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        punishments: dict[int, PunishmentConfig] = {}
        for row in rows:
            config = PunishmentConfig(
                guild_id=row["guild_id"],
                strike_count=row["strike_count"],
                action=PunishmentAction(row["action"]),
                duration_seconds=row["duration_seconds"],
            )
            punishments[config.strike_count] = config
        return punishments

    async def has_punishments(self, guild_id: int) -> bool:
        cursor = await self._conn().execute(
            "SELECT 1 FROM strike_punishments WHERE guild_id = ? LIMIT 1;",
            (guild_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row is not None

    async def set_punishment(
        self,
        guild_id: int,
        strike_count: int,
        action: PunishmentAction,
        duration_seconds: int | None,
    ) -> None:
        await self._conn().execute(
            """
            INSERT INTO strike_punishments (guild_id, strike_count, action, duration_seconds)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, strike_count) DO UPDATE SET
                action = excluded.action,
                duration_seconds = excluded.duration_seconds;
            """,
            (guild_id, strike_count, action.value, duration_seconds),
        )
        await self._conn().commit()

    async def remove_punishment(self, guild_id: int, strike_count: int) -> None:
        await self._conn().execute(
            "DELETE FROM strike_punishments WHERE guild_id = ? AND strike_count = ?;",
            (guild_id, strike_count),
        )
        await self._conn().commit()

    async def change_strikes(self, guild_id: int, user_id: int, delta: int) -> tuple[int, int]:
        cursor = await self._conn().execute(
            "SELECT strikes FROM member_strikes WHERE guild_id = ? AND user_id = ?;",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        await cursor.close()

        old_total = int(row["strikes"]) if row else 0
        new_total = max(old_total + delta, 0)

        await self._conn().execute(
            """
            INSERT INTO member_strikes (guild_id, user_id, strikes)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET strikes = excluded.strikes;
            """,
            (guild_id, user_id, new_total),
        )
        await self._conn().commit()
        return old_total, new_total

    async def get_strikes(self, guild_id: int, user_id: int) -> int:
        cursor = await self._conn().execute(
            "SELECT strikes FROM member_strikes WHERE guild_id = ? AND user_id = ?;",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row["strikes"]) if row else 0

    async def add_case(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int | None,
        action: str,
        reason: str,
        created_at: datetime,
        *,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cursor = await self._conn().execute(
            """
            INSERT INTO moderation_cases (
                guild_id,
                user_id,
                moderator_id,
                action,
                reason,
                created_at,
                expires_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                guild_id,
                user_id,
                moderator_id,
                action,
                reason,
                created_at.isoformat(),
                expires_at.isoformat() if expires_at else None,
                json.dumps(metadata) if metadata else None,
            ),
        )
        await self._conn().commit()
        return int(cursor.lastrowid)

    async def schedule_action(
        self,
        guild_id: int,
        user_id: int,
        action: str,
        execute_at: datetime,
        case_id: int | None = None,
    ) -> None:
        await self._conn().execute(
            """
            INSERT INTO scheduled_actions (guild_id, user_id, action, execute_at, case_id)
            VALUES (?, ?, ?, ?, ?);
            """,
            (guild_id, user_id, action, execute_at.isoformat(), case_id),
        )
        await self._conn().commit()

    async def get_due_scheduled_actions(self, before: datetime) -> list[aiosqlite.Row]:
        cursor = await self._conn().execute(
            """
            SELECT * FROM scheduled_actions
            WHERE execute_at <= ?
            ORDER BY execute_at ASC;
            """,
            (before.isoformat(),),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    async def delete_scheduled_action(self, schedule_id: int) -> None:
        await self._conn().execute(
            "DELETE FROM scheduled_actions WHERE schedule_id = ?;",
            (schedule_id,),
        )
        await self._conn().commit()

    async def clear_scheduled_actions(self, guild_id: int, user_id: int, action: str) -> None:
        await self._conn().execute(
            """
            DELETE FROM scheduled_actions
            WHERE guild_id = ? AND user_id = ? AND action = ?;
            """,
            (guild_id, user_id, action),
        )
        await self._conn().commit()

    async def get_next_scheduled_action(
        self,
        guild_id: int,
        user_id: int,
        action: str,
    ) -> aiosqlite.Row | None:
        cursor = await self._conn().execute(
            """
            SELECT schedule_id, guild_id, user_id, action, execute_at, case_id
            FROM scheduled_actions
            WHERE guild_id = ? AND user_id = ? AND action = ?
            ORDER BY execute_at ASC
            LIMIT 1;
            """,
            (guild_id, user_id, action),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def add_ignored_target(self, guild_id: int, target_id: int, target_type: str) -> None:
        await self._conn().execute(
            """
            INSERT OR IGNORE INTO ignored_targets (guild_id, target_id, target_type)
            VALUES (?, ?, ?);
            """,
            (guild_id, target_id, target_type),
        )
        await self._conn().commit()

    async def remove_ignored_target(self, guild_id: int, target_id: int, target_type: str) -> None:
        await self._conn().execute(
            """
            DELETE FROM ignored_targets
            WHERE guild_id = ? AND target_id = ? AND target_type = ?;
            """,
            (guild_id, target_id, target_type),
        )
        await self._conn().commit()

    async def list_ignored_targets(self, guild_id: int) -> list[aiosqlite.Row]:
        cursor = await self._conn().execute(
            """
            SELECT guild_id, target_id, target_type
            FROM ignored_targets
            WHERE guild_id = ?
            ORDER BY target_type, target_id;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    async def add_invite_whitelist_target(self, guild_id: int, target_guild_id: int) -> None:
        await self._conn().execute(
            """
            INSERT OR IGNORE INTO invite_whitelist (guild_id, target_guild_id)
            VALUES (?, ?);
            """,
            (guild_id, target_guild_id),
        )
        await self._conn().commit()

    async def remove_invite_whitelist_target(self, guild_id: int, target_guild_id: int) -> None:
        await self._conn().execute(
            """
            DELETE FROM invite_whitelist
            WHERE guild_id = ? AND target_guild_id = ?;
            """,
            (guild_id, target_guild_id),
        )
        await self._conn().commit()

    async def list_invite_whitelist_targets(self, guild_id: int) -> list[int]:
        cursor = await self._conn().execute(
            """
            SELECT target_guild_id
            FROM invite_whitelist
            WHERE guild_id = ?
            ORDER BY target_guild_id ASC;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [int(row["target_guild_id"]) for row in rows]

    async def upsert_automod_filter(
        self,
        guild_id: int,
        name: str,
        strikes: int,
        items: tuple[AutoModFilterItem, ...],
    ) -> None:
        payload = json.dumps(
            [{"type": item.item_type.value, "value": item.value} for item in items],
            ensure_ascii=True,
        )
        await self._conn().execute(
            """
            INSERT INTO automod_filters (guild_id, name, strikes, items_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, name) DO UPDATE SET
                strikes = excluded.strikes,
                items_json = excluded.items_json;
            """,
            (guild_id, name.lower(), strikes, payload),
        )
        await self._conn().commit()

    async def delete_automod_filter(self, guild_id: int, name: str) -> bool:
        cursor = await self._conn().execute(
            """
            DELETE FROM automod_filters
            WHERE guild_id = ? AND name = ?;
            """,
            (guild_id, name.lower()),
        )
        deleted = cursor.rowcount if cursor.rowcount is not None else 0
        await self._conn().commit()
        return deleted > 0

    async def list_automod_filters(self, guild_id: int) -> list[AutoModFilter]:
        cursor = await self._conn().execute(
            """
            SELECT guild_id, name, strikes, items_json
            FROM automod_filters
            WHERE guild_id = ?
            ORDER BY name ASC;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        filters: list[AutoModFilter] = []
        for row in rows:
            raw_items = json.loads(row["items_json"])
            items = tuple(
                AutoModFilterItem(item_type=FilterItemType(item["type"]), value=str(item["value"]))
                for item in raw_items
            )
            filters.append(
                AutoModFilter(
                    guild_id=int(row["guild_id"]),
                    name=str(row["name"]),
                    strikes=int(row["strikes"]),
                    items=items,
                )
            )
        return filters

    async def get_antinuke_thresholds(
        self,
        guild_id: int,
    ) -> dict[AntiNukeEventType, AntiNukeThresholdConfig]:
        cursor = await self._conn().execute(
            """
            SELECT guild_id, event_type, count, window_seconds, enabled
            FROM antinuke_thresholds
            WHERE guild_id = ?;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        thresholds: dict[AntiNukeEventType, AntiNukeThresholdConfig] = {}
        for row in rows:
            event_type = AntiNukeEventType(row["event_type"])
            thresholds[event_type] = AntiNukeThresholdConfig(
                guild_id=int(row["guild_id"]),
                event_type=event_type,
                count=int(row["count"]),
                window_seconds=int(row["window_seconds"]),
                enabled=bool(row["enabled"]),
            )
        return thresholds

    async def upsert_antinuke_threshold(
        self,
        guild_id: int,
        event_type: AntiNukeEventType,
        *,
        count: int,
        window_seconds: int,
        enabled: bool,
    ) -> None:
        await self._conn().execute(
            """
            INSERT INTO antinuke_thresholds (guild_id, event_type, count, window_seconds, enabled)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (guild_id, event_type) DO UPDATE SET
                count = excluded.count,
                window_seconds = excluded.window_seconds,
                enabled = excluded.enabled;
            """,
            (guild_id, event_type.value, count, window_seconds, int(enabled)),
        )
        await self._conn().commit()

    async def list_antinuke_trust_entries(self, guild_id: int) -> list[AntiNukeTrustEntry]:
        cursor = await self._conn().execute(
            """
            SELECT guild_id, subject_id, subject_type
            FROM antinuke_trust_entries
            WHERE guild_id = ?
            ORDER BY subject_type ASC, subject_id ASC;
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            AntiNukeTrustEntry(
                guild_id=int(row["guild_id"]),
                subject_id=int(row["subject_id"]),
                subject_type=TrustSubjectType(row["subject_type"]),
            )
            for row in rows
        ]

    async def add_antinuke_trust_entry(
        self,
        guild_id: int,
        subject_id: int,
        subject_type: TrustSubjectType,
    ) -> None:
        await self._conn().execute(
            """
            INSERT OR IGNORE INTO antinuke_trust_entries (guild_id, subject_id, subject_type)
            VALUES (?, ?, ?);
            """,
            (guild_id, subject_id, subject_type.value),
        )
        await self._conn().commit()

    async def remove_antinuke_trust_entry(
        self,
        guild_id: int,
        subject_id: int,
        subject_type: TrustSubjectType,
    ) -> bool:
        cursor = await self._conn().execute(
            """
            DELETE FROM antinuke_trust_entries
            WHERE guild_id = ? AND subject_id = ? AND subject_type = ?;
            """,
            (guild_id, subject_id, subject_type.value),
        )
        deleted = cursor.rowcount if cursor.rowcount is not None else 0
        await self._conn().commit()
        return deleted > 0

    async def add_antinuke_incident(
        self,
        guild_id: int,
        *,
        actor_id: int | None,
        actor_name: str | None,
        event_type: AntiNukeEventType,
        audit_log_id: int | None,
        target_id: int | None,
        target_name: str | None,
        mode: AntiNukeMode,
        summary: str,
        response_action: str | None,
        response_result: str | None,
        rollback_action: str | None,
        rollback_result: str | None,
        trusted: bool,
        freeze_expires_at: datetime | None,
        created_at: datetime,
        evidence: dict[str, Any] | None = None,
    ) -> int:
        cursor = await self._conn().execute(
            """
            INSERT INTO antinuke_incidents (
                guild_id,
                actor_id,
                actor_name,
                event_type,
                audit_log_id,
                target_id,
                target_name,
                mode,
                summary,
                response_action,
                response_result,
                rollback_action,
                rollback_result,
                trusted,
                freeze_expires_at,
                created_at,
                evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                guild_id,
                actor_id,
                actor_name,
                event_type.value,
                audit_log_id,
                target_id,
                target_name,
                mode.value,
                summary,
                response_action,
                response_result,
                rollback_action,
                rollback_result,
                int(trusted),
                freeze_expires_at.isoformat() if freeze_expires_at else None,
                created_at.isoformat(),
                json.dumps(evidence or {}, ensure_ascii=True),
            ),
        )
        await self._conn().commit()
        return int(cursor.lastrowid)

    async def list_antinuke_incidents(self, guild_id: int, *, limit: int = 5) -> list[AntiNukeIncident]:
        cursor = await self._conn().execute(
            """
            SELECT *
            FROM antinuke_incidents
            WHERE guild_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (guild_id, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        incidents: list[AntiNukeIncident] = []
        for row in rows:
            incidents.append(
                AntiNukeIncident(
                    incident_id=int(row["incident_id"]),
                    guild_id=int(row["guild_id"]),
                    actor_id=row["actor_id"],
                    actor_name=row["actor_name"],
                    event_type=AntiNukeEventType(row["event_type"]),
                    audit_log_id=row["audit_log_id"],
                    target_id=row["target_id"],
                    target_name=row["target_name"],
                    mode=AntiNukeMode(row["mode"]),
                    summary=str(row["summary"]),
                    response_action=row["response_action"],
                    response_result=row["response_result"],
                    rollback_action=row["rollback_action"],
                    rollback_result=row["rollback_result"],
                    trusted=bool(row["trusted"]),
                    freeze_expires_at=row["freeze_expires_at"],
                    created_at=str(row["created_at"]),
                    evidence=json.loads(row["evidence_json"] or "{}"),
                )
            )
        return incidents

    async def get_active_antinuke_freeze(self, guild_id: int, *, now: datetime) -> datetime | None:
        cursor = await self._conn().execute(
            """
            SELECT freeze_expires_at
            FROM antinuke_incidents
            WHERE guild_id = ?
              AND freeze_expires_at IS NOT NULL
              AND freeze_expires_at > ?
            ORDER BY freeze_expires_at DESC
            LIMIT 1;
            """,
            (guild_id, now.isoformat()),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None or row["freeze_expires_at"] is None:
            return None
        return datetime.fromisoformat(str(row["freeze_expires_at"]))

    async def clear_active_antinuke_freeze(self, guild_id: int, *, now: datetime) -> bool:
        cursor = await self._conn().execute(
            """
            UPDATE antinuke_incidents
            SET freeze_expires_at = NULL
            WHERE guild_id = ?
              AND freeze_expires_at IS NOT NULL
              AND freeze_expires_at > ?;
            """,
            (guild_id, now.isoformat()),
        )
        changed = cursor.rowcount if cursor.rowcount is not None else 0
        await self._conn().commit()
        return changed > 0

    async def upsert_message_snapshot(
        self,
        *,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        author_display: str,
        content: str,
        updated_at: datetime,
    ) -> None:
        await self._conn().execute(
            """
            INSERT INTO message_snapshots (
                message_id,
                guild_id,
                channel_id,
                author_id,
                author_display,
                content,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (message_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                channel_id = excluded.channel_id,
                author_id = excluded.author_id,
                author_display = excluded.author_display,
                content = excluded.content,
                updated_at = excluded.updated_at;
            """,
            (
                message_id,
                guild_id,
                channel_id,
                author_id,
                author_display,
                content,
                updated_at.isoformat(),
            ),
        )
        await self._conn().commit()

    async def upsert_message_snapshots_bulk(
        self,
        snapshots: list[tuple[int, int, int, int, str, str, str]],
    ) -> None:
        if not snapshots:
            return

        await self._conn().executemany(
            """
            INSERT INTO message_snapshots (
                message_id,
                guild_id,
                channel_id,
                author_id,
                author_display,
                content,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (message_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                channel_id = excluded.channel_id,
                author_id = excluded.author_id,
                author_display = excluded.author_display,
                content = excluded.content,
                updated_at = excluded.updated_at;
            """,
            snapshots,
        )
        await self._conn().commit()

    async def fetch_message_snapshot(self, message_id: int) -> aiosqlite.Row | None:
        cursor = await self._conn().execute(
            """
            SELECT message_id, guild_id, channel_id, author_id, author_display, content, updated_at
            FROM message_snapshots
            WHERE message_id = ?;
            """,
            (message_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetch_message_snapshots(self, message_ids: list[int]) -> dict[int, aiosqlite.Row]:
        if not message_ids:
            return {}

        placeholders = ", ".join("?" for _ in message_ids)
        cursor = await self._conn().execute(
            f"""
            SELECT message_id, guild_id, channel_id, author_id, author_display, content, updated_at
            FROM message_snapshots
            WHERE message_id IN ({placeholders});
            """,
            message_ids,
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return {int(row["message_id"]): row for row in rows}

    async def delete_message_snapshot(self, message_id: int) -> None:
        await self._conn().execute(
            "DELETE FROM message_snapshots WHERE message_id = ?;",
            (message_id,),
        )
        await self._conn().commit()

    async def delete_message_snapshots(self, message_ids: list[int]) -> None:
        if not message_ids:
            return

        placeholders = ", ".join("?" for _ in message_ids)
        await self._conn().execute(
            f"DELETE FROM message_snapshots WHERE message_id IN ({placeholders});",
            message_ids,
        )
        await self._conn().commit()
