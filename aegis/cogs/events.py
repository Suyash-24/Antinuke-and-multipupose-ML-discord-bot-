from __future__ import annotations

import asyncio
import io
import json
import re
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp
import discord
from discord.ext import commands

from aegis.bot import AegisBot
from aegis.models import AutoModFilter, AutoModFilterItem, FilterItemType, LogType
from aegis.ui import build_panel
from aegis.utils import format_identity, format_timestamp, normalize_message_content, truncate, utcnow

INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)
INVITE_CODE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/([A-Za-z0-9-]+)",
    re.IGNORECASE,
)
REFERRAL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:bit\.ly|cutt\.ly|tinyurl\.com|linktr\.ee|grabify\.link|iplogger\.(?:org|com))\S*",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
MENTION_MINIMUM = 4
ROLE_MENTION_MINIMUM = 2
RAIDMODE_AUTO_DISABLE_SECONDS = 120
FILTER_TEST_CASES = (
    "welcome",
    "i will follow the rules",
    "this is a sentence",
)
COPYPASTA_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Navy Seal",
        (
            "what the fuck did you just fucking say about me",
            "i graduated top of my class in the navy seals",
        ),
    ),
    (
        "Bee Movie",
        (
            "according to all known laws of aviation",
            "there is no way a bee should be able to fly",
        ),
    ),
    (
        "Lorem Spam",
        (
            "lorem ipsum dolor sit amet",
            "consectetur adipiscing elit",
        ),
    ),
)
REFERRAL_SUBSTRINGS = (
    "?ref=",
    "ref=",
    "affiliate",
    "utm_source=",
)
FAILURE_EMOJI = "<:failed:1488505866935078922>"
SNAPSHOT_WARMUP_LIMIT = 75
ARCHIVE_FILE_SIZE_LIMIT = 7_500_000


@dataclass(slots=True)
class BulkDeletedMessageRecord:
    message_id: int
    author_id: int
    author_display: str
    content: str


@dataclass(slots=True)
class AutoModDecision:
    strikes: int = 0
    delete_message: bool = False
    reasons: list[str] = field(default_factory=list)
    rule_names: list[str] = field(default_factory=list)
    warning_text: str | None = None


class EventsCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot
        self._snapshot_warmup_guild_ids: set[int] = set()
        self._invite_cache: dict[str, tuple[int | None, float]] = {}
        self._last_join_attempt: dict[int, float] = {}

    def _record_last_join_attempt(self, guild_id: int) -> None:
        self._last_join_attempt[guild_id] = utcnow().timestamp()

    def _seconds_since_last_join_attempt(self, guild_id: int) -> float | None:
        last = self._last_join_attempt.get(guild_id)
        if last is None:
            return None
        return utcnow().timestamp() - last

    def _add_decision(
        self,
        decision: AutoModDecision,
        *,
        rule_name: str,
        reason: str,
        strikes: int,
        delete_message: bool = True,
    ) -> None:
        if strikes > 0:
            decision.strikes += strikes
        decision.reasons.append(reason)
        decision.rule_names.append(rule_name)
        decision.delete_message = decision.delete_message or delete_message

    async def _persist_snapshot_safe(
        self,
        *,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        author_display: str,
        content: str,
    ) -> None:
        try:
            await self.bot.persist_message_snapshot_data(
                message_id=message_id,
                guild_id=guild_id,
                channel_id=channel_id,
                author_id=author_id,
                author_display=author_display,
                content=content,
            )
        except Exception:
            # Snapshot persistence must not block moderation flow.
            return

    def _contains_referral_link(self, content: str) -> bool:
        if REFERRAL_RE.search(content):
            return True
        lowered = content.lower()
        return any(fragment in lowered for fragment in REFERRAL_SUBSTRINGS)

    def _contains_everyone_ping(self, message: discord.Message) -> bool:
        if message.author.guild_permissions.mention_everyone:
            return False

        filtered = message.content.replace("`@everyone`", "").replace("`@here`", "")
        if "@everyone" in filtered or "@here" in filtered:
            return True

        return any(
            role.name.lower() in {"everyone", "here"}
            for role in message.role_mentions
        )

    def _find_copypasta_name(self, content: str) -> str | None:
        normalized = normalize_message_content(content)
        if len(normalized) < 120:
            return None

        for name, snippets in COPYPASTA_SIGNATURES:
            if any(snippet in normalized for snippet in snippets):
                return name
        return None

    @staticmethod
    def _is_word_boundary(message: str, index: int) -> bool:
        if index < 0 or index >= len(message):
            return True
        char = message[index]
        return not char.isalnum()

    def _glob_matches(self, glob_pattern: str, message: str) -> bool:
        collapsed = re.sub(r"\*+", "*", glob_pattern.lower())
        start_wildcard = collapsed.startswith("*")
        end_wildcard = collapsed.endswith("*")
        core = collapsed[1 if start_wildcard else 0 : len(collapsed) - (1 if end_wildcard else 0)]
        if not core:
            return False

        index = message.find(core)
        while index != -1:
            before_index = index - 1
            after_index = index + len(core)
            if (
                (start_wildcard or self._is_word_boundary(message, before_index))
                and (end_wildcard or self._is_word_boundary(message, after_index))
            ):
                return True
            index = message.find(core, index + 1)
        return False

    def _filter_item_matches(self, item: AutoModFilterItem, lowered_content: str) -> bool:
        if item.item_type is FilterItemType.QUOTE:
            return item.value.lower() in lowered_content
        if item.item_type is FilterItemType.REGEX:
            try:
                return re.search(item.value, lowered_content, flags=re.IGNORECASE) is not None
            except re.error:
                return False
        return self._glob_matches(item.value, lowered_content)

    def _find_matching_filter(
        self,
        filters: list[AutoModFilter],
        lowered_content: str,
    ) -> AutoModFilter | None:
        matched_filter: AutoModFilter | None = None
        for automod_filter in filters:
            if any(self._filter_item_matches(item, lowered_content) for item in automod_filter.items):
                if matched_filter is None or automod_filter.strikes > matched_filter.strikes:
                    matched_filter = automod_filter
        return matched_filter

    async def _resolve_invite_guild_id(self, invite_code: str) -> int | None:
        cache_ttl_seconds = 900
        now_ts = utcnow().timestamp()
        cached = self._invite_cache.get(invite_code)
        if cached is not None and now_ts - cached[1] <= cache_ttl_seconds:
            return cached[0]

        guild_id: int | None = None
        try:
            invite = await self.bot.fetch_invite(f"https://discord.gg/{invite_code}")
            invite_guild = getattr(invite, "guild", None)
            if invite_guild is not None:
                guild_id = int(invite_guild.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            guild_id = None

        self._invite_cache[invite_code] = (guild_id, now_ts)
        if len(self._invite_cache) > 1500:
            self._invite_cache.pop(next(iter(self._invite_cache)))
        return guild_id

    async def _contains_external_invite(
        self,
        message: discord.Message,
        content: str,
        invite_whitelist: set[int],
    ) -> bool:
        invite_codes = {match.group(1) for match in INVITE_CODE_RE.finditer(content)}
        if not invite_codes:
            return False

        for invite_code in invite_codes:
            target_guild_id = await self._resolve_invite_guild_id(invite_code)
            if target_guild_id is None:
                return True
            if target_guild_id != message.guild.id and target_guild_id not in invite_whitelist:
                return True
        return False

    async def _resolve_redirect_chain(self, session: aiohttp.ClientSession, url: str) -> list[str]:
        for method in ("HEAD", "GET"):
            try:
                async with session.request(
                    method,
                    url,
                    allow_redirects=True,
                    max_redirects=8,
                ) as response:
                    history = [str(item.url) for item in response.history]
                    return history + [str(response.url)]
            except (aiohttp.ClientError, asyncio.TimeoutError):
                continue
        return [url]

    async def _check_resolved_links(
        self,
        message: discord.Message,
        content: str,
        *,
        detect_invites: bool,
        detect_referrals: bool,
        invite_whitelist: set[int],
    ) -> tuple[bool, bool]:
        links = []
        for match in URL_RE.finditer(content):
            candidate = match.group(0).rstrip(">")
            if candidate not in links:
                links.append(candidate)
            if len(links) >= 6:
                break

        if not links:
            return False, False

        contains_invite = False
        contains_referral = False
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for link in links:
                chain = await self._resolve_redirect_chain(session, link)
                for resolved in chain:
                    if detect_invites and not contains_invite:
                        invite_codes = {match.group(1) for match in INVITE_CODE_RE.finditer(resolved)}
                        for invite_code in invite_codes:
                            target_guild_id = await self._resolve_invite_guild_id(invite_code)
                            if target_guild_id is None:
                                contains_invite = True
                                break
                            if target_guild_id != message.guild.id and target_guild_id not in invite_whitelist:
                                contains_invite = True
                                break

                    if detect_referrals and not contains_referral and self._contains_referral_link(resolved):
                        contains_referral = True

                    if (not detect_invites or contains_invite) and (not detect_referrals or contains_referral):
                        return contains_invite, contains_referral

        return contains_invite, contains_referral

    async def _maybe_dehoist_member(self, member: discord.Member) -> None:
        settings = await self.bot.db.fetch_guild_settings(member.guild.id)
        threshold = settings.dehoist_char
        if not threshold:
            return

        if member.bot or member.id == member.guild.owner_id:
            return

        permissions = member.guild_permissions
        if (
            permissions.administrator
            or permissions.manage_guild
            or permissions.kick_members
            or permissions.ban_members
        ):
            return

        me = member.guild.me
        if me is None or member.top_role >= me.top_role:
            return

        display_name = member.display_name or member.name
        if not display_name:
            return
        if display_name[0] > threshold:
            return

        cleaned = display_name
        while cleaned and not cleaned[0].isalnum() and cleaned[0] <= threshold:
            cleaned = cleaned[1:]
        cleaned = cleaned.strip() or display_name
        desired_nick = f"z-{cleaned}"[:32]

        if member.nick == desired_nick:
            return

        try:
            await member.edit(nick=desired_nick, reason="Aegis auto dehoist")
        except discord.HTTPException:
            return

    async def _warmup_guild_message_snapshots(self, guild: discord.Guild) -> None:
        me = guild.me
        if me is None:
            return

        channels: list[discord.TextChannel | discord.Thread] = []
        for channel in guild.text_channels:
            perms = channel.permissions_for(me)
            if perms.view_channel and perms.read_message_history:
                channels.append(channel)

        for thread in guild.threads:
            perms = thread.permissions_for(me)
            if perms.view_channel and perms.read_message_history:
                channels.append(thread)

        for channel in channels:
            rows: list[tuple[int, int, int, int, str, str, str]] = []

            try:
                async for message in channel.history(limit=SNAPSHOT_WARMUP_LIMIT):
                    if message.guild is None:
                        continue

                    content = message.content or "[no text]"
                    author_display = format_identity(message.author)
                    self.bot.cache_message_snapshot_data(
                        message_id=message.id,
                        guild_id=message.guild.id,
                        channel_id=message.channel.id,
                        author_id=message.author.id,
                        author_display=author_display,
                        content=content,
                    )
                    rows.append(
                        (
                            message.id,
                            message.guild.id,
                            message.channel.id,
                            message.author.id,
                            author_display,
                            content,
                            utcnow().isoformat(),
                        )
                    )
            except (discord.Forbidden, discord.HTTPException):
                continue

            if rows:
                await self.bot.db.upsert_message_snapshots_bulk(rows)

    async def _delete_message_safely(self, message: discord.Message) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            return

    def _safe_archive_bytes(self, text: str) -> bytes:
        payload = text.encode("utf-8")
        if len(payload) <= ARCHIVE_FILE_SIZE_LIMIT:
            return payload

        marker = "\n\n[truncated by Aegis due to file size limits]"
        marker_bytes = marker.encode("utf-8")
        return payload[: ARCHIVE_FILE_SIZE_LIMIT - len(marker_bytes)] + marker_bytes

    async def _collect_bulk_delete_records(
        self,
        payload: discord.RawBulkMessageDeleteEvent,
    ) -> list[BulkDeletedMessageRecord]:
        records: dict[int, BulkDeletedMessageRecord] = {}

        cached_messages = getattr(payload, "cached_messages", None) or []
        for message in cached_messages:
            records[message.id] = BulkDeletedMessageRecord(
                message_id=message.id,
                author_id=message.author.id,
                author_display=format_identity(message.author),
                content=message.content or "[no text]",
            )

        missing_ids = [message_id for message_id in payload.message_ids if message_id not in records]
        for message_id in missing_ids:
            snapshot = self.bot.get_message_snapshot(message_id)
            if snapshot is None:
                continue
            records[message_id] = BulkDeletedMessageRecord(
                message_id=message_id,
                author_id=snapshot.author_id,
                author_display=snapshot.author_display,
                content=snapshot.content,
            )

        unresolved_ids = [message_id for message_id in payload.message_ids if message_id not in records]
        if unresolved_ids:
            persisted = await self.bot.fetch_persisted_message_snapshots(unresolved_ids)
            for message_id, snapshot in persisted.items():
                records[message_id] = BulkDeletedMessageRecord(
                    message_id=message_id,
                    author_id=snapshot.author_id,
                    author_display=snapshot.author_display,
                    content=snapshot.content,
                )

        return [records[message_id] for message_id in sorted(records)]

    def _build_bulk_delete_archive_files(
        self,
        guild: discord.Guild,
        deleted_channel_id: int,
        deleted_channel_label: str,
        message_ids: list[int],
        records: list[BulkDeletedMessageRecord],
    ) -> tuple[list[discord.File], str, str]:
        now = utcnow()
        stamp = now.strftime("%Y%m%d-%H%M%S")
        base_name = f"bulk-delete-{guild.id}-{deleted_channel_id}-{stamp}"
        view_filename = f"{base_name}.txt"
        download_filename = f"{base_name}.json"

        lines = [
            "Aegis Bulk Delete Transcript",
            f"Guild: {guild.name} ({guild.id})",
            f"Channel: {deleted_channel_label} ({deleted_channel_id})",
            f"Deleted IDs: {len(message_ids)}",
            f"Recovered Messages: {len(records)}",
            f"Generated: {now.isoformat()}",
            "",
            "Messages",
            "========",
        ]

        for record in records:
            created_at = discord.utils.snowflake_time(record.message_id)
            timestamp = created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = (record.content or "[no text]").replace("\r\n", "\n").replace("\r", "\n")
            content = content.replace("\n", "\\n")
            lines.append(
                f"[{timestamp}] {record.author_display} | ID: {record.author_id} | Message: {record.message_id} | {content}"
            )

        if not records:
            lines.append("No message content could be recovered for this bulk delete event.")

        view_text = "\n".join(lines)

        json_payload = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "channel_id": deleted_channel_id,
            "channel_label": deleted_channel_label,
            "deleted_ids": [int(message_id) for message_id in sorted(message_ids)],
            "deleted_count": len(message_ids),
            "recovered_count": len(records),
            "generated_at": now.isoformat(),
            "messages": [
                {
                    "message_id": record.message_id,
                    "author_id": record.author_id,
                    "author": record.author_display,
                    "timestamp": discord.utils.snowflake_time(record.message_id).isoformat(),
                    "content": record.content,
                }
                for record in records
            ],
        }
        download_text = json.dumps(json_payload, ensure_ascii=True, indent=2)

        files = [
            discord.File(io.BytesIO(self._safe_archive_bytes(view_text)), filename=view_filename),
            discord.File(io.BytesIO(self._safe_archive_bytes(download_text)), filename=download_filename),
        ]
        return files, view_filename, download_filename

    async def _resolve_archive_attachment_urls(
        self,
        log_message: discord.Message,
        view_filename: str,
        download_filename: str,
    ) -> tuple[str | None, str | None]:
        attachments = {
            attachment.filename: attachment.url or attachment.proxy_url
            for attachment in log_message.attachments
        }
        view_url = attachments.get(view_filename)
        download_url = attachments.get(download_filename)

        if view_url is None and log_message.attachments:
            first = log_message.attachments[0]
            view_url = first.url or first.proxy_url
        if download_url is None and log_message.attachments:
            last = log_message.attachments[-1]
            download_url = last.url or last.proxy_url

        if view_url is not None or download_url is not None:
            return view_url, download_url

        cached_message = discord.utils.find(
            lambda cached: cached.id == log_message.id,
            self.bot.cached_messages,
        )
        if cached_message is not None and cached_message.attachments:
            cached_attachments = {
                attachment.filename: attachment.url or attachment.proxy_url
                for attachment in cached_message.attachments
            }
            view_url = cached_attachments.get(view_filename)
            download_url = cached_attachments.get(download_filename)

            if view_url is None:
                first = cached_message.attachments[0]
                view_url = first.url or first.proxy_url
            if download_url is None:
                last = cached_message.attachments[-1]
                download_url = last.url or last.proxy_url

            if view_url is not None or download_url is not None:
                return view_url, download_url

        latest = log_message
        for _ in range(4):
            try:
                await asyncio.sleep(0.35)
                latest = await log_message.channel.fetch_message(log_message.id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                break

            fetched = {
                attachment.filename: attachment.url or attachment.proxy_url
                for attachment in latest.attachments
            }
            view_url = fetched.get(view_filename)
            download_url = fetched.get(download_filename)

            if view_url is None and latest.attachments:
                first = latest.attachments[0]
                view_url = first.url or first.proxy_url
            if download_url is None and latest.attachments:
                last = latest.attachments[-1]
                download_url = last.url or last.proxy_url

            if view_url is not None or download_url is not None:
                return view_url, download_url

        if latest.attachments:
            first = latest.attachments[0]
            last = latest.attachments[-1]
            return first.url or first.proxy_url, last.url or last.proxy_url
        return None, None

    async def _automod_enforce(
        self,
        message: discord.Message,
        *,
        strikes: int,
        rule_name: str,
        rule_reason: str,
        delete_message: bool = True,
    ) -> None:
        if delete_message:
            await self._delete_message_safely(message)

        await self.bot.apply_strikes(
            message.guild,
            message.author,
            strikes,
            rule_reason,
            moderator=self.bot.user,
            source=f"AutoMod - {rule_name}",
        )
        await self.bot.send_log(
            message.guild,
            LogType.MOD,
            f"AutoMod - {rule_name}",
            "Aegis detected a moderation rule violation.",
            tone="warning",
            fields=[
                ("User", format_identity(message.author)),
                ("Channel", message.channel.mention),
                ("Strikes Added", str(strikes)),
                ("Reason", rule_reason),
                ("Message", truncate(message.content or "[no text]")),
            ],
        )

    # ── Core ──────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Aegis online as {self.bot.user} ({self.bot.user.id})")

        for guild in self.bot.guilds:
            if guild.id in self._snapshot_warmup_guild_ids:
                continue
            self._snapshot_warmup_guild_ids.add(guild.id)
            asyncio.create_task(self._warmup_guild_message_snapshots(guild))

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context[AegisBot], error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        error = getattr(error, "original", error)
        title = f"{FAILURE_EMOJI} Command Error"
        description = "Aegis could not complete that command."
        tone = "danger"
        show_usage = False

        if isinstance(error, commands.MissingRequiredArgument):
            description = f"Missing argument: `{error.param.name}`"
            show_usage = True
        elif isinstance(error, commands.BadArgument):
            description = str(error)
            show_usage = True
        elif isinstance(error, commands.MissingPermissions):
            description = "You do not have permission to use that command."
        elif isinstance(error, commands.NoPrivateMessage):
            description = "That command only works in servers."
        elif isinstance(error, discord.Forbidden):
            description = "Aegis is missing a Discord permission needed to finish that action."
        else:
            description = str(error)

        signature = ""
        if show_usage and ctx.command:
            signature = f"`{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.command.signature}`".strip()

        await ctx.send(
            view=build_panel(
                title,
                description,
                tone=tone,
                accented=False,
                fields=[("Usage", signature)] if signature else [],
            )
        )

    # ── AutoMod (on_message) ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return

        self.bot.cache_message_snapshot(message)
        await self._persist_snapshot_safe(
            message_id=message.id,
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            author_display=format_identity(message.author),
            content=message.content,
        )

        if message.author.bot:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return

        if await self.bot.is_automod_exempt(member, message.channel):
            return

        settings = await self.bot.db.fetch_guild_settings(message.guild.id)
        content = message.content or ""
        lowered_content = content.lower()
        decision = AutoModDecision()

        filters = await self.bot.db.list_automod_filters(message.guild.id)
        invite_whitelist = set(await self.bot.db.list_invite_whitelist_targets(message.guild.id))

        if settings.duplicate_strike_threshold:
            occurrences = self.bot.register_duplicate_message(message)
            if (
                settings.duplicate_delete_threshold is not None
                and occurrences == settings.duplicate_delete_threshold
            ):
                decision.warning_text = "Please stop spamming."
                decision.delete_message = True
            elif (
                settings.duplicate_delete_threshold is not None
                and occurrences > settings.duplicate_delete_threshold
            ):
                decision.delete_message = True

            if occurrences >= settings.duplicate_strike_threshold:
                self._add_decision(
                    decision,
                    rule_name="Duplicate Spam",
                    reason=f"Repeated message spam detected ({occurrences} copies).",
                    strikes=settings.duplicate_strikes,
                    delete_message=decision.delete_message,
                )

        if settings.max_lines:
            line_count = len(content.split("\n")) if content else 1
            if line_count > settings.max_lines:
                line_delta = line_count - settings.max_lines
                strikes = max((line_delta + settings.max_lines - 1) // settings.max_lines, 1)
                self._add_decision(
                    decision,
                    rule_name="Max Lines",
                    reason=f"Message exceeded the line limit of {settings.max_lines} (found {line_count}).",
                    strikes=strikes,
                )

        if settings.anti_copypasta_strikes:
            copypasta_name = self._find_copypasta_name(content)
            if copypasta_name is not None:
                self._add_decision(
                    decision,
                    rule_name="Anti Copypasta",
                    reason=f"{copypasta_name} copypasta detected.",
                    strikes=settings.anti_copypasta_strikes,
                )

        if settings.anti_everyone_strikes and self._contains_everyone_ping(message):
            self._add_decision(
                decision,
                rule_name="Anti Everyone",
                reason="Attempted @everyone/@here mention abuse.",
                strikes=settings.anti_everyone_strikes,
            )

        if settings.anti_invite_strikes and INVITE_RE.search(content):
            if await self._contains_external_invite(message, content, invite_whitelist):
                self._add_decision(
                    decision,
                    rule_name="Anti Invite",
                    reason="Discord invite advertisement detected.",
                    strikes=settings.anti_invite_strikes,
                )

        member_mentions = {
            mentioned.id
            for mentioned in message.mentions
            if not mentioned.bot and mentioned.id != member.id
        }
        if settings.max_mentions and settings.max_mentions >= MENTION_MINIMUM and len(member_mentions) > settings.max_mentions:
            extra_mentions = len(member_mentions) - settings.max_mentions
            self._add_decision(
                decision,
                rule_name="Max Mentions",
                reason=f"Mentioning {len(member_mentions)} users (max {settings.max_mentions}).",
                strikes=max(extra_mentions, 1),
            )

        role_mentions = len(set(message.role_mentions))
        if (
            settings.max_role_mentions
            and settings.max_role_mentions >= ROLE_MENTION_MINIMUM
            and role_mentions > settings.max_role_mentions
        ):
            extra_mentions = role_mentions - settings.max_role_mentions
            self._add_decision(
                decision,
                rule_name="Max Role Mentions",
                reason=f"Mentioning {role_mentions} roles (max {settings.max_role_mentions}).",
                strikes=max(extra_mentions, 1),
            )

        if settings.anti_referral_strikes and self._contains_referral_link(content):
            self._add_decision(
                decision,
                rule_name="Anti Referral",
                reason="Referral or suspicious redirect link detected.",
                strikes=settings.anti_referral_strikes,
            )

        matched_filter = self._find_matching_filter(filters, lowered_content)
        if matched_filter is not None:
            self._add_decision(
                decision,
                rule_name="Filter",
                reason=f"'{matched_filter.name}' filter matched.",
                strikes=matched_filter.strikes,
            )

        if (
            not decision.delete_message
            and settings.resolve_urls
            and (settings.anti_invite_strikes != 0 or settings.anti_referral_strikes != 0)
            and URL_RE.search(content)
        ):
            resolved_invite, resolved_referral = await self._check_resolved_links(
                message,
                content,
                detect_invites=settings.anti_invite_strikes != 0,
                detect_referrals=settings.anti_referral_strikes != 0,
                invite_whitelist=invite_whitelist,
            )
            if resolved_invite:
                self._add_decision(
                    decision,
                    rule_name="Resolve Links",
                    reason="Invite advertisement detected through redirected URL.",
                    strikes=settings.anti_invite_strikes,
                )
            if resolved_referral:
                self._add_decision(
                    decision,
                    rule_name="Resolve Links",
                    reason="Referral link detected through redirected URL.",
                    strikes=settings.anti_referral_strikes,
                )

        if decision.warning_text:
            try:
                warning_message = await message.channel.send(f"{message.author.mention} {decision.warning_text}")
                await warning_message.delete(delay=2.5)
            except discord.HTTPException:
                pass

        if decision.delete_message:
            await self._delete_message_safely(message)

        if decision.delete_message and decision.strikes <= 0:
            reason_text = ", ".join(decision.reasons)
            await self.bot.send_log(
                message.guild,
                LogType.MOD,
                "AutoMod Message Removed",
                "Aegis removed a message for an AutoMod rule configured as delete-only.",
                tone="warning",
                fields=[
                    ("User", format_identity(message.author)),
                    ("Channel", message.channel.mention),
                    ("Rules", "\n".join(decision.rule_names[:8])),
                    ("Strikes Added", "0"),
                    ("Reason", truncate(reason_text, 700)),
                    ("Message", truncate(content or "[no text]")),
                ],
            )
            return

        if decision.strikes <= 0:
            return

        reason_text = ", ".join(decision.reasons)
        await self.bot.apply_strikes(
            message.guild,
            message.author,
            decision.strikes,
            reason_text,
            moderator=self.bot.user,
            source="AutoMod",
        )
        await self.bot.send_log(
            message.guild,
            LogType.MOD,
            "AutoMod Violation",
            "Aegis detected one or more AutoMod rule violations.",
            tone="warning",
            fields=[
                ("User", format_identity(message.author)),
                ("Channel", message.channel.mention),
                ("Rules", "\n".join(decision.rule_names[:8])),
                ("Strikes Added", str(decision.strikes)),
                ("Reason", truncate(reason_text, 700)),
                ("Message", truncate(content or "[no text]")),
            ],
        )

    # ── Message Logs ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        channel = guild.get_channel_or_thread(payload.channel_id)
        channel_mention = channel.mention if channel else f"`{payload.channel_id}`"

        message = payload.cached_message
        snapshot = self.bot.pop_message_snapshot(payload.message_id)
        if message is None and snapshot is None:
            snapshot = await self.bot.fetch_persisted_message_snapshot(payload.message_id)

        target_author_id: int | None = None
        author_text = "Unknown"
        content_text: str | None = None

        if message is not None:
            target_author_id = message.author.id
            author_text = format_identity(message.author)
            content_text = message.content or "[no text]"
        elif snapshot is not None:
            target_author_id = snapshot.author_id
            author_text = snapshot.author_display
            content_text = snapshot.content

        if target_author_id is not None and author_text == "Unknown":
            author_text = f"<@{target_author_id}> (`{target_author_id}`)"

        deleted_by = None

        if guild.me and guild.me.guild_permissions.view_audit_log:
            try:
                # Delay slightly to allow audit log to generate or update
                await asyncio.sleep(1.0)
                cutoff = utcnow() - timedelta(seconds=20)
                async for entry in guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=8):
                    if entry.created_at < cutoff:
                        continue

                    extra_channel = getattr(getattr(entry, "extra", None), "channel", None)
                    if extra_channel is None or extra_channel.id != payload.channel_id:
                        continue

                    target = getattr(entry, "target", None)
                    if target_author_id is not None:
                        if target is None or target.id != target_author_id:
                            continue
                    else:
                        if target is None:
                            continue
                        target_author_id = target.id
                        author_text = format_identity(target)

                    deleted_by = entry.user
                    break
            except discord.Forbidden:
                pass

        # Skip logging Aegis's own messages if self-deleted
        if target_author_id == self.bot.user.id and (deleted_by is None or deleted_by.id == self.bot.user.id):
            await self.bot.drop_persisted_message_snapshot(payload.message_id)
            return

        if content_text is not None:
            fields = [
                ("Author", author_text),
                ("Channel", channel_mention),
                ("Content", truncate(content_text)),
            ]
            if deleted_by and deleted_by.id != target_author_id:
                fields.append(("Deleted By", format_identity(deleted_by)))

            await self.bot.send_log(
                guild,
                LogType.MESSAGE,
                "Message Deleted",
                "A message was deleted.",
                tone="warning",
                fields=fields,
            )
        else:
            fields = [
                ("Message ID", f"`{payload.message_id}`"),
                ("Author", author_text),
                ("Channel", channel_mention),
            ]
            if deleted_by and deleted_by.id != target_author_id:
                fields.append(("Deleted By", format_identity(deleted_by)))

            await self.bot.send_log(
                guild,
                LogType.MESSAGE,
                "Message Deleted",
                "A message was deleted (uncached — no content available).",
                tone="warning",
                fields=fields,
            )

        await self.bot.drop_persisted_message_snapshot(payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        channel = guild.get_channel_or_thread(payload.channel_id)
        channel_mention = channel.mention if channel else f"`{payload.channel_id}`"

        message_ids = list(payload.message_ids)
        records = await self._collect_bulk_delete_records(payload)
        archive_files, view_filename, download_filename = self._build_bulk_delete_archive_files(
            guild,
            payload.channel_id,
            channel_mention,
            message_ids,
            records,
        )

        for message_id in message_ids:
            self.bot.pop_message_snapshot(message_id)

        timestamp_value = format_timestamp(utcnow())
        base_fields = [
            ("Archive", "Resolving archive links..."),
            ("Channel", channel_mention),
            ("Deleted", str(len(payload.message_ids))),
            ("Recovered", str(len(records))),
            ("Timestamp", timestamp_value),
        ]

        settings = await self.bot.db.fetch_guild_settings(guild.id)
        channel_id = getattr(settings, LogType.MESSAGE.value)
        if channel_id is None:
            await self.bot.drop_persisted_message_snapshots(message_ids)
            return

        log_channel = guild.get_channel_or_thread(channel_id)
        if log_channel is None:
            await self.bot.drop_persisted_message_snapshots(message_ids)
            return

        try:
            log_message = await log_channel.send(content="Preparing bulk archive...", files=archive_files)
        except discord.HTTPException:
            await self.bot.drop_persisted_message_snapshots(message_ids)
            return

        if log_message is not None:
            view_url, download_url = await self._resolve_archive_attachment_urls(
                log_message,
                view_filename,
                download_filename,
            )
            fallback_url = log_message.jump_url

            if view_url and download_url:
                archive_value = f"[View]({view_url})\n[Download]({download_url})"
            elif view_url:
                archive_value = f"[View]({view_url})"
            elif download_url:
                archive_value = f"[Download]({download_url})"
            else:
                archive_value = f"Archive files attached below.\n[Open Message]({fallback_url})"

            actions: list[tuple[str, str]] = []
            if view_url:
                actions.append(("View", view_url))
            if download_url:
                actions.append(("Download", download_url))

            panel_view = build_panel(
                "Bulk Message Delete",
                "Multiple messages were deleted in one action.",
                tone="warning",
                fields=[(name, value if name != "Archive" else archive_value) for name, value in base_fields],
                actions=actions,
            )

            attachments_to_keep = list(log_message.attachments)
            if not attachments_to_keep:
                cached_message = discord.utils.find(
                    lambda cached: cached.id == log_message.id,
                    self.bot.cached_messages,
                )
                if cached_message is not None and cached_message.attachments:
                    attachments_to_keep = list(cached_message.attachments)

            if not attachments_to_keep:
                try:
                    refreshed = await log_message.channel.fetch_message(log_message.id)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    refreshed = None
                if refreshed is not None and refreshed.attachments:
                    attachments_to_keep = list(refreshed.attachments)

            try:
                if attachments_to_keep:
                    await log_message.edit(
                        content=None,
                        embed=None,
                        view=panel_view,
                        attachments=attachments_to_keep,
                    )
                else:
                    await log_message.edit(content=None, embed=None, view=panel_view)
            except discord.HTTPException:
                pass

        await self.bot.drop_persisted_message_snapshots(message_ids)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        channel = guild.get_channel_or_thread(payload.channel_id)
        channel_mention = channel.mention if channel else f"`{payload.channel_id}`"

        before_message = payload.cached_message
        snapshot = self.bot.get_message_snapshot(payload.message_id) if before_message is None else None
        if before_message is None and snapshot is None:
            snapshot = await self.bot.fetch_persisted_message_snapshot(payload.message_id)

        new_content = payload.data.get("content")
        if new_content is None:
            return  # Embed-only update, skip

        after_content = new_content or "[no text]"
        before_content: str | None = None
        author_text = "Unknown"
        author_id: int | None = None

        if before_message is not None:
            before_content = before_message.content or "[no text]"
            author_text = format_identity(before_message.author)
            author_id = before_message.author.id
            self.bot.cache_message_snapshot(before_message)
        elif snapshot is not None:
            before_content = snapshot.content
            author_text = snapshot.author_display
            author_id = snapshot.author_id
        else:
            author_data = payload.data.get("author", {})
            author_name = author_data.get("username")
            author_id_raw = author_data.get("id")
            if isinstance(author_id_raw, int):
                author_id = author_id_raw
            elif isinstance(author_id_raw, str) and author_id_raw.isdigit():
                author_id = int(author_id_raw)

            if author_name and author_id is not None:
                author_text = f"{author_name} (`{author_id}`)"
            elif author_id is not None:
                author_text = f"<@{author_id}> (`{author_id}`)"

        if before_content is not None and before_content == after_content:
            self.bot.update_message_snapshot_content(payload.message_id, after_content)
            if isinstance(author_id, int):
                await self._persist_snapshot_safe(
                    message_id=payload.message_id,
                    guild_id=guild.id,
                    channel_id=payload.channel_id,
                    author_id=author_id,
                    author_display=author_text,
                    content=after_content,
                )
            return

        if before_content is not None:
            await self.bot.send_log(
                guild,
                LogType.MESSAGE,
                "Message Edited",
                "A message was edited.",
                tone="info",
                fields=[
                    ("Author", author_text),
                    ("Channel", channel_mention),
                    ("Before", truncate(before_content)),
                    ("After", truncate(after_content)),
                ],
            )
        else:
            await self.bot.send_log(
                guild,
                LogType.MESSAGE,
                "Message Edited",
                "A message was edited (uncached — no previous content).",
                tone="info",
                fields=[
                    ("Author", author_text),
                    ("Channel", channel_mention),
                    ("New Content", truncate(after_content)),
                ],
            )

        if isinstance(author_id, int):
            self.bot.cache_message_snapshot_data(
                message_id=payload.message_id,
                guild_id=guild.id,
                channel_id=payload.channel_id,
                author_id=author_id,
                author_display=author_text,
                content=after_content,
            )
            await self._persist_snapshot_safe(
                message_id=payload.message_id,
                guild_id=guild.id,
                channel_id=payload.channel_id,
                author_id=author_id,
                author_display=author_text,
                content=after_content,
            )

    # ── Server Logs ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            await self.bot.send_log(
                member.guild,
                LogType.SERVER,
                "Bot Joined",
                "A bot joined the server.",
                tone="info",
                fields=[("Member", format_identity(member))],
            )
            return

        settings = await self.bot.db.fetch_guild_settings(member.guild.id)
        previous_attempt_age = self._seconds_since_last_join_attempt(member.guild.id)
        self._record_last_join_attempt(member.guild.id)

        if settings.raid_mode_enabled:
            if (
                settings.anti_raid_joins
                and settings.anti_raid_seconds
                and previous_attempt_age is not None
                and previous_attempt_age > RAIDMODE_AUTO_DISABLE_SECONDS
            ):
                await self.bot.toggle_raid_mode(
                    member.guild,
                    False,
                    reason="No recent join attempts",
                    moderator=self.bot.user,
                    automatic=True,
                )
                settings = await self.bot.db.fetch_guild_settings(member.guild.id)

        if settings.raid_mode_enabled:
            await self.bot.notify_user(
                member,
                "Server Locked Down",
                f"**{member.guild.name}** is currently in raid mode, so new joins are blocked.",
                tone="danger",
            )
            try:
                await member.kick(reason="Aegis raid mode lockdown.")
            except discord.HTTPException:
                return

            await self.bot.send_log(
                member.guild,
                LogType.SERVER,
                "Raid Mode Blocked Join",
                "Aegis removed a new join while raid mode was active.",
                tone="danger",
                fields=[("User", format_identity(member))],
            )
            return

        if settings.anti_raid_joins and settings.anti_raid_seconds:
            join_count = self.bot.register_join(
                member.guild.id,
                window_seconds=settings.anti_raid_seconds,
            )
            if join_count >= settings.anti_raid_joins:
                await self.bot.toggle_raid_mode(
                    member.guild,
                    True,
                    reason=f"{join_count} joins in {settings.anti_raid_seconds}s",
                    moderator=self.bot.user,
                    automatic=True,
                )

        await self._maybe_dehoist_member(member)

        await self.bot.send_log(
            member.guild,
            LogType.SERVER,
            "Member Joined",
            "A new member joined the server.",
            tone="success",
            fields=[
                ("Member", format_identity(member)),
                ("Account Created", format_timestamp(member.created_at)),
            ],
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.bot.send_log(
            member.guild,
            LogType.SERVER,
            "Member Left",
            "A member left or was removed from the server.",
            tone="neutral",
            fields=[("Member", format_identity(member))],
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.bot.send_log(
            guild,
            LogType.SERVER,
            "Member Banned",
            "A member was banned from the server.",
            tone="danger",
            fields=[("User", format_identity(user))],
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.bot.send_log(
            guild,
            LogType.SERVER,
            "Member Unbanned",
            "A member was unbanned from the server.",
            tone="success",
            fields=[("User", format_identity(user))],
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.display_name != after.display_name:
            await self._maybe_dehoist_member(after)

        # Nickname change
        if before.nick != after.nick:
            await self.bot.send_log(
                after.guild,
                LogType.SERVER,
                "Nickname Changed",
                "A member's nickname was updated.",
                tone="info",
                fields=[
                    ("Member", format_identity(after)),
                    ("Before", before.nick or "None"),
                    ("After", after.nick or "None"),
                ],
            )

        # Role changes
        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        if added_roles:
            await self.bot.send_log(
                after.guild,
                LogType.SERVER,
                "Roles Added",
                "Roles were added to a member.",
                tone="info",
                fields=[
                    ("Member", format_identity(after)),
                    ("Added", ", ".join(role.mention for role in added_roles)),
                ],
            )

        if removed_roles:
            await self.bot.send_log(
                after.guild,
                LogType.SERVER,
                "Roles Removed",
                "Roles were removed from a member.",
                tone="warning",
                fields=[
                    ("Member", format_identity(after)),
                    ("Removed", ", ".join(role.mention for role in removed_roles)),
                ],
            )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes: list[tuple[str, str]] = []

        if before.name != after.name:
            changes.append(("Name", f"{before.name} → {after.name}"))

        if before.icon != after.icon:
            old_icon = f"[Link]({before.icon.url})" if before.icon else "None"
            new_icon = f"[Link]({after.icon.url})" if after.icon else "Removed"
            changes.append(("Icon", f"{old_icon} → {new_icon}"))

        if before.banner != after.banner:
            old_banner = f"[Link]({before.banner.url})" if before.banner else "None"
            new_banner = f"[Link]({after.banner.url})" if after.banner else "Removed"
            changes.append(("Banner", f"{old_banner} → {new_banner}"))

        if before.description != after.description:
            changes.append(("Description", f"{truncate(before.description or 'None')} → {truncate(after.description or 'None')}"))

        if before.owner_id != after.owner_id:
            changes.append(("Owner", f"`{before.owner_id}` → `{after.owner_id}`"))

        if before.verification_level != after.verification_level:
            changes.append(("Verification Level", f"{before.verification_level.name} → {after.verification_level.name}"))

        if before.default_notifications != after.default_notifications:
            changes.append(("Default Notifications", f"{before.default_notifications.name} → {after.default_notifications.name}"))

        if before.explicit_content_filter != after.explicit_content_filter:
            changes.append(("Content Filter", f"{before.explicit_content_filter.name} → {after.explicit_content_filter.name}"))

        if before.afk_channel != after.afk_channel:
            old_afk = before.afk_channel.mention if before.afk_channel else "None"
            new_afk = after.afk_channel.mention if after.afk_channel else "None"
            changes.append(("AFK Channel", f"{old_afk} → {new_afk}"))

        if before.system_channel != after.system_channel:
            old_sys = before.system_channel.mention if before.system_channel else "None"
            new_sys = after.system_channel.mention if after.system_channel else "None"
            changes.append(("System Channel", f"{old_sys} → {new_sys}"))

        if before.vanity_url_code != after.vanity_url_code:
            changes.append(("Vanity URL", f"`{before.vanity_url_code or 'None'}` → `{after.vanity_url_code or 'None'}`"))

        if not changes:
            return

        await self.bot.send_log(
            after,
            LogType.SERVER,
            "Server Updated",
            "Server settings were changed.",
            tone="info",
            fields=changes,
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self.bot.send_log(
            role.guild,
            LogType.SERVER,
            "Role Created",
            "A new role was created.",
            tone="success",
            fields=[
                ("Role", role.mention),
                ("ID", f"`{role.id}`"),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.bot.send_log(
            role.guild,
            LogType.SERVER,
            "Role Deleted",
            "A role was deleted.",
            tone="danger",
            fields=[
                ("Role", role.name),
                ("ID", f"`{role.id}`"),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changes: list[tuple[str, str]] = []

        if before.name != after.name:
            changes.append(("Name", f"{before.name} → {after.name}"))
        if before.color != after.color:
            changes.append(("Color", f"`{before.color}` → `{after.color}`"))
        if before.hoist != after.hoist:
            changes.append(("Hoisted", f"{before.hoist} → {after.hoist}"))
        if before.mentionable != after.mentionable:
            changes.append(("Mentionable", f"{before.mentionable} → {after.mentionable}"))
        if before.permissions != after.permissions:
            changes.append(("Permissions", "Updated"))

        if not changes:
            return

        await self.bot.send_log(
            after.guild,
            LogType.SERVER,
            "Role Updated",
            "A role was modified.",
            tone="info",
            fields=[("Role", after.mention)] + changes,
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self.bot.send_log(
            channel.guild,
            LogType.SERVER,
            "Channel Created",
            "A new channel was created.",
            tone="success",
            fields=[
                ("Channel", channel.mention),
                ("Type", str(channel.type).replace("_", " ").title()),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.bot.send_log(
            channel.guild,
            LogType.SERVER,
            "Channel Deleted",
            "A channel was deleted.",
            tone="danger",
            fields=[
                ("Channel", channel.name),
                ("Type", str(channel.type).replace("_", " ").title()),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        changes: list[tuple[str, str]] = []

        if before.name != after.name:
            changes.append(("Name", f"{before.name} → {after.name}"))
        if hasattr(before, "topic") and hasattr(after, "topic"):
            if before.topic != after.topic:
                changes.append(("Topic", f"{truncate(before.topic or 'None')} → {truncate(after.topic or 'None')}"))
        if hasattr(before, "slowmode_delay") and hasattr(after, "slowmode_delay"):
            if before.slowmode_delay != after.slowmode_delay:
                changes.append(("Slowmode", f"{before.slowmode_delay}s → {after.slowmode_delay}s"))
        if hasattr(before, "nsfw") and hasattr(after, "nsfw"):
            if before.nsfw != after.nsfw:
                changes.append(("NSFW", f"{before.nsfw} → {after.nsfw}"))

        if not changes:
            return

        await self.bot.send_log(
            after.guild,
            LogType.SERVER,
            "Channel Updated",
            "A channel was modified.",
            tone="info",
            fields=[("Channel", after.mention)] + changes,
        )

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: list[discord.Emoji],
        after: list[discord.Emoji],
    ) -> None:
        before_set = {e.id for e in before}
        after_set = {e.id for e in after}

        added = [e for e in after if e.id not in before_set]
        removed = [e for e in before if e.id not in after_set]

        if added:
            await self.bot.send_log(
                guild,
                LogType.SERVER,
                "Emojis Added",
                "New emojis were added to the server.",
                tone="success",
                fields=[("Emojis", " ".join(str(e) for e in added[:15]))],
            )

        if removed:
            await self.bot.send_log(
                guild,
                LogType.SERVER,
                "Emojis Removed",
                "Emojis were removed from the server.",
                tone="warning",
                fields=[("Emojis", ", ".join(e.name for e in removed[:15]))],
            )

    # ── Voice Logs ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # --- Voicemove session handling ---
        if member.id == self.bot.user.id and before.channel != after.channel:
            sessions = getattr(self.bot, "voicemove_sessions", {})
            session = sessions.get(member.guild.id)

            if session is not None:
                old_channel = before.channel
                new_channel = after.channel

                if new_channel is None:
                    sessions.pop(member.guild.id, None)
                elif old_channel is not None and new_channel is not None and old_channel.id != new_channel.id:
                    members_to_move = [
                        m for m in old_channel.members
                        if m.id != self.bot.user.id
                    ]

                    for target in members_to_move:
                        try:
                            await target.move_to(
                                new_channel,
                                reason="Aegis voicemove: dragged to new channel.",
                            )
                        except discord.HTTPException:
                            pass

                    session["channel_id"] = new_channel.id

        # --- Voice channel join / leave / move ---
        if before.channel != after.channel:
            if before.channel is None and after.channel is not None:
                await self.bot.send_log(
                    member.guild,
                    LogType.VOICE,
                    "Voice Join",
                    "A member joined a voice channel.",
                    tone="success",
                    fields=[
                        ("Member", format_identity(member)),
                        ("Channel", after.channel.mention),
                    ],
                )
            elif before.channel is not None and after.channel is None:
                await self.bot.send_log(
                    member.guild,
                    LogType.VOICE,
                    "Voice Leave",
                    "A member left a voice channel.",
                    tone="warning",
                    fields=[
                        ("Member", format_identity(member)),
                        ("Channel", before.channel.mention),
                    ],
                )
            elif before.channel is not None and after.channel is not None:
                await self.bot.send_log(
                    member.guild,
                    LogType.VOICE,
                    "Voice Move",
                    "A member moved between voice channels.",
                    tone="info",
                    fields=[
                        ("Member", format_identity(member)),
                        ("From", before.channel.mention),
                        ("To", after.channel.mention),
                    ],
                )

        # --- Server mute / unmute ---
        if before.mute != after.mute:
            state = "Muted" if after.mute else "Unmuted"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                f"Server {state}",
                f"A member was server {state.lower()}.",
                tone="warning" if after.mute else "success",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )

        # --- Server deafen / undeafen ---
        if before.deaf != after.deaf:
            state = "Deafened" if after.deaf else "Undeafened"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                f"Server {state}",
                f"A member was server {state.lower()}.",
                tone="warning" if after.deaf else "success",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )

        # --- Self mute ---
        if before.self_mute != after.self_mute:
            state = "Self Muted" if after.self_mute else "Self Unmuted"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                state,
                f"A member {state.lower()}.",
                tone="info",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )

        # --- Self deafen ---
        if before.self_deaf != after.self_deaf:
            state = "Self Deafened" if after.self_deaf else "Self Undeafened"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                state,
                f"A member {state.lower()}.",
                tone="info",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )

        # --- Streaming ---
        if before.self_stream != after.self_stream:
            state = "Started Streaming" if after.self_stream else "Stopped Streaming"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                state,
                f"A member {state.lower()}.",
                tone="info",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )

        # --- Camera / Video ---
        if before.self_video != after.self_video:
            state = "Camera On" if after.self_video else "Camera Off"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                state,
                f"A member turned their camera {'on' if after.self_video else 'off'}.",
                tone="info",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )

        # --- Stage suppress ---
        if before.suppress != after.suppress:
            state = "Suppressed" if after.suppress else "Became Speaker"
            await self.bot.send_log(
                member.guild,
                LogType.VOICE,
                state,
                f"A member was {state.lower()} in a stage channel.",
                tone="info",
                fields=[
                    ("Member", format_identity(member)),
                    ("Channel", after.channel.mention if after.channel else "N/A"),
                ],
            )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(EventsCog(bot))

