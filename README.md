# VerdictForge — Legal Judgment Crawler & Extractor (CLI)

VerdictForge is a **CLI-first Python pipeline** for crawling Singapore eLitigation judgments and extracting structured legal metadata with **evidence-backed provenance**.

This project is designed as a **clean, realistic baseline** for legal data extraction tasks: simple to run, easy to audit, and intentionally conservative in what it claims to extract.

---

## What this project does

VerdictForge crawls publicly available judgments from eLitigation.sg and extracts:

- **case_citation** (e.g. `[2025] SGHCR 33`)
- **decision_date**
- **presiding_judges** (best-effort heuristic)
- **parties** (claimants / defendants)
- **legal_references_cited** (case + statute references, heuristic)

Each extracted value is optionally accompanied by **evidence spans** (line numbers + snippets) to support auditability and debugging.

---

## Design principles

- CLI-only (no web UI)
- Local-first (SQLite by default)
- Polite crawling (rate limits, retries, jitter)
- Best-effort extraction (missing fields are allowed)
- Explicit validation + error tracking
- Reproducible runs with stored raw HTML

---

## Setup

```bash
cd app
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Initialize the database:

```bash
python -m legaldata initdb
```

---

## Usage

### Crawl judgments (safe demo caps)

```bash
python -m legaldata crawl --max-pages 3 --max-cases 50
```

Raw HTML is stored under `./data/raw/` and structured outputs go into `./data/legaldata.db`.

---

### Extract from a single judgment URL

Extract **all variables**:

```bash
python -m legaldata extract https://www.elitigation.sg/gd/s/2025_SGHCR_33
```

Extract **selected variables by name**:

```bash
python -m legaldata extract https://www.elitigation.sg/gd/s/2025_SGHCR_33   --var case_citation   --var presiding_judges
```

---

### Show evidence spans

Add `--with-evidence` to display where values came from:

```bash
python -m legaldata extract https://www.elitigation.sg/gd/s/2025_SGHCR_33 --with-evidence
```

Evidence includes:
- line numbers
- short text snippets
- extraction method (line / regex / DOM)

---

### Inspect latest extracted values (QA)

```bash
python -m legaldata search presiding_judges --limit 10
```

With evidence:

```bash
python -m legaldata search presiding_judges --limit 10 --with-evidence
```

---

### Pipeline statistics

```bash
python -m legaldata stats
```

Shows:
- total documents seen
- extracted vs failed
- top validation / extraction errors

---

## Running tests

From the `app/` directory:

```bash
python -m pytest -q
```

Verbose mode:

```bash
python -m pytest -vv
```

Tests cover:
- individual extractors
- validators
- known edge cases from real judgments

---

## Notes & limitations

- HTML structure varies across courts and years
- Some judgments do not list judges in a consistent format
- Missing values are expected and allowed
- This baseline avoids LLM usage by design

---

## License

For evaluation and educational use.
