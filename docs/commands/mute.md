# mute

> Generated from the shared Aegis command catalog.

## Summary

Apply the configured muted role to one or more members.

## Description

Adds the Aegis muted role to the selected members, optionally schedules an automatic unmute, and records the case.

## Syntax

- `^mute <users...> [duration] [reason]`

## Access

Manage Roles permission or configured mod role

## Aliases

None

## Examples

- `^mute @user 30m cooldown`
- `^mute @user excessive arguments`

## Notes

- The muted role must be created first with `^setup muted`.

## Related

[`unmute`](unmute.md), [`setup muted`](setup-muted.md), [`punishment`](punishment.md)
