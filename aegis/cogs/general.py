from __future__ import annotations

import discord
from discord.ext import commands

from aegis.bot import AegisBot
from aegis.ui import build_panel
from aegis.utils import format_timestamp, humanize_duration, utcnow


class GeneralCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot
        self.started_at = utcnow()

    @commands.command()
    async def about(self, ctx: commands.Context[AegisBot]) -> None:
        uptime = humanize_duration(utcnow() - self.started_at)
        guild_count = len(self.bot.guilds)
        user_count = len(self.bot.users)
        command_count = len(self.bot.commands)
        active_prefix = self.bot.config.prefix
        if ctx.guild is not None:
            active_prefix = await self.bot.get_guild_prefix(ctx.guild.id)
        thumbnail_url = self.bot.user.display_avatar.url if self.bot.user else None
        fields = [
            ("Prefix", f"`{active_prefix}`"),
            ("Servers", str(guild_count)),
            ("Uptime", uptime),
            ("Users", str(user_count)),
            ("Stack", "`discord.py 2.6`"),
            ("Commands", str(command_count)),
        ]
        actions: list[tuple[str, str]] = []
        if self.bot.config.docs_base_url:
            fields.append(("Docs", self.bot.config.docs_base_url))
            actions.append(("Open Docs", self.bot.config.docs_base_url))

        await ctx.send(
            view=build_panel(
                "Aegis",
                "Quick snapshot of runtime and docs.",
                tone="info",
                fields=fields,
                actions=actions,
                thumbnail_url=thumbnail_url,
            )
        )

    @commands.command()
    async def invite(self, ctx: commands.Context[AegisBot]) -> None:
        if self.bot.config.client_id is None:
            await ctx.send(
                view=build_panel(
                    "Invite Not Configured",
                    "Set `DISCORD_CLIENT_ID` in your environment to generate the invite URL.",
                    tone="warning",
                )
            )
            return

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
        url = discord.utils.oauth_url(self.bot.config.client_id, permissions=permissions)

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(
                "## Invite Aegis\nUse this **Button** to add Aegis."
            ),
            discord.ui.Separator(
                visible=True,
                spacing=discord.SeparatorSpacing.small,
            ),
            discord.ui.ActionRow(
                discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Invite Aegis",
                    url=url,
                )
            ),
        ]

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(*items, accent_color=discord.Colour.from_str("#1DB885")))
        await ctx.send(view=view)

    @commands.command()
    async def ping(self, ctx: commands.Context[AegisBot]) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(
            view=build_panel(
                "Ping",
                tone="success" if latency_ms < 200 else "warning",
                fields=[("Latency", f"`{latency_ms}ms`")],
            )
        )

    @commands.command()
    async def roleinfo(self, ctx: commands.Context[AegisBot], *, role: discord.Role) -> None:
        permissions = [name.replace("_", " ").title() for name, value in role.permissions if value]
        preview = ", ".join(permissions[:12]) if permissions else "No elevated permissions"
        if len(permissions) > 12:
            preview = f"{preview}, ..."

        await ctx.send(
            view=build_panel(
                f"Role - {role.name}",
                "Quick role breakdown.",
                tone="info",
                accented=False,
                fields=[
                    ("ID", f"`{role.id}`"),
                    ("Members", str(len(role.members))),
                    ("Position", str(role.position)),
                    ("Mentionable", "Yes" if role.mentionable else "No"),
                    ("Created", format_timestamp(role.created_at)),
                    ("Permissions", preview),
                ],
            )
        )

    @commands.command()
    async def serverinfo(self, ctx: commands.Context[AegisBot]) -> None:
        guild = ctx.guild
        if guild is None:
            return

        details_text = "\n\n".join(
            [
                f"**Owner**\n{str(guild.owner) if guild.owner else 'Unknown'}",
                f"**ID**\n`{guild.id}`",
                f"**Members**\n{guild.member_count or len(guild.members)}",
                f"**Boost Level**\n{guild.premium_tier}",
                f"**Verification**\n{guild.verification_level.name.replace('_', ' ').title()}",
                f"**Created**\n{format_timestamp(guild.created_at)}",
            ]
        )

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## Server - {guild.name}\nLive guild snapshot."),
            discord.ui.Separator(
                visible=True,
                spacing=discord.SeparatorSpacing.small,
            ),
        ]

        if guild.icon:
            items.append(
                discord.ui.Section(
                    details_text,
                    accessory=discord.ui.Thumbnail(guild.icon.url),
                )
            )
        else:
            items.append(discord.ui.TextDisplay(details_text))

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(*items))
        await ctx.send(view=view)

    @commands.command()
    async def userinfo(
        self,
        ctx: commands.Context[AegisBot],
        *,
        user: discord.Member | None = None,
    ) -> None:
        member = user or ctx.author
        joined_at = format_timestamp(member.joined_at) if member.joined_at else "Unknown"

        await ctx.send(
            view=build_panel(
                f"User - {member}",
                "Member details from the \ncurrent server.",
                tone="info",
                thumbnail_url=member.display_avatar.url,
                accented=False,
                fields=[
                    ("ID", f"`{member.id}`"),
                    ("Display Name", member.display_name),
                    ("Top Role", member.top_role.name if member.top_role else "@everyone"),
                    ("Joined Server", joined_at),
                    ("Created Account", format_timestamp(member.created_at)),
                ],
            )
        )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(GeneralCog(bot))
