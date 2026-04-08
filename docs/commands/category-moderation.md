# Moderation

Hands-on actions for kicking, banning, muting, cleaning, and voice moderation.

## Commands

### [`kick`](kick.md)

Remove one or more members from the server.

- **Syntax:** `^kick <users...> [reason]`
- **Access:** Kick Members permission or configured mod role

### [`ban`](ban.md)

Ban one or more users permanently or for a duration.

- **Syntax:** `^ban <users...> [duration] [reason]`
- **Access:** Ban Members permission or configured mod role

### [`silentban`](silentban.md)

Ban users without deleting message history.

- **Syntax:** `^silentban <users...> [duration] [reason]`
- **Access:** Ban Members permission or configured mod role

### [`softban`](softban.md)

Ban and immediately unban a member to clear recent messages.

- **Syntax:** `^softban <users...> [reason]`
- **Access:** Ban Members permission or configured mod role

### [`unban`](unban.md)

Remove an active ban from one or more users.

- **Syntax:** `^unban <users...> [reason]`
- **Access:** Ban Members permission or configured mod role

### [`mute`](mute.md)

Apply the configured muted role to one or more members.

- **Syntax:** `^mute <users...> [duration] [reason]`
- **Access:** Manage Roles permission or configured mod role

### [`unmute`](unmute.md)

Remove the muted role from one or more members.

- **Syntax:** `^unmute <users...> [reason]`
- **Access:** Manage Roles permission or configured mod role

### [`clean`](clean.md)

Bulk-delete messages with optional content and user filters.

- **Syntax:** `^clean <amount> [filters...]`
- **Access:** Manage Messages permission or configured mod role

### [`voicekick`](voicekick.md)

Disconnect one or more members from voice.

- **Syntax:** `^voicekick <users...> [reason]`
- **Access:** Move Members permission or configured mod role

### [`voicemove`](voicemove.md)

Start a guided voice move session with Aegis.

- **Syntax:** `^voicemove`
- **Access:** Move Members permission or configured mod role

### [`voicemovestop`](voicemovestop.md)

End the current voice move session and disconnect Aegis.

- **Syntax:** `^voicemovestop`
- **Access:** Move Members permission or configured mod role
