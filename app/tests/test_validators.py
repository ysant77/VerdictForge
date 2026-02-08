from datetime import date
from legaldata.core.schemas import ExtractedCase
from legaldata.validators.quality_gates import validate_extracted_case

def test_validator_accepts_basic():
    rec = ExtractedCase(url="x", case_citation="[2025] SGHCR 33", decision_date=date(2025,9,29))
    ok, errors = validate_extracted_case(rec)
    assert ok
    assert errors == []
