# automod antiduplicate

> Generated from the shared Aegis command catalog.

## Summary

Configure duplicate-message spam detection.

## Description

Tracks repeated messages by the same user in a rolling window and can delete them, add strikes, or both.

## Syntax

- `^automod antiduplicate <strike-threshold|off> [delete-threshold] [strikes]`

## Access

Manage Server permission

## Aliases

`automod antispam`

## Examples

- `^automod antiduplicate 4`
- `^automod antiduplicate 6 3 2`
- `^automod antispam off`

## Notes

- Set `strikes` to `0` for delete-only handling.

## Related

[`automod maxlines`](automod-maxlines.md), [`punishment`](punishment.md)
