"""
Data access layer — async repository pattern for all database operations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session_factory
from src.db.models import Applied, Job, JobStatus, UserPreference

logger = logging.getLogger(__name__)


class JobRepository:
    """Handles all Job-related database operations."""

    async def _get_session(self) -> AsyncSession:
        """Create a new session."""
        factory = get_session_factory()
        return factory()

    async def save_job(self, job: Job) -> tuple[Job, bool]:
        """
        Save a job to the database. Returns (job, is_new).
        Skips if source_id already exists (deduplication).
        """
        async with await self._get_session() as session:
            # Check for existing job by source_id
            result = await session.exec(
                select(Job).where(Job.source_id == job.source_id)
            )
            existing = result.first()

            if existing:
                logger.debug(f"Job already exists: {job.source_id}")
                return existing, False

            session.add(job)
            await session.commit()
            await session.refresh(job)
            logger.info(f"New job saved: '{job.title}' at '{job.company}'")
            return job, True

    async def save_jobs_batch(self, jobs: list[Job]) -> int:
        """Save multiple jobs, skip duplicates. Returns count of new jobs."""
        new_count = 0
        for job in jobs:
            _, is_new = await self.save_job(job)
            if is_new:
                new_count += 1
        return new_count

    async def get_unscored_jobs(self, limit: int = 50) -> list[Job]:
        """Get jobs that haven't been scored by AI yet."""
        async with await self._get_session() as session:
            result = await session.exec(
                select(Job)
                .where(Job.match_score.is_(None))  # type: ignore
                .where(Job.status == JobStatus.NEW)
                .order_by(Job.discovered_at.desc())  # type: ignore
                .limit(limit)
            )
            return list(result.all())

    async def update_job_score(
        self, job_id: int, score: int, report_json: str
    ) -> None:
        """Update a job's match score and report."""
        async with await self._get_session() as session:
            result = await session.exec(
                select(Job).where(Job.id == job_id)
            )
            job = result.first()
            if job:
                job.match_score = score
                job.match_report_json = report_json
                job.status = JobStatus.SCORED
                job.status_updated_at = datetime.utcnow()
                session.add(job)
                await session.commit()

    async def get_unnotified_matches(self, min_score: int = 7) -> list[Job]:
        """Get high-scoring jobs that haven't been sent to Telegram yet."""
        async with await self._get_session() as session:
            result = await session.exec(
                select(Job)
                .where(Job.match_score >= min_score)
                .where(Job.status == JobStatus.SCORED)
                .order_by(Job.match_score.desc())  # type: ignore
            )
            return list(result.all())

    async def mark_notified(self, job_id: int) -> None:
        """Mark a job as notified (sent to Telegram)."""
        async with await self._get_session() as session:
            result = await session.exec(
                select(Job).where(Job.id == job_id)
            )
            job = result.first()
            if job:
                job.status = JobStatus.NOTIFIED
                job.notified_at = datetime.utcnow()
                job.status_updated_at = datetime.utcnow()
                session.add(job)
                await session.commit()

    async def update_status(self, job_id: int, status: JobStatus) -> None:
        """Update a job's lifecycle status."""
        async with await self._get_session() as session:
            result = await session.exec(
                select(Job).where(Job.id == job_id)
            )
            job = result.first()
            if job:
                job.status = status
                job.status_updated_at = datetime.utcnow()
                session.add(job)
                await session.commit()

    async def get_job_by_id(self, job_id: int) -> Optional[Job]:
        """Fetch a single job by ID."""
        async with await self._get_session() as session:
            result = await session.exec(
                select(Job).where(Job.id == job_id)
            )
            return result.first()

    async def get_stats(self, days: int = 7) -> dict:
        """Get aggregated statistics for the past N days."""
        async with await self._get_session() as session:
            cutoff = datetime.utcnow() - timedelta(days=days)

            # Total jobs found
            total_result = await session.exec(
                select(func.count(Job.id)).where(Job.discovered_at >= cutoff)
            )
            total = total_result.one()

            # Jobs by score range
            high_match_result = await session.exec(
                select(func.count(Job.id))
                .where(Job.discovered_at >= cutoff)
                .where(Job.match_score >= 7)
            )
            high_matches = high_match_result.one()

            # Applied count
            applied_result = await session.exec(
                select(func.count(Applied.id))
                .where(Applied.applied_at >= cutoff)
            )
            applied = applied_result.one()

            # Ignored count
            ignored_result = await session.exec(
                select(func.count(Job.id))
                .where(Job.discovered_at >= cutoff)
                .where(Job.status == JobStatus.IGNORED)
            )
            ignored = ignored_result.one()

            return {
                "period_days": days,
                "total_found": total,
                "high_matches": high_matches,
                "applied": applied,
                "ignored": ignored,
            }


class PreferenceRepository:
    """Handles user preference operations."""

    async def get_or_create(self, user_id: int) -> UserPreference:
        """Get user preferences, creating defaults if none exist."""
        from src.config import get_settings

        settings = get_settings()

        async with get_session_factory()() as session:
            result = await session.exec(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            pref = result.first()

            if not pref:
                pref = UserPreference(
                    user_id=user_id,
                    roles=",".join(settings.default_roles),
                    regions=",".join(settings.default_regions),
                    min_score=settings.min_match_score,
                )
                session.add(pref)
                await session.commit()
                await session.refresh(pref)
                logger.info(f"Created default preferences for user {user_id}")

            return pref

    async def update_roles(self, user_id: int, roles: list[str]) -> UserPreference:
        """Update a user's target roles."""
        async with get_session_factory()() as session:
            result = await session.exec(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            pref = result.first()
            if pref:
                pref.set_roles_list(roles)
                pref.updated_at = datetime.utcnow()
                session.add(pref)
                await session.commit()
                await session.refresh(pref)
            return pref

    async def update_regions(self, user_id: int, regions: list[str]) -> UserPreference:
        """Update a user's target regions."""
        async with get_session_factory()() as session:
            result = await session.exec(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            pref = result.first()
            if pref:
                pref.set_regions_list(regions)
                pref.updated_at = datetime.utcnow()
                session.add(pref)
                await session.commit()
                await session.refresh(pref)
            return pref

    async def get_all_active_configs(self) -> list[dict]:
        """Get all unique role/region combos across active users for the scraper."""
        async with get_session_factory()() as session:
            result = await session.exec(
                select(UserPreference).where(
                    UserPreference.notifications_enabled == True  # noqa: E712
                )
            )
            prefs = result.all()

            # Deduplicate role/region combos
            combos: set[tuple[str, str]] = set()
            for pref in prefs:
                for role in pref.get_roles_list():
                    for region in pref.get_regions_list():
                        combos.add((role, region))

            return [{"role": role, "region": region} for role, region in combos]


# Module-level singletons
_job_repo: JobRepository | None = None
_pref_repo: PreferenceRepository | None = None


def get_job_repo() -> JobRepository:
    global _job_repo
    if _job_repo is None:
        _job_repo = JobRepository()
    return _job_repo


def get_pref_repo() -> PreferenceRepository:
    global _pref_repo
    if _pref_repo is None:
        _pref_repo = PreferenceRepository()
    return _pref_repo
