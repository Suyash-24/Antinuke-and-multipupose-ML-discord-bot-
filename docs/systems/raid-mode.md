# Raid Mode

Raid mode is the fast-response layer for suspicious join floods.

## Manual raid mode

Use `^raidmode on` when staff can already see a raid starting. Aegis raises the verification level and logs the override.

Use `^raidmode off` when the situation is under control.

## Automatic raid mode

Use `^automod antiraid` to define a joins-per-seconds threshold. When that burst is detected, Aegis enables raid mode automatically.

## When to use it

Raid mode is for join pressure and immediate gate-hardening.

It is not the same as anti-nuke:

- **raid mode**: suspicious member joins
- **anti-nuke**: destructive administrative actions

## Related commands

- `^raidmode`
- `^automod antiraid`
