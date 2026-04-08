# antinuke mode

> Generated from the shared Aegis command catalog.

## Summary

Set the default anti-nuke response mode.

## Description

Chooses whether Aegis should `contain`, `ban`, or `alert` when an untrusted destructive threshold is reached.

## Syntax

- `^antinuke mode <contain|ban|alert>`

## Access

Server owner or anti-nuke trusted entry

## Aliases

None

## Examples

- `^antinuke mode contain`
- `^antinuke mode alert`

## Notes

- None

## Related

[`antinuke enable`](antinuke-enable.md), [`antinuke threshold`](antinuke-threshold.md)
