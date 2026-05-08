"""Add pages.token_count for search scoring.

Revision ID: 0004_pages_token_count
Revises: 0003_page_links_crawl_eligible
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_pages_token_count"
down_revision = "0003_page_links_crawl_eligible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pages",
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("pages", "token_count")

