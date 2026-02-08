from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legaldata.core.config import settings
from legaldata.core.http_client import PoliteAsyncHttpClient
from legaldata.core.schemas import ExtractedCase
from legaldata.extractors.case_citation import extract_case_citation
from legaldata.extractors.decision_date import extract_decision_date
from legaldata.extractors.presiding_judges import extract_presiding_judges
from legaldata.extractors.parties import extract_parties
from legaldata.extractors.legal_references import extract_legal_references
from legaldata.parsers.html_parser import parse_html
from legaldata.sources.elitigation.listing import build_listing_url, parse_listing_html
from legaldata.storage.db import Document, Extraction
from legaldata.storage.raw_store import RawStore
from legaldata.validators.quality_gates import validate_extracted_case


USER_AGENT = "SMU-CDL-AssessmentScraper/1.0 (contact: youremail@example.com) respectful-crawl"


class ElitigationPipeline:
    """End-to-end pipeline for eLitigation HTML judgments."""

    def __init__(self) -> None:
        self.raw_store = RawStore(settings.raw_store_dir)

    async def crawl_and_process(
        self,
        session: AsyncSession,
        *,
        crawl_id: int,
        max_pages: int | None = None,
        max_cases: int | None = None,
    ) -> dict:
        client = PoliteAsyncHttpClient(
            user_agent=USER_AGENT,
            timeout_s=settings.timeout_s,
            max_concurrency=settings.max_concurrency,
            min_delay_s=settings.min_delay_s,
            max_retries=settings.max_retries,
        )

        stats = {"pages_crawled": 0, "cases_seen": 0, "cases_processed": 0, "cases_failed": 0}

        try:
            page = 1
            seen_urls: set[str] = set()
            while True:
                if max_pages is not None and stats["pages_crawled"] >= max_pages:
                    break

                listing_url = build_listing_url(settings.source_listing_url, page)
                listing_res = await client.get_text(listing_url)
                listing = parse_listing_html(settings.source_base_url, listing_res.text, page_num=page)
                stats["pages_crawled"] += 1

                if not listing.judgment_urls:
                    break

                new_urls = [u for u in listing.judgment_urls if u not in seen_urls]
                for u in new_urls:
                    seen_urls.add(u)

                stats["cases_seen"] = len(seen_urls)

                if max_cases is not None and len(seen_urls) > max_cases:
                    new_urls = new_urls[: max(0, max_cases - (len(seen_urls) - len(new_urls)))]

                async def process(url: str) -> None:
                    nonlocal stats
                    try:
                        await self._process_one(session, client, url)
                        stats["cases_processed"] += 1
                    except Exception:
                        stats["cases_failed"] += 1

                await asyncio.gather(*(process(u) for u in new_urls))

                if max_cases is not None and stats["cases_seen"] >= max_cases:
                    break

                page += 1

            return stats
        finally:
            await client.close()

    async def _process_one(
        self,
        session: AsyncSession,
        client: PoliteAsyncHttpClient,
        url: str,
    ) -> None:
        # idempotency: if already fetched+extracted, skip
        existing = await session.scalar(select(Document).where(Document.url == url))
        if existing and existing.status == "EXTRACTED":
            return

        if not existing:
            existing = Document(url=url, source="elitigation", status="RECEIVED")
            session.add(existing)
            await session.commit()
            await session.refresh(existing)

        try:
            res = await client.get_text(url)
            raw_path = self.raw_store.write_html(url, res.text)

            existing.raw_path = str(raw_path)
            existing.status = "FETCHED"
            existing.fetched_at = datetime.utcnow()
            await session.commit()

            parsed = parse_html(url, res.text)

            case_cit, ev_cit = extract_case_citation(parsed)
            dec_date, ev_date = extract_decision_date(parsed)
            judges, ev_j = extract_presiding_judges(parsed)
            parties, ev_p = extract_parties(parsed)
            refs, ev_r = extract_legal_references(parsed)

            record = ExtractedCase(
                url=url,
                case_citation=case_cit,
                decision_date=dec_date,
                presiding_judges=judges,
                legal_references_cited=refs,
                parties=parties,
                evidence={
                    "case_citation": ev_cit,
                    "decision_date": ev_date,
                    "presiding_judges": ev_j,
                    "parties": ev_p,
                    "legal_references_cited": ev_r[:50],  # cap evidence stored to keep db smaller
                },
                extractor_version="v1",
            )

            ok, errors = validate_extracted_case(record)
            if not ok:
                existing.status = "FAILED"
                existing.error = "; ".join(errors)[:4000]
                await session.commit()
                return

            # upsert extraction
            if existing.extraction:
                ex = existing.extraction
            else:
                ex = Extraction(document_id=existing.id)
                session.add(ex)

            ex.case_citation = record.case_citation
            ex.decision_date = record.decision_date.isoformat() if record.decision_date else None
            ex.presiding_judges = record.presiding_judges
            ex.parties = record.parties.model_dump()
            ex.legal_references_cited = [r.model_dump() for r in record.legal_references_cited]
            ex.evidence = {k: [e.model_dump() for e in v] for k, v in record.evidence.items()}
            ex.extractor_version = record.extractor_version

            existing.status = "EXTRACTED"
            existing.error = None
            await session.commit()

        except Exception as e:
            existing.status = "FAILED"
            existing.error = f"{type(e).__name__}: {e}"[:4000]
            await session.commit()
            raise
