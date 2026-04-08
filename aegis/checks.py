from __future__ import annotations

import discord
from discord.ext import commands


def require_manage_guild() -> commands.Check:
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        permissions = ctx.author.guild_permissions
        if permissions.administrator or permissions.manage_guild:
            return True

        raise commands.MissingPermissions(["manage_guild"])

    return commands.check(predicate)


def require_moderation(permission_name: str) -> commands.Check:
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        permissions = ctx.author.guild_permissions
        if permissions.administrator or getattr(permissions, permission_name, False):
            return True

        settings = await ctx.bot.db.fetch_guild_settings(ctx.guild.id)
        if settings.mod_role_id and discord.utils.get(ctx.author.roles, id=settings.mod_role_id):
            return True

        raise commands.MissingPermissions([permission_name])

    return commands.check(predicate)


def require_antinuke_control(*, owner_only: bool = False) -> commands.Check:
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        if ctx.author.id == ctx.guild.owner_id:
            return True

        if owner_only:
            raise commands.CheckFailure("Only the server owner can manage anti-nuke trust settings.")

        if await ctx.bot.is_antinuke_trusted(ctx.guild, ctx.author):
            return True

        raise commands.CheckFailure(
            "Only the server owner or an anti-nuke trusted entry can manage anti-nuke settings."
        )

    return commands.check(predicate)
