"""Page graph tables (edges, clusters, metrics).

Revision ID: 0007_page_graph_tables
Revises: 0006_fetch_duration_ms
Create Date: 2026-05-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_page_graph_tables"
down_revision: Union[str, None] = "0006_fetch_duration_ms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EDGE_TYPES = (
    "link",
    "content_similarity",
    "url_hierarchy",
    "shared_terms",
    "near_duplicate",
    "co_ranked",
    "manual",
)


def upgrade() -> None:
    edge_type_ck = "ck_page_graph_edges_edge_type"
    edge_type_in = ", ".join(f"'{t}'" for t in _EDGE_TYPES)

    op.create_table(
        "page_graph_edges",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("crawl_job_id", sa.BigInteger(), nullable=False),
        sa.Column("source_page_id", sa.BigInteger(), nullable=False),
        sa.Column("target_page_id", sa.BigInteger(), nullable=False),
        sa.Column("edge_type", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint(
            f"edge_type IN ({edge_type_in})",
            name=edge_type_ck,
        ),
        sa.ForeignKeyConstraint(
            ["crawl_job_id"],
            ["crawl_jobs.id"],
            name="fk_page_graph_edges_crawl_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["pages.id"],
            name="fk_page_graph_edges_source_page_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_page_id"],
            ["pages.id"],
            name="fk_page_graph_edges_target_page_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "crawl_job_id",
            "source_page_id",
            "target_page_id",
            "edge_type",
            name="uq_page_graph_edges_job_src_tgt_type",
        ),
    )
    op.create_index(
        "ix_page_graph_edges_crawl_job_id",
        "page_graph_edges",
        ["crawl_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_graph_edges_crawl_job_source",
        "page_graph_edges",
        ["crawl_job_id", "source_page_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_graph_edges_crawl_job_target",
        "page_graph_edges",
        ["crawl_job_id", "target_page_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_graph_edges_crawl_job_edge_type",
        "page_graph_edges",
        ["crawl_job_id", "edge_type"],
        unique=False,
    )

    op.create_table(
        "page_graph_clusters",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("crawl_job_id", sa.BigInteger(), nullable=False),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("cluster_id", sa.BigInteger(), nullable=False),
        sa.Column("cluster_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["crawl_job_id"],
            ["crawl_jobs.id"],
            name="fk_page_graph_clusters_crawl_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["pages.id"],
            name="fk_page_graph_clusters_page_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "crawl_job_id",
            "page_id",
            name="uq_page_graph_clusters_job_page",
        ),
    )
    op.create_index(
        "ix_page_graph_clusters_crawl_job_id",
        "page_graph_clusters",
        ["crawl_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_graph_clusters_crawl_job_cluster_id",
        "page_graph_clusters",
        ["crawl_job_id", "cluster_id"],
        unique=False,
    )

    op.create_table(
        "page_graph_metrics",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("crawl_job_id", sa.BigInteger(), nullable=False),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("pagerank", sa.Float(), nullable=True),
        sa.Column("in_degree", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("out_degree", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("betweenness", sa.Float(), nullable=True),
        sa.Column("closeness", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["crawl_job_id"],
            ["crawl_jobs.id"],
            name="fk_page_graph_metrics_crawl_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["pages.id"],
            name="fk_page_graph_metrics_page_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "crawl_job_id",
            "page_id",
            name="uq_page_graph_metrics_job_page",
        ),
    )
    op.create_index(
        "ix_page_graph_metrics_crawl_job_id",
        "page_graph_metrics",
        ["crawl_job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_page_graph_metrics_crawl_job_id", table_name="page_graph_metrics")
    op.drop_table("page_graph_metrics")

    op.drop_index(
        "ix_page_graph_clusters_crawl_job_cluster_id",
        table_name="page_graph_clusters",
    )
    op.drop_index("ix_page_graph_clusters_crawl_job_id", table_name="page_graph_clusters")
    op.drop_table("page_graph_clusters")

    op.drop_index(
        "ix_page_graph_edges_crawl_job_edge_type",
        table_name="page_graph_edges",
    )
    op.drop_index("ix_page_graph_edges_crawl_job_target", table_name="page_graph_edges")
    op.drop_index("ix_page_graph_edges_crawl_job_source", table_name="page_graph_edges")
    op.drop_index("ix_page_graph_edges_crawl_job_id", table_name="page_graph_edges")
    op.drop_table("page_graph_edges")
