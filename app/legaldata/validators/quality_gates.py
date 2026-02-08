from __future__ import annotations

import re
from datetime import date

from legaldata.core.schemas import ExtractedCase

CITATION_RE = re.compile(r"^\[\d{4}\]\s+SG[A-Z]{2,}\s+\d+", re.IGNORECASE)


def validate_extracted_case(record: ExtractedCase) -> tuple[bool, list[str]]:
    """
    Return (ok, errors).

    Coverage-first policy for Task 2:
    - Missing fields are allowed (NOT errors).
    - Only flag *implausible* or *clearly noisy* outputs when values exist.
    """
    errors: list[str] = []

    # case_citation: OK if missing; validate only if present
    if record.case_citation is not None:
        cit = record.case_citation.strip()
        if cit and not CITATION_RE.match(cit):
            errors.append(f"case_citation format unexpected: {record.case_citation}")

    # decision_date: OK if missing; sanity-check only if present
    if record.decision_date is not None:
        # shouldn't be in far future (allow up to +1 year buffer)
        max_future = date.today().replace(year=date.today().year + 1)
        if record.decision_date > max_future:
            errors.append(f"decision_date seems implausible: {record.decision_date.isoformat()}")

    # judges: OK if missing/empty; validate tokens only if list exists
    for j in (record.presiding_judges or []):
        # ignore empty/None tokens, but flag very short weird ones
        if j is None:
            continue
        token = str(j).strip()
        if token and len(token) < 4:
            errors.append(f"suspicious judge token: {token!r}")

    # references: OK if missing; keep bounded if list exists
    refs = record.legal_references_cited or []
    if len(refs) > 2000:
        errors.append("too many legal references extracted; likely parser noise")

    ok = len(errors) == 0
    return ok, errors
