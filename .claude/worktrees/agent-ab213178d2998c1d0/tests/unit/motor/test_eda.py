import pandas as pd
import pytest
from motor.eda import peak_distribution, profile_summary


def _frame() -> pd.DataFrame:
    n = 10
    rows = []
    for pid, base in ((1, 0.0), (2, 100.0)):
        for k in range(n):
            rows.append(
                {
                    "profile_id": pid,
                    "pm": base + k,
                    "stator_winding": base + 2 * k,
                    "coolant": 20.0 + k,
                    "ambient": 22.0,
                    "motor_speed": 100.0 * k,
                    "torque": float(k),
                }
            )
    return pd.DataFrame(rows)


def test_profile_summary():
    s = profile_summary(_frame())
    assert list(s["profile_id"]) == [1, 2]
    assert list(s["n_rows"]) == [10, 10]
    assert s["duration_h"].iloc[0] == pytest.approx(10 / 2 / 3600)
    assert s["pm_max"].tolist() == [9.0, 109.0]
    assert s["coolant_min"].iloc[0] == 20.0
    assert s["motor_speed_max"].iloc[0] == 900.0


def test_windows_never_span_profiles():
    # window = 4 rows: 2 full windows per profile, trailing 2 rows dropped.
    p = peak_distribution(_frame(), "pm", window_s=2.0)
    assert p.tolist() == [3.0, 7.0, 103.0, 107.0]


def test_window_larger_than_profile_gives_empty():
    assert len(peak_distribution(_frame(), "pm", window_s=60.0)) == 0
