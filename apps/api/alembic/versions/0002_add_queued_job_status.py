"""Extend ``crawl_jobs.status`` CHECK constraint to include ``queued`` (API creates jobs in this state).

Revision ID: 0002_queued_status
Revises: 0001_initial
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_queued_status"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_crawl_jobs_status", "crawl_jobs", type_="check")
    op.create_check_constraint(
        "ck_crawl_jobs_status",
        "crawl_jobs",
        "status IN ('queued', 'pending', 'running', 'completed', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE crawl_jobs SET status = 'pending' WHERE status = 'queued'"),
    )
    op.drop_constraint("ck_crawl_jobs_status", "crawl_jobs", type_="check")
    op.create_check_constraint(
        "ck_crawl_jobs_status",
        "crawl_jobs",
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
    )
