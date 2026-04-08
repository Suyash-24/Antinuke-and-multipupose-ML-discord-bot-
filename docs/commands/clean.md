# clean

> Generated from the shared Aegis command catalog.

## Summary

Bulk-delete messages with optional content and user filters.

## Description

Purges recent channel messages in bulk. You can filter by amount, member/user, plain text, regex, bots, embeds, links, or images.

## Syntax

- `^clean <amount> [filters...]`

## Access

Manage Messages permission or configured mod role

## Aliases

None

## Examples

- `^clean 50`
- `^clean 100 @user links`
- `^clean 25 `free nitro``

## Notes

- Messages older than two weeks cannot be bulk-deleted by Discord.
- Non-trusted staff are capped on large clean requests.

## Related

[`kick`](kick.md), [`softban`](softban.md)
