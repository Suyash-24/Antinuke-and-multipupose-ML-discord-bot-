# Commands

Browse the full Aegis command reference by category or jump straight into a specific command.

## [General](category-general.md)

- [help](help.md): Show command categories or detailed help for a category or command.
- [about](about.md): Show a quick snapshot of the bot, uptime, and command count.
- [invite](invite.md): Get the invite link and required permissions for Aegis.
- [ping](ping.md): Check the bot's WebSocket latency.
- [roleinfo](roleinfo.md): Inspect a role's basic details and permissions.
- [serverinfo](serverinfo.md): View a live overview of the current server.
- [userinfo](userinfo.md): Inspect a member's identity and server profile.

## [Moderation](category-moderation.md)

- [kick](kick.md): Remove one or more members from the server.
- [ban](ban.md): Ban one or more users permanently or for a duration.
- [silentban](silentban.md): Ban users without deleting message history.
- [softban](softban.md): Ban and immediately unban a member to clear recent messages.
- [unban](unban.md): Remove an active ban from one or more users.
- [mute](mute.md): Apply the configured muted role to one or more members.
- [unmute](unmute.md): Remove the muted role from one or more members.
- [clean](clean.md): Bulk-delete messages with optional content and user filters.
- [voicekick](voicekick.md): Disconnect one or more members from voice.
- [voicemove](voicemove.md): Start a guided voice move session with Aegis.
- [voicemovestop](voicemovestop.md): End the current voice move session and disconnect Aegis.

## [Settings](category-settings.md)

- [setup](setup.md): Show available setup actions for first-time server configuration.
- [setup muted](setup-muted.md): Create or register the muted role used by Aegis.
- [modrole](modrole.md): Set or clear the extra moderator role recognized by Aegis.
- [modlog](modlog.md): Set the moderation case log channel.
- [messagelog](messagelog.md): Set the message edit/delete log channel.
- [serverlog](serverlog.md): Set the server event log channel.
- [voicelog](voicelog.md): Set the voice event log channel.
- [settings](settings.md): Show the current Aegis configuration for the server.

## [AutoMod](category-automod.md)

- [automod](automod.md): Show the current AutoMod snapshot for the server.
- [automod show](automod-show.md): Alias for the main AutoMod snapshot view.
- [automod antiinvite](automod-antiinvite.md): Set the invite filter punishment.
- [automod antireferral](automod-antireferral.md): Set the referral-link punishment.
- [automod anticopypasta](automod-anticopypasta.md): Detect and punish known copypasta spam.
- [automod antieveryone](automod-antieveryone.md): Control punishment for `@everyone` and `@here` abuse.
- [automod maxmentions](automod-maxmentions.md): Set the mention threshold for regular user mentions.
- [automod maxrolementions](automod-maxrolementions.md): Set the threshold for role mentions in one message.
- [automod maxlines](automod-maxlines.md): Set the line-count threshold for multi-line spam.
- [automod antiduplicate](automod-antiduplicate.md): Configure duplicate-message spam detection.
- [automod resolvelinks](automod-resolvelinks.md): Enable or disable redirect-link resolution.
- [automod autodehoist](automod-autodehoist.md): Configure automatic nickname dehoisting.
- [automod whitelist](automod-whitelist.md): Manage the invite whitelist for allowed guild IDs.
- [automod filter](automod-filter.md): Show the current custom AutoMod filters.
- [automod filter add](automod-filter-add.md): Create or update a named custom AutoMod filter.
- [automod filter remove](automod-filter-remove.md): Delete a named custom filter.
- [automod filter list](automod-filter-list.md): List all custom AutoMod filters for the server.
- [automod antiraid](automod-antiraid.md): Configure the join-burst trigger for automatic raid mode.
- [automod ignore](automod-ignore.md): Exclude a role or channel from AutoMod enforcement.
- [automod unignore](automod-unignore.md): Remove a role or channel from the AutoMod ignore list.
- [punishment](punishment.md): Map strike thresholds to automatic punishments.
- [strike](strike.md): Manually add strikes to one or more members.
- [pardon](pardon.md): Manually remove strikes from one or more members.
- [check](check.md): Inspect a member's moderation state in one panel.
- [raidmode](raidmode.md): Manually turn raid mode on or off.

## [Anti-Nuke](category-antinuke.md)

- [antinuke](antinuke.md): Show the current anti-nuke status panel.
- [antinuke status](antinuke-status.md): Show the anti-nuke status panel explicitly.
- [antinuke enable](antinuke-enable.md): Enable anti-nuke enforcement for the server.
- [antinuke disable](antinuke-disable.md): Disable anti-nuke enforcement for the server.
- [antinuke mode](antinuke-mode.md): Set the default anti-nuke response mode.
- [antinuke log](antinuke-log.md): Set the anti-nuke incident log channel.
- [antinuke trust](antinuke-trust.md): Show the anti-nuke trust list.
- [antinuke trust add](antinuke-trust-add.md): Add a user or role to the anti-nuke trust list.
- [antinuke trust remove](antinuke-trust-remove.md): Remove a user or role from the anti-nuke trust list.
- [antinuke threshold](antinuke-threshold.md): Override the count and window for an anti-nuke event.
- [antinuke protect](antinuke-protect.md): Turn a specific anti-nuke event family on or off.
- [antinuke incidents](antinuke-incidents.md): Review recent anti-nuke incidents for the server.
- [antinuke resetfreeze](antinuke-resetfreeze.md): Clear the active emergency freeze window manually.
