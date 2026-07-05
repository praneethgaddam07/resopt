"""Resume/JD text extraction from uploaded files + a no-LLM contact fallback."""
from __future__ import annotations

import io
import re
import unicodedata


def clean_text(s: str) -> str:
    """Strip chars that break downstream encoders/renderers but keep real text.

    PDF/docx extraction injects U+2028/U+2029 line separators, zero-width marks,
    BOMs, and stray control chars. Left in, they crash the LLM HTTP layer (the
    "ascii codec cannot encode \\u2028" error) and corrupt the .docx. We normalize
    separators to newlines and drop control/format chars, while preserving accents,
    punctuation, and emoji.
    """
    if not s:
        return s
    s = s.replace("\u2028", "\n").replace("\u2029", "\n").replace("\ufeff", "")
    # category()[0] == "C" covers Cc/Cf/Cs/Co/Cn (control/format/surrogate/etc.).
    return "".join(c for c in s if c in "\n\t\r" or unicodedata.category(c)[0] != "C")


def _pdf_link_uris(reader) -> list[str]:
    """URLs hiding in PDF link annotations. Résumés typically show 'LinkedIn' or a
    name as display text while the real URL lives only in the annotation — text
    extraction alone loses it, producing dead links downstream."""
    uris: list[str] = []
    for page in reader.pages:
        for annot in (page.get("/Annots") or []):
            try:
                uri = annot.get_object().get("/A", {}).get("/URI")
                if uri:
                    uris.append(str(uri))
            except Exception:  # noqa: BLE001 - malformed annotation: skip, don't fail extraction
                continue
    return uris


def _docx_link_uris(doc) -> list[str]:
    """External hyperlink targets from a .docx (stored in relationships, not text)."""
    try:
        return [rel.target_ref for rel in doc.part.rels.values()
                if "hyperlink" in rel.reltype and rel.is_external]
    except Exception:  # noqa: BLE001
        return []


def _with_links(text: str, uris: list[str]) -> str:
    """Append discovered URLs so extraction (LLM + regex) sees the REAL links."""
    seen, keep = set(), []
    for u in uris:
        u = (u or "").strip().replace("mailto:", "")
        if u and u not in seen and not u.startswith("tel:"):
            seen.add(u)
            keep.append(u)
    if not keep:
        return text
    return text + "\n\nLINKS FOUND IN THE ORIGINAL FILE (use these exact URLs):\n" \
        + "\n".join(keep[:12])


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """Extract plain text from an uploaded .pdf, .docx, or .txt resume — including
    the URLs behind hyperlinked display text (PDF annotations / DOCX relationships)."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return clean_text(_with_links(text, _pdf_link_uris(reader)))
    if name.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return clean_text(_with_links(text, _docx_link_uris(doc)))
    if name.endswith(".txt"):
        return clean_text(file_bytes.decode("utf-8", errors="ignore"))
    raise ValueError(f"Unsupported file type: {filename}. Use .pdf, .docx, or .txt.")


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_LINKEDIN_RE = re.compile(r"(linkedin\.com/[^\s)\]]+)", re.IGNORECASE)


def regex_contact(resume_text: str) -> dict:
    """Best-effort contact extraction without an LLM (used as a mock/fallback)."""
    email = _EMAIL_RE.search(resume_text)
    phone = _PHONE_RE.search(resume_text)
    linkedin = _LINKEDIN_RE.search(resume_text)
    # First non-empty line that isn't an email/phone is a decent name guess.
    name = ""
    for line in resume_text.splitlines():
        s = line.strip()
        if s and not _EMAIL_RE.search(s) and not _PHONE_RE.search(s) and len(s) < 60:
            name = s
            break
    return {
        "name": name or "Candidate Name",
        "phone": (phone.group(0).strip() if phone else ""),
        "email": (email.group(0) if email else ""),
        "linkedin": (linkedin.group(0) if linkedin else ""),
        "location": "",
        "education": [{"degree": "Degree", "school": "University", "dates": "", "gpa": ""}],
        "certifications": [],
    }
