"""
Database models for JobFinderAI.
Supports dynamic roles, regions, and full job tracking lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    """Job processing lifecycle status."""

    NEW = "new"  # Just discovered
    SCORED = "scored"  # AI has scored it
    NOTIFIED = "notified"  # User has been notified via Telegram
    REVIEWING = "reviewing"  # User is reviewing
    DRAFTING = "drafting"  # Resume is being drafted
    APPLIED = "applied"  # User applied
    IGNORED = "ignored"  # User chose to skip


class Job(SQLModel, table=True):
    """A discovered job posting."""

    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    company: str = Field(index=True)
    location: str = Field(default="")
    description: str = Field(default="")
    source_url: str = Field(default="")
    source_id: str = Field(unique=True, index=True)  # For deduplication
    posted_date: Optional[str] = Field(default=None)
    discovered_at: datetime = Field(default_factory=datetime.utcnow)

    # AI Matching
    match_score: Optional[int] = Field(default=None, index=True)
    match_report_json: Optional[str] = Field(default=None)  # JSON string of SuitabilityReport

    # Search metadata
    search_role: str = Field(default="", index=True)  # Which role query found this
    search_region: str = Field(default="", index=True)  # Which region query found this

    # Lifecycle
    status: str = Field(default=JobStatus.NEW, index=True)
    notified_at: Optional[datetime] = Field(default=None)
    status_updated_at: Optional[datetime] = Field(default=None)


class Applied(SQLModel, table=True):
    """Track jobs the user has applied to."""

    __tablename__ = "applied"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    resume_path: Optional[str] = Field(default=None)
    cover_letter_path: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    application_url: Optional[str] = Field(default=None)


class UserPreference(SQLModel, table=True):
    """
    Dynamic user preferences stored in DB.
    Allows updating roles and regions via Telegram commands
    without restarting the bot.
    """

    __tablename__ = "user_preferences"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(unique=True, index=True)  # Telegram user ID

    # Dynamic job search config (stored as comma-separated strings)
    roles: str = Field(default="")  # e.g. "SAP ABAP Consultant,Solution Architect"
    regions: str = Field(default="")  # e.g. "Saudi Arabia,United Arab Emirates"

    # Notification preferences
    min_score: int = Field(default=7)
    notifications_enabled: bool = Field(default=True)

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def get_roles_list(self) -> list[str]:
        """Parse roles string into a list."""
        if not self.roles:
            return []
        return [r.strip() for r in self.roles.split(",") if r.strip()]

    def set_roles_list(self, roles: list[str]) -> None:
        """Set roles from a list."""
        self.roles = ",".join(roles)

    def get_regions_list(self) -> list[str]:
        """Parse regions string into a list."""
        if not self.regions:
            return []
        return [r.strip() for r in self.regions.split(",") if r.strip()]

    def set_regions_list(self, regions: list[str]) -> None:
        """Set regions from a list."""
        self.regions = ",".join(regions)
