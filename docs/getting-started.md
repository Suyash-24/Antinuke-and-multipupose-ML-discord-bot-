# Getting Started

This guide is for Discord server admins and moderators using Aegis in a live server.
It focuses on in-server setup, not bot development or self-hosting.

## 1. Confirm Aegis is in your server

Use `^about` to confirm the bot is online and responsive.

If Aegis is not in the server yet, ask your server owner to invite it.

## 2. Check permissions and role position

Aegis needs moderation permissions to work correctly. Verify it can use:

- View Audit Log
- Manage Guild
- Manage Roles
- Manage Channels
- Manage Webhooks
- Manage Messages
- Kick Members
- Ban Members
- Moderate Members
- Move Members

Also place the Aegis role above roles it may need to mute or manage.

## 3. Set the main moderation channels

Run these first:

1. `^modlog #mod-logs`
2. `^messagelog #message-logs`
3. `^serverlog #server-logs`
4. `^voicelog #voice-logs`

## 4. Configure mute baseline

Run:

1. `^setup muted`
2. `^settings`

This ensures mute actions can be applied immediately.

## 5. Enable recommended AutoMod baseline

Suggested starting points:

- `^automod`
- `^punishment 1 warn`
- `^punishment 3 mute 1h`
- `^punishment 5 ban`
- `^automod antiinvite 2`
- `^automod antieveryone 1`
- `^automod antiduplicate 4 3 1`
- `^automod antiraid on`

## 6. Enable anti-nuke protection

Run:

1. `^antinuke enable`
2. `^antinuke mode contain`
3. `^antinuke status`

Anti-nuke access model:

- owner only: `^antinuke trust`, `^antinuke trust add`, `^antinuke trust remove`
- owner or anti-nuke trusted entry: most other `^antinuke` commands

## 7. Use help and docs in Discord

For discovery and onboarding, use:

- `^help`
- `^help moderation`
- `^help <command>`

Docs site:

- https://aegis.project-bot.workers.dev

## 8. Quick health checks

Run these after setup:

- `^settings`
- `^automod`
- `^antinuke status`
- `^check <user>` (moderator check)
