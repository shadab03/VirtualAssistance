"""
Google Jobs scraper using SerpApi.
Fetches job listings based on dynamic role/region combinations.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from serpapi import GoogleSearch

from src.config import get_settings
from src.db.models import Job

logger = logging.getLogger(__name__)


class GoogleJobsScraper:
    """Scrapes Google Jobs via SerpApi for given roles and regions."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.serpapi_api_key

    def _generate_source_id(self, title: str, company: str, location: str) -> str:
        """Generate a deterministic source ID for deduplication."""
        raw = f"{title}|{company}|{location}".lower().strip()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _search_jobs_sync(
        self,
        query: str,
        location: str,
        num_results: int = 10,
    ) -> list[dict]:
        """
        Synchronous SerpApi call (will be run in executor for async).
        Returns raw job results from the API.
        """
        params = {
            "engine": "google_jobs",
            "q": query,
            "location": location,
            "api_key": self.api_key,
            "hl": "en",
            "num": str(num_results),
        }

        try:
            search = GoogleSearch(params)
            results = search.get_dict()

            jobs = results.get("jobs_results", [])
            logger.info(
                f"SerpApi returned {len(jobs)} jobs for '{query}' in '{location}'"
            )
            return jobs

        except Exception as e:
            logger.error(f"SerpApi search failed for '{query}' in '{location}': {e}")
            return []

    async def search_jobs(
        self,
        query: str,
        location: str,
        num_results: int = 10,
    ) -> list[Job]:
        """
        Search for jobs asynchronously.
        Runs the synchronous SerpApi call in a thread executor.
        """
        loop = asyncio.get_event_loop()
        raw_jobs = await loop.run_in_executor(
            None,
            self._search_jobs_sync,
            query,
            location,
            num_results,
        )

        jobs = []
        for raw in raw_jobs:
            try:
                title = raw.get("title", "Unknown Title")
                company = raw.get("company_name", "Unknown Company")
                job_location = raw.get("location", location)

                # Build description from available fields
                description_parts = []
                if raw.get("description"):
                    description_parts.append(raw["description"])

                # Extract highlights if available
                highlights = raw.get("detected_extensions", {})
                if highlights.get("posted_at"):
                    description_parts.append(f"Posted: {highlights['posted_at']}")
                if highlights.get("schedule_type"):
                    description_parts.append(f"Type: {highlights['schedule_type']}")
                if highlights.get("salary"):
                    description_parts.append(f"Salary: {highlights['salary']}")

                description = "\n".join(description_parts)

                # Generate source_id for deduplication
                source_id = raw.get("job_id") or self._generate_source_id(
                    title, company, job_location
                )

                # Extract apply link
                apply_links = raw.get("apply_options", [])
                source_url = ""
                if apply_links:
                    source_url = apply_links[0].get("link", "")
                elif raw.get("share_link"):
                    source_url = raw["share_link"]

                job = Job(
                    title=title,
                    company=company,
                    location=job_location,
                    description=description,
                    source_url=source_url,
                    source_id=source_id,
                    posted_date=highlights.get("posted_at", ""),
                    search_role=query,
                    search_region=location,
                )
                jobs.append(job)

            except Exception as e:
                logger.error(f"Failed to parse job result: {e}")
                continue

        logger.info(f"Parsed {len(jobs)} jobs from search results")
        return jobs

    async def search_all_combos(
        self,
        roles: list[str],
        regions: list[str],
        num_results: int = 10,
    ) -> list[Job]:
        """
        Search all role × region combinations.
        Used by the scheduler to cover all configured searches.
        """
        all_jobs: list[Job] = []
        seen_ids: set[str] = set()

        for role in roles:
            for region in regions:
                jobs = await self.search_jobs(role, region, num_results)
                for job in jobs:
                    if job.source_id not in seen_ids:
                        seen_ids.add(job.source_id)
                        all_jobs.append(job)
                    else:
                        logger.debug(
                            f"Dedup in batch: '{job.title}' at '{job.company}'"
                        )

                # Be respectful of API rate limits
                await asyncio.sleep(1)

        logger.info(
            f"Total unique jobs from {len(roles)}×{len(regions)} combos: {len(all_jobs)}"
        )
        return all_jobs


# Module-level singleton
_scraper: GoogleJobsScraper | None = None


def get_scraper() -> GoogleJobsScraper:
    global _scraper
    if _scraper is None:
        _scraper = GoogleJobsScraper()
    return _scraper
