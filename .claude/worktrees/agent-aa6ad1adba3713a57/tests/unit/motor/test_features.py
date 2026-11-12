import numpy as np
import pandas as pd
import pytest
from motor.features import (
    DERIVED,
    EWMA_SPANS,
    INPUT_COLUMNS,
    add_derived,
    add_ewma,
    make_features,
)


def test_derived_values(synthetic_measures):
    df = add_derived(synthetic_measures(n_profiles=1, n_rows=50))
    assert np.allclose(df["i_s"], np.hypot(df["i_d"], df["i_q"]))
    assert np.allclose(df["u_s"], np.hypot(df["u_d"], df["u_q"]))
    assert np.allclose(df["p_el"], df["i_s"] * df["u_s"])
    assert np.allclose(df["i_s_x_w"], df["i_s"] * df["motor_speed"])


def test_no_leak_across_profiles(synthetic_measures):
    df = synthetic_measures(n_profiles=3, n_rows=100)
    out = add_ewma(df, ["i_q"], [10])
    for _, g in out.groupby("profile_id"):
        assert g["i_q_ewm10"].iloc[0] == pytest.approx(g["i_q"].iloc[0])


def test_feature_order_deterministic(synthetic_measures):
    df = synthetic_measures(n_profiles=2, n_rows=80)
    _, a = make_features(df, spans=(5, 10))
    _, b = make_features(df, spans=(5, 10))
    assert a == b
    base = [*INPUT_COLUMNS, *DERIVED]
    assert a[: len(base)] == base
    assert a[len(base)] == f"{base[0]}_ewm5"
    assert len(a) == len(base) * 3
    _, c = make_features(df.iloc[:10].copy())
    assert c[-1] == f"{base[-1]}_ewm{EWMA_SPANS[-1]}"


def test_constant_input_gives_constant_ewma():
    df = pd.DataFrame({"profile_id": [1] * 20 + [2] * 20, "x": [3.0] * 20 + [-1.5] * 20})
    out = add_ewma(df, ["x"], [4, 9])
    assert np.allclose(out["x_ewm4"], out["x"])
    assert np.allclose(out["x_ewm9"], out["x"])


def test_recursive_formula_five_rows():
    x = [1.0, 2.0, 4.0, 3.0, 0.0]
    df = pd.DataFrame({"profile_id": [1] * 5, "x": x})
    span = 3
    alpha = 2 / (span + 1)
    expected = [x[0]]
    for v in x[1:]:
        expected.append(alpha * v + (1 - alpha) * expected[-1])
    out = add_ewma(df, ["x"], [span])
    assert np.allclose(out["x_ewm3"], expected)
