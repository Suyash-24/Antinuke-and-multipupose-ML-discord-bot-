from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DOCS_BASE_URL = "https://aegis.project-bot.workers.dev"


@dataclass(slots=True)
class AppConfig:
    token: str
    prefix: str
    database_path: Path
    client_id: int | None = None
    docs_base_url: str | None = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is required. Add it to your environment or .env file.")

        client_id_raw = os.getenv("DISCORD_CLIENT_ID")
        docs_base_url = os.getenv("DOCS_BASE_URL", DEFAULT_DOCS_BASE_URL)
        database_path = Path(os.getenv("AEGIS_DATABASE_PATH", "data/aegis.db"))
        database_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            token=token,
            prefix="^",
            database_path=database_path,
            client_id=int(client_id_raw) if client_id_raw else None,
            docs_base_url=docs_base_url.strip().rstrip("/") if docs_base_url else None,
        )
