from __future__ import annotations

import re
from typing import Iterable

from legaldata.core.schemas import EvidenceSpan, LegalReference
from legaldata.parsers.html_parser import ParsedDocument

# Best-effort, conservative patterns:
CASE_CIT_RE = re.compile(r"\[(\d{4})\]\s+\d+\s+SLR\(R\)\s+\d+|\[(\d{4})\]\s+SG[A-Z]{2,}\s+\d+", re.IGNORECASE)
STATUTE_RE = re.compile(r"\b[A-Z][A-Za-z ]+ Act\b(?:\s+\d{4})?(?:\s*\(\d{4}\s+Rev\s+Ed\))?", re.IGNORECASE)
PINPOINT_RE = re.compile(r"\bat\s*\[(\d+)\]", re.IGNORECASE)

def extract_legal_references(doc: ParsedDocument) -> tuple[list[LegalReference], list[EvidenceSpan]]:
    refs: list[LegalReference] = []
    ev: list[EvidenceSpan] = []

    # Scan body lines (beyond header) but keep bounded for speed
    for i, ln in enumerate(doc.lines[:2000]):
        # cases
        for m in CASE_CIT_RE.finditer(ln):
            cit = m.group(0).strip()
            pin = None
            pm = PINPOINT_RE.search(ln)
            if pm:
                pin = f"[{pm.group(1)}]"
            ref = LegalReference(ref_type="case", citation=cit, pinpoint=pin,
                                 evidence=EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:220]))
            refs.append(ref)
            ev.append(ref.evidence)

        # statutes
        for m in STATUTE_RE.finditer(ln):
            cit = m.group(0).strip()
            ref = LegalReference(ref_type="statute", citation=cit, pinpoint=None,
                                 evidence=EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:220]))
            refs.append(ref)
            ev.append(ref.evidence)

    # de-dup by (type,citation,pinpoint)
    seen = set()
    deduped = []
    for r in refs:
        key = (r.ref_type, r.citation.lower(), r.pinpoint or "")
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped, ev
