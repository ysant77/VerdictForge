from __future__ import annotations

import re
from typing import Final

from legaldata.core.schemas import EvidenceSpan
from legaldata.parsers.html_parser import ParsedDocument

# Common SG judicial titles seen on eLitigation pages
TITLES: Final = r"(?:CJ|JA|J|JC|SJ|AR|DJ|Magistrate)"

# 1) Postfix: "Name Title" or "Name Title:"
POSTFIX_RE: Final = re.compile(
    rf"^(?P<name>[A-Z][A-Za-z'.\- ]{{2,}}?)\s+(?P<title>{TITLES})\b\s*:?\s*$"
)

# 2) Prefix: "Title Name" or "Title Name:"
# Example: "AR Tan Yu Qing"
PREFIX_RE: Final = re.compile(
    rf"^(?P<title>{TITLES})\s+(?P<name>[A-Z][A-Za-z'.\- ]{{2,}}?)\b\s*:?\s*$"
)

# 3) Some pages have "Before: Name Title" / "Coram: ..."
BEFORE_RE: Final = re.compile(
    rf"^(?:Before|Coram)\s*:\s*(?P<name>[A-Z][A-Za-z'.\- ]{{2,}}?)\s+(?P<title>{TITLES})\b\s*:?\s*$",
    re.IGNORECASE,
)

# Heuristic anchors: judge line tends to be near these header-ish lines
ANCHORS: Final = (
    "general division",
    "court of appeal",
    "family justice courts",
    "originating claim",
    "summons",
    "grounds of decision",
    "judgment reserved",
)


def extract_presiding_judges(doc: ParsedDocument) -> tuple[list[str], list[EvidenceSpan]]:
    judges: list[str] = []
    evidence: list[EvidenceSpan] = []
    lines = doc.lines or []

    def _add(name: str, title: str, idx: int, snippet: str) -> None:
        # Normalize to "Name Title" consistently, even if page shows "AR Name"
        clean_name = " ".join(name.split())
        clean_title = title.strip()
        val = f"{clean_name} {clean_title}".strip()

        if val not in judges:
            judges.append(val)

        evidence.append(EvidenceSpan(kind="line", location=f"lines[{idx}]", snippet=snippet[:200]))

    if not lines:
        return judges, evidence

    # Search in a focused window near the first anchor (reduces false positives).
    head = lines[:600]
    anchor_idx = None
    for i, ln in enumerate(head):
        lo = (ln or "").strip().lower()
        if any(a in lo for a in ANCHORS):
            anchor_idx = i
            break

    if anchor_idx is None:
        window = head
        base = 0
    else:
        start = max(0, anchor_idx - 80)
        end = min(len(head), anchor_idx + 120)
        window = head[start:end]
        base = start

    def try_match(line: str, idx: int) -> bool:
        s = (line or "").strip()
        if not s:
            return False

        m = POSTFIX_RE.match(s)
        if m:
            _add(m.group("name"), m.group("title"), idx, s)
            return True

        m = PREFIX_RE.match(s)
        if m:
            _add(m.group("name"), m.group("title"), idx, s)
            return True

        m = BEFORE_RE.match(s)
        if m:
            _add(m.group("name"), m.group("title"), idx, s)
            return True

        return False

    # Pass 1: direct line matches
    for off, ln in enumerate(window):
        try_match(ln, base + off)

    # Pass 2: stitched windows (handles HTML splits like ["AR Tan Yu Qing", ":"])
    if not judges:
        for i in range(0, len(window) - 2):
            idx = base + i
            w = " ".join([x.strip() for x in window[i : i + 3] if x and x.strip()])
            if try_match(w, idx):
                break

    # De-dupe evidence while preserving order
    seen = set()
    ev2: list[EvidenceSpan] = []
    for ev in evidence:
        key = (ev.location, ev.snippet)
        if key not in seen:
            seen.add(key)
            ev2.append(ev)

    return judges, ev2
