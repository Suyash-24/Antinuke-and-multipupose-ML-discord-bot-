# AutoMod

Automated moderation, strike management, and raid protection controls.

## Commands

### [`automod`](automod.md)

Show the current AutoMod snapshot for the server.

- **Syntax:** `^automod`
- **Access:** Manage Server permission

### [`automod show`](automod-show.md)

Alias for the main AutoMod snapshot view.

- **Syntax:** `^automod show`
- **Access:** Manage Server permission

### [`automod antiinvite`](automod-antiinvite.md)

Set the invite filter punishment.

- **Syntax:** `^automod antiinvite <strikes|delete|off>`
- **Access:** Manage Server permission

### [`automod antireferral`](automod-antireferral.md)

Set the referral-link punishment.

- **Syntax:** `^automod antireferral <strikes|delete|off>`
- **Access:** Manage Server permission

### [`automod anticopypasta`](automod-anticopypasta.md)

Detect and punish known copypasta spam.

- **Syntax:** `^automod anticopypasta <strikes|delete|off>`
- **Access:** Manage Server permission

### [`automod antieveryone`](automod-antieveryone.md)

Control punishment for `@everyone` and `@here` abuse.

- **Syntax:** `^automod antieveryone <strikes|delete|off>`
- **Access:** Manage Server permission

### [`automod maxmentions`](automod-maxmentions.md)

Set the mention threshold for regular user mentions.

- **Syntax:** `^automod maxmentions <count|off>`
- **Access:** Manage Server permission

### [`automod maxrolementions`](automod-maxrolementions.md)

Set the threshold for role mentions in one message.

- **Syntax:** `^automod maxrolementions <count|off>`
- **Access:** Manage Server permission

### [`automod maxlines`](automod-maxlines.md)

Set the line-count threshold for multi-line spam.

- **Syntax:** `^automod maxlines <count|off>`
- **Access:** Manage Server permission

### [`automod antiduplicate`](automod-antiduplicate.md)

Configure duplicate-message spam detection.

- **Syntax:** `^automod antiduplicate <strike-threshold|off> [delete-threshold] [strikes]`
- **Access:** Manage Server permission

### [`automod resolvelinks`](automod-resolvelinks.md)

Enable or disable redirect-link resolution.

- **Syntax:** `^automod resolvelinks <on|off>`
- **Access:** Manage Server permission

### [`automod autodehoist`](automod-autodehoist.md)

Configure automatic nickname dehoisting.

- **Syntax:** `^automod autodehoist <character|off>`
- **Access:** Manage Server permission

### [`automod whitelist`](automod-whitelist.md)

Manage the invite whitelist for allowed guild IDs.

- **Syntax:** `^automod whitelist <add|remove|show> [guild-id...]`
- **Access:** Manage Server permission

### [`automod filter`](automod-filter.md)

Show the current custom AutoMod filters.

- **Syntax:** `^automod filter`
- **Access:** Manage Server permission

### [`automod filter add`](automod-filter-add.md)

Create or update a named custom AutoMod filter.

- **Syntax:** `^automod filter add <name> <strikes> <patterns...>`
- **Access:** Manage Server permission

### [`automod filter remove`](automod-filter-remove.md)

Delete a named custom filter.

- **Syntax:** `^automod filter remove <name>`
- **Access:** Manage Server permission

### [`automod filter list`](automod-filter-list.md)

List all custom AutoMod filters for the server.

- **Syntax:** `^automod filter list`
- **Access:** Manage Server permission

### [`automod antiraid`](automod-antiraid.md)

Configure the join-burst trigger for automatic raid mode.

- **Syntax:** `^automod antiraid <on|off|joins/seconds>`
- **Access:** Manage Server permission

### [`automod ignore`](automod-ignore.md)

Exclude a role or channel from AutoMod enforcement.

- **Syntax:** `^automod ignore <role|channel>`
- **Access:** Manage Server permission

### [`automod unignore`](automod-unignore.md)

Remove a role or channel from the AutoMod ignore list.

- **Syntax:** `^automod unignore <role|channel>`
- **Access:** Manage Server permission

### [`punishment`](punishment.md)

Map strike thresholds to automatic punishments.

- **Syntax:** `^punishment <strikes> <warn|mute|kick|ban|softban|silentban|none> [duration]`
- **Access:** Manage Server permission

### [`strike`](strike.md)

Manually add strikes to one or more members.

- **Syntax:** `^strike [count] <users...> <reason>`
- **Access:** Moderate Members permission or configured mod role

### [`pardon`](pardon.md)

Manually remove strikes from one or more members.

- **Syntax:** `^pardon [count] <users...> <reason>`
- **Access:** Moderate Members permission or configured mod role

### [`check`](check.md)

Inspect a member's moderation state in one panel.

- **Syntax:** `^check`
- **Access:** Moderate Members permission or configured mod role

### [`raidmode`](raidmode.md)

Manually turn raid mode on or off.

- **Syntax:** `^raidmode <on|off> [reason]`
- **Access:** Manage Server permission
