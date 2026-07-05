"""Text-based PDF renderer — mirrors the DOCX single-column, ATS-safe layout.

Pure-Python (fpdf2, core fonts — no font files, no LibreOffice, tiny footprint).
DOCX stays the recommended upload for ATS parsing; the PDF is the human-facing
copy (email, print, portfolio). Same sections, same portal rules, same
StyleOptions, so the two downloads always agree.
"""
from __future__ import annotations

import io

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .portals import PortalRules, SECTION_LABELS
from .formatter import (StyleOptions, _fit, _estimate_lines, _fmt_dates, _norm_url,
                        _section_gap, _entry_gap)
from dataclasses import replace

# fpdf2 core fonts are latin-1; transliterate the few common non-latin-1 chars.
_TR = str.maketrans({
    "•": "-", "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', " ": " ", " ": " ", "→": "->",
    "·": "-", "…": "...", "✓": "-", "●": "-",
})

# Core-font mapping for our ATS-safe font list.
_FONT_MAP = {"Calibri": "helvetica", "Carlito": "helvetica", "Arial": "helvetica",
             "Helvetica": "helvetica", "Georgia": "times", "Times New Roman": "times"}


def _tx(s: str) -> str:
    return (s or "").translate(_TR).encode("latin-1", "replace").decode("latin-1")


class _Pdf(FPDF):
    """Letter, pt units, shared style state."""

    def __init__(self, st: StyleOptions):
        super().__init__(orientation="portrait", unit="pt", format="Letter")
        self.st = st
        self.fam = _FONT_MAP.get(st.font, "helvetica")
        self.set_margins(st.margin_h, st.margin_v, st.margin_h)
        self.set_auto_page_break(True, margin=st.margin_v)
        self.add_page()
        self.set_text_color(26, 26, 26)

    def _lh(self, size: int) -> float:
        # ~1.15x is Word's single-spacing; 1.3x read as airy/double-spaced in the PDF.
        return size * 1.16 * self.st.line_spacing

    def _width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def _vspace(self, h):
        """Add `h` pt of vertical gap. fpdf2's ln(0) is a trap — it falls back to
        the last cell's height (a phantom blank line) instead of moving zero, so
        skip the call entirely when there's no gap to add."""
        if h and h > 0:
            self.ln(h)

    def para(self, text, *, size=None, bold=False, italic=False, space_after=None,
             caps=False, indent=0.0):
        st = self.st
        size = size if size is not None else st.size_body
        style = ("B" if bold else "") + ("I" if italic else "")
        self.set_font(self.fam, style, size)
        if indent:
            self.set_x(self.l_margin + indent)
        self.multi_cell(self._width() - indent, self._lh(size),
                        _tx(text.upper() if caps else text), align="L",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._vspace(st.entry_space if space_after is None else space_after)

    def keep_together(self, needed: float):
        """Page-break now if less than `needed` height remains — stops a sub-heading
        (or a bullet's marker) from being orphaned at the bottom of a page."""
        if self.get_y() + needed > self.page_break_trigger:
            self.add_page()

    def bullet(self, text, *, size=None):
        """A real round bullet (drawn, not a glyph — core PDF fonts can't render '•')
        with a hanging indent so wrapped lines align under the text, not the marker."""
        st = self.st
        size = size if size is not None else st.size_body
        self.set_font(self.fam, "", size)
        # Never draw the marker on one page and let its text flow to the next (the
        # "empty bullet" bug) — break first so marker + first line stay together.
        self.keep_together(self._lh(size))
        x0 = self.l_margin + 4
        y0 = self.get_y()
        tx = x0 + max(6.0, size * 0.55)
        if st.bullet == "•":
            r = max(1.0, size * 0.11)
            self.set_fill_color(40, 40, 40)
            self.ellipse(x0 + 1, y0 + self._lh(size) / 2 - r, r * 2, r * 2, style="F")
        else:  # user picked the dash style
            self.text(x0, y0 + self._lh(size) * 0.72, "-")
        old_lm = self.l_margin
        self.set_left_margin(tx)            # hanging indent for wrapped lines
        self.set_xy(tx, y0)
        self.multi_cell(self.w - self.r_margin - tx, self._lh(size), _tx(text),
                        align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_left_margin(old_lm)
        self._vspace(st.entry_space)

    def two_col(self, left, right, *, size=None, bold=False, space_after=1):
        """`left` flush-left, `right` flush-right on one line (no tables)."""
        st = self.st
        size = size if size is not None else st.size_sub
        self.set_font(self.fam, "B" if bold else "", size)
        left, right = _tx(left), _tx(right)
        rw = (self.get_string_width(right) + 4) if right else 0
        y0 = self.get_y()
        self.multi_cell(self._width() - rw, self._lh(size), left, align="L",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y1 = self.get_y()
        if right:
            self.set_font(self.fam, "", size)
            self.set_xy(self.l_margin + self._width() - rw, y0)
            self.cell(rw, self._lh(size), right, align="R")
        self.set_y(max(y1, y0 + self._lh(size)))
        self._vspace(space_after)

    def heading(self, label):
        st = self.st
        self._vspace(_section_gap(st))   # even top gap for every section (mirrors DOCX)
        self.set_font(self.fam, "B" if st.bold_headings else "", st.size_heading)
        if st.accent:
            self.set_text_color(int(st.accent[0:2], 16), int(st.accent[2:4], 16),
                                int(st.accent[4:6], 16))
        self.cell(self._width(), self._lh(st.size_heading), _tx(label.upper()),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(26, 26, 26)
        if st.divider:
            y = self.get_y() + 1
            self.set_draw_color(150, 150, 150)
            self.line(self.l_margin, y, self.l_margin + self._width(), y)
        self._vspace(st.heading_gap)


def build_pdf_bytes(data: dict, contact: dict, portal: PortalRules,
                    section_order: list[str] | None = None,
                    style: StyleOptions | dict | None = None) -> bytes:
    st = style if isinstance(style, StyleOptions) else StyleOptions.from_dict(style)
    if st.date_format == "asis":  # same portal-default rule as the DOCX builder
        st = replace(st, date_format=("num_year" if portal.date_format == "mmddyyyy"
                                      else "mon_year"))
    if st.fit_one_page:
        st = _fit(st, _estimate_lines(data, contact))
    pdf = _Pdf(st)

    education = data.get("education") or contact.get("education") or []
    certs = data.get("certifications") or contact.get("certifications") or []

    def r_contact():
        pdf.set_font(pdf.fam, "B", st.size_name)
        align = {"left": "L", "center": "C", "right": "R"}.get(st.header_align, "L")
        pdf.cell(pdf._width(), pdf._lh(st.size_name), _tx(contact.get("name", "Candidate Name")),
                 align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        bits = []
        for k in ("phone", "email", "location", "linkedin", "github", "portfolio"):
            v = (contact.get(k) or "").strip()
            if v:
                bits.append(v)
        if bits:
            pdf.set_font(pdf.fam, "", max(9, st.size_body - 1))
            pdf.multi_cell(pdf._width(), pdf._lh(max(9, st.size_body - 1)),
                           _tx("    ".join(bits)), align=align,
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)
        if portal.job_title_tagline_page1 and data.get("job_title"):  # Taleo
            pdf.para(data["job_title"], bold=True, size=st.size_heading, space_after=4)

    def r_summary():
        if data.get("job_title") and not portal.job_title_tagline_page1:
            pdf.para(data["job_title"], bold=st.bold_sub, size=st.size_heading,
                     space_after=st.heading_gap)
        pdf.heading(SECTION_LABELS["summary"])
        pdf.para(data.get("summary", ""), space_after=st.entry_space)  # next heading owns the gap

    def r_skills():
        cats = [c for c in data.get("skills", []) if c.get("skills")]
        if not cats:
            return
        pdf.heading(SECTION_LABELS["skills"])
        if st.skills_layout == "inline":
            pdf.para(", ".join(s for c in cats for s in c["skills"]),
                     space_after=st.entry_space)
        else:
            gap = 0 if st.skills_layout == "compact" else 1
            for c in cats:
                lh = pdf._lh(st.size_body)
                pdf.keep_together(lh)
                pdf.set_font(pdf.fam, "B" if st.bold_sub else "", st.size_body)
                pdf.write(lh, _tx(f"{c.get('name', 'Skills')}: "))   # bold label (matches DOCX)
                pdf.set_font(pdf.fam, "", st.size_body)
                pdf.write(lh, _tx(", ".join(c["skills"])))            # normal skills, flows/wraps
                pdf.ln(lh + gap)

    def r_certs():
        if not certs:
            return
        pdf.heading(SECTION_LABELS["certifications"])
        for c in certs:
            if isinstance(c, dict):
                line = " — ".join(x for x in [c.get("name", ""), c.get("issuer", "")] if x)
                if c.get("url"):
                    line += f"  {_norm_url(c['url'])}"  # visible plain-text URL (ATS-safe)
            else:
                line = str(c)
            pdf.para(line, space_after=1)

    def r_experience():
        pdf.heading(SECTION_LABELS["experience"])
        for i, exp in enumerate(data.get("experiences", [])):
            if i:
                pdf._vspace(_entry_gap(st))       # even inter-entry gap (2nd job onward)
            left = ", ".join(x for x in [exp.get("title", ""), exp.get("company", "")] if x)
            right = " | ".join(x for x in [_fmt_dates(exp.get("duration", ""), st.date_format),
                                           exp.get("location", "")] if x)
            pdf.keep_together(pdf._lh(st.size_sub) * 3)  # don't orphan the role header
            pdf.two_col(left, right, bold=st.bold_sub)
            if exp.get("bridge_line"):
                pdf.para(exp["bridge_line"], italic=True, size=max(9, st.size_body - 1))
            for b in exp.get("bullets", []):
                pdf.bullet(b)

    def r_projects():
        projects = data.get("projects", [])
        if not projects:
            return
        pdf.heading(SECTION_LABELS["projects"])
        for i, proj in enumerate(projects):
            if i:
                pdf._vspace(_entry_gap(st))       # same inter-entry gap as experience
            pdf.keep_together(pdf._lh(st.size_sub) * 3)  # keep the title with its first bullet
            pdf.para(proj.get("title", "Project"), bold=st.bold_sub, space_after=1)
            for b in proj.get("bullets", []):
                pdf.bullet(b)

    def r_education():
        items = education if isinstance(education, list) else [education]
        items = [e for e in items if e]
        if not items:
            return
        pdf.heading(SECTION_LABELS["education"])
        rendered = 0  # count only emitted entries, so the FIRST gets no top gap
        for e in items:
            if isinstance(e, dict):
                deg, sch = e.get("degree", "").strip(), e.get("school", "").strip()
                if not (deg or sch):
                    continue
                if rendered:
                    pdf._vspace(_entry_gap(st))
                # Same two-line shape as the DOCX: primary + dates, then secondary + GPA.
                # Keeps the long degree off the same line as the GPA (no wrap collision).
                primary, secondary = ((deg, sch) if st.education_order == "degree" else (sch, deg))
                pdf.two_col(primary, _fmt_dates(e.get("dates", ""), st.date_format),
                            bold=st.bold_sub, space_after=0)
                tail = secondary + (f", GPA: {e['gpa']}" if e.get("gpa", "").strip() else "")
                if tail.strip(", "):
                    pdf.para(tail, space_after=st.entry_space)
                rendered += 1
            else:
                if rendered:
                    pdf._vspace(_entry_gap(st))
                pdf.para(str(e), space_after=st.entry_space)
                rendered += 1

    renderers = {"contact": r_contact, "summary": r_summary, "skills": r_skills,
                 "certifications": r_certs, "experience": r_experience,
                 "projects": r_projects, "education": r_education}
    seen = set()
    for key in (section_order or portal.section_order):
        if key in renderers and key not in seen:
            seen.add(key)
            renderers[key]()

    out = pdf.output()
    return bytes(out)
