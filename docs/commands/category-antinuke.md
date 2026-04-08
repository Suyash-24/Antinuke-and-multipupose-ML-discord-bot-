# Anti-Nuke

Security controls for destructive admin activity, trust, freeze, and incident review.

## Commands

### [`antinuke`](antinuke.md)

Show the current anti-nuke status panel.

- **Syntax:** `^antinuke`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke status`](antinuke-status.md)

Show the anti-nuke status panel explicitly.

- **Syntax:** `^antinuke status`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke enable`](antinuke-enable.md)

Enable anti-nuke enforcement for the server.

- **Syntax:** `^antinuke enable`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke disable`](antinuke-disable.md)

Disable anti-nuke enforcement for the server.

- **Syntax:** `^antinuke disable`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke mode`](antinuke-mode.md)

Set the default anti-nuke response mode.

- **Syntax:** `^antinuke mode <contain|ban|alert>`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke log`](antinuke-log.md)

Set the anti-nuke incident log channel.

- **Syntax:** `^antinuke log [#channel|off]`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke trust`](antinuke-trust.md)

Show the anti-nuke trust list.

- **Syntax:** `^antinuke trust`
- **Access:** Server owner only

### [`antinuke trust add`](antinuke-trust-add.md)

Add a user or role to the anti-nuke trust list.

- **Syntax:** `^antinuke trust add <user|role>`
- **Access:** Server owner only

### [`antinuke trust remove`](antinuke-trust-remove.md)

Remove a user or role from the anti-nuke trust list.

- **Syntax:** `^antinuke trust remove <user|role>`
- **Access:** Server owner only

### [`antinuke threshold`](antinuke-threshold.md)

Override the count and window for an anti-nuke event.

- **Syntax:** `^antinuke threshold <event> <count> <seconds>`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke protect`](antinuke-protect.md)

Turn a specific anti-nuke event family on or off.

- **Syntax:** `^antinuke protect <event> <on|off>`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke incidents`](antinuke-incidents.md)

Review recent anti-nuke incidents for the server.

- **Syntax:** `^antinuke incidents [limit]`
- **Access:** Server owner or anti-nuke trusted entry

### [`antinuke resetfreeze`](antinuke-resetfreeze.md)

Clear the active emergency freeze window manually.

- **Syntax:** `^antinuke resetfreeze`
- **Access:** Server owner or anti-nuke trusted entry
