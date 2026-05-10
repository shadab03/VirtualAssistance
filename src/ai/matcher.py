"""
AI Job Matcher - Compares job descriptions against the master profile
and returns a structured suitability report.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.ai.prompts import JOB_MATCHER_SYSTEM_PROMPT, JOB_MATCHER_USER_PROMPT
from src.config import get_settings

logger = logging.getLogger(__name__)


class SuitabilityReport(BaseModel):
    """Structured output from the AI job matcher."""

    score: int = Field(ge=1, le=10, description="Overall suitability score 1-10")
    summary: str = Field(description="Executive summary of match quality")
    matching_skills: list[str] = Field(default_factory=list, description="Matching skills")
    gap_analysis: list[str] = Field(default_factory=list, description="Skill gaps identified")
    keyword_suggestions: list[str] = Field(
        default_factory=list, description="Keywords for resume"
    )
    recommended_focus: str = Field(default="", description="What to emphasize in application")


class JobMatcher:
    """Matches job postings against a candidate's master profile using AI."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url
        )
        self.model = settings.openai_model
        self._profile_cache: str | None = None

    async def load_profile(self, profile_path: Path | None = None) -> str:
        """Load the master profile from file."""
        if self._profile_cache:
            return self._profile_cache

        settings = get_settings()
        path = profile_path or (settings.data_dir / "master_profile.md")

        if not path.exists():
            logger.warning(f"Master profile not found at {path}. Using empty profile.")
            return "No master profile configured yet."

        self._profile_cache = path.read_text(encoding="utf-8")
        logger.info(f"Loaded master profile from {path} ({len(self._profile_cache)} chars)")
        return self._profile_cache

    def clear_profile_cache(self) -> None:
        """Clear the cached profile (call after profile update)."""
        self._profile_cache = None

    async def analyze_job(
        self,
        job_description: str,
        job_title: str = "",
        company: str = "",
        location: str = "",
        profile_path: Path | None = None,
    ) -> SuitabilityReport:
        """
        Analyze how well a job posting matches the master profile.

        Returns a SuitabilityReport with score, analysis, and recommendations.
        """
        profile = await self.load_profile(profile_path)

        user_prompt = JOB_MATCHER_USER_PROMPT.format(
            master_profile=profile,
            job_title=job_title or "Not specified",
            company=company or "Not specified",
            location=location or "Not specified",
            job_description=job_description,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": JOB_MATCHER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Low temp for consistent, analytical output
                max_tokens=2000,
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from OpenAI")
                return SuitabilityReport(
                    score=0,
                    summary="Error: Empty response from AI",
                    recommended_focus="Unable to analyze",
                )

            data = json.loads(content)
            report = SuitabilityReport(**data)
            logger.info(
                f"Job analyzed: '{job_title}' at '{company}' -> Score: {report.score}/10"
            )
            return report

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return SuitabilityReport(
                score=0,
                summary=f"Error: Failed to parse AI response - {e}",
                recommended_focus="Unable to analyze",
            )
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return SuitabilityReport(
                score=0,
                summary=f"Error: AI analysis failed - {e}",
                recommended_focus="Unable to analyze",
            )


# Module-level singleton
_matcher: JobMatcher | None = None


def get_matcher() -> JobMatcher:
    """Return the singleton JobMatcher instance."""
    global _matcher
    if _matcher is None:
        _matcher = JobMatcher()
    return _matcher
