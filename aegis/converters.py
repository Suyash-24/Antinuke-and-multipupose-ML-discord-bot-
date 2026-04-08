from __future__ import annotations

import re
from datetime import timedelta

import discord
from discord.ext import commands

_DURATION_RE = re.compile(r"(?i)(\d+)([smhdw])")
_DURATION_MAP = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


class DurationConverter(commands.Converter[timedelta]):
    async def convert(self, ctx: commands.Context, argument: str) -> timedelta:
        matches = list(_DURATION_RE.finditer(argument))
        if not matches or "".join(match.group(0) for match in matches).lower() != argument.lower():
            raise commands.BadArgument("Duration must look like `10m`, `2h`, `7d`, or `1w2d`.")

        total_seconds = 0
        for match in matches:
            total_seconds += int(match.group(1)) * _DURATION_MAP[match.group(2).lower()]

        if total_seconds <= 0:
            raise commands.BadArgument("Duration must be greater than zero.")

        return timedelta(seconds=total_seconds)


class IgnoreTargetConverter(commands.Converter[discord.Role | discord.abc.GuildChannel]):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role | discord.abc.GuildChannel:
        for converter in (commands.RoleConverter(), commands.GuildChannelConverter()):
            try:
                return await converter.convert(ctx, argument)
            except commands.BadArgument:
                continue

        raise commands.BadArgument("Target must be a role or a guild channel.")


class MemberOrUserConverter(commands.Converter[discord.Member | discord.User]):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Member | discord.User:
        for converter in (commands.MemberConverter(), commands.UserConverter()):
            try:
                return await converter.convert(ctx, argument)
            except commands.BadArgument:
                continue

        raise commands.BadArgument("Provide a valid member mention, username, or user ID.")
