from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from legaldata.core.schemas import EvidenceSpan

from legaldata.core.config import settings
from legaldata.core.http_client import PoliteAsyncHttpClient
from legaldata.parsers.html_parser import parse_html
from legaldata.extractors.registry import supported_variables, extract_by_names, extract_all
from legaldata.validators.quality_gates import validate_extracted_case
from legaldata.core.schemas import ExtractedCase
from legaldata.storage.session import SessionLocal, init_db
from legaldata.storage.db import Document, Extraction, CrawlRun
from legaldata.storage.raw_store import RawStore
from legaldata.sources.elitigation.listing import build_listing_url, parse_listing_html


app = typer.Typer(add_completion=False, help="CLI for crawling and extracting eLitigation judgments.")
console = Console()

USER_AGENT = "SMU-CDL-AssessmentScraper/1.0 (contact: youremail@example.com) respectful-crawl"


def _format_value(var: str, val: object) -> str:
    if val is None:
        return ""

    # Judges: list[str] -> "A; B; C"
    if var == "presiding_judges":
        if isinstance(val, list):
            cleaned = [str(x).strip() for x in val if str(x).strip()]
            return "; ".join(cleaned)
        return str(val).strip()

    # Parties: show names instead of counts (works with your Parties pydantic model)
    if var == "parties":
        # If your extractor returns a Parties model, it should have claimants/defendants
        claimants = []
        defendants = []
        try:
            claimants = getattr(val, "claimants", []) or []
            defendants = getattr(val, "defendants", []) or []
        except Exception:
            pass

        if claimants or defendants:
            c_txt = "; ".join([str(x).strip() for x in claimants if str(x).strip()])
            d_txt = "; ".join([str(x).strip() for x in defendants if str(x).strip()])
            return f"Claimants: {c_txt or '-'} | Defendants: {d_txt or '-'}"

        # fallback: if it's a dict-like
        if isinstance(val, dict):
            c = val.get("claimants") or []
            d = val.get("defendants") or []
            c_txt = "; ".join([str(x).strip() for x in c if str(x).strip()])
            d_txt = "; ".join([str(x).strip() for x in d if str(x).strip()])
            return f"Claimants: {c_txt or '-'} | Defendants: {d_txt or '-'}"

        return str(val)

    # Legal references: list -> show count + first few
    if var == "legal_references_cited":
        if isinstance(val, list):
            if not val:
                return "0 refs"
            first = []
            for r in val[:3]:
                # r might be a model or a string
                cite = getattr(r, "citation", None)
                first.append((cite or str(r)).strip())
            return f"{len(val)} refs | " + ", ".join([x for x in first if x])
        return str(val)

    # Default
    return str(val)

def _normalize_db_evidence(ev: object) -> list[EvidenceSpan]:
    """
    Convert DB-stored evidence (list[dict]) back into EvidenceSpan objects
    so _format_evidence can be reused unchanged.
    """
    if not ev or not isinstance(ev, list):
        return []

    spans: list[EvidenceSpan] = []
    for item in ev:
        if isinstance(item, EvidenceSpan):
            spans.append(item)
        elif isinstance(item, dict):
            try:
                spans.append(EvidenceSpan(**item))
            except Exception:
                continue
    return spans

def _format_evidence(ev: object, max_items: int = 2) -> str:
    """
    Render EvidenceSpan list into a short, human-friendly snippet.
    Expected: list[EvidenceSpan] with fields like kind/location/snippet.
    Defensive: return empty string if shape differs.
    """
    if not ev:
        return ""

    if not isinstance(ev, list):
        return ""

    chunks: list[str] = []
    for item in ev[:max_items]:
        try:
            loc = getattr(item, "location", "") or ""
            snippet = getattr(item, "snippet", "") or ""
            snippet = " ".join(str(snippet).split())
            if loc and snippet:
                chunks.append(f"{loc}: {snippet[:140]}")
            elif snippet:
                chunks.append(snippet[:140])
        except Exception:
            continue

    return "\n".join(chunks)


@app.command()
def initdb() -> None:
    """Create DB tables (assessment-friendly)."""
    asyncio.run(init_db())
    console.print("[green]DB initialised.[/green]")


@app.command()
def crawl(
    max_pages: Optional[int] = typer.Option(3, help="Safety cap for demo. Use --max-pages 0 for unlimited."),
    max_cases: Optional[int] = typer.Option(50, help="Safety cap for demo. Use --max-cases 0 for unlimited."),
) -> None:
    """Crawl judgments listing and extract variables into the DB."""
    asyncio.run(_crawl_async(max_pages if max_pages and max_pages > 0 else None,
                             max_cases if max_cases and max_cases > 0 else None))


async def _crawl_async(max_pages: Optional[int], max_cases: Optional[int]) -> None:
    await init_db()
    raw_store = RawStore(settings.raw_store_dir)
    raw_store.ensure()

    client = PoliteAsyncHttpClient(
        user_agent=USER_AGENT,
        timeout_s=settings.timeout_s,
        max_concurrency=settings.max_concurrency,
        min_delay_s=settings.min_delay_s,
        max_retries=settings.max_retries,
    )

    async with SessionLocal() as session:
        run = CrawlRun(status="RUNNING", params={"max_pages": max_pages, "max_cases": max_cases})
        session.add(run)
        await session.commit()
        await session.refresh(run)

        stats = {"pages_crawled": 0, "cases_seen": 0, "cases_processed": 0, "cases_failed": 0}

        try:
            page = 1
            seen_urls: set[str] = set()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                t_pages = progress.add_task("Listing pages", total=max_pages or 10_000_000)
                t_cases = progress.add_task("Cases processed", total=max_cases or 10_000_000)

                while True:
                    if max_pages is not None and stats["pages_crawled"] >= max_pages:
                        break

                    listing_url = build_listing_url(settings.source_listing_url, page)
                    listing_res = await client.get_text(listing_url)
                    listing = parse_listing_html(settings.source_base_url, listing_res.text, page_num=page)
                    console.print(f"[dim]Page {page}: found {len(listing.judgment_urls)} judgment links[/dim]")
                    stats["pages_crawled"] += 1
                    progress.advance(t_pages, 1)

                    if not listing.judgment_urls:
                        break

                    new_urls = [u for u in listing.judgment_urls if u not in seen_urls]
                    for u in new_urls:
                        seen_urls.add(u)

                    stats["cases_seen"] = len(seen_urls)

                    if max_cases is not None and stats["cases_seen"] >= max_cases:
                        new_urls = new_urls[: max(0, max_cases - (stats["cases_seen"] - len(new_urls)))]

                    async def process(url: str) -> None:
                        nonlocal stats
                        try:
                            async with SessionLocal() as task_session:
                                await _process_one(task_session, client, raw_store, url)
                            stats["cases_processed"] += 1
                        except Exception:
                            stats["cases_failed"] += 1
                        finally:
                            progress.advance(t_cases, 1)

                    await asyncio.gather(*(process(u) for u in new_urls))

                    if max_cases is not None and stats["cases_seen"] >= max_cases:
                        break
                    page += 1

            run.status = "DONE"
            run.stats = stats
            run.finished_at = datetime.utcnow()
            await session.commit()

            console.print("[green]Crawl complete[/green]", stats)

        except Exception as e:
            run.status = "FAILED"
            run.error = f"{type(e).__name__}: {e}"
            run.finished_at = datetime.utcnow()
            await session.commit()
            raise
        finally:
            await client.close()


async def _process_one(
    session: AsyncSession,
    client: PoliteAsyncHttpClient,
    raw_store: RawStore,
    url: str,
) -> None:
    """
    Process a single judgment URL.

    Coverage-first policy:
    - Always store raw HTML if fetched.
    - Always store an Extraction row (even if some fields are missing).
    - Treat validator outputs as WARNINGS, not hard failures.
    - Mark FAILED only for true runtime exceptions.
    """
    try:
        # Optional: normalize gdviewer -> gd for easier extraction
        if "/gdviewer/s/" in url:
            url = url.replace("/gdviewer/s/", "/gd/s/")

        existing = await session.scalar(select(Document).where(Document.url == url))
        if existing and existing.status == "EXTRACTED":
            return

        if not existing:
            existing = Document(url=url, source="elitigation", status="RECEIVED")
            session.add(existing)
            try:
                await session.commit()
            except IntegrityError:
                # URL already inserted by another worker / previous run
                await session.rollback()
                existing = await session.scalar(select(Document).where(Document.url == url))

        # Fetch + persist raw artifact
        res = await client.get_text(url)
        raw_path = raw_store.write_html(url, res.text)

        existing.raw_path = str(raw_path)
        existing.status = "FETCHED"
        existing.fetched_at = datetime.utcnow()
        existing.error = None
        await session.commit()

        # Parse + extract
        parsed = parse_html(url, res.text)
        extracted = extract_all(parsed)

        record = ExtractedCase(url=url)

        # Unpack extraction outputs
        for k, payload  in extracted.items():
            if isinstance(payload, tuple) and len(payload) == 2:
                v, ev = payload
            else:
                v, ev = payload, []

            if k == "case_citation":
                record.case_citation = v
            elif k == "decision_date":
                record.decision_date = v
            elif k == "presiding_judges":
                record.presiding_judges = v or []
            elif k == "parties":
                record.parties = v
            elif k == "legal_references_cited":
                record.legal_references_cited = v or []

            record.evidence[k] = ev or []

        # Validation => WARNINGS only (do not fail the document)
        ok, errors = validate_extracted_case(record)

        # Always write Extraction (partial allowed)
        ex = await session.scalar(select(Extraction).where(Extraction.document_id == existing.id))
        if ex is None:
            ex = Extraction(document_id=existing.id)
            session.add(ex)

        ex.case_citation = record.case_citation
        ex.decision_date = record.decision_date.isoformat() if record.decision_date else None
        ex.presiding_judges = record.presiding_judges
        ex.parties = record.parties.model_dump() if record.parties else None
        ex.legal_references_cited = (
            [r.model_dump() for r in record.legal_references_cited]
            if record.legal_references_cited
            else []
        )
        ex.evidence = {k: [e.model_dump() for e in v] for k, v in record.evidence.items()}
        ex.extractor_version = record.extractor_version

        # Mark as EXTRACTED regardless; store warnings in `error` for visibility
        existing.status = "EXTRACTED"

        # If validator says not ok, record warnings instead of failing
        existing.error = "; ".join(errors)[:4000] if (not ok and errors) else None

        await session.commit()

    except Exception as e:
        # True failure case (network error, parse crash, etc.)
        await session.rollback()

        # Try to persist failure reason if we have a Document row
        existing = await session.scalar(select(Document).where(Document.url == url))
        if existing:
            existing.status = "FAILED"
            existing.error = f"{type(e).__name__}: {e}"[:4000]
            await session.commit()

        # Re-raise to let caller count failures / log
        raise


@app.command()
def extract(
    url: str = typer.Argument(..., help="Judgment URL (e.g. https://www.elitigation.sg/gd/s/2025_SGHCR_33)"),
    variable: list[str] = typer.Option(
        None,
        "--var",
        help=f"Variable(s) to extract. Supported: {', '.join(supported_variables())}. "
             f"If omitted, extracts all.",
    ),
    with_evidence: bool = typer.Option(
        False,
        "--with-evidence",
        help="Show 1–2 evidence snippets per variable (best-effort).",
    ),
) -> None:
    """Extract one or more variables from a single judgment URL (does not require crawl)."""
    asyncio.run(_extract_one_async(url, variable, with_evidence))



async def _extract_one_async(url: str, variables: Optional[list[str]], with_evidence: bool) -> None:
    await init_db()
    raw_store = RawStore(settings.raw_store_dir)
    raw_store.ensure()

    client = PoliteAsyncHttpClient(
        user_agent=USER_AGENT,
        timeout_s=settings.timeout_s,
        max_concurrency=1,
        min_delay_s=settings.min_delay_s,
        max_retries=settings.max_retries,
    )

    try:
        res = await client.get_text(url)
        parsed = parse_html(url, res.text)

        if variables:
            out = extract_by_names(parsed, variables)
        else:
            out = extract_all(parsed)

        table = Table(title="Extraction result", show_lines=True)
        table.add_column("Variable", style="bold")
        table.add_column("Value")

        if with_evidence:
            table.add_column("Evidence (best-effort)")

        for var, payload in out.items():
            # Defensive: extractor may return (val, ev) OR just val
            if isinstance(payload, tuple) and len(payload) == 2:
                val, ev = payload
            else:
                val, ev = payload, []

            row_val = _format_value(var, val)

            if with_evidence:
                row_ev = _format_evidence(ev, max_items=2)
                table.add_row(var, row_val, row_ev)
            else:
                table.add_row(var, row_val)

        console.print(table)

    finally:
        await client.close()



@app.command()
def search(
    variable: str = typer.Argument(..., help="Variable name to search"),
    limit: int = typer.Option(10, help="Number of recent results"),
    with_evidence: bool = typer.Option(
        False,
        "--with-evidence",
        help="Show evidence snippets if available",
    ),
) -> None:
    asyncio.run(_search_async(variable, limit, with_evidence))



async def _search_async(variable: str, limit: int, with_evidence: bool) -> None:
    if variable not in supported_variables():
        raise typer.BadParameter(
            f"Unknown variable '{variable}'. Supported: {', '.join(supported_variables())}"
        )

    await init_db()

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Document, Extraction)
                .join(Extraction, Extraction.document_id == Document.id)
                .order_by(Extraction.extracted_at.desc())
                .limit(limit)
            )
        ).all()

        table = Table(title=f"Latest {limit} values: {variable}", show_lines=True)
        table.add_column("Extracted At")
        table.add_column("URL")
        table.add_column("Value")
        if with_evidence:
            table.add_column("Evidence (best-effort)")

        # "Querying DB..." spinner while we format rows (nice UX)
        with Progress(
            SpinnerColumn(),
            TextColumn("Querying DB..."),
            console=console,
            transient=True,
        ) as progress:
            t = progress.add_task("query", total=max(len(rows), 1))

            for d, e in rows:
                # Map variable -> field
                if variable == "case_citation":
                    val = e.case_citation
                elif variable == "decision_date":
                    val = e.decision_date
                elif variable == "presiding_judges":
                    val = e.presiding_judges
                elif variable == "parties":
                    val = e.parties
                elif variable == "legal_references_cited":
                    val = e.legal_references_cited
                else:
                    # Should never happen due to supported_variables() check
                    val = None

                val_txt = _format_value(variable, val)

                if with_evidence:
                    # evidence is stored as dict: {var: [EvidenceSpanDump, ...], ...}
                    ev_dict = e.evidence or {}
                    raw_ev = ev_dict.get(variable, [])
                    ev_spans = _normalize_db_evidence(raw_ev)
                    ev_txt = _format_evidence(ev_spans)
                    table.add_row(str(e.extracted_at), d.url, val_txt, ev_txt)
                else:
                    table.add_row(str(e.extracted_at), d.url, val_txt)

                progress.advance(t, 1)

        console.print(table)


@app.command()
def stats() -> None:
    """Show simple pipeline health stats (counts by status + top error reasons)."""
    asyncio.run(_stats_async())


async def _stats_async() -> None:
    await init_db()
    async with SessionLocal() as session:
        docs = (await session.execute(select(Document.status, Document.error))).all()

        status_counts: dict[str, int] = {}
        for status, _err in docs:
            status_counts[status] = status_counts.get(status, 0) + 1

        err_counts: dict[str, int] = {}
        for _status, err in docs:
            if not err:
                continue
            key = str(err)[:120]
            err_counts[key] = err_counts.get(key, 0) + 1

        table = Table(title="Pipeline stats", show_lines=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        for k in ["RECEIVED", "FETCHED", "EXTRACTED", "FAILED"]:
            table.add_row(f"documents.{k.lower()}", str(status_counts.get(k, 0)))

        table.add_row("documents.total", str(sum(status_counts.values())))
        console.print(table)

        if err_counts:
            err_table = Table(title="Top error reasons (truncated)", show_lines=True)
            err_table.add_column("Count", justify="right")
            err_table.add_column("Error")
            for err, cnt in sorted(err_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                err_table.add_row(str(cnt), err)
            console.print(err_table)
        else:
            console.print("[green]No errors recorded.[/green]")

if __name__ == "__main__":
    app()
