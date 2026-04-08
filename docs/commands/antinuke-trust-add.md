# antinuke trust add

> Generated from the shared Aegis command catalog.

## Summary

Add a user or role to the anti-nuke trust list.

## Description

Adds a role or individual user that should bypass anti-nuke enforcement. Use this carefully, because trusted entries can change anti-nuke settings and ignore enforcement.

## Syntax

- `^antinuke trust add <user|role>`

## Access

Server owner only

## Aliases

None

## Examples

- `^antinuke trust add @HeadAdmin`
- `^antinuke trust add @Security`

## Notes

- None

## Related

[`antinuke trust`](antinuke-trust.md), [`antinuke trust remove`](antinuke-trust-remove.md)
