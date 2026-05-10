"""
Bot middleware — user authorization and error handling.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.config import get_settings

logger = logging.getLogger(__name__)


async def auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is authorized. Returns True if allowed."""
    settings = get_settings()

    # If no whitelist configured, allow everyone (dev mode)
    if not settings.allowed_user_ids:
        return True

    user_id = update.effective_user.id if update.effective_user else None
    if user_id and user_id in settings.allowed_user_ids:
        return True

    logger.warning(f"Unauthorized access attempt from user {user_id}")
    if update.message:
        await update.message.reply_text(
            "⛔ You are not authorized to use this bot."
        )
    return False


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for the Telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ An error occurred. Please try again later."
        )
