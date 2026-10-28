"""Application services (orchestrate core engines and adapters). Contract: docs/10 §10."""

from reval.services.project import DiffReport, PlanOutcome, Project

__all__ = ["DiffReport", "PlanOutcome", "Project"]
