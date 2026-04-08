# kick

> Generated from the shared Aegis command catalog.

## Summary

Remove one or more members from the server.

## Description

Kicks the selected members after hierarchy checks, sends them a DM when possible, and records a moderation case in the mod log.

## Syntax

- `^kick <users...> [reason]`

## Access

Kick Members permission or configured mod role

## Aliases

None

## Examples

- `^kick @user spam`
- `^kick @user1 @user2 repeated rule breaking`

## Notes

- Non-trusted staff are rate-limited and capped on high-risk moderation actions.

## Related

[`ban`](ban.md), [`mute`](mute.md), [`clean`](clean.md)
