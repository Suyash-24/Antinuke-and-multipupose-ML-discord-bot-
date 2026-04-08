# punishment

> Generated from the shared Aegis command catalog.

## Summary

Map strike thresholds to automatic punishments.

## Description

Defines what Aegis should do when a member reaches a specific strike count, including warn, mute, kick, ban, softban, silentban, or removing a threshold.

## Syntax

- `^punishment <strikes> <warn|mute|kick|ban|softban|silentban|none> [duration]`

## Access

Manage Server permission

## Aliases

None

## Examples

- `^punishment 1 warn`
- `^punishment 3 mute 1h`
- `^punishment 5 ban`
- `^punishment 3 none`

## Notes

- None

## Related

[`strike`](strike.md), [`pardon`](pardon.md), [`check`](check.md)
