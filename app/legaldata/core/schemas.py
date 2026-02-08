from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    """Where/why we believe a value was extracted."""
    kind: Literal["line", "regex", "dom"] = "line"
    location: str = Field(..., description="Human-friendly locator: e.g., 'header lines[12]' or 'para 40'")
    snippet: str = Field(..., description="Small snippet showing the match.")


class LegalReference(BaseModel):
    """One cited authority (best-effort normalization)."""
    ref_type: Literal["case", "statute", "other"] = "case"
    citation: str
    pinpoint: Optional[str] = None
    evidence: Optional[EvidenceSpan] = None


class Parties(BaseModel):
    claimants: list[str] = Field(default_factory=list)
    defendants: list[str] = Field(default_factory=list)


class ExtractedCase(BaseModel):
    url: str

    # Task 1 variables
    case_citation: Optional[str] = None
    decision_date: Optional[date] = None
    presiding_judges: list[str] = Field(default_factory=list)
    legal_references_cited: list[LegalReference] = Field(default_factory=list)

    # Helpful extra metadata
    parties: Parties = Field(default_factory=Parties)

    # Provenance
    evidence: dict[str, list[EvidenceSpan]] = Field(default_factory=dict)

    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    extractor_version: str = "v1"
