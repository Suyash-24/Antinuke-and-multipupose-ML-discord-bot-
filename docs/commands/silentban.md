# silentban

> Generated from the shared Aegis command catalog.

## Summary

Ban users without deleting message history.

## Description

Works like `ban` but keeps message deletion at zero seconds. This is useful when you want the ban without wiping recent evidence from channels.

## Syntax

- `^silentban <users...> [duration] [reason]`

## Access

Ban Members permission or configured mod role

## Aliases

None

## Examples

- `^silentban @user evidence preserved`
- `^silentban @user 1d manual review`

## Notes

- None

## Related

[`ban`](ban.md), [`softban`](softban.md), [`unban`](unban.md)
