from __future__ import annotations

import logging

from aegis.bot import AegisBot
from aegis.config import AppConfig

logging.basicConfig(level=logging.INFO)


def main() -> None:
    config = AppConfig.from_env()
    bot = AegisBot(config)
    bot.run(config.token)


if __name__ == "__main__":
    main()
