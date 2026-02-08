from __future__ import annotations

from collections.abc import Callable
from typing import Any

from legaldata.parsers.html_parser import ParsedDocument
from legaldata.core.schemas import EvidenceSpan, LegalReference, Parties

from legaldata.extractors.case_citation import extract_case_citation
from legaldata.extractors.decision_date import extract_decision_date
from legaldata.extractors.presiding_judges import extract_presiding_judges
from legaldata.extractors.parties import extract_parties
from legaldata.extractors.legal_references import extract_legal_references


ExtractorFn = Callable[[ParsedDocument], tuple[Any, list[EvidenceSpan]]]


def extract_all(doc: ParsedDocument) -> dict[str, tuple[Any, list[EvidenceSpan]]]:
    """Extract all supported variables from a ParsedDocument."""
    refs, ev_refs = extract_legal_references(doc)
    parties, ev_parties = extract_parties(doc)

    return {
        "case_citation": extract_case_citation(doc),
        "decision_date": extract_decision_date(doc),
        "presiding_judges": extract_presiding_judges(doc),
        "parties": (parties, ev_parties),
        "legal_references_cited": (refs, ev_refs),
    }


def supported_variables() -> list[str]:
    return [
        "case_citation",
        "decision_date",
        "presiding_judges",
        "parties",
        "legal_references_cited",
    ]


def extract_by_names(doc: ParsedDocument, names: list[str]) -> dict[str, tuple[Any, list[EvidenceSpan]]]:
    """Extract only the requested variables.

    Names are validated; unknown names raise ValueError.
    """
    all_vars = extract_all(doc)
    unknown = [n for n in names if n not in all_vars]
    if unknown:
        raise ValueError(f"Unknown variable(s): {unknown}. Supported: {supported_variables()}")
    return {n: all_vars[n] for n in names}
