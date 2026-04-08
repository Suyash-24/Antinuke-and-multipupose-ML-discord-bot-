# automod filter add

> Generated from the shared Aegis command catalog.

## Summary

Create or update a named custom AutoMod filter.

## Description

Defines a named filter with one or more patterns and a strike value. Aegis can match quotes, glob-like patterns, and regex entries.

## Syntax

- `^automod filter add <name> <strikes> <patterns...>`

## Access

Manage Server permission

## Aliases

`automod filter create`

## Examples

- `^automod filter add scam 2 "free nitro" regex:^steam gift$`

## Notes

- None

## Related

[`automod filter remove`](automod-filter-remove.md), [`automod filter list`](automod-filter-list.md)
