from __future__ import annotations

from app.infrastructure.database import build_database, initialize_database
from app.interfaces.telegram.bot import build_telegram_application
from app.settings import settings


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    engine, _ = build_database(settings.database_url)
    initialize_database(engine)
    application = build_telegram_application(settings.telegram_bot_token, settings.telegram_owner_id)
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
