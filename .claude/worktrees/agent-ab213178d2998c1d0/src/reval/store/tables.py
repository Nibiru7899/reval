"""SQLAlchemy Core table definitions (docs/10 §8, ADR 0003). Only portable column types are used."""

from sqlalchemy import Column, Index, Integer, MetaData, String, Table, Text

metadata = MetaData()

# created_seq values come from this counter, never from a clock (AGENTS rule 1 spirit, reproducibility).
counters = Table(
    "counters",
    metadata,
    Column("name", String, primary_key=True),
    Column("value", Integer, nullable=False),
)

snapshots = Table(
    "snapshots",
    metadata,
    Column("id", String, primary_key=True),
    Column("git_rev", String, nullable=True),
    Column("created_seq", Integer, nullable=False, unique=True),
    Column("body", Text, nullable=False),
)

evidence = Table(
    "evidence",
    metadata,
    Column("id", String, primary_key=True),
    Column("subject_id", String, nullable=False, index=True),
    Column("producer_id", String, nullable=False, index=True),
    Column("snapshot_id", String, nullable=False, index=True),
    Column("created_seq", Integer, nullable=False, unique=True),
    Column("body", Text, nullable=False),
)

assessments = Table(
    "assessments",
    metadata,
    Column("snapshot_id", String, primary_key=True),
    Column("claim_id", String, primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("created_seq", Integer, nullable=False, index=True),
    Column("status", String, nullable=False),
    Column("input_hash", String, nullable=False),
    Column("body", Text, nullable=False),
)

plans = Table(
    "plans",
    metadata,
    Column("id", String, primary_key=True),
    Column("snapshot_id", String, nullable=False, index=True),
    Column("created_seq", Integer, nullable=False, unique=True),
    Column("body", Text, nullable=False),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False),
    Column("state", String, nullable=False),
    Column("payload", Text, nullable=False),
    Column("result", Text, nullable=True),
    Column("created_seq", Integer, nullable=False, unique=True),
)

reports = Table(
    "reports",
    metadata,
    Column("id", String, primary_key=True),
    Column("snapshot_id", String, nullable=False),
    Column("body", Text, nullable=False),
)

Index("ix_reports_snapshot_id", reports.c.snapshot_id)
