"""
Job scraping pipeline scheduler.
Orchestrates: Scrape → Deduplicate → Score → Notify
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.ai.matcher import get_matcher
from src.config import get_settings
from src.db.models import Job
from src.db.repository import get_job_repo, get_pref_repo
from src.scraper.google_jobs import get_scraper

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_scrape_pipeline(app: Application | None = None) -> dict:
    """
    The main job scraping pipeline:
    1. Collect unique role/region combos from all user preferences
    2. Scrape Google Jobs for each combo
    3. Save to DB (dedup handled by repository)
    4. Score new (unscored) jobs with AI
    5. Send notifications for high-scoring matches

    Returns a summary dict of what happened.
    """
    settings = get_settings()
    scraper = get_scraper()
    job_repo = get_job_repo()
    pref_repo = get_pref_repo()
    matcher = get_matcher()

    summary = {
        "scraped": 0,
        "new_saved": 0,
        "scored": 0,
        "notifications_sent": 0,
        "errors": [],
    }

    # Step 1: Gather all active role/region combinations
    combos = await pref_repo.get_all_active_configs()
    if not combos:
        # Fallback to defaults if no user preferences exist
        roles = settings.default_roles
        regions = settings.default_regions
    else:
        roles = list({c["role"] for c in combos})
        regions = list({c["region"] for c in combos})

    logger.info(f"Pipeline starting: {len(roles)} roles × {len(regions)} regions")

    # Step 2: Scrape
    try:
        jobs = await scraper.search_all_combos(roles, regions, num_results=10)
        summary["scraped"] = len(jobs)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        summary["errors"].append(f"Scraping: {e}")
        return summary

    # Step 3: Save to DB (dedup)
    try:
        new_count = await job_repo.save_jobs_batch(jobs)
        summary["new_saved"] = new_count
        logger.info(f"Saved {new_count} new jobs (of {len(jobs)} scraped)")
    except Exception as e:
        logger.error(f"DB save failed: {e}")
        summary["errors"].append(f"DB save: {e}")
        return summary

    # Step 4: Score unscored jobs with AI
    if settings.openai_api_key:
        unscored = await job_repo.get_unscored_jobs(limit=20)
        for job in unscored:
            try:
                report = await matcher.analyze_job(
                    job_description=job.description,
                    job_title=job.title,
                    company=job.company,
                    location=job.location,
                )
                await job_repo.update_job_score(
                    job_id=job.id,
                    score=report.score,
                    report_json=report.model_dump_json(),
                )
                summary["scored"] += 1
            except Exception as e:
                logger.error(f"Scoring failed for job {job.id}: {e}")
                summary["errors"].append(f"Scoring job {job.id}: {e}")
    else:
        logger.warning("OpenAI API key not set — skipping AI scoring")

    # Step 5: Notify via Telegram
    if app:
        try:
            from src.bot.notifications import notify_new_matches

            count = await notify_new_matches(app)
            summary["notifications_sent"] = count
        except Exception as e:
            logger.error(f"Notification failed: {e}")
            summary["errors"].append(f"Notifications: {e}")

    logger.info(
        f"Pipeline complete: {summary['scraped']} scraped, "
        f"{summary['new_saved']} new, {summary['scored']} scored, "
        f"{summary['notifications_sent']} notified"
    )
    return summary


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    """
    Setup the APScheduler to run the pipeline at configured intervals.
    The app reference is passed so notifications can be sent.
    """
    global _scheduler
    settings = get_settings()

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_scrape_pipeline,
        "interval",
        minutes=settings.scrape_interval_minutes,
        args=[app],
        id="job_scrape_pipeline",
        name="Job Scrape Pipeline",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )

    logger.info(
        f"Scheduler configured: pipeline runs every {settings.scrape_interval_minutes} minutes"
    )
    return _scheduler


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
