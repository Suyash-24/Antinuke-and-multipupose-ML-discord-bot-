# antinuke threshold

> Generated from the shared Aegis command catalog.

## Summary

Override the count and window for an anti-nuke event.

## Description

Customizes how many actions within how many seconds should trip an anti-nuke event family such as channel deletion or webhook creation.

## Syntax

- `^antinuke threshold <event> <count> <seconds>`

## Access

Server owner or anti-nuke trusted entry

## Aliases

None

## Examples

- `^antinuke threshold channel_delete 2 10`
- `^antinuke threshold webhook_create 1 20`

## Notes

- None

## Related

[`antinuke protect`](antinuke-protect.md), [`antinuke mode`](antinuke-mode.md)
