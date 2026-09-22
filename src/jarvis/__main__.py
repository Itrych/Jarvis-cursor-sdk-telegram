from __future__ import annotations

import asyncio
import logging
import sys

from jarvis.config import load_settings

log = logging.getLogger("jarvis")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    _configure_logging()
    settings = load_settings()
    log.info("projects_root=%s", settings.projects_root)
    log.info("default_model=%s", settings.default_model)
    log.info("telegram_token_set=%s", settings.telegram_ready)
    log.info("cursor_api_key_set=%s", settings.cursor_ready)
    log.info("allowed_user_ids=%s", sorted(settings.allowed_user_ids) or "bootstrap")

    if not settings.telegram_ready:
        log.error(
            "TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and fill it in."
        )
        sys.exit(1)

    from jarvis.bot import run_bot

    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    main()
