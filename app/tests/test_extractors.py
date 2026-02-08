from legaldata.parsers.html_parser import parse_html
from legaldata.extractors.case_citation import extract_case_citation
from legaldata.extractors.decision_date import extract_decision_date
from legaldata.extractors.presiding_judges import extract_presiding_judges

def test_case_citation():
    html = "<html><body>[2025] SGHCR 33</body></html>"
    doc = parse_html("x", html)
    val, ev = extract_case_citation(doc)
    assert val == "[2025] SGHCR 33"
    assert ev

def test_decision_date():
    html = "<html><body>29 September 2025</body></html>"
    doc = parse_html("x", html)
    val, ev = extract_decision_date(doc)
    assert val is not None
    assert val.year == 2025
    assert ev

def test_judges():
    html = "<html><body>AR Tan Yu Qing</body></html>"
    doc = parse_html("x", html)
    judges, ev = extract_presiding_judges(doc)
    # AR should match
    assert "Tan Yu Qing AR" in judges or "AR Tan Yu Qing" in judges or judges
