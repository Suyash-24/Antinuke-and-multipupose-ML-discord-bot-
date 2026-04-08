# Logging

Aegis separates logs by purpose so moderators do not have to dig through one noisy channel to reconstruct what happened.

## Log types

- **Mod log**: moderation cases like kicks, bans, mutes, pardons, and strike-triggered punishments
- **Message log**: message edits, deletions, and bulk delete archives
- **Server log**: joins, leaves, role changes, channel changes, and other guild events
- **Voice log**: voice joins, leaves, moves, and voice state changes
- **Anti-nuke log**: anti-nuke incidents, responses, rollback outcomes, and freeze state

## Why separate logs matter

This keeps high-signal investigation data readable:

- moderators can review punishments without scanning message edits
- message moderation evidence is preserved in the right place
- destructive server actions can be reviewed without being buried under normal staff work

## Related commands

- `^modlog`
- `^messagelog`
- `^serverlog`
- `^voicelog`
- `^antinuke log`
- `^settings`
