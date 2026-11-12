"""Shared pytest configuration: skip data-marked tests when the dataset is absent; Hypothesis profiles."""

import os
from pathlib import Path

import pytest
from hypothesis import settings

DATA_PARQUET = "examples/motor_thermal/data/processed/measures.parquet"
SKIP_REASON = "motor dataset not downloaded; see P0-03 / P1-01"
_ROOT = Path(__file__).resolve().parent.parent

settings.register_profile("ci", max_examples=200)
settings.register_profile("thorough", max_examples=2000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if (_ROOT / DATA_PARQUET).exists():
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if "data" in item.keywords:
            item.add_marker(skip)
