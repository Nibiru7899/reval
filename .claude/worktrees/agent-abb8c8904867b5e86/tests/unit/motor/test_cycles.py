import numpy as np
import pandas as pd
import pytest
from motor.cycles import (
    CLASS_DURATIONS_S,
    HZ,
    blocks,
    length_class,
    make_library,
    recorded,
    recorded_temperatures,
)
from motor.splits import Splits


def _df() -> pd.DataFrame:
    rng = np.random.default_rng(1)
    frames = []
    for pid in range(1, 9):
        n = 8000
        frames.append(
            pd.DataFrame(
                {
                    "profile_id": pid,
                    "t": np.arange(n) * 0.5,
                    "torque": np.repeat(rng.uniform(-100, 200, n // 100), 100),
                    "motor_speed": np.repeat(rng.uniform(0, 5000, n // 100), 100),
                    "coolant": rng.uniform(20, 60, n),
                    "ambient": rng.uniform(20, 28, n),
                    "pm": rng.uniform(40, 90, n),
                    "stator_winding": rng.uniform(40, 100, n),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


SPLITS = Splits(train=(1, 2, 3, 4), calib=(5,), test=(6, 7), reserve=(8,))


def test_blocks_rows_and_columns() -> None:
    out = blocks({"blocks": [[100, 3000, 60], [50, 1000, 90.5]], "coolant": 40, "ambient": 25})
    assert len(out) == round((60 + 90.5) * HZ)
    assert list(out.columns) == ["torque", "motor_speed", "coolant", "ambient", "t"]
    assert out["t"].iloc[1] == 0.5
    assert out["torque"].iloc[0] == 100 and out["motor_speed"].iloc[-1] == 1000


def test_blocks_rejects_empty_and_zero() -> None:
    with pytest.raises(ValueError):
        blocks({"blocks": [], "coolant": 1, "ambient": 1})
    with pytest.raises(ValueError):
        blocks({"blocks": [[1, 1, 0]], "coolant": 1, "ambient": 1})


def test_length_class() -> None:
    assert length_class(300) == "short" and length_class(600) == "short"
    assert length_class(601) == "medium" and length_class(1800) == "medium"
    assert length_class(1801) == "long" and length_class(9000) == "long"


def test_recorded_segment_and_test_only() -> None:
    df = _df()
    seg = recorded(6, 100.0, 60.0, df, splits=SPLITS)
    assert len(seg) == 120 and seg["t"].iloc[0] == 0.0
    ref = df[df.profile_id == 6].iloc[200:320]
    assert np.allclose(seg["torque"].to_numpy(), ref["torque"].to_numpy())
    assert len(recorded_temperatures(6, 100.0, 60.0, df)) == 120
    with pytest.raises(ValueError):
        recorded(1, 0.0, 60.0, df, splits=SPLITS)
    with pytest.raises(ValueError):
        recorded(8, 0.0, 60.0, df, splits=SPLITS)
    with pytest.raises(ValueError):
        recorded(6, 3990.0, 60.0, df, splits=SPLITS)


def test_library_deterministic_and_test_only() -> None:
    df = _df()
    a = make_library(0, SPLITS, data=df)
    b = make_library(0, SPLITS, data=df)
    assert a == b
    assert a != make_library(1, SPLITS, data=df)
    par = [s for s in a if s["generator"] == "motor.cycles:blocks"]
    rec = [s for s in a if s["generator"] == "motor.cycles:recorded"]
    assert len(par) == 40 and len(rec) == 40
    assert len({s["id"] for s in a}) == 80
    assert {s["params"]["profile_id"] for s in rec} <= set(SPLITS.test)
    for s in par:
        p = s["params"]
        total = sum(b[2] for b in p["blocks"])
        assert total in CLASS_DURATIONS_S.values()
        assert 2 <= len(p["blocks"]) <= 6
        assert len(blocks(p)) == total * HZ
    for s in rec:
        p = s["params"]
        recorded(p["profile_id"], p["start_s"], p["duration_s"], df, splits=SPLITS)


def test_library_has_out_of_envelope_cycles() -> None:
    df = _df()
    lib = make_library(0, SPLITS, data=df)
    par = [s["params"] for s in lib if s["generator"] == "motor.cycles:blocks"]
    train = df[df.profile_id.isin(SPLITS.train)]
    vmax = train["motor_speed"].quantile(0.995)
    tmax = train["torque"].quantile(0.995)
    cmax = train["coolant"].quantile(0.995)
    out = [p for p in par if any(b[1] > vmax or b[0] > tmax for b in p["blocks"]) or p["coolant"] > cmax]
    assert len(out) >= 8
