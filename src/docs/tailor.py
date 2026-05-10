"""
AI-powered resume tailoring.
Uses GPT-4o to rewrite parts of the master profile based on the job.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from src.ai.matcher import get_matcher
from src.ai.prompts import RESUME_TAILOR_SYSTEM_PROMPT, RESUME_TAILOR_USER_PROMPT
from src.config import get_settings
from src.db.models import Job

logger = logging.getLogger(__name__)


class TailoredContent(BaseModel):
    """Structured tailored resume content."""

    professional_summary: str
    key_achievements: list[str]
    skills_highlight: list[str]
    key_projects: list[dict[str, str]]


async def tailor_resume(job: Job) -> TailoredContent | None:
    """
    Tailor the master profile for a specific job.
    Returns tailored sections ready for the template.
    """
    settings = get_settings()
    matcher = get_matcher()
    
    if not settings.openai_api_key:
        logger.error("Cannot tailor resume: OPENAI_API_KEY is not set.")
        return None

    profile = await matcher.load_profile()
    if not profile or "No master profile" in profile:
        logger.error("Cannot tailor resume: No valid master profile found.")
        return None

    suitability_report = job.match_report_json or "No suitability report available."

    user_prompt = RESUME_TAILOR_USER_PROMPT.format(
        master_profile=profile,
        job_title=job.title,
        company=job.company,
        location=job.location,
        job_description=job.description,
        suitability_report=suitability_report,
    )

    try:
        response = await matcher.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": RESUME_TAILOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        content = response.choices[0].message.content
        if not content:
            logger.error("Empty response from OpenAI during tailoring.")
            return None

        data = json.loads(content)
        tailored = TailoredContent(**data)
        logger.info(f"Successfully tailored resume content for job {job.id}.")
        return tailored

    except Exception as e:
        logger.error(f"Failed to tailor resume: {e}")
        return None
