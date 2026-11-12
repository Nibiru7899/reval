import importlib.util
from pathlib import Path

import pytest

_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


def _hook_path() -> str:
    spec = importlib.util.spec_from_file_location("reval_conftest", _CONFTEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.DATA_PARQUET)


@pytest.mark.data
def test_data_marked_test_is_skipped_without_dataset() -> None:
    assert True


def test_hook_path_constant() -> None:
    assert _hook_path() == "examples/motor_thermal/data/processed/measures.parquet"
