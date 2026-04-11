from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import lru_cache

from discord.ext import commands


@dataclass(slots=True, frozen=True)
class CommandCategory:
    key: str
    title: str
    summary: str
    aliases: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class CommandDoc:
    name: str
    category: str
    slug: str
    summary: str
    description: str
    syntax: tuple[str, ...]
    access: str
    aliases: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    public: bool = True


@dataclass(slots=True, frozen=True)
class SystemGuide:
    slug: str
    title: str
    summary: str
    related_commands: tuple[str, ...] = ()


GENERAL = CommandCategory(
    key="general",
    title="General",
    summary="Everyday info and discovery commands for normal users and moderators.",
    aliases=("info", "utility"),
)
MODERATION = CommandCategory(
    key="moderation",
    title="Moderation",
    summary="Hands-on actions for kicking, banning, muting, cleaning, and voice moderation.",
    aliases=("mod",),
)
SETTINGS = CommandCategory(
    key="settings",
    title="Settings",
    summary="Server configuration commands for logs, setup, and moderation defaults.",
    aliases=("config", "configuration"),
)
AUTOMOD = CommandCategory(
    key="automod",
    title="AutoMod",
    summary="Automated moderation, strike management, and raid protection controls.",
    aliases=("auto-mod", "strikes"),
)
ANTINUKE = CommandCategory(
    key="antinuke",
    title="Anti-Nuke",
    summary="Security controls for destructive admin activity, trust, freeze, and incident review.",
    aliases=("anti-nuke", "security"),
)

CATEGORIES: tuple[CommandCategory, ...] = (
    GENERAL,
    MODERATION,
    SETTINGS,
    AUTOMOD,
    ANTINUKE,
)


def command(
    *,
    name: str,
    category: str,
    slug: str,
    summary: str,
    description: str,
    syntax: tuple[str, ...],
    access: str,
    aliases: tuple[str, ...] = (),
    examples: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    related: tuple[str, ...] = (),
) -> CommandDoc:
    return CommandDoc(
        name=name,
        category=category,
        slug=slug,
        summary=summary,
        description=description,
        syntax=syntax,
        access=access,
        aliases=aliases,
        examples=examples,
        notes=notes,
        related=related,
    )


COMMANDS: tuple[CommandDoc, ...] = (
    command(
        name="help",
        category=GENERAL.key,
        slug="help",
        summary="Show command categories or detailed help for a category or command.",
        description="Use `^help` to explore Aegis inside Discord. You can open a category overview or inspect a single command with syntax, examples, and access requirements.",
        syntax=("^help", "^help <category>", "^help <command>"),
        access="Everyone",
        examples=("^help", "^help moderation", "^help antinuke mode"),
        notes=(
            "Help panels include docs links, including category/command deep links when available.",
        ),
        related=("about", "invite"),
    ),
    command(
        name="about",
        category=GENERAL.key,
        slug="about",
        summary="Show a quick snapshot of the bot, uptime, and command count.",
        description="Displays a compact overview of Aegis including prefix, uptime, server count, and the current runtime stack.",
        syntax=("^about",),
        access="Everyone",
        examples=("^about",),
        notes=("Includes a direct docs link when docs URL is configured.",),
        related=("help", "ping", "invite"),
    ),
    command(
        name="invite",
        category=GENERAL.key,
        slug="invite",
        summary="Get the invite link and required permissions for Aegis.",
        description="Shows a panel with an invite button for the bot. This is useful when you want to add Aegis to another server with the recommended permissions set.",
        syntax=("^invite",),
        access="Everyone",
        examples=("^invite",),
        related=("about", "help"),
    ),
    command(
        name="ping",
        category=GENERAL.key,
        slug="ping",
        summary="Check the bot's WebSocket latency.",
        description="Returns a small health panel with Aegis latency so you can quickly confirm the bot is responding.",
        syntax=("^ping",),
        access="Everyone",
        examples=("^ping",),
        related=("about",),
    ),
    command(
        name="roleinfo",
        category=GENERAL.key,
        slug="roleinfo",
        summary="Inspect a role's basic details and permissions.",
        description="Shows the role ID, member count, position, mentionability, creation time, and a preview of enabled permissions.",
        syntax=("^roleinfo <role>",),
        access="Everyone",
        examples=("^roleinfo @Moderators", "^roleinfo Staff"),
        related=("serverinfo", "userinfo"),
    ),
    command(
        name="serverinfo",
        category=GENERAL.key,
        slug="serverinfo",
        summary="View a live overview of the current server.",
        description="Shows ownership, server ID, member count, boost level, verification level, and creation time for the current guild.",
        syntax=("^serverinfo",),
        access="Everyone",
        examples=("^serverinfo",),
        related=("roleinfo", "userinfo"),
    ),
    command(
        name="userinfo",
        category=GENERAL.key,
        slug="userinfo",
        summary="Inspect a member's identity and server profile.",
        description="Shows the user ID, display name, top role, join date, and account creation time. If no user is provided, Aegis shows your own profile.",
        syntax=("^userinfo", "^userinfo <member>"),
        access="Everyone",
        examples=("^userinfo", "^userinfo @Suyash"),
        related=("serverinfo", "roleinfo"),
    ),
    command(
        name="kick",
        category=MODERATION.key,
        slug="kick",
        summary="Remove one or more members from the server.",
        description="Kicks the selected members after hierarchy checks, sends them a DM when possible, and records a moderation case in the mod log.",
        syntax=("^kick <users...> [reason]",),
        access="Kick Members permission or configured mod role",
        examples=("^kick @user spam", "^kick @user1 @user2 repeated rule breaking"),
        notes=("Non-trusted staff are rate-limited and capped on high-risk moderation actions.",),
        related=("ban", "mute", "clean"),
    ),
    command(
        name="ban",
        category=MODERATION.key,
        slug="ban",
        summary="Ban one or more users permanently or for a duration.",
        description="Bans the selected users, deletes recent messages, optionally schedules an automatic unban, and records the case for later review.",
        syntax=("^ban <users...> [duration] [reason]",),
        access="Ban Members permission or configured mod role",
        examples=("^ban @user scam links", "^ban @user 7d raid alt"),
        notes=("Temporary bans are tracked by the scheduler and removed automatically when they expire.",),
        related=("silentban", "softban", "unban"),
    ),
    command(
        name="silentban",
        category=MODERATION.key,
        slug="silentban",
        summary="Ban users without deleting message history.",
        description="Works like `ban` but keeps message deletion at zero seconds. This is useful when you want the ban without wiping recent evidence from channels.",
        syntax=("^silentban <users...> [duration] [reason]",),
        access="Ban Members permission or configured mod role",
        examples=("^silentban @user evidence preserved", "^silentban @user 1d manual review"),
        related=("ban", "softban", "unban"),
    ),
    command(
        name="softban",
        category=MODERATION.key,
        slug="softban",
        summary="Ban and immediately unban a member to clear recent messages.",
        description="Softban requires the user to still be in the server. Aegis bans them to remove recent content and then immediately unbans them so they can rejoin later.",
        syntax=("^softban <users...> [reason]",),
        access="Ban Members permission or configured mod role",
        examples=("^softban @user flood cleanup",),
        notes=("Softban only works for members who are still present in the guild.",),
        related=("ban", "clean"),
    ),
    command(
        name="unban",
        category=MODERATION.key,
        slug="unban",
        summary="Remove an active ban from one or more users.",
        description="Unbans the selected users, clears scheduled temporary-ban expirations, and records the action in the case log.",
        syntax=("^unban <users...> [reason]",),
        access="Ban Members permission or configured mod role",
        examples=("^unban 123456789012345678 appeal accepted", "^unban @user mistaken identity"),
        related=("ban", "silentban"),
    ),
    command(
        name="mute",
        category=MODERATION.key,
        slug="mute",
        summary="Apply the configured muted role to one or more members.",
        description="Adds the Aegis muted role to the selected members, optionally schedules an automatic unmute, and records the case.",
        syntax=("^mute <users...> [duration] [reason]",),
        access="Manage Roles permission or configured mod role",
        examples=("^mute @user 30m cooldown", "^mute @user excessive arguments"),
        notes=("The muted role must be created first with `^setup muted`.",),
        related=("unmute", "setup muted", "punishment"),
    ),
    command(
        name="unmute",
        category=MODERATION.key,
        slug="unmute",
        summary="Remove the muted role from one or more members.",
        description="Removes the configured muted role, clears scheduled unmute timers, and records the change in the moderation case history.",
        syntax=("^unmute <users...> [reason]",),
        access="Manage Roles permission or configured mod role",
        examples=("^unmute @user served mute", "^unmute @user appeal granted"),
        related=("mute",),
    ),
    command(
        name="clean",
        category=MODERATION.key,
        slug="clean",
        summary="Bulk-delete messages with optional content and user filters.",
        description="Purges recent channel messages in bulk. You can filter by amount, member/user, plain text, regex, bots, embeds, links, or images.",
        syntax=("^clean <amount> [filters...]",),
        access="Manage Messages permission or configured mod role",
        examples=("^clean 50", "^clean 100 @user links", "^clean 25 `free nitro`"),
        notes=(
            "Messages older than two weeks cannot be bulk-deleted by Discord.",
            "Non-trusted staff are capped on large clean requests.",
        ),
        related=("kick", "softban"),
    ),
    command(
        name="voicekick",
        category=MODERATION.key,
        slug="voicekick",
        summary="Disconnect one or more members from voice.",
        description="Moves the selected members out of voice by disconnecting them, then records a voice moderation case.",
        syntax=("^voicekick <users...> [reason]",),
        access="Move Members permission or configured mod role",
        examples=("^voicekick @user loud mic spam", "^voicekick @user1 @user2 voice raid"),
        related=("voicemove", "voicemovestop"),
    ),
    command(
        name="voicemove",
        category=MODERATION.key,
        slug="voicemove",
        summary="Start a guided voice move session with Aegis.",
        description="Aegis joins a target voice channel and waits. When you drag Aegis to another channel, members from the old channel are moved to the new one.",
        syntax=("^voicemove", "^voicemove <voice-channel>"),
        access="Move Members permission or configured mod role",
        examples=("^voicemove", "^voicemove General VC"),
        notes=("Use `^voicemovestop` to end the active move session.",),
        related=("voicekick", "voicemovestop"),
    ),
    command(
        name="voicemovestop",
        category=MODERATION.key,
        slug="voicemovestop",
        summary="End the current voice move session and disconnect Aegis.",
        description="Stops the active guided voice move session for the server and cleanly disconnects the bot from voice.",
        syntax=("^voicemovestop",),
        access="Move Members permission or configured mod role",
        examples=("^voicemovestop",),
        related=("voicemove",),
    ),
    command(
        name="setup",
        category=SETTINGS.key,
        slug="setup",
        summary="Show available setup actions for first-time server configuration.",
        description="Displays a short setup overview. Right now the main first-run setup action is creating or registering the muted role with `^setup muted`.",
        syntax=("^setup",),
        access="Manage Server permission",
        examples=("^setup",),
        related=("setup muted", "settings"),
    ),
    command(
        name="setup muted",
        category=SETTINGS.key,
        slug="setup-muted",
        summary="Create or register the muted role used by Aegis.",
        description="Creates the `Aegis Muted` role when needed, applies restrictive overwrites across channels where possible, and stores the role for future mute actions.",
        syntax=("^setup muted",),
        access="Manage Server permission",
        examples=("^setup muted",),
        notes=("Run this before using `^mute` if your server has not configured a muted role yet.",),
        related=("mute", "settings"),
    ),
    command(
        name="modrole",
        category=SETTINGS.key,
        slug="modrole",
        summary="Set or clear the extra moderator role recognized by Aegis.",
        description="Lets you designate one role as a moderation override so members with that role can use moderation commands even if they do not hold the raw Discord permission.",
        syntax=("^modrole [role]",),
        access="Manage Server permission",
        examples=("^modrole @Staff", "^modrole"),
        related=("settings",),
    ),
    command(
        name="modlog",
        category=SETTINGS.key,
        slug="modlog",
        summary="Set the moderation case log channel.",
        description="Stores the text channel used for moderation actions such as kicks, bans, mutes, and strike-based punishments.",
        syntax=("^modlog [#channel|off]",),
        access="Manage Server permission",
        examples=("^modlog #mod-logs", "^modlog off"),
        related=("messagelog", "serverlog", "voicelog"),
    ),
    command(
        name="messagelog",
        category=SETTINGS.key,
        slug="messagelog",
        summary="Set the message edit/delete log channel.",
        description="Stores the channel used for message log entries including edits, deletions, and bulk delete archives.",
        syntax=("^messagelog [#channel|off]",),
        access="Manage Server permission",
        examples=("^messagelog #message-logs", "^messagelog off"),
        related=("modlog", "serverlog"),
    ),
    command(
        name="serverlog",
        category=SETTINGS.key,
        slug="serverlog",
        summary="Set the server event log channel.",
        description="Stores the channel used for joins, leaves, nickname changes, role updates, channel changes, and broader guild event logs.",
        syntax=("^serverlog [#channel|off]",),
        access="Manage Server permission",
        examples=("^serverlog #server-logs", "^serverlog off"),
        related=("modlog", "messagelog", "voicelog"),
    ),
    command(
        name="voicelog",
        category=SETTINGS.key,
        slug="voicelog",
        summary="Set the voice event log channel.",
        description="Stores the channel used for voice joins, leaves, moves, mute/deafen state changes, and voice moderation event logs.",
        syntax=("^voicelog [#channel|off]",),
        access="Manage Server permission",
        examples=("^voicelog #voice-logs", "^voicelog off"),
        related=("serverlog", "voicekick"),
    ),
    command(
        name="prefix",
        category=SETTINGS.key,
        slug="prefix",
        summary="Set the server-specific command prefix.",
        description="Changes the command prefix used in the current server only. You can also reset it back to the default prefix.",
        syntax=("^prefix", "^prefix <new-prefix>", "^prefix default"),
        access="Manage Server permission",
        examples=("^prefix !", "^prefix ?", "^prefix default"),
        notes=("Prefix must be 1 to 5 characters and cannot include spaces.",),
        related=("settings", "help"),
    ),
    command(
        name="settings",
        category=SETTINGS.key,
        slug="settings",
        summary="Show the current Aegis configuration for the server.",
        description="Displays the saved moderation, logging, AutoMod, and anti-nuke configuration for the current guild in one place.",
        syntax=("^settings",),
        access="Manage Server permission",
        examples=("^settings",),
        related=("setup", "modrole", "antinuke status", "automod"),
    ),
    command(
        name="automod",
        category=AUTOMOD.key,
        slug="automod",
        summary="Show the current AutoMod snapshot for the server.",
        description="Displays the active AutoMod configuration overview, including enabled rules, thresholds, and raid protection settings.",
        syntax=("^automod",),
        access="Manage Server permission",
        examples=("^automod",),
        related=("automod show", "punishment", "raidmode"),
    ),
    command(
        name="automod show",
        category=AUTOMOD.key,
        slug="automod-show",
        summary="Alias for the main AutoMod snapshot view.",
        description="Shows the same AutoMod overview as `^automod`.",
        syntax=("^automod show",),
        access="Manage Server permission",
        examples=("^automod show",),
        related=("automod",),
    ),
    command(
        name="automod antiinvite",
        category=AUTOMOD.key,
        slug="automod-antiinvite",
        summary="Set the invite filter punishment.",
        description="Controls how Aegis reacts when users post Discord invite links. You can disable it, delete only, or assign strikes.",
        syntax=("^automod antiinvite <strikes|delete|off>",),
        access="Manage Server permission",
        examples=("^automod antiinvite 2", "^automod antiinvite delete", "^automod antiinvite off"),
        related=("automod whitelist", "punishment"),
    ),
    command(
        name="automod antireferral",
        category=AUTOMOD.key,
        slug="automod-antireferral",
        summary="Set the referral-link punishment.",
        description="Controls how Aegis reacts to suspicious referral or tracking-link spam such as affiliate or redirect-heavy links.",
        syntax=("^automod antireferral <strikes|delete|off>",),
        access="Manage Server permission",
        examples=("^automod antireferral 1", "^automod antireferral delete"),
        related=("automod antiinvite",),
    ),
    command(
        name="automod anticopypasta",
        category=AUTOMOD.key,
        slug="automod-anticopypasta",
        summary="Detect and punish known copypasta spam.",
        description="Flags large known spam copypastas and applies delete-only or strike-based handling depending on your setting.",
        syntax=("^automod anticopypasta <strikes|delete|off>",),
        access="Manage Server permission",
        aliases=("automod antipasta", "automod anti-copypasta"),
        examples=("^automod anticopypasta 1", "^automod anti-copypasta delete"),
        related=("automod filter add",),
    ),
    command(
        name="automod antieveryone",
        category=AUTOMOD.key,
        slug="automod-antieveryone",
        summary="Control punishment for `@everyone` and `@here` abuse.",
        description="Lets you delete only, assign strikes, or disable the rule for `@everyone` and `@here` mentions.",
        syntax=("^automod antieveryone <strikes|delete|off>",),
        access="Manage Server permission",
        examples=("^automod antieveryone 1", "^automod antieveryone delete"),
        related=("automod maxmentions",),
    ),
    command(
        name="automod maxmentions",
        category=AUTOMOD.key,
        slug="automod-maxmentions",
        summary="Set the mention threshold for regular user mentions.",
        description="Triggers AutoMod when a single message exceeds the configured user-mention count.",
        syntax=("^automod maxmentions <count|off>",),
        access="Manage Server permission",
        examples=("^automod maxmentions 5", "^automod maxmentions off"),
        related=("automod antieveryone", "automod maxrolementions"),
    ),
    command(
        name="automod maxrolementions",
        category=AUTOMOD.key,
        slug="automod-maxrolementions",
        summary="Set the threshold for role mentions in one message.",
        description="Triggers AutoMod when a message mentions too many roles at once.",
        syntax=("^automod maxrolementions <count|off>",),
        access="Manage Server permission",
        examples=("^automod maxrolementions 2", "^automod maxrolementions off"),
        related=("automod maxmentions",),
    ),
    command(
        name="automod maxlines",
        category=AUTOMOD.key,
        slug="automod-maxlines",
        summary="Set the line-count threshold for multi-line spam.",
        description="Flags messages that exceed the configured number of lines, which is helpful against pasted wall spam.",
        syntax=("^automod maxlines <count|off>",),
        access="Manage Server permission",
        examples=("^automod maxlines 12", "^automod maxlines off"),
        related=("automod anticopypasta",),
    ),
    command(
        name="automod antiduplicate",
        category=AUTOMOD.key,
        slug="automod-antiduplicate",
        summary="Configure duplicate-message spam detection.",
        description="Tracks repeated messages by the same user in a rolling window and can delete them, add strikes, or both.",
        syntax=(
            "^automod antiduplicate <strike-threshold|off> [delete-threshold] [strikes]",
        ),
        access="Manage Server permission",
        aliases=("automod antispam",),
        examples=("^automod antiduplicate 4", "^automod antiduplicate 6 3 2", "^automod antispam off"),
        notes=("Set `strikes` to `0` for delete-only handling.",),
        related=("automod maxlines", "punishment"),
    ),
    command(
        name="automod resolvelinks",
        category=AUTOMOD.key,
        slug="automod-resolvelinks",
        summary="Enable or disable redirect-link resolution.",
        description="When enabled, Aegis resolves redirect-style URLs so invite and referral checks can look through certain wrappers.",
        syntax=("^automod resolvelinks <on|off>",),
        access="Manage Server permission",
        examples=("^automod resolvelinks on", "^automod resolvelinks off"),
        related=("automod antiinvite", "automod antireferral"),
    ),
    command(
        name="automod autodehoist",
        category=AUTOMOD.key,
        slug="automod-autodehoist",
        summary="Configure automatic nickname dehoisting.",
        description="When enabled, Aegis watches for nicknames that begin with a specific hoist character and normalizes them automatically.",
        syntax=("^automod autodehoist <character|off>",),
        access="Manage Server permission",
        aliases=("automod dehoist",),
        examples=("^automod autodehoist !", "^automod dehoist off"),
        related=("automod",),
    ),
    command(
        name="automod whitelist",
        category=AUTOMOD.key,
        slug="automod-whitelist",
        summary="Manage the invite whitelist for allowed guild IDs.",
        description="Lets you add, remove, or show guild IDs that bypass the Anti Invite rule. This whitelist is for destination guilds, not for user accounts.",
        syntax=("^automod whitelist <add|remove|show> [guild-id...]",),
        access="Manage Server permission",
        aliases=("automod whitelistinvites",),
        examples=("^automod whitelist show", "^automod whitelist add 123456789012345678"),
        related=("automod antiinvite",),
    ),
    command(
        name="automod filter",
        category=AUTOMOD.key,
        slug="automod-filter",
        summary="Show the current custom AutoMod filters.",
        description="Opens the custom filter overview. Filters let you match exact quotes, globs, or regex patterns and assign strikes when they match.",
        syntax=("^automod filter",),
        access="Manage Server permission",
        aliases=("automod filters",),
        examples=("^automod filter",),
        related=("automod filter add", "automod filter list"),
    ),
    command(
        name="automod filter add",
        category=AUTOMOD.key,
        slug="automod-filter-add",
        summary="Create or update a named custom AutoMod filter.",
        description="Defines a named filter with one or more patterns and a strike value. Aegis can match quotes, glob-like patterns, and regex entries.",
        syntax=("^automod filter add <name> <strikes> <patterns...>",),
        access="Manage Server permission",
        aliases=("automod filter create",),
        examples=("^automod filter add scam 2 \"free nitro\" regex:^steam gift$",),
        related=("automod filter remove", "automod filter list"),
    ),
    command(
        name="automod filter remove",
        category=AUTOMOD.key,
        slug="automod-filter-remove",
        summary="Delete a named custom filter.",
        description="Removes an AutoMod filter by name so Aegis stops checking those patterns.",
        syntax=("^automod filter remove <name>",),
        access="Manage Server permission",
        aliases=("automod filter delete",),
        examples=("^automod filter remove scam",),
        related=("automod filter add", "automod filter list"),
    ),
    command(
        name="automod filter list",
        category=AUTOMOD.key,
        slug="automod-filter-list",
        summary="List all custom AutoMod filters for the server.",
        description="Shows saved filter names, strike values, and their pattern definitions.",
        syntax=("^automod filter list",),
        access="Manage Server permission",
        aliases=("automod filter show",),
        examples=("^automod filter list",),
        related=("automod filter", "automod filter add"),
    ),
    command(
        name="automod antiraid",
        category=AUTOMOD.key,
        slug="automod-antiraid",
        summary="Configure the join-burst trigger for automatic raid mode.",
        description="Turns automatic raid mode on or off, or sets a custom joins-per-seconds threshold that enables raid mode during suspicious join bursts.",
        syntax=("^automod antiraid <on|off|joins/seconds>",),
        access="Manage Server permission",
        aliases=("automod autoraidmode", "automod autoraid", "automod autoantiraid"),
        examples=("^automod antiraid on", "^automod antiraid 10/8", "^automod autoraid off"),
        related=("raidmode",),
    ),
    command(
        name="automod ignore",
        category=AUTOMOD.key,
        slug="automod-ignore",
        summary="Exclude a role or channel from AutoMod enforcement.",
        description="Adds a role or guild channel to the ignore list so AutoMod skips checks there.",
        syntax=("^automod ignore <role|channel>",),
        access="Manage Server permission",
        examples=("^automod ignore #staff-chat", "^automod ignore @Trusted"),
        related=("automod unignore", "settings"),
    ),
    command(
        name="automod unignore",
        category=AUTOMOD.key,
        slug="automod-unignore",
        summary="Remove a role or channel from the AutoMod ignore list.",
        description="Re-enables normal AutoMod checks for the selected role or channel.",
        syntax=("^automod unignore <role|channel>",),
        access="Manage Server permission",
        examples=("^automod unignore #staff-chat", "^automod unignore @Trusted"),
        related=("automod ignore",),
    ),
    command(
        name="punishment",
        category=AUTOMOD.key,
        slug="punishment",
        summary="Map strike thresholds to automatic punishments.",
        description="Defines what Aegis should do when a member reaches a specific strike count, including warn, mute, kick, ban, softban, silentban, or removing a threshold.",
        syntax=("^punishment <strikes> <warn|mute|kick|ban|softban|silentban|none> [duration]",),
        access="Manage Server permission",
        examples=("^punishment 1 warn", "^punishment 3 mute 1h", "^punishment 5 ban", "^punishment 3 none"),
        related=("strike", "pardon", "check"),
    ),
    command(
        name="strike",
        category=AUTOMOD.key,
        slug="strike",
        summary="Manually add strikes to one or more members.",
        description="Adds strikes to the selected members and immediately checks the configured punishment ladder for any threshold they just reached.",
        syntax=("^strike [count] <users...> <reason>",),
        access="Moderate Members permission or configured mod role",
        examples=("^strike @user advertising", "^strike 2 @user repeat offense"),
        related=("pardon", "punishment", "check"),
    ),
    command(
        name="pardon",
        category=AUTOMOD.key,
        slug="pardon",
        summary="Manually remove strikes from one or more members.",
        description="Reduces a member's active strike total without deleting case history so moderators can correct or forgive past moderation decisions.",
        syntax=("^pardon [count] <users...> <reason>",),
        access="Moderate Members permission or configured mod role",
        examples=("^pardon @user appeal accepted", "^pardon 2 @user corrected mistake"),
        related=("strike", "check"),
    ),
    command(
        name="check",
        category=AUTOMOD.key,
        slug="check",
        summary="Inspect a member's moderation state in one panel.",
        description="Shows current strikes, mute state, remaining mute time, ban state, remaining ban time, and the best available ban reason.",
        syntax=("^check", "^check <user>"),
        access="Moderate Members permission or configured mod role",
        examples=("^check", "^check @user"),
        related=("strike", "pardon", "punishment"),
    ),
    command(
        name="raidmode",
        category=AUTOMOD.key,
        slug="raidmode",
        summary="Manually turn raid mode on or off.",
        description="Enables or disables raid mode by raising or restoring the server verification level. Use this when you want a manual security override.",
        syntax=("^raidmode <on|off> [reason]",),
        access="Manage Server permission",
        examples=("^raidmode on active join flood", "^raidmode off situation handled"),
        related=("automod antiraid",),
    ),
    command(
        name="antinuke",
        category=ANTINUKE.key,
        slug="antinuke",
        summary="Show the current anti-nuke status panel.",
        description="Displays anti-nuke readiness, mode, active freeze, trusted entries, and configured thresholds for the server.",
        syntax=("^antinuke",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke",),
        related=("antinuke status", "antinuke incidents"),
    ),
    command(
        name="antinuke status",
        category=ANTINUKE.key,
        slug="antinuke-status",
        summary="Show the anti-nuke status panel explicitly.",
        description="Shows anti-nuke readiness, required permission health, active freeze state, trusted entries, and event thresholds.",
        syntax=("^antinuke status",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke status",),
        related=("antinuke", "antinuke incidents"),
    ),
    command(
        name="antinuke enable",
        category=ANTINUKE.key,
        slug="antinuke-enable",
        summary="Enable anti-nuke enforcement for the server.",
        description="Turns on audit-log-backed anti-nuke monitoring and live response handling for destructive admin actions.",
        syntax=("^antinuke enable",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke enable",),
        related=("antinuke disable", "antinuke mode"),
    ),
    command(
        name="antinuke disable",
        category=ANTINUKE.key,
        slug="antinuke-disable",
        summary="Disable anti-nuke enforcement for the server.",
        description="Stops live anti-nuke enforcement until it is re-enabled. This does not erase thresholds, trust entries, or incident history.",
        syntax=("^antinuke disable",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke disable",),
        related=("antinuke enable",),
    ),
    command(
        name="antinuke mode",
        category=ANTINUKE.key,
        slug="antinuke-mode",
        summary="Set the default anti-nuke response mode.",
        description="Chooses whether Aegis should `contain`, `ban`, or `alert` when an untrusted destructive threshold is reached.",
        syntax=("^antinuke mode <contain|ban|alert>",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke mode contain", "^antinuke mode alert"),
        related=("antinuke enable", "antinuke threshold"),
    ),
    command(
        name="antinuke log",
        category=ANTINUKE.key,
        slug="antinuke-log",
        summary="Set the anti-nuke incident log channel.",
        description="Stores the channel used for anti-nuke incidents. If disabled, Aegis falls back to the moderation log or server log where possible.",
        syntax=("^antinuke log [#channel|off]",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke log #security-logs", "^antinuke log off"),
        related=("modlog", "serverlog", "antinuke incidents"),
    ),
    command(
        name="antinuke canary",
        category=ANTINUKE.key,
        slug="antinuke-canary",
        summary="Show canary trap status and decoy asset health.",
        description="Displays whether canary trap is enabled, whether all decoy assets are armed, and any permission gaps that could prevent reliable re-arming.",
        syntax=("^antinuke canary", "^antinuke canary status"),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke canary", "^antinuke canary status"),
        related=("antinuke canary enable", "antinuke canary rotate", "antinuke status"),
    ),
    command(
        name="antinuke canary status",
        category=ANTINUKE.key,
        slug="antinuke-canary-status",
        summary="Show anti-nuke canary trap status explicitly.",
        description="Shows canary trap enablement, armed asset health, and permission gaps that may affect canary provisioning or rotation.",
        syntax=("^antinuke canary status",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke canary status",),
        related=("antinuke canary", "antinuke canary enable", "antinuke canary rotate"),
    ),
    command(
        name="antinuke canary enable",
        category=ANTINUKE.key,
        slug="antinuke-canary-enable",
        summary="Enable and arm anti-nuke canary trap assets.",
        description="Creates decoy role, channel, and webhook assets that should never be touched during normal operations. Any touch event is treated as a high-confidence hostile signal.",
        syntax=("^antinuke canary enable",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke canary enable",),
        related=("antinuke canary", "antinuke canary disable", "antinuke mode"),
    ),
    command(
        name="antinuke canary disable",
        category=ANTINUKE.key,
        slug="antinuke-canary-disable",
        summary="Disable canary trap and clean up decoy assets.",
        description="Turns off canary trap enforcement and removes stored canary assets where possible.",
        syntax=("^antinuke canary disable",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke canary disable",),
        related=("antinuke canary", "antinuke canary enable"),
    ),
    command(
        name="antinuke canary rotate",
        category=ANTINUKE.key,
        slug="antinuke-canary-rotate",
        summary="Rotate canary decoys by replacing all canary assets.",
        description="Removes the current canary role, channel, and webhook decoys and creates fresh replacements to reduce long-lived exposure.",
        syntax=("^antinuke canary rotate",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke canary rotate",),
        related=("antinuke canary", "antinuke canary status"),
    ),
    command(
        name="antinuke trust",
        category=ANTINUKE.key,
        slug="antinuke-trust",
        summary="Show the anti-nuke trust list.",
        description="Displays the roles and users that bypass anti-nuke enforcement. Trusted entries can still be logged for visibility, but they are not automatically punished.",
        syntax=("^antinuke trust",),
        access="Server owner only",
        examples=("^antinuke trust",),
        related=("antinuke trust add", "antinuke trust remove"),
    ),
    command(
        name="antinuke trust add",
        category=ANTINUKE.key,
        slug="antinuke-trust-add",
        summary="Add a user or role to the anti-nuke trust list.",
        description="Adds a role or individual user that should bypass anti-nuke enforcement. Use this carefully, because trusted entries can change anti-nuke settings and ignore enforcement.",
        syntax=("^antinuke trust add <user|role>",),
        access="Server owner only",
        examples=("^antinuke trust add @HeadAdmin", "^antinuke trust add @Security"),
        related=("antinuke trust", "antinuke trust remove"),
    ),
    command(
        name="antinuke trust remove",
        category=ANTINUKE.key,
        slug="antinuke-trust-remove",
        summary="Remove a user or role from the anti-nuke trust list.",
        description="Removes a bypass entry so the user or role is once again subject to anti-nuke enforcement and cannot manage anti-nuke settings.",
        syntax=("^antinuke trust remove <user|role>",),
        access="Server owner only",
        examples=("^antinuke trust remove @HeadAdmin",),
        related=("antinuke trust add",),
    ),
    command(
        name="antinuke threshold",
        category=ANTINUKE.key,
        slug="antinuke-threshold",
        summary="Override the count and window for an anti-nuke event.",
        description="Customizes how many actions within how many seconds should trip an anti-nuke event family such as channel deletion or webhook creation.",
        syntax=("^antinuke threshold <event> <count> <seconds>",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke threshold channel_delete 2 10", "^antinuke threshold webhook_create 1 20"),
        related=("antinuke protect", "antinuke mode"),
    ),
    command(
        name="antinuke protect",
        category=ANTINUKE.key,
        slug="antinuke-protect",
        summary="Turn a specific anti-nuke event family on or off.",
        description="Enables or disables detection for one anti-nuke event type without changing the saved threshold numbers.",
        syntax=("^antinuke protect <event> <on|off>",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke protect role_update on", "^antinuke protect guild_update off"),
        related=("antinuke threshold",),
    ),
    command(
        name="antinuke incidents",
        category=ANTINUKE.key,
        slug="antinuke-incidents",
        summary="Review recent anti-nuke incidents for the server.",
        description="Lists recent anti-nuke incidents with actor, event family, time, response outcome, and freeze information where applicable.",
        syntax=("^antinuke incidents [limit]",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke incidents", "^antinuke incidents 10"),
        related=("antinuke status", "antinuke resetfreeze"),
    ),
    command(
        name="antinuke resetfreeze",
        category=ANTINUKE.key,
        slug="antinuke-resetfreeze",
        summary="Clear the active emergency freeze window manually.",
        description="Removes the current anti-nuke emergency freeze so trusted operators can resume high-risk moderation commands immediately.",
        syntax=("^antinuke resetfreeze",),
        access="Server owner or anti-nuke trusted entry",
        examples=("^antinuke resetfreeze",),
        related=("antinuke status", "antinuke incidents"),
    ),
)

SYSTEM_GUIDES: tuple[SystemGuide, ...] = (
    SystemGuide(
        slug="logging",
        title="Logging",
        summary="How Aegis separates moderation, message, server, voice, and anti-nuke logs.",
        related_commands=("modlog", "messagelog", "serverlog", "voicelog", "antinuke log"),
    ),
    SystemGuide(
        slug="strike-ladder",
        title="Strike Ladder",
        summary="How manual strikes and punishment thresholds work together.",
        related_commands=("strike", "pardon", "punishment", "check"),
    ),
    SystemGuide(
        slug="automod-overview",
        title="AutoMod",
        summary="Invite, mention, duplicate, filter, and raid protections with configurable punishments.",
        related_commands=("automod", "automod antiinvite", "automod antiduplicate", "raidmode"),
    ),
    SystemGuide(
        slug="raid-mode",
        title="Raid Mode",
        summary="Manual and automatic join-burst protection for suspicious server raids.",
        related_commands=("automod antiraid", "raidmode"),
    ),
    SystemGuide(
        slug="antinuke-overview",
        title="Anti-Nuke",
        summary="Real-time detection of destructive admin actions and the difference between contain, ban, and alert modes.",
        related_commands=("antinuke", "antinuke mode", "antinuke incidents"),
    ),
    SystemGuide(
        slug="antinuke-trust-and-freeze",
        title="Anti-Nuke Trust and Freeze",
        summary="Who can manage anti-nuke, how trust entries work, and what emergency freeze blocks.",
        related_commands=("antinuke trust", "antinuke resetfreeze", "antinuke status"),
    ),
)


def iter_commands() -> tuple[CommandDoc, ...]:
    return COMMANDS


def iter_guides() -> tuple[SystemGuide, ...]:
    return SYSTEM_GUIDES


@lru_cache(maxsize=1)
def category_map() -> dict[str, CommandCategory]:
    mapping: dict[str, CommandCategory] = {}
    for category in CATEGORIES:
        mapping[category.key] = category
        mapping[category.title.lower()] = category
        for alias in category.aliases:
            mapping[alias.lower()] = category
    return mapping


@lru_cache(maxsize=1)
def command_map() -> dict[str, CommandDoc]:
    mapping: dict[str, CommandDoc] = {}
    for entry in COMMANDS:
        mapping[entry.name.lower()] = entry
        for alias in entry.aliases:
            mapping[alias.lower()] = entry
    return mapping


def get_category(query: str) -> CommandCategory | None:
    return category_map().get(query.strip().lower())


def get_command(query: str) -> CommandDoc | None:
    normalized = query.strip().lower()
    if normalized in command_map():
        return command_map()[normalized]
    return None


def commands_for_category(category_key: str) -> tuple[CommandDoc, ...]:
    return tuple(entry for entry in COMMANDS if entry.category == category_key)


def category_slug(category_key: str) -> str:
    return f"category-{category_key}"


def docs_url(base_url: str | None, entry: CommandDoc) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/commands/{entry.slug}/"


def category_docs_url(base_url: str | None, category_key: str) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/commands/{category_slug(category_key)}/"


def guide_docs_url(base_url: str | None, guide: SystemGuide) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/systems/{guide.slug}/"


def _runtime_command_names() -> set[str]:
    from aegis.cogs import antinuke, automod, general, help, moderation, settings

    command_names: set[str] = set()
    for module in (general, help, moderation, settings, automod, antinuke):
        for obj in module.__dict__.values():
            if not inspect.isclass(obj) or not issubclass(obj, commands.Cog):
                continue
            for attribute in vars(obj).values():
                if isinstance(attribute, commands.Command):
                    command_names.add(attribute.qualified_name)
    return command_names


def validate_catalog(*, include_runtime_check: bool = True) -> None:
    seen_names: set[str] = set()
    seen_slugs: set[str] = set()
    valid_categories = {category.key for category in CATEGORIES}

    for entry in COMMANDS:
        if entry.name in seen_names:
            raise RuntimeError(f"Duplicate catalog command name: {entry.name}")
        if entry.slug in seen_slugs:
            raise RuntimeError(f"Duplicate catalog command slug: {entry.slug}")
        if entry.category not in valid_categories:
            raise RuntimeError(f"Unknown catalog category `{entry.category}` for {entry.name}")
        if not entry.syntax:
            raise RuntimeError(f"Catalog command `{entry.name}` must define at least one syntax string.")
        seen_names.add(entry.name)
        seen_slugs.add(entry.slug)

    if not include_runtime_check:
        return

    runtime_names = _runtime_command_names()
    catalog_names = {entry.name for entry in COMMANDS}
    missing = runtime_names - catalog_names
    extra = catalog_names - runtime_names
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing catalog entries: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"catalog entries without runtime commands: {', '.join(sorted(extra))}")
        raise RuntimeError("Command catalog mismatch: " + "; ".join(parts))
