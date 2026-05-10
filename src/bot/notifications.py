"""
Telegram notification formatting and delivery.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from src.config import get_settings
from src.db.models import Job
from src.db.repository import get_job_repo

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special_chars else c for c in str(text))


def _score_emoji(score: int) -> str:
    if score >= 9:
        return "🔥"
    elif score >= 7:
        return "⭐"
    elif score >= 5:
        return "🟡"
    return "🔴"


def format_job_card(job: Job) -> tuple[str, InlineKeyboardMarkup]:
    """Format a job as a Telegram message card with inline buttons."""
    score = job.match_score or 0
    emoji = _score_emoji(score)

    summary = ""
    if job.match_report_json:
        try:
            report = json.loads(job.match_report_json)
            summary = report.get("summary", "")
        except json.JSONDecodeError:
            pass

    card = (
        f"{emoji} *Match Score: {score}/10*\n\n"
        f"💼 *{_escape_md(job.title)}*\n"
        f"🏢 {_escape_md(job.company)}\n"
        f"📍 {_escape_md(job.location)}\n"
    )
    if job.posted_date:
        card += f"📅 {_escape_md(job.posted_date)}\n"
    if summary:
        card += f"\n📝 _{_escape_md(summary)}_\n"
    if job.source_url:
        card += f"\n🔗 [Apply Link]({job.source_url})\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Draft Resume", callback_data=f"draft_{job.id}"),
            InlineKeyboardButton("❌ Ignore", callback_data=f"ignore_{job.id}"),
        ],
        [
            InlineKeyboardButton("📝 Details", callback_data=f"details_{job.id}"),
            InlineKeyboardButton("📨 Applied", callback_data=f"apply_{job.id}"),
        ],
    ])
    return card, keyboard


async def notify_new_matches(app: "Application") -> int:
    """Send notifications for unnotified high-scoring jobs."""
    settings = get_settings()
    job_repo = get_job_repo()

    jobs = await job_repo.get_unnotified_matches(min_score=settings.min_match_score)
    if not jobs:
        return 0

    user_ids = settings.allowed_user_ids
    if not user_ids:
        logger.warning("No ALLOWED_USER_IDS configured — skipping notifications")
        return 0

    sent = 0
    for job in jobs:
        card, keyboard = format_job_card(job)
        for user_id in user_ids:
            try:
                await app.bot.send_message(
                    chat_id=user_id, text=card,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=keyboard, disable_web_page_preview=True,
                )
                sent += 1
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
        await job_repo.mark_notified(job.id)

    logger.info(f"Sent {sent} notifications for {len(jobs)} jobs")
    return sent
