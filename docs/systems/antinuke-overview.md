# Anti-Nuke

Anti-nuke protects the server itself when destructive administrative behavior starts happening in real time.

## What it watches

Aegis anti-nuke focuses on core destructive actions such as:

- channel creation, deletion, and update bursts
- role creation, deletion, and dangerous permission updates
- webhook creation, deletion, and updates
- unauthorized bot additions
- security-relevant guild updates

## Response modes

- **contain**: try to strip dangerous roles or remove the malicious bot, then freeze high-risk commands
- **ban**: ban the actor when possible, then freeze
- **alert**: log only, with no automatic punishment

## Why conservative rollback matters

Anti-nuke intentionally avoids broad “rebuild the server” behavior in v1. Safe rollback is limited to narrow, deterministic changes such as newly added bots, new webhooks, or certain dangerous permission grants.

## Related commands

- `^antinuke`
- `^antinuke enable`
- `^antinuke mode`
- `^antinuke threshold`
- `^antinuke incidents`
