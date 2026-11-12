# ADR 0003 — Local-first storage: SQLite default, PostgreSQL optional

- **Status:** accepted
- **Date:** 2026-10-24

## Context
ReVal should run inside an engineer's repo with zero setup, and also back a multi-user web workspace for the demo.

## Decision
SQLAlchemy 2 models with Alembic migrations. SQLite (`.reval/reval.db`) is the default for the CLI. PostgreSQL is selected by
`REVAL_DATABASE_URL` for the server and Docker Compose. Only portable SQL types are used (JSON stored as text/JSONB via a SQLAlchemy type).
Background jobs use a `jobs` table and an in-process worker. No Celery or Redis.

## Consequences
- No services are needed for the core workflow or CI.
- Integration tests run against SQLite always and against PostgreSQL in one CI job.
