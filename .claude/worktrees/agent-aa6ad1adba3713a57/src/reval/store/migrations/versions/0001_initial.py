"""initial schema (docs/10 section 8)

Idempotent on purpose: ``SqlStore`` still calls ``create_all`` for SQLite dev use, so a database may
already hold these tables before Alembic first sees it; existing tables are left alone.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _missing(name: str) -> bool:
    return not sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _missing("counters"):
        op.create_table(
            "counters",
            sa.Column("name", sa.String(), primary_key=True),
            sa.Column("value", sa.Integer(), nullable=False),
        )
    if _missing("snapshots"):
        op.create_table(
            "snapshots",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("git_rev", sa.String(), nullable=True),
            sa.Column("created_seq", sa.Integer(), nullable=False, unique=True),
            sa.Column("body", sa.Text(), nullable=False),
        )
    if _missing("evidence"):
        op.create_table(
            "evidence",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("subject_id", sa.String(), nullable=False),
            sa.Column("producer_id", sa.String(), nullable=False),
            sa.Column("snapshot_id", sa.String(), nullable=False),
            sa.Column("created_seq", sa.Integer(), nullable=False, unique=True),
            sa.Column("body", sa.Text(), nullable=False),
        )
        op.create_index("ix_evidence_subject_id", "evidence", ["subject_id"])
        op.create_index("ix_evidence_producer_id", "evidence", ["producer_id"])
        op.create_index("ix_evidence_snapshot_id", "evidence", ["snapshot_id"])
    if _missing("assessments"):
        op.create_table(
            "assessments",
            sa.Column("snapshot_id", sa.String(), primary_key=True),
            sa.Column("claim_id", sa.String(), primary_key=True),
            sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=False),
            sa.Column("created_seq", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("input_hash", sa.String(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
        )
        op.create_index("ix_assessments_created_seq", "assessments", ["created_seq"])
    if _missing("plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("snapshot_id", sa.String(), nullable=False),
            sa.Column("created_seq", sa.Integer(), nullable=False, unique=True),
            sa.Column("body", sa.Text(), nullable=False),
        )
        op.create_index("ix_plans_snapshot_id", "plans", ["snapshot_id"])
    if _missing("jobs"):
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("created_seq", sa.Integer(), nullable=False, unique=True),
        )
    if _missing("reports"):
        op.create_table(
            "reports",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("snapshot_id", sa.String(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
        )
        op.create_index("ix_reports_snapshot_id", "reports", ["snapshot_id"])


def downgrade() -> None:
    for name in ("reports", "jobs", "plans", "assessments", "evidence", "snapshots", "counters"):
        op.drop_table(name)
