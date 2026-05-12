"""ORM models aligned with Alembic revision ``0001_initial`` (see docs/database-schema.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_crawl_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    seed_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_seed_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    same_domain_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    pages_crawled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pages_indexed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pages_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    pages: Mapped[list[Page]] = relationship(back_populates="crawl_job", cascade="all, delete-orphan")
    page_links: Mapped[list[PageLink]] = relationship(back_populates="crawl_job", cascade="all, delete-orphan")
    crawl_errors: Mapped[list[CrawlError]] = relationship(
        back_populates="crawl_job", cascade="all, delete-orphan",
    )
    page_graph_edges: Mapped[list[PageGraphEdge]] = relationship(
        "PageGraphEdge", back_populates="crawl_job",
    )
    page_graph_clusters: Mapped[list[PageGraphCluster]] = relationship(
        "PageGraphCluster", back_populates="crawl_job",
    )
    page_graph_metrics: Mapped[list[PageGraphMetric]] = relationship(
        "PageGraphMetric", back_populates="crawl_job",
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("crawl_job_id", "normalized_url", name="uq_pages_job_normalized_url"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    crawl_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fetch_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    crawl_job: Mapped[CrawlJob] = relationship(back_populates="pages")
    outbound_links: Mapped[list[PageLink]] = relationship(
        back_populates="source_page",
        foreign_keys="PageLink.source_page_id",
        cascade="all, delete-orphan",
    )
    inverted_rows: Mapped[list[InvertedIndex]] = relationship(
        back_populates="page", cascade="all, delete-orphan",
    )


class PageLink(Base):
    __tablename__ = "page_links"
    __table_args__ = (
        UniqueConstraint(
            "crawl_job_id",
            "source_page_id",
            "target_normalized_url",
            name="uq_page_links_job_source_target",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    crawl_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_page_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="SET NULL"),
        nullable=True,
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    is_crawl_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )

    crawl_job: Mapped[CrawlJob] = relationship(back_populates="page_links")
    source_page: Mapped[Page] = relationship(
        back_populates="outbound_links",
        foreign_keys=[source_page_id],
    )
    target_page: Mapped[Page | None] = relationship(foreign_keys=[target_page_id])


class CrawlError(Base):
    __tablename__ = "crawl_errors"
    __table_args__ = (
        UniqueConstraint("crawl_job_id", "normalized_url", name="uq_crawl_errors_job_normalized_url"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    crawl_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fetch_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    crawl_job: Mapped[CrawlJob] = relationship(back_populates="crawl_errors")


class Term(Base):
    __tablename__ = "terms"
    __table_args__ = (UniqueConstraint("term", name="uq_terms_term"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    document_frequency: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    postings: Mapped[list[InvertedIndex]] = relationship(back_populates="term", cascade="all, delete-orphan")


class InvertedIndex(Base):
    __tablename__ = "inverted_index"
    __table_args__ = (
        UniqueConstraint("term_id", "page_id", name="uq_inverted_index_term_page"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    term_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    term: Mapped[Term] = relationship(back_populates="postings")
    page: Mapped[Page] = relationship(back_populates="inverted_rows")


class PageGraphEdge(Base):
    __tablename__ = "page_graph_edges"
    __table_args__ = (
        CheckConstraint(
            "edge_type IN ("
            "'link', 'content_similarity', 'url_hierarchy', 'shared_terms', "
            "'near_duplicate', 'co_ranked', 'manual')",
            name="ck_page_graph_edges_edge_type",
        ),
        UniqueConstraint(
            "crawl_job_id",
            "source_page_id",
            "target_page_id",
            "edge_type",
            name="uq_page_graph_edges_job_src_tgt_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    crawl_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    evidence: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    crawl_job: Mapped[CrawlJob] = relationship("CrawlJob", back_populates="page_graph_edges")
    source_page: Mapped[Page] = relationship(foreign_keys=[source_page_id])
    target_page: Mapped[Page] = relationship(foreign_keys=[target_page_id])


class PageGraphCluster(Base):
    __tablename__ = "page_graph_clusters"
    __table_args__ = (
        UniqueConstraint("crawl_job_id", "page_id", name="uq_page_graph_clusters_job_page"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    crawl_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    cluster_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cluster_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    crawl_job: Mapped[CrawlJob] = relationship("CrawlJob", back_populates="page_graph_clusters")


class PageGraphMetric(Base):
    __tablename__ = "page_graph_metrics"
    __table_args__ = (
        UniqueConstraint("crawl_job_id", "page_id", name="uq_page_graph_metrics_job_page"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    crawl_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    pagerank: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_degree: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    out_degree: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    betweenness: Mapped[float | None] = mapped_column(Float, nullable=True)
    closeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    crawl_job: Mapped[CrawlJob] = relationship("CrawlJob", back_populates="page_graph_metrics")


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
