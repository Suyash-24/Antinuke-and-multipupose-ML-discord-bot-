# Aegis

Aegis is a Python moderation bot built around the same core ideas that make serious moderation tools useful in practice:

- focused moderation commands
- structured logging
- configurable AutoMod
- strike-based escalation
- real-time anti-nuke protection

## Why Aegis exists

The goal is not to cram in every possible command. Aegis focuses on the moderation surface that actually matters when a team is handling spam, raids, punishment history, and destructive admin behavior.

## What you can do with Aegis

### Moderate directly

Use commands like `^kick`, `^ban`, `^mute`, `^clean`, `^voicekick`, and `^voicemove` for fast staff action.

### Configure automation

Tune invite filtering, mention limits, duplicate-message spam handling, custom pattern filters, and anti-raid behavior under the `^automod` command group.

### Protect the server itself

Use `^antinuke` to monitor destructive admin activity, control anti-nuke mode, manage trusted entries, and review incidents.

### Keep an audit trail

Aegis separates moderation logs, message logs, server logs, voice logs, and anti-nuke incident logs so staff can review what happened later.

## Recommended reading

- Start with [Getting Started](getting-started.md) if you are adding Aegis to a new server.
- Use [Commands](commands/index.md) for syntax and examples.
- Use [Systems](systems/index.md) to understand how strikes, logging, raid mode, and anti-nuke work together.

## In Discord

Once the custom help command is available in your bot deployment, you can also use:

- `^help`
- `^help moderation`
- `^help ban`
- `^help antinuke mode`
