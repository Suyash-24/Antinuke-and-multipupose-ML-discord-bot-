# softban

> Generated from the shared Aegis command catalog.

## Summary

Ban and immediately unban a member to clear recent messages.

## Description

Softban requires the user to still be in the server. Aegis bans them to remove recent content and then immediately unbans them so they can rejoin later.

## Syntax

- `^softban <users...> [reason]`

## Access

Ban Members permission or configured mod role

## Aliases

None

## Examples

- `^softban @user flood cleanup`

## Notes

- Softban only works for members who are still present in the guild.

## Related

[`ban`](ban.md), [`clean`](clean.md)
