"""
JobFinderAI — Main entry point.
Bootstraps the Telegram bot, database, and scheduler.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os
from pathlib import Path

from telegram.ext import ApplicationBuilder

from src.bot.handlers import register_handlers
from src.bot.middleware import error_handler
from src.config import get_settings
from src.db.engine import close_db, init_db
from src.scraper.scheduler import setup_scheduler


def setup_logging() -> None:
    """Configure application logging."""
    settings = get_settings()

    logging.basicConfig(
        format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
        level=getattr(logging, settings.log_level, logging.INFO),
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


def ensure_directories() -> None:
    """Create necessary data directories."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    (settings.output_dir / "resumes").mkdir(exist_ok=True)


async def handle_web_request(reader, writer):
    """Dummy web server to satisfy Render's Web Service port binding."""
    try:
        await reader.read(1024)
        response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nJobFinderAI is running!"
        writer.write(response.encode("utf-8"))
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()

async def start_dummy_server():
    """Start the dummy web server."""
    port = int(os.environ.get("PORT", 8080))
    server = await asyncio.start_server(handle_web_request, "0.0.0.0", port)
    logging.getLogger(__name__).info(f"Dummy web server listening on port {port} (for Render free tier)")
    async with server:
        await server.serve_forever()

async def post_init(application) -> None:
    """Called after the Application has been initialized."""
    # Initialize database
    await init_db()

    # Setup and start the scheduler
    scheduler = setup_scheduler(application)
    scheduler.start()

    # Start dummy web server in the background for Render Free Tier
    asyncio.create_task(start_dummy_server())

    logger = logging.getLogger(__name__)
    logger.info("🚀 JobFinderAI is ready!")


async def post_shutdown(application) -> None:
    """Called when the Application is shutting down."""
    from src.scraper.scheduler import get_scheduler

    scheduler = get_scheduler()
    if scheduler:
        scheduler.shutdown(wait=False)

    await close_db()
    logging.getLogger(__name__).info("👋 JobFinderAI shut down cleanly")


def main() -> None:
    """Main entry point — build and run the Telegram bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    settings = get_settings()

    # Validate critical config
    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith("your_"):
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN not configured!\n"
            "   1. Copy .env.example to .env\n"
            "   2. Get a token from @BotFather on Telegram\n"
            "   3. Set TELEGRAM_BOT_TOKEN in .env"
        )
        sys.exit(1)

    ensure_directories()

    logger.info("=" * 60)
    logger.info("  JobFinderAI — Starting Up")
    logger.info(f"  Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'SQLite'}")
    logger.info(f"  Roles: {settings.default_roles}")
    logger.info(f"  Regions: {settings.default_regions}")
    logger.info(f"  Scrape interval: {settings.scrape_interval_minutes} min")
    logger.info(f"  Min match score: {settings.min_match_score}")
    logger.info("=" * 60)

    # Build the Telegram application
    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register all handlers
    register_handlers(application)

    # Register global error handler
    application.add_error_handler(error_handler)

    # Run with long polling
    logger.info("Starting Telegram bot with long polling...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
