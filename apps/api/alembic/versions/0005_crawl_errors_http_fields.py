"""Add crawl error HTTP context fields.

Revision ID: 0005_crawl_errors_http_fields
Revises: 0004_pages_token_count
Create Date: 2026-05-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_crawl_errors_http_fields"
down_revision: Union[str, None] = "0004_pages_token_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawl_errors", sa.Column("final_url", sa.Text(), nullable=True))
    op.add_column("crawl_errors", sa.Column("status_code", sa.Integer(), nullable=True))
    op.add_column("crawl_errors", sa.Column("content_type", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_errors", "content_type")
    op.drop_column("crawl_errors", "status_code")
    op.drop_column("crawl_errors", "final_url")

