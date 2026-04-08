# antinuke trust remove

> Generated from the shared Aegis command catalog.

## Summary

Remove a user or role from the anti-nuke trust list.

## Description

Removes a bypass entry so the user or role is once again subject to anti-nuke enforcement and cannot manage anti-nuke settings.

## Syntax

- `^antinuke trust remove <user|role>`

## Access

Server owner only

## Aliases

None

## Examples

- `^antinuke trust remove @HeadAdmin`

## Notes

- None

## Related

[`antinuke trust add`](antinuke-trust-add.md)
