"""
PDF Generator using WeasyPrint and Jinja2.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logging.warning("WeasyPrint not installed or missing system dependencies. PDF generation will fail.")

from src.config import get_settings
from src.db.models import Job
from src.docs.tailor import TailoredContent

logger = logging.getLogger(__name__)


def generate_pdf(job: Job, tailored_content: TailoredContent, output_path: Path) -> Path | None:
    """
    Generate a PDF resume from a Jinja2 template and tailored content.
    Returns the path to the generated PDF.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("Cannot generate PDF: WeasyPrint is not available.")
        return None

    settings = get_settings()
    templates_dir = settings.templates_dir
    
    # Setup Jinja2 environment
    env = Environment(loader=FileSystemLoader(templates_dir))
    
    try:
        template = env.get_template("resume.html")
    except Exception as e:
        logger.error(f"Failed to load resume template: {e}")
        return None

    # Hardcoded profile data for now, ideally parsed from the master profile
    # but we will just pass the tailored content into the template.
    template_vars = {
        "job_title": job.title,
        "company": job.company,
        "summary": tailored_content.professional_summary,
        "achievements": tailored_content.key_achievements,
        "skills": tailored_content.skills_highlight,
        "projects": tailored_content.key_projects,
    }

    try:
        html_content = template.render(**template_vars)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        css_path = templates_dir / "resume.css"
        css_obj = CSS(filename=str(css_path)) if css_path.exists() else None
        
        html_obj = HTML(string=html_content, base_url=str(templates_dir))
        
        if css_obj:
            html_obj.write_pdf(target=str(output_path), stylesheets=[css_obj])
        else:
            html_obj.write_pdf(target=str(output_path))
            
        logger.info(f"Generated PDF at {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        return None
