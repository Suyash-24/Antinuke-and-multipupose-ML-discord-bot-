from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

import discord
from discord.ext import commands

from aegis.bot import AegisBot
from aegis.checks import require_moderation
from aegis.converters import DurationConverter
from aegis.models import LogType
from aegis.ui import build_panel
from aegis.utils import format_identity, humanize_duration, truncate, unique_by_id, utcnow

SUCCESS_EMOJI = "<:success:1414275742870798538>"
FAILURE_EMOJI = "<:failed:1488505866935078922>"


class ModerationCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot

    def _audit_reason(self, actor: discord.abc.User, reason: str) -> str:
        return truncate(f"{actor} ({actor.id}): {reason}", 450)

    def _check_member_target(self, ctx: commands.Context[AegisBot], member: discord.Member) -> str | None:
        if member.id == ctx.author.id:
            return "You cannot moderate yourself."
        if member.id == self.bot.user.id:
            return "You cannot moderate Aegis."
        if member.id == ctx.guild.owner_id:
            return "You cannot moderate the server owner."
        if ctx.guild.owner_id != ctx.author.id and member.top_role >= ctx.author.top_role:
            return "Your role is not high enough to moderate that member."
        if ctx.me is not None and member.top_role >= ctx.me.top_role:
            return "My role is not high enough to moderate that member."
        return None

    def _check_user_target(
        self,
        ctx: commands.Context[AegisBot],
        user: discord.User | discord.Member,
    ) -> str | None:
        member = ctx.guild.get_member(user.id)
        if member is None:
            return None
        return self._check_member_target(ctx, member)

    async def _send_summary(
        self,
        ctx: commands.Context[AegisBot],
        title: str,
        description: str,
        successes: list[str],
        failures: list[str],
    ) -> None:
        lines: list[str] = []
        lines.extend(f"{SUCCESS_EMOJI} {entry}" for entry in successes[:10])
        lines.extend(f"{FAILURE_EMOJI} {entry}" for entry in failures[:10])

        if not lines:
            lines.append(f"{FAILURE_EMOJI} No members were processed.")

        extra = max(0, len(successes) + len(failures) - len(lines))
        if extra:
            lines.append(f"...and {extra} more result(s).")

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(discord.ui.TextDisplay("\n".join(lines))))
        await ctx.send(view=view)

    @commands.command()
    @require_moderation("kick_members")
    async def kick(
        self,
        ctx: commands.Context[AegisBot],
        members: commands.Greedy[discord.Member],
        *,
        reason: str = "No reason provided",
    ) -> None:
        members = unique_by_id(members)
        if not members:
            if reason != "No reason provided":
                raise commands.BadArgument("Please provide a valid user.")
            raise commands.BadArgument("Provide at least one member to kick.")

        await self.bot.enforce_high_risk_command_policy(ctx, target_count=len(members))

        successes: list[str] = []
        failures: list[str] = []
        for member in members:
            failure = self._check_member_target(ctx, member)
            if failure:
                failures.append(f"{member}: {failure}")
                continue

            try:
                await self.bot.notify_user(
                    member,
                    "You Were Kicked",
                    f"You were removed from **{ctx.guild.name}**.",
                    tone="danger",
                    fields=[("Reason", reason), ("Moderator", format_identity(ctx.author))],
                )
                await member.kick(reason=self._audit_reason(ctx.author, reason))
                await self.bot.record_case(ctx.guild, member, ctx.author, "kick", reason)
                successes.append(str(member))
            except discord.HTTPException as error:
                failures.append(f"{member}: {error}")

        lines: list[str] = []
        lines.extend(f"{SUCCESS_EMOJI} **{member}** was kicked." for member in successes[:10])
        lines.extend(f"{FAILURE_EMOJI} {failure}" for failure in failures[:10])

        if not lines:
            lines.append(f"{FAILURE_EMOJI} No members were processed.")

        extra = max(0, len(successes) + len(failures) - len(lines))
        if extra:
            lines.append(f"...and {extra} more result(s).")

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(discord.ui.TextDisplay("\n".join(lines))))
        await ctx.send(view=view)

    @commands.command()
    @require_moderation("ban_members")
    async def ban(
        self,
        ctx: commands.Context[AegisBot],
        users: commands.Greedy[discord.User],
        duration: Optional[DurationConverter] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        users = unique_by_id(users)
        if not users:
            if reason != "No reason provided":
                raise commands.BadArgument("Provide a valid user.")
            raise commands.BadArgument("Provide at least one user to ban.")

        await self.bot.enforce_high_risk_command_policy(ctx, target_count=len(users))

        expires_at = utcnow() + duration if duration else None
        successes: list[str] = []
        failures: list[str] = []

        for user in users:
            failure = self._check_user_target(ctx, user)
            if failure:
                failures.append(f"{user}: {failure}")
                continue

            try:
                await self.bot.notify_user(
                    user,
                    "You Were Banned",
                    f"You were banned from **{ctx.guild.name}**.",
                    tone="danger",
                    fields=[
                        ("Reason", reason),
                        ("Duration", humanize_duration(duration) if duration else "Permanent"),
                        ("Moderator", format_identity(ctx.author)),
                    ],
                )
                await ctx.guild.ban(
                    user,
                    delete_message_seconds=21600,
                    reason=self._audit_reason(ctx.author, reason),
                )
                case_id = await self.bot.record_case(
                    ctx.guild,
                    user,
                    ctx.author,
                    "ban",
                    reason,
                    expires_at=expires_at,
                )
                if expires_at:
                    await self.bot.db.schedule_action(ctx.guild.id, user.id, "unban", expires_at, case_id)
                successes.append(f"**{user}** was banned.")
            except discord.HTTPException as error:
                failures.append(f"{user}: {error}")

        await self._send_summary(
            ctx,
            "Ban Complete",
            "Aegis finished the requested ban action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("ban_members")
    async def silentban(
        self,
        ctx: commands.Context[AegisBot],
        users: commands.Greedy[discord.User],
        duration: Optional[DurationConverter] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        users = unique_by_id(users)
        if not users:
            if reason != "No reason provided":
                raise commands.BadArgument("Provide a valid user.")
            raise commands.BadArgument("Provide at least one user to ban.")

        await self.bot.enforce_high_risk_command_policy(ctx, target_count=len(users))

        expires_at = utcnow() + duration if duration else None
        successes: list[str] = []
        failures: list[str] = []

        for user in users:
            failure = self._check_user_target(ctx, user)
            if failure:
                failures.append(f"{user}: {failure}")
                continue

            try:
                await self.bot.notify_user(
                    user,
                    "You Were Banned",
                    f"You were banned from **{ctx.guild.name}**.",
                    tone="danger",
                    fields=[
                        ("Reason", reason),
                        ("Duration", humanize_duration(duration) if duration else "Permanent"),
                        ("Moderator", format_identity(ctx.author)),
                    ],
                )
                await ctx.guild.ban(
                    user,
                    delete_message_seconds=0,
                    reason=self._audit_reason(ctx.author, reason),
                )
                case_id = await self.bot.record_case(
                    ctx.guild,
                    user,
                    ctx.author,
                    "silentban",
                    reason,
                    expires_at=expires_at,
                )
                if expires_at:
                    await self.bot.db.schedule_action(ctx.guild.id, user.id, "unban", expires_at, case_id)
                successes.append(f"**{user}** was banned.")
            except discord.HTTPException as error:
                failures.append(f"{user}: {error}")

        await self._send_summary(
            ctx,
            "Silent Ban Complete",
            "Aegis finished the requested silent ban action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("ban_members")
    async def softban(
        self,
        ctx: commands.Context[AegisBot],
        users: commands.Greedy[discord.User],
        *,
        reason: str = "No reason provided",
    ) -> None:
        users = unique_by_id(users)
        if not users:
            if reason != "No reason provided":
                raise commands.BadArgument("Provide a valid user.")
            raise commands.BadArgument("Provide at least one user to softban.")

        await self.bot.enforce_high_risk_command_policy(ctx, target_count=len(users))

        successes: list[str] = []
        failures: list[str] = []
        for user in users:
            failure = self._check_user_target(ctx, user)
            if failure:
                failures.append(f"{user}: {failure}")
                continue

            member = ctx.guild.get_member(user.id)
            if member is None:
                failures.append(f"{user}: Softban requires the user to still be in the server.")
                continue

            try:
                await self.bot.notify_user(
                    user,
                    "You Were Softbanned",
                    f"Your recent messages were removed from **{ctx.guild.name}**.",
                    tone="danger",
                    fields=[("Reason", reason), ("Moderator", format_identity(ctx.author))],
                )
                await ctx.guild.ban(
                    user,
                    delete_message_seconds=21600,
                    reason=self._audit_reason(ctx.author, reason),
                )
                await ctx.guild.unban(user, reason="Aegis softban completion.")
                await self.bot.record_case(ctx.guild, user, ctx.author, "softban", reason)
                successes.append(f"**{user}** was softbanned.")
            except discord.HTTPException as error:
                failures.append(f"{user}: {error}")

        await self._send_summary(
            ctx,
            "Softban Complete",
            "Aegis finished the requested softban action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("ban_members")
    async def unban(
        self,
        ctx: commands.Context[AegisBot],
        users: commands.Greedy[discord.User],
        *,
        reason: str = "No reason provided",
    ) -> None:
        users = unique_by_id(users)
        if not users:
            if reason != "No reason provided":
                raise commands.BadArgument("Provide a valid user.")
            raise commands.BadArgument("Provide at least one user to unban.")

        successes: list[str] = []
        failures: list[str] = []
        for user in users:
            try:
                await ctx.guild.unban(user, reason=self._audit_reason(ctx.author, reason))
                await self.bot.db.clear_scheduled_actions(ctx.guild.id, user.id, "unban")
                await self.bot.record_case(ctx.guild, user, ctx.author, "unban", reason)
                successes.append(f"**{user}** was unbanned.")
            except discord.NotFound:
                failures.append(f"{user}: That user is not banned.")
            except discord.HTTPException as error:
                failures.append(f"{user}: {error}")

        await self._send_summary(
            ctx,
            "Unban Complete",
            "Aegis finished the requested unban action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("manage_roles")
    async def mute(
        self,
        ctx: commands.Context[AegisBot],
        members: commands.Greedy[discord.Member],
        duration: Optional[DurationConverter] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        muted_role = ctx.guild.get_role(settings.muted_role_id or 0) if settings.muted_role_id else None
        if muted_role is None:
            await ctx.send(
                view=build_panel(
                    "Mute Role Missing",
                    "Run `^setup muted` before using the mute system.",
                    tone="warning",
                    accented=False,
                )
            )
            return

        members = unique_by_id(members)
        if not members:
            raise commands.BadArgument("Provide at least one member to mute.")

        expires_at = utcnow() + duration if duration else None
        successes: list[str] = []
        failures: list[str] = []

        for member in members:
            failure = self._check_member_target(ctx, member)
            if failure:
                failures.append(f"{member}: {failure}")
                continue
            if muted_role in member.roles:
                failures.append(f"{member}: Already muted.")
                continue

            try:
                await self.bot.notify_user(
                    member,
                    "You Were Muted",
                    f"You lost send and voice permissions in **{ctx.guild.name}**.",
                    tone="warning",
                    fields=[
                        ("Reason", reason),
                        ("Duration", humanize_duration(duration) if duration else "Permanent"),
                        ("Moderator", format_identity(ctx.author)),
                    ],
                )
                await member.add_roles(muted_role, reason=self._audit_reason(ctx.author, reason))
                case_id = await self.bot.record_case(
                    ctx.guild,
                    member,
                    ctx.author,
                    "mute",
                    reason,
                    expires_at=expires_at,
                )
                if expires_at:
                    await self.bot.db.schedule_action(ctx.guild.id, member.id, "unmute", expires_at, case_id)
                successes.append(f"**{member}** was muted.")
            except discord.HTTPException as error:
                failures.append(f"{member}: {error}")

        await self._send_summary(
            ctx,
            "Mute Complete",
            "Aegis finished the requested mute action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("manage_roles")
    async def unmute(
        self,
        ctx: commands.Context[AegisBot],
        members: commands.Greedy[discord.Member],
        *,
        reason: str = "No reason provided",
    ) -> None:
        settings = await self.bot.db.fetch_guild_settings(ctx.guild.id)
        muted_role = ctx.guild.get_role(settings.muted_role_id or 0) if settings.muted_role_id else None
        if muted_role is None:
            raise commands.BadArgument("Aegis has no muted role configured yet.")

        members = unique_by_id(members)
        if not members:
            raise commands.BadArgument("Provide at least one member to unmute.")

        successes: list[str] = []
        failures: list[str] = []
        for member in members:
            failure = self._check_member_target(ctx, member)
            if failure:
                failures.append(f"{member}: {failure}")
                continue
            if muted_role not in member.roles:
                failures.append(f"{member}: Not muted.")
                continue

            try:
                await member.remove_roles(muted_role, reason=self._audit_reason(ctx.author, reason))
                await self.bot.db.clear_scheduled_actions(ctx.guild.id, member.id, "unmute")
                await self.bot.record_case(ctx.guild, member, ctx.author, "unmute", reason)
                successes.append(f"**{member}** was unmuted.")
            except discord.HTTPException as error:
                failures.append(f"{member}: {error}")

        await self._send_summary(
            ctx,
            "Unmute Complete",
            "Aegis finished the requested unmute action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("manage_messages")
    async def clean(
        self,
        ctx: commands.Context[AegisBot],
        *parameters: str,
    ) -> None:
        limit = 100
        user_ids: set[int] = set()
        text_filters: list[str] = []
        regex_filters: list[re.Pattern[str]] = []
        literal_flags = {
            "bots": False,
            "embeds": False,
            "links": False,
            "images": False,
        }

        member_converter = commands.MemberConverter()
        user_converter = commands.UserConverter()

        for raw_parameter in parameters:
            parameter = raw_parameter.strip()
            lowered = parameter.lower()

            if lowered in literal_flags:
                literal_flags[lowered] = True
                continue

            if parameter.isdigit():
                parsed_limit = int(parameter)
                if parsed_limit < 2 or parsed_limit > 1000:
                    raise commands.BadArgument("Clean amount must be between 2 and 1000.")
                limit = parsed_limit
                continue

            if parameter.startswith("`") and parameter.endswith("`") and len(parameter) > 2:
                pattern = parameter[1:-1]
                try:
                    regex_filters.append(re.compile(pattern, re.IGNORECASE))
                except re.error:
                    raise commands.BadArgument("Invalid regex pattern for clean filter.")
                continue

            try:
                member = await member_converter.convert(ctx, parameter)
                user_ids.add(member.id)
                continue
            except commands.BadArgument:
                pass

            try:
                user = await user_converter.convert(ctx, parameter)
                user_ids.add(user.id)
                continue
            except commands.BadArgument:
                pass

            text_filters.append(parameter.lower())

        has_filters = any(literal_flags.values()) or bool(user_ids) or bool(text_filters) or bool(regex_filters)
        link_re = re.compile(r"https?://|www\.", re.IGNORECASE)
        cutoff = discord.utils.utcnow() - timedelta(days=14)

        def has_image_content(message: discord.Message) -> bool:
            if message.attachments:
                return True
            for embed in message.embeds:
                if embed.image or embed.thumbnail or embed.video:
                    return True
            return False

        def matches_filters(message: discord.Message) -> bool:
            if message.id == ctx.message.id:
                return False

            if not has_filters:
                return True

            content = message.content or ""
            lowered_content = content.lower()

            if literal_flags["bots"] and message.author.bot:
                return True
            if literal_flags["embeds"] and bool(message.embeds):
                return True
            if literal_flags["links"] and link_re.search(content):
                return True
            if literal_flags["images"] and has_image_content(message):
                return True
            if user_ids and message.author.id in user_ids:
                return True
            if any(text in lowered_content for text in text_filters):
                return True
            if any(pattern.search(content) for pattern in regex_filters):
                return True

            return False

        older_filtered_matches = 0

        def check(message: discord.Message) -> bool:
            nonlocal older_filtered_matches

            if not matches_filters(message):
                return False
            if message.created_at < cutoff:
                older_filtered_matches += 1
                return False
            return True

        await self.bot.enforce_high_risk_command_policy(ctx, clean_amount=limit)

        try:
            deleted = await ctx.channel.purge(limit=limit + 1, check=check, bulk=True)
        except discord.HTTPException as error:
            view = discord.ui.LayoutView(timeout=None)
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(f"{FAILURE_EMOJI} Failed to clean messages: {error}")
                )
            )
            await ctx.send(view=view)
            return

        deleted_count = len(deleted)

        active_filters: list[str] = []
        if literal_flags["bots"]:
            active_filters.append("bots")
        if literal_flags["embeds"]:
            active_filters.append("embeds")
        if literal_flags["links"]:
            active_filters.append("links")
        if literal_flags["images"]:
            active_filters.append("images")
        if user_ids:
            active_filters.append(f"users({len(user_ids)})")
        if text_filters:
            active_filters.append(f"text({len(text_filters)})")
        if regex_filters:
            active_filters.append(f"regex({len(regex_filters)})")
        filter_summary = ", ".join(active_filters) if active_filters else "None"

        await self.bot.send_log(
            ctx.guild,
            LogType.MOD,
            "Messages Cleaned",
            "Aegis removed messages in bulk.",
            tone="warning",
            fields=[
                ("Channel", ctx.channel.mention),
                ("Deleted", str(deleted_count)),
                ("Scan Limit", str(limit)),
                ("Filters", filter_summary),
            ],
        )

        label = "message" if deleted_count == 1 else "messages"
        note = ""
        if older_filtered_matches > 0 and deleted_count < limit:
            note = "\nNote: Messages older than two weeks cannot be deleted."

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{SUCCESS_EMOJI} Successfully cleaned {deleted_count} {label}.{note}")
            )
        )
        await ctx.send(view=view)

    @commands.command()
    @require_moderation("move_members")
    async def voicekick(
        self,
        ctx: commands.Context[AegisBot],
        members: commands.Greedy[discord.Member],
        *,
        reason: str = "No reason provided",
    ) -> None:
        members = unique_by_id(members)
        if not members:
            if reason != "No reason provided":
                raise commands.BadArgument("Please give a valid user.")
            raise commands.BadArgument("Provide at least one member to disconnect from voice.")

        successes: list[str] = []
        failures: list[str] = []
        for member in members:
            failure = self._check_member_target(ctx, member)
            if failure:
                failures.append(f"{member}: {failure}")
                continue
            if member.voice is None or member.voice.channel is None:
                failures.append(f"{member}: Not connected to voice.")
                continue

            try:
                await member.move_to(None, reason=self._audit_reason(ctx.author, reason))
                case_id = await self.bot.record_case(ctx.guild, member, ctx.author, "voicekick", reason)
                successes.append(f"**Kicked** {member} from Voice")
            except discord.HTTPException as error:
                failures.append(f"Failed to kick {member} from Voice : {error}")

        await self._send_summary(
            ctx,
            "Voice Kick Complete",
            "Aegis finished the requested voice disconnect action.",
            successes,
            failures,
        )

    @commands.command()
    @require_moderation("move_members")
    async def voicemove(
        self,
        ctx: commands.Context[AegisBot],
        channel: Optional[discord.VoiceChannel | discord.StageChannel] = None,
    ) -> None:
        """Join a voice channel and wait. When Aegis is dragged to a new channel,
        all users in the old channel are moved to the new one."""

        me = ctx.guild.me
        if me is None:
            raise commands.BadArgument("I could not resolve my guild member state.")

        await self.bot.enforce_high_risk_command_policy(ctx)

        if not me.guild_permissions.move_members:
            raise commands.BadArgument("I need the **Move Members** permission to do that.")

        # Determine which channel to join
        target_channel = channel
        if target_channel is None:
            author_voice = getattr(ctx.author, "voice", None)
            if author_voice is None or author_voice.channel is None:
                raise commands.BadArgument(
                    "Join a voice channel first, or specify one: "
                    f"`{ctx.clean_prefix}voicemove <channel>`"
                )
            target_channel = author_voice.channel

        # If already connected in this guild, disconnect first
        existing_vc = ctx.guild.voice_client
        if existing_vc:
            try:
                await existing_vc.disconnect(force=True)
            except Exception:
                pass

        # Clear any previous session
        self.bot.voicemove_sessions.pop(ctx.guild.id, None)

        # Connect Aegis to the voice channel
        try:
            voice_client = await target_channel.connect()
        except Exception as exc:
            raise commands.BadArgument(f"Failed to connect to the voice channel: {exc}")

        # Deafen ourselves after connecting
        try:
            await ctx.guild.change_voice_state(channel=target_channel, self_deaf=True)
        except Exception:
            pass

        # Store the session AFTER successful connection
        self.bot.voicemove_sessions[ctx.guild.id] = {
            "channel_id": target_channel.id,
            "moderator_id": ctx.author.id,
        }

        await ctx.send(
            view=build_panel(
                "Voice Move Active",
                f"Joined **{target_channel.name}**. Drag Aegis to move everyone.\n"
                f"Use `{ctx.clean_prefix}voicemovestop` to stop.",
                tone="success",
            )
        )

    @commands.command()
    @require_moderation("move_members")
    async def voicemovestop(
        self,
        ctx: commands.Context[AegisBot],
    ) -> None:
        """Stop the active voicemove session and disconnect Aegis from voice."""

        session = self.bot.voicemove_sessions.pop(ctx.guild.id, None)

        if session is None:
            raise commands.BadArgument("There is no active voicemove session in this server.")

        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect(force=True)

        await ctx.send(
            view=build_panel(
                "Voice Move Stopped",
                "Aegis disconnected and the voicemove session has ended.",
                tone="info",
            )
        )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(ModerationCog(bot))
