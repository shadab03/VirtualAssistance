"""
Telegram bot command and callback handlers.
"""

from __future__ import annotations

import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import get_settings
from src.db.models import JobStatus
from src.db.repository import get_job_repo, get_pref_repo
from src.scraper.scheduler import run_scrape_pipeline

logger = logging.getLogger(__name__)


# ===========================================================================
# Command Handlers
# ===========================================================================


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — Welcome message and quick setup."""
    user = update.effective_user
    pref_repo = get_pref_repo()

    # Initialize user preferences with defaults
    prefs = await pref_repo.get_or_create(user.id)

    welcome = (
        f"👋 *Welcome, {user.first_name}\\!*\n\n"
        f"🤖 I'm your *AI Job Search Assistant*\\. I monitor job postings, "
        f"score them against your profile, and help you apply\\.\n\n"
        f"*Your current setup:*\n"
        f"🎯 *Roles:* {_escape_md(', '.join(prefs.get_roles_list()) or 'None set')}\n"
        f"🌍 *Regions:* {_escape_md(', '.join(prefs.get_regions_list()) or 'None set')}\n"
        f"📊 *Min Score:* {prefs.min_score}/10\n\n"
        f"*Commands:*\n"
        f"/roles \\- View/update target roles\n"
        f"/regions \\- View/update search regions\n"
        f"/search \\- Run a manual job search\n"
        f"/stats \\- View job search statistics\n"
        f"/scan \\- Trigger a full scrape pipeline now\n"
        f"/help \\- Show this help message"
    )

    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — Show all available commands."""
    help_text = (
        "📖 *Available Commands*\n\n"
        "/start \\- Welcome \\& setup\n"
        "/roles \\- View/update target job roles\n"
        "/regions \\- View/update search regions\n"
        "/search `<query>` \\- Manual job search\n"
        "/stats \\- Job search statistics\n"
        "/scan \\- Run scrape pipeline now\n"
        "/profile \\- Upload/view master profile\n"
        "/help \\- This help message"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_roles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /roles — View or update target roles.
    Usage:
      /roles           — View current roles
      /roles set SAP ABAP Consultant, Solution Architect
      /roles add Data Engineer
      /roles remove SAP MM Consultant
    """
    user = update.effective_user
    pref_repo = get_pref_repo()
    prefs = await pref_repo.get_or_create(user.id)
    args = " ".join(context.args) if context.args else ""

    if not args:
        # Show current roles
        roles = prefs.get_roles_list()
        if roles:
            role_list = "\n".join(f"  • {r}" for r in roles)
            msg = f"🎯 *Your Target Roles:*\n{_escape_md(role_list)}"
        else:
            msg = "🎯 No roles configured\\."

        msg += (
            "\n\n*Usage:*\n"
            "`/roles set Role1, Role2, Role3`\n"
            "`/roles add New Role`\n"
            "`/roles remove Old Role`"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        return

    parts = args.split(" ", 1)
    action = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""

    if action == "set" and value:
        new_roles = [r.strip() for r in value.split(",") if r.strip()]
        await pref_repo.update_roles(user.id, new_roles)
        role_list = "\n".join(f"  ✅ {r}" for r in new_roles)
        await update.message.reply_text(
            f"🎯 Roles updated:\n{role_list}", parse_mode=None
        )

    elif action == "add" and value:
        roles = prefs.get_roles_list()
        new_role = value.strip()
        if new_role not in roles:
            roles.append(new_role)
            await pref_repo.update_roles(user.id, roles)
            await update.message.reply_text(
                f"✅ Added role: {new_role}", parse_mode=None
            )
        else:
            await update.message.reply_text(
                f"ℹ️ Role already exists: {new_role}", parse_mode=None
            )

    elif action == "remove" and value:
        roles = prefs.get_roles_list()
        target = value.strip()
        if target in roles:
            roles.remove(target)
            await pref_repo.update_roles(user.id, roles)
            await update.message.reply_text(
                f"🗑️ Removed role: {target}", parse_mode=None
            )
        else:
            await update.message.reply_text(
                f"⚠️ Role not found: {target}", parse_mode=None
            )

    else:
        await update.message.reply_text(
            "❌ Invalid usage. Try:\n"
            "/roles set SAP Consultant, Architect\n"
            "/roles add Data Engineer\n"
            "/roles remove SAP MM",
            parse_mode=None,
        )


async def cmd_regions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /regions — View or update search regions.
    Usage mirrors /roles: set, add, remove
    """
    user = update.effective_user
    pref_repo = get_pref_repo()
    prefs = await pref_repo.get_or_create(user.id)
    args = " ".join(context.args) if context.args else ""

    if not args:
        regions = prefs.get_regions_list()
        if regions:
            region_list = "\n".join(f"  • {r}" for r in regions)
            msg = f"🌍 *Your Search Regions:*\n{_escape_md(region_list)}"
        else:
            msg = "🌍 No regions configured\\."

        msg += (
            "\n\n*Usage:*\n"
            "`/regions set Saudi Arabia, UAE, Remote`\n"
            "`/regions add Germany`\n"
            "`/regions remove Remote`"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        return

    parts = args.split(" ", 1)
    action = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""

    if action == "set" and value:
        new_regions = [r.strip() for r in value.split(",") if r.strip()]
        await pref_repo.update_regions(user.id, new_regions)
        region_list = "\n".join(f"  ✅ {r}" for r in new_regions)
        await update.message.reply_text(
            f"🌍 Regions updated:\n{region_list}", parse_mode=None
        )

    elif action == "add" and value:
        regions = prefs.get_regions_list()
        new_region = value.strip()
        if new_region not in regions:
            regions.append(new_region)
            await pref_repo.update_regions(user.id, regions)
            await update.message.reply_text(
                f"✅ Added region: {new_region}", parse_mode=None
            )
        else:
            await update.message.reply_text(
                f"ℹ️ Region already exists: {new_region}", parse_mode=None
            )

    elif action == "remove" and value:
        regions = prefs.get_regions_list()
        target = value.strip()
        if target in regions:
            regions.remove(target)
            await pref_repo.update_regions(user.id, regions)
            await update.message.reply_text(
                f"🗑️ Removed region: {target}", parse_mode=None
            )
        else:
            await update.message.reply_text(
                f"⚠️ Region not found: {target}", parse_mode=None
            )

    else:
        await update.message.reply_text(
            "❌ Invalid usage. Try:\n"
            "/regions set Saudi Arabia, UAE\n"
            "/regions add Germany\n"
            "/regions remove Remote",
            parse_mode=None,
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats — Show job search statistics."""
    job_repo = get_job_repo()

    # Get stats for multiple periods
    stats_7d = await job_repo.get_stats(days=7)
    stats_1d = await job_repo.get_stats(days=1)

    msg = (
        "📊 *Job Search Statistics*\n\n"
        f"*Last 24 Hours:*\n"
        f"  🔍 Found: {stats_1d['total_found']}\n"
        f"  ⭐ Matched \\(≥7\\): {stats_1d['high_matches']}\n"
        f"  📨 Applied: {stats_1d['applied']}\n\n"
        f"*Last 7 Days:*\n"
        f"  🔍 Found: {stats_7d['total_found']}\n"
        f"  ⭐ Matched \\(≥7\\): {stats_7d['high_matches']}\n"
        f"  📨 Applied: {stats_7d['applied']}\n"
        f"  🚫 Ignored: {stats_7d['ignored']}"
    )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search <query> — Manual ad-hoc job search."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /search SAP ABAP Consultant Riyadh",
            parse_mode=None,
        )
        return

    query = " ".join(context.args)
    await update.message.reply_text(
        f"🔍 Searching for: *{_escape_md(query)}*\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    user = update.effective_user
    pref_repo = get_pref_repo()
    prefs = await pref_repo.get_or_create(user.id)
    regions = prefs.get_regions_list() or get_settings().default_regions

    from src.scraper.google_jobs import get_scraper

    scraper = get_scraper()
    all_jobs = []
    for region in regions:
        jobs = await scraper.search_jobs(query, region, num_results=5)
        all_jobs.extend(jobs)

    if not all_jobs:
        await update.message.reply_text(
            "😕 No jobs found for that search. Try different keywords.",
            parse_mode=None,
        )
        return

    # Save to DB and score
    job_repo = get_job_repo()
    new_count = await job_repo.save_jobs_batch(all_jobs)

    # Score new jobs
    settings = get_settings()
    matcher = None
    if settings.openai_api_key:
        from src.ai.matcher import get_matcher

        matcher = get_matcher()

    scored_count = 0
    for job in all_jobs:
        if matcher and job.id:
            try:
                report = await matcher.analyze_job(
                    job_description=job.description,
                    job_title=job.title,
                    company=job.company,
                    location=job.location,
                )
                await job_repo.update_job_score(
                    job.id, report.score, report.model_dump_json()
                )
                scored_count += 1
            except Exception as e:
                logger.error(f"Scoring failed for job {job.id}: {e}")

    # Send results
    results_msg = f"🔍 *Search Results for:* {_escape_md(query)}\n"
    results_msg += f"Found {len(all_jobs)} jobs \\({new_count} new\\)\n\n"

    # Show top 5 jobs
    from src.bot.notifications import format_job_card

    shown = 0
    for job in all_jobs[:5]:
        if job.id:
            db_job = await job_repo.get_job_by_id(job.id)
            if db_job:
                card, keyboard = format_job_card(db_job)
                await update.message.reply_text(
                    card,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=keyboard,
                )
                shown += 1

    if len(all_jobs) > 5:
        await update.message.reply_text(
            f"ℹ️ Showing top 5 of {len(all_jobs)} results.",
            parse_mode=None,
        )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /scan — Trigger a full scrape pipeline immediately."""
    await update.message.reply_text(
        "🔄 Running full scrape pipeline\\.\\.\\. This may take a minute\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    app = context.application
    summary = await run_scrape_pipeline(app)

    errors_text = ""
    if summary["errors"]:
        errors_text = "\n⚠️ Errors: " + "; ".join(summary["errors"][:3])

    msg = (
        f"✅ *Pipeline Complete*\n\n"
        f"🔍 Scraped: {summary['scraped']}\n"
        f"🆕 New: {summary['new_saved']}\n"
        f"🧠 Scored: {summary['scored']}\n"
        f"📤 Notified: {summary['notifications_sent']}"
        f"{_escape_md(errors_text)}"
    )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile — View or upload master profile."""
    settings = get_settings()
    profile_path = settings.data_dir / "master_profile.md"

    if update.message.document:
        # User is uploading a new profile
        file = await update.message.document.get_file()
        await file.download_to_drive(str(profile_path))

        # Clear the matcher's cached profile
        from src.ai.matcher import get_matcher

        get_matcher().clear_profile_cache()

        await update.message.reply_text(
            "✅ Master profile updated successfully!",
            parse_mode=None,
        )
        return

    # Show current profile info
    if profile_path.exists():
        content = profile_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        preview = "\n".join(lines[:10])
        msg = (
            f"📄 *Master Profile*\n"
            f"Size: {len(content)} characters\n"
            f"Lines: {len(lines)}\n\n"
            f"*Preview:*\n```\n{_escape_md(preview)}\n```\n\n"
            f"To update, send a \\`.md\\` file with /profile"
        )
    else:
        msg = (
            "📄 No master profile found\\.\n\n"
            "Send a markdown file \\(`.md`\\) to set your profile\\."
        )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ===========================================================================
# Callback Query Handlers (Inline Buttons)
# ===========================================================================


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data:
        return

    parts = data.split("_", 2)
    if len(parts) < 2:
        return

    action = parts[0]
    job_id = int(parts[1])

    job_repo = get_job_repo()
    job = await job_repo.get_job_by_id(job_id)

    if not job:
        await query.edit_message_text("⚠️ Job not found in database.")
        return

    if action == "details":
        await _show_details(query, job)
    elif action == "ignore":
        await _ignore_job(query, job, job_repo)
    elif action == "draft":
        await _draft_resume(query, job, context)
    elif action == "apply":
        await _mark_applied(query, job, job_repo)


async def _show_details(query, job: Job) -> None:
    """Show full job details and AI suitability report."""
    report_text = "No AI analysis available."
    if job.match_report_json:
        try:
            report = json.loads(job.match_report_json)
            matching = "\n".join(f"  ✅ {s}" for s in report.get("matching_skills", []))
            gaps = "\n".join(f"  ❌ {g}" for g in report.get("gap_analysis", []))
            keywords = ", ".join(report.get("keyword_suggestions", []))

            report_text = (
                f"📊 Score: {report.get('score', '?')}/10\n"
                f"📝 {report.get('summary', 'N/A')}\n\n"
                f"✅ Matching Skills:\n{matching}\n\n"
                f"❌ Gaps:\n{gaps}\n\n"
                f"🔑 Keywords: {keywords}\n\n"
                f"💡 Focus: {report.get('recommended_focus', 'N/A')}"
            )
        except json.JSONDecodeError:
            report_text = "Error parsing AI report."

    desc_preview = job.description[:800] + ("..." if len(job.description) > 800 else "")

    msg = (
        f"📋 {job.title}\n"
        f"🏢 {job.company}\n"
        f"📍 {job.location}\n"
        f"🔗 {job.source_url or 'No link'}\n\n"
        f"--- Description ---\n{desc_preview}\n\n"
        f"--- AI Analysis ---\n{report_text}"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Draft Resume", callback_data=f"draft_{job.id}"),
                InlineKeyboardButton("❌ Ignore", callback_data=f"ignore_{job.id}"),
            ],
            [
                InlineKeyboardButton("📨 Mark Applied", callback_data=f"apply_{job.id}"),
            ],
        ]
    )

    # Message might be too long for edit, try sending new
    try:
        await query.edit_message_text(msg, reply_markup=keyboard)
    except Exception:
        await query.message.reply_text(msg, reply_markup=keyboard)


async def _ignore_job(query, job: Job, job_repo) -> None:
    """Mark a job as ignored."""
    await job_repo.update_status(job.id, JobStatus.IGNORED)
    await query.edit_message_text(
        f"🚫 Ignored: {job.title} at {job.company}"
    )


async def _draft_resume(query, job: Job, context) -> None:
    """Trigger resume drafting (Phase 4 placeholder)."""
    await query.edit_message_text(
        f"📝 Drafting resume for:\n{job.title} at {job.company}\n\n"
        f"⏳ Resume generation will be available in Phase 4.\n"
        f"For now, the job has been marked for application."
    )
    job_repo = get_job_repo()
    await job_repo.update_status(job.id, JobStatus.DRAFTING)


async def _mark_applied(query, job: Job, job_repo) -> None:
    """Mark a job as applied."""
    await job_repo.update_status(job.id, JobStatus.APPLIED)

    from src.db.models import Applied

    applied = Applied(job_id=job.id)
    from src.db.engine import get_session_factory

    async with get_session_factory()() as session:
        session.add(applied)
        await session.commit()

    await query.edit_message_text(
        f"📨 Marked as applied: {job.title} at {job.company}"
    )


# ===========================================================================
# Utilities
# ===========================================================================


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    escaped = ""
    for char in text:
        if char in special_chars:
            escaped += f"\\{char}"
        else:
            escaped += char
    return escaped


# ===========================================================================
# Handler Registration
# ===========================================================================


def register_handlers(app) -> None:
    """Register all handlers with the Telegram application."""
    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("roles", cmd_roles))
    app.add_handler(CommandHandler("regions", cmd_regions))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("profile", cmd_profile))

    # Profile file upload (when user sends a document with /profile)
    app.add_handler(
        MessageHandler(filters.Document.ALL & filters.Caption("/profile"), cmd_profile)
    )

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("All Telegram handlers registered")
