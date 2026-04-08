# Aegis

Aegis is a Python Discord moderation bot focused on practical server operations:

- focused moderation commands
- structured logging
- configurable AutoMod
- strike-based punishment ladders
- anti-nuke protection for destructive admin activity

## Runtime

- Python `3.11+`
- `discord.py 2.6`
- SQLite via `aiosqlite`

## Quick Start

1. Copy `.env.example` to `.env`
2. Set:
   - `DISCORD_TOKEN`
   - `DISCORD_CLIENT_ID`
   - `AEGIS_DATABASE_PATH`
   - `DOCS_BASE_URL=https://aegis.project-bot.workers.dev` so `^help` links into the published docs site
3. Install the bot:

```bash
python -m pip install -e .
```

4. Start Aegis:

```bash
python -m aegis.main
```

## Docs

The full command reference and system guides live in the MkDocs site under `docs/`.

Generate the command pages from the shared catalog:

```bash
python scripts/generate_docs.py
```

Install docs tooling:

```bash
python -m pip install -e .[docs]
```

Preview the docs locally:

```bash
mkdocs serve
```

Build the static site:

```bash
mkdocs build
```

## Deploy Docs To Cloudflare Pages

1. Push this repository to GitHub.
2. In Cloudflare Dashboard, open `Workers & Pages` -> `Create` -> `Pages` -> `Connect to Git`.
3. Select this repo and configure:
   - `Framework preset`: `None`
   - `Build command`: `python -m pip install -e .[docs] && python scripts/generate_docs.py && mkdocs build --strict`
   - `Build output directory`: `site`
   - `Root directory`: `/` (default)
4. In Pages project settings, set environment variable:
   - `PYTHON_VERSION=3.11`
5. Deploy. Cloudflare will provide a free `*.pages.dev` URL.

### Optional: Custom Domain

1. In your Pages project, go to `Custom domains` and add your domain/subdomain.
2. Set `DOCS_BASE_URL` for your bot to that final docs URL so `^help` buttons deep-link correctly.
   - Current URL: `https://aegis.project-bot.workers.dev`
3. Set `site_url` in `mkdocs.yml` to the same final URL.

## In Discord

Aegis ships with a custom help command backed by the same shared command catalog as the docs site:

- `^help`
- `^help moderation`
- `^help ban`
- `^help antinuke mode`

## Notes

- Anti-nuke trust-list changes are owner-only.
- Most other anti-nuke controls are limited to the owner plus explicitly trusted anti-nuke entries.
- High-risk moderation commands are rate-limited for non-trusted staff when anti-nuke protections are active.