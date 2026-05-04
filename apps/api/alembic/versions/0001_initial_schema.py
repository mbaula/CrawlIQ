"""Initial CrawlIQ schema with parallel-safe uniqueness.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl_jobs",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("seed_url", sa.Text(), nullable=False),
        sa.Column("normalized_seed_url", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="2"),
        sa.Column(
            "same_domain_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("pages_crawled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_crawl_jobs_status",
        ),
    )
    op.create_index(
        "ix_crawl_jobs_normalized_seed_url",
        "crawl_jobs",
        ["normalized_seed_url"],
        unique=False,
    )
    op.create_index(
        "ix_crawl_jobs_status_created_at",
        "crawl_jobs",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "pages",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("crawl_job_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("raw_html_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["crawl_job_id"],
            ["crawl_jobs.id"],
            name="fk_pages_crawl_job_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "crawl_job_id",
            "normalized_url",
            name="uq_pages_job_normalized_url",
        ),
    )
    op.create_index("ix_pages_crawl_job_id", "pages", ["crawl_job_id"], unique=False)
    op.create_index(
        "ix_pages_crawl_job_depth",
        "pages",
        ["crawl_job_id", "depth"],
        unique=False,
    )

    op.create_table(
        "page_links",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("crawl_job_id", sa.BigInteger(), nullable=False),
        sa.Column("source_page_id", sa.BigInteger(), nullable=False),
        sa.Column("target_normalized_url", sa.Text(), nullable=False),
        sa.Column("target_page_id", sa.BigInteger(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["crawl_job_id"],
            ["crawl_jobs.id"],
            name="fk_page_links_crawl_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["pages.id"],
            name="fk_page_links_source_page_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_page_id"],
            ["pages.id"],
            name="fk_page_links_target_page_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "crawl_job_id",
            "source_page_id",
            "target_normalized_url",
            name="uq_page_links_job_source_target",
        ),
    )
    op.create_index(
        "ix_page_links_crawl_job_target_norm",
        "page_links",
        ["crawl_job_id", "target_normalized_url"],
        unique=False,
    )
    op.create_index(
        "ix_page_links_target_page_id",
        "page_links",
        ["target_page_id"],
        unique=False,
    )

    op.create_table(
        "crawl_errors",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("crawl_job_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["crawl_job_id"],
            ["crawl_jobs.id"],
            name="fk_crawl_errors_crawl_job_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "crawl_job_id",
            "normalized_url",
            name="uq_crawl_errors_job_normalized_url",
        ),
    )
    op.create_index(
        "ix_crawl_errors_crawl_job_id",
        "crawl_errors",
        ["crawl_job_id"],
        unique=False,
    )

    op.create_table(
        "terms",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column(
            "document_frequency",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint("term", name="uq_terms_term"),
    )

    op.create_table(
        "inverted_index",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("term_id", sa.BigInteger(), nullable=False),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "term_frequency",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["terms.id"],
            name="fk_inverted_index_term_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["pages.id"],
            name="fk_inverted_index_page_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "term_id",
            "page_id",
            name="uq_inverted_index_term_page",
        ),
    )
    op.create_index(
        "ix_inverted_index_term_id",
        "inverted_index",
        ["term_id"],
        unique=False,
    )
    op.create_index(
        "ix_inverted_index_page_id",
        "inverted_index",
        ["page_id"],
        unique=False,
    )

    op.create_table(
        "search_queries",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_search_queries_created_at",
        "search_queries",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_search_queries_created_at", table_name="search_queries")
    op.drop_table("search_queries")

    op.drop_index("ix_inverted_index_page_id", table_name="inverted_index")
    op.drop_index("ix_inverted_index_term_id", table_name="inverted_index")
    op.drop_table("inverted_index")

    op.drop_table("terms")

    op.drop_index("ix_crawl_errors_crawl_job_id", table_name="crawl_errors")
    op.drop_table("crawl_errors")

    op.drop_index("ix_page_links_target_page_id", table_name="page_links")
    op.drop_index("ix_page_links_crawl_job_target_norm", table_name="page_links")
    op.drop_table("page_links")

    op.drop_index("ix_pages_crawl_job_depth", table_name="pages")
    op.drop_index("ix_pages_crawl_job_id", table_name="pages")
    op.drop_table("pages")

    op.drop_index("ix_crawl_jobs_status_created_at", table_name="crawl_jobs")
    op.drop_index("ix_crawl_jobs_normalized_seed_url", table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
