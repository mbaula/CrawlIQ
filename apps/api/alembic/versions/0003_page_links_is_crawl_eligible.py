"""Add ``page_links.is_crawl_eligible`` for frontier vs full link graph.

Revision ID: 0003_page_links_is_crawl_eligible
Revises: 0002_queued_status
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_page_links_is_crawl_eligible"
down_revision: Union[str, None] = "0002_queued_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "page_links",
        sa.Column(
            "is_crawl_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.alter_column("page_links", "is_crawl_eligible", server_default=None)


def downgrade() -> None:
    op.drop_column("page_links", "is_crawl_eligible")
