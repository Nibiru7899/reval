from collections.abc import Callable

import pandas as pd
import pytest

from tests.helpers.motor_synth import synthetic_measures as _synthetic_measures


@pytest.fixture
def synthetic_measures() -> Callable[..., pd.DataFrame]:
    """Factory: synthetic_measures(n_profiles=3, n_rows=600, seed=0)."""
    return _synthetic_measures
