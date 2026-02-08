from __future__ import annotations

import re
from legaldata.core.schemas import EvidenceSpan, Parties
from legaldata.parsers.html_parser import ParsedDocument

V_LINE_RE = re.compile(r"^\s*v\s*$", re.IGNORECASE)


def _clean_name(s: str) -> str:
    s = (s or "").replace("…", "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def extract_parties(doc: ParsedDocument) -> tuple[Parties, list[EvidenceSpan]]:
    ev: list[EvidenceSpan] = []
    parties = Parties()

    lines = (doc.lines or [])[:450]

    # ---------- Strategy 1: Between ... And ----------
    try:
        idx_between = next(i for i, ln in enumerate(lines) if (ln or "").strip().lower() == "between")
    except StopIteration:
        idx_between = None

    if idx_between is not None:
        i = idx_between + 1

        # Claimants until "And"
        while i < len(lines):
            ln = lines[i] or ""
            if ln.strip().lower() == "and":
                break
            name = _clean_name(ln)
            if name and "claimant" not in name.lower():
                parties.claimants.append(name)
                ev.append(EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:200]))
            i += 1

        # Defendants after "And"
        if i < len(lines) and (lines[i] or "").strip().lower() == "and":
            i += 1
            while i < len(lines):
                ln = lines[i] or ""
                lo = ln.lower()
                if "grounds of decision" in lo:
                    break
                name = _clean_name(ln)
                if name and "defendant" not in name.lower():
                    parties.defendants.append(name)
                    ev.append(EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:200]))
                i += 1

        parties.claimants = [p for p in parties.claimants if p and "claimant" not in p.lower()]
        parties.defendants = [p for p in parties.defendants if p and "defendant" not in p.lower()]
        return parties, ev

    header = lines[:250]
    v_idxs = [i for i, ln in enumerate(header) if V_LINE_RE.match((ln or "").strip())]
    if v_idxs:
        v_i = v_idxs[0]

        # Collect up to 5 non-empty lines above v as claimants (stop at section heading)
        for i in range(v_i - 1, max(-1, v_i - 8), -1):
            ln = header[i] or ""
            name = _clean_name(ln)
            if not name:
                continue
            lo = name.lower()
            if "grounds of decision" in lo or "judgment" in lo:
                break
            if "claimant" in lo or "defendant" in lo:
                continue
            parties.claimants.insert(0, name)
            ev.append(EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:200]))
            if len(parties.claimants) >= 3:
                break

        # Collect up to 5 non-empty lines below v as defendants
        for i in range(v_i + 1, min(len(header), v_i + 8)):
            ln = header[i] or ""
            name = _clean_name(ln)
            if not name:
                continue
            lo = name.lower()
            if "grounds of decision" in lo:
                break
            if "claimant" in lo or "defendant" in lo:
                continue
            parties.defendants.append(name)
            ev.append(EvidenceSpan(kind="line", location=f"lines[{i}]", snippet=ln[:200]))
            if len(parties.defendants) >= 3:
                break

        return parties, ev

    return parties, ev
