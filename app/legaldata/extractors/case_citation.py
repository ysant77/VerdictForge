from __future__ import annotations

import re
from typing import Optional

from legaldata.core.schemas import EvidenceSpan
from legaldata.parsers.html_parser import ParsedDocument


# Best-effort: match "[YYYY] SGXXXX N" (don’t anchor end-of-string)
CITATION_RE = re.compile(r"\[(\d{4})\]\s+SG[A-Z]{2,}\s+\d+", re.IGNORECASE)
URL_SLUG_RE = re.compile(r"/gd/s/(?P<slug>\d{4}_[A-Z]+_\d+)$", re.IGNORECASE)

def extract_case_citation(doc: ParsedDocument) -> tuple[Optional[str], list[EvidenceSpan]]:
    evidence: list[EvidenceSpan] = []

    # Try text first
    for i, ln in enumerate((doc.lines or [])[:400]):
        m = CITATION_RE.search(ln)
        if m:
            val = m.group(0).strip()
            evidence.append(EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:200]))
            return val, evidence

    m = CITATION_RE.search(doc.text or "")
    if m:
        val = m.group(0).strip()
        evidence.append(EvidenceSpan(kind="regex", location=f"full_text[{m.start()}:{m.end()}]", snippet=(doc.text or "")[max(0,m.start()-60):m.end()+60][:200]))
        return val, evidence

    # Fallback: infer from URL
    um = URL_SLUG_RE.search(doc.url)
    if um:
        slug = um.group("slug")  # e.g. 2026_SGHCA_3
        year, court, num = slug.split("_")
        val = f"[{year}] {court} {int(num)}"
        evidence.append(EvidenceSpan(kind="regex", location="url_slug_fallback", snippet=slug))
        return val, evidence

    return None, evidence