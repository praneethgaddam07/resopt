"""Per-portal ATS rules, encoded from ATS_Portal_Documentation v1.0.

Each PortalRules object captures the machine-actionable rules for one ATS:
section order, date format, special formatting requirements, and the tone /
keyword behavior the workflow engine should respect. Universal rules apply to
every portal and are enforced unconditionally by the formatter and validators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable


# --- Date formatting -------------------------------------------------------

def _fmt_month_year(d: date) -> str:
    return d.strftime("%b %Y")  # "May 2023"


def _fmt_month_year_full(d: date) -> str:
    return d.strftime("%B %Y")  # "May 2023" with full month -> "May 2023"


def _fmt_mmddyyyy(d: date) -> str:
    return d.strftime("%m/%d/%Y")  # "05/01/2023"


# Date format keys -> (label, formatter, range separator)
DATE_FORMATS: dict[str, tuple[str, Callable[[date], str], str]] = {
    "month_year_emdash": ("May 2023 – Aug 2024", _fmt_month_year, " – "),
    "month_year": ("May 2023", _fmt_month_year, " - "),
    "mmddyyyy": ("05/01/2023", _fmt_mmddyyyy, " - "),
}


@dataclass(frozen=True)
class PortalRules:
    key: str
    name: str
    category: str
    # Ordered section names (lowercase canonical keys the formatter understands):
    # contact, summary, skills, certifications, experience, projects, education
    section_order: tuple[str, ...]
    date_format: str  # key into DATE_FORMATS
    # Special behaviors:
    plain_text_urls: bool = False          # iCIMS: URLs as visible plain text, not hyperlinks
    job_title_tagline_page1: bool = False  # Taleo: title tagline under contact on page 1
    leadership_principle_tags: bool = False  # Amazon: LP tag on every bullet
    aws_services_individually: bool = False  # Amazon: name EC2/S3/... never grouped "AWS"
    cert_before_skills: bool = False       # Amazon: certs above Skills on page 1
    star_every_bullet: bool = False        # Greenhouse/Lever: full STAR statements
    exact_match_strict: bool = True        # most enterprise ATS: no synonym/tense/plural drift
    mission_driven_tone: bool = False      # Paycom (mission roles)
    apply_window_hours: int | None = None  # Greenhouse/Lever: 48h
    pass_threshold: tuple[int, int] = (60, 75)  # typical keyword-match band
    notes: tuple[str, ...] = field(default_factory=tuple)

    def fmt_date(self, d: date) -> str:
        _, fn, _ = DATE_FORMATS[self.date_format]
        return fn(d)

    def date_separator(self) -> str:
        _, _, sep = DATE_FORMATS[self.date_format]
        return sep

    def date_example(self) -> str:
        return DATE_FORMATS[self.date_format][0]


# Canonical section keys for display labels in the document.
SECTION_LABELS = {
    "contact": "Contact",
    "summary": "Summary",
    "skills": "Skills",
    "certifications": "Certifications",
    "experience": "Work Experience",
    "projects": "Academic Projects",
    "education": "Education",
}


PORTALS: dict[str, PortalRules] = {
    "workday": PortalRules(
        key="workday",
        name="Workday",
        category="Enterprise · Fortune 500+",
        section_order=("contact", "summary", "skills", "certifications",
                       "experience", "projects", "education"),
        date_format="month_year_emdash",
        notes=(
            "Keyword mismatch is the #1 rejection reason — exact phrase only.",
            "Top 2-3 JD keywords must appear in the Summary.",
            "Use 'Present' for current roles. Upload the file, don't hand-fill forms.",
        ),
    ),
    "taleo": PortalRules(
        key="taleo",
        name="Oracle Taleo",
        category="Enterprise · 65%+ Fortune 500",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",
        job_title_tagline_page1=True,
        notes=(
            "Strips complex formatting aggressively — single column only.",
            "Key skills + job title must appear on page 1 before other content.",
            "Recruiters see the score before opening the resume.",
        ),
    ),
    "adp": PortalRules(
        key="adp",
        name="ADP Workforce Now",
        category="Mid-market · 50–5,000 employees",
        section_order=("contact", "summary", "skills", "experience",
                       "education", "certifications"),
        date_format="month_year",  # "Jan 2024" abbreviated month+year
        notes=(
            "Section order is mandatory: Contact > Summary > Skills > Experience "
            "> Education > Certifications.",
            "Certifications always last; spell out abbreviations exactly.",
            "Keywords must appear in bullets, not only in the skills list.",
        ),
    ),
    "greenhouse": PortalRules(
        key="greenhouse",
        name="Greenhouse",
        category="Startup & scale-up · 150,000+ companies",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",
        star_every_bullet=True,
        exact_match_strict=False,  # humans read directly; mirror JD but tone-match
        apply_window_hours=48,
        notes=(
            "Humans read the resume directly — visual quality matters most here.",
            "Every bullet must be a full STAR statement with a metric.",
            "Match the company's own tone; apply within 48 hours.",
        ),
    ),
    "lever": PortalRules(
        key="lever",
        name="Lever",
        category="Startup · relationship-driven pipeline",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",
        star_every_bullet=True,
        apply_window_hours=48,
        notes=(
            "Screening weights direct phrase matches over semantic equivalents.",
            "LinkedIn headline must match the exact job title in the posting.",
            "Application timing matters — first 48 hours is the priority window.",
        ),
    ),
    "amazon": PortalRules(
        key="amazon",
        name="Amazon Internal ATS",
        category="Amazon-specific · Leadership Principle evaluation",
        section_order=("contact", "summary", "certifications", "skills",
                       "experience", "projects", "education"),
        date_format="month_year",
        leadership_principle_tags=True,
        aws_services_individually=True,
        cert_before_skills=True,
        notes=(
            "Every bullet tagged with a Leadership Principle in parentheses.",
            "AWS cert before Skills on page 1; name every AWS service individually.",
            "Call out graduation window in summary for new-grad programs.",
        ),
    ),
    "icims": PortalRules(
        key="icims",
        name="iCIMS",
        category="Enterprise · URL and date format critical",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="mmddyyyy",
        plain_text_urls=True,
        notes=(
            "LinkedIn + cert URLs as full visible plain text — not hyperlinked.",
            "Dates strictly MM/DD/YYYY. Exact phrase match, no tense/plural drift.",
            "Write both 'SQL' and 'Structured Query Language'.",
        ),
    ),
    "paycor": PortalRules(
        key="paycor",
        name="Paycor / Paycom",
        category="Mid-market payroll-adjacent ATS",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",
        mission_driven_tone=True,  # Paycom may require mission-driven tone
        notes=(
            "Single-column PDF; exact JD keywords embedded in bullets.",
            "Summary tight at 3-4 lines; no special symbols.",
            "Paycom: warm, mission-driven tone for mission-oriented roles.",
        ),
    ),
    "ashby": PortalRules(
        key="ashby",
        name="Ashby",
        category="Startup & scale-up · structured scorecards + AI review",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",  # clear, consistent — Ashby computes years from dates
        notes=(
            "Structured hiring scorecards + AI-assisted review against predefined "
            "criteria — tailor to the JD's exact skills and qualifications.",
            "Recruiters filter by skills, experience, location, and custom requirements — "
            "align to real keywords, don't keyword-stuff.",
            "Consistent employment dates: Ashby may calculate years of experience "
            "directly from them.",
            "Single-column DOCX or text-based PDF; keep everything in the body — headers, "
            "footers, images, and graphics may not parse.",
        ),
    ),
    "successfactors": PortalRules(
        key="successfactors",
        name="SAP SuccessFactors",
        category="Enterprise · exact keyword & competency matching",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",  # "Jan 2024" — consistent, parser-safe
        notes=(
            "Relies heavily on EXACT keyword and competency matching — mirror the JD's "
            "skills and phrases verbatim.",
            "Consistent date formats ('Jan 2024' or '01/2024') — parsing errors skew "
            "experience calculations and recruiter searches.",
            "Prove relevant competencies and qualifications — don't repeat keywords "
            "excessively.",
            "After uploading, REVIEW the parsed fields: job titles, dates, skills, and "
            "company names.",
        ),
    ),
    "smartrecruiters": PortalRules(
        key="smartrecruiters",
        name="SmartRecruiters",
        category="Mid-market & enterprise · skills-based screening",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year_emdash",   # "Jan 2024 – Present"
        notes=(
            "Skills-based screening — include a dedicated Skills section; skills map to hiring criteria.",
            "Mirror the JD's skills/phrases; exact keywords carry the strongest weight even with AI matching.",
            "Acronym + full phrase for skills/certs/degrees, e.g. 'Search Engine Optimization (SEO)', "
            "'Master of Business Administration (MBA)'.",
            "Standard headings (Work Experience, Education, Skills, Certifications); reverse-chronological.",
            "Standard dates: 'Jan 2024 – Present' or '01/2024 – 03/2026' — no abbreviated years or odd formats.",
        ),
    ),
    "bamboohr": PortalRules(
        key="bamboohr",
        name="BambooHR",
        category="SMB · recruiters read directly (no keyword search)",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",
        notes=(
            "No résumé keyword search — a recruiter reads it directly; readability matters more than formatting.",
            "No tense/abbreviation/acronym matching — match the JD's keywords EXACTLY.",
            "Add keyword variations for recruiter searches, e.g. 'Project Management Professional (PMP)' "
            "plus 'project manager'.",
            "Clean single-column layout that's easy to skim.",
        ),
    ),
    "generic": PortalRules(
        key="generic",
        name="Generic / Unknown",
        category="Safe defaults for any portal",
        section_order=("contact", "summary", "skills", "experience",
                       "projects", "education", "certifications"),
        date_format="month_year",
        notes=(
            "Single-column; exact JD keywords in bullets; full degree names.",
            "Acronym + full phrase; repeat hard skills across sections.",
        ),
    ),
}


# Universal, non-negotiable rules applied to every portal (formatter + validators).
UNIVERSAL_RULES = {
    "single_column": True,
    "fonts": ("Arial", "Calibri", "Helvetica", "Times New Roman"),
    "contact_in_body": True,            # never in header/footer
    "no_tables": True,
    "no_graphics": True,
    "no_special_symbols": ("#", ";", "_", "---"),
    "acronym_plus_full_phrase": True,
    "full_degree_names": True,
    "metric_on_every_bullet": True,
    "summary_max_lines": 4,
    "skills_total_range": (25, 40),
    "filename_pattern": "Lastname_Companyname",
}


def get_portal(key: str | None) -> PortalRules:
    return PORTALS.get((key or "generic").lower(), PORTALS["generic"])


# Temporarily hidden from the user-facing portal picker. The rules + engine behavior
# (LP tags, AWS-services-individually, cert-before-skills) stay intact, so restoring is
# a one-line change — just drop the key from this set.
_HIDDEN_PORTALS = {"amazon"}


def list_portals() -> list[dict]:
    out = []
    for p in PORTALS.values():
        if p.key in _HIDDEN_PORTALS:
            continue
        out.append({
            "key": p.key,
            "name": p.name,
            "category": p.category,
            "date_example": p.date_example(),
            "section_order": list(p.section_order),
            "apply_window_hours": p.apply_window_hours,
            "notes": list(p.notes),
        })
    return out
