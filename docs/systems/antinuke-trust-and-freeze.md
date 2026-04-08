# Anti-Nuke Trust and Freeze

Anti-nuke has stricter access control than the rest of Aegis on purpose.

## Trust model

By default, the server owner is always trusted.

Additional trusted entries can be added:

- trusted users
- trusted roles

Trusted entries bypass anti-nuke enforcement and can manage most anti-nuke settings.

## Owner-only controls

The most sensitive anti-nuke trust-list commands are owner-only:

- `^antinuke trust`
- `^antinuke trust add`
- `^antinuke trust remove`

## Emergency freeze

When anti-nuke triggers on an untrusted actor, Aegis activates an emergency freeze window.

During freeze:

- non-trusted staff are blocked from high-risk moderation commands
- trusted anti-nuke operators can still investigate and respond
- the owner can clear the freeze manually if needed

## Related commands

- `^antinuke status`
- `^antinuke trust`
- `^antinuke resetfreeze`
