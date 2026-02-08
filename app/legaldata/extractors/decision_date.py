from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from legaldata.core.schemas import EvidenceSpan
from legaldata.parsers.html_parser import ParsedDocument

# eLitigation often has a standalone line like: "29 September 2025"
DATE_LINE_RE = re.compile(
    r"^(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$",
    re.IGNORECASE,
)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_decision_date(doc: ParsedDocument) -> tuple[Optional[date], list[EvidenceSpan]]:
    evidence: list[EvidenceSpan] = []
    # Heuristic: scan header-ish lines and pick the LAST valid standalone date
    found: Optional[date] = None
    found_ev: Optional[EvidenceSpan] = None

    for i, ln in enumerate(doc.lines[:200]):
        m = DATE_LINE_RE.match(ln)
        if not m:
            continue
        day = int(m.group(1))
        month = MONTHS[m.group(2).lower()]
        year = int(m.group(3))
        try:
            d = date(year, month, day)
            found = d
            found_ev = EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln)
        except ValueError:
            continue

    if found and found_ev:
        evidence.append(found_ev)
        return found, evidence

    return None, evidence
