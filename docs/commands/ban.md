# ban

> Generated from the shared Aegis command catalog.

## Summary

Ban one or more users permanently or for a duration.

## Description

Bans the selected users, deletes recent messages, optionally schedules an automatic unban, and records the case for later review.

## Syntax

- `^ban <users...> [duration] [reason]`

## Access

Ban Members permission or configured mod role

## Aliases

None

## Examples

- `^ban @user scam links`
- `^ban @user 7d raid alt`

## Notes

- Temporary bans are tracked by the scheduler and removed automatically when they expire.

## Related

[`silentban`](silentban.md), [`softban`](softban.md), [`unban`](unban.md)
