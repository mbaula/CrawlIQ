"""Store HTTP fetch duration for stats (pages + crawl_errors).

Revision ID: 0006_fetch_duration_ms
Revises: 0005_crawl_errors_http_fields
Create Date: 2026-05-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_fetch_duration_ms"
down_revision: Union[str, None] = "0005_crawl_errors_http_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pages",
        sa.Column("fetch_duration_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "crawl_errors",
        sa.Column("fetch_duration_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crawl_errors", "fetch_duration_ms")
    op.drop_column("pages", "fetch_duration_ms")
