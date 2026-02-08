from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, Integer, String, Text, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="elitigation")
    raw_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED")  # RECEIVED/FETCHED/EXTRACTED/FAILED
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    extraction: Mapped["Extraction"] = relationship(back_populates="document", uselist=False)


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (UniqueConstraint("document_id", name="uq_extractions_document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    case_citation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # ISO string to keep simple
    presiding_judges: Mapped[list] = mapped_column(JSON, default=list)
    parties: Mapped[dict] = mapped_column(JSON, default=dict)
    legal_references_cited: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)

    extractor_version: Mapped[str] = mapped_column(String(32), default="v1")

    document: Mapped["Document"] = relationship(back_populates="extraction")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")  # RUNNING/DONE/FAILED
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
