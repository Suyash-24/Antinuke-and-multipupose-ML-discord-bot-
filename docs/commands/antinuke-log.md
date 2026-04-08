# antinuke log

> Generated from the shared Aegis command catalog.

## Summary

Set the anti-nuke incident log channel.

## Description

Stores the channel used for anti-nuke incidents. If disabled, Aegis falls back to the moderation log or server log where possible.

## Syntax

- `^antinuke log [#channel|off]`

## Access

Server owner or anti-nuke trusted entry

## Aliases

None

## Examples

- `^antinuke log #security-logs`
- `^antinuke log off`

## Notes

- None

## Related

[`modlog`](modlog.md), [`serverlog`](serverlog.md), [`antinuke incidents`](antinuke-incidents.md)
