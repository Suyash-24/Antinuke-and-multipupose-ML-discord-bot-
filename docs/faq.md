# Troubleshooting

## `^help` does not show docs buttons

Use the docs site directly:

- https://aegis.project-bot.workers.dev

If docs buttons are missing in your server, ask the bot maintainer to set `DOCS_BASE_URL`.

## `^mute` says the mute role is missing

Run:

```text
^setup muted
```

## AutoMod rules are enabled but no punishments happen

Check the strike ladder with:

```text
^automod
^settings
```

Then configure thresholds with `^punishment`.

## Anti-nuke status says the server is degraded

Review:

- `View Audit Log`
- `Manage Roles`
- `Ban Members`
- `Manage Webhooks`
- bot role position relative to dangerous staff roles

## `clean` skipped old messages

Discord cannot bulk-delete messages older than two weeks.

## The docs site changed but pages look stale

Your browser is probably caching an older version. Try a hard refresh first.

- Windows/Linux: `Ctrl+F5`
- macOS: `Cmd+Shift+R`

If it still looks stale, reopen the docs tab.
