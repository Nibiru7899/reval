from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from motor import lptn
from motor.lptn import NODES

PARQUET = Path("examples/motor_thermal/data/processed/measures.parquet")


def _synthetic_profiles(p_true, n_profiles=4, n_rows=6000, seed=0, noise=0.05) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for pid in range(n_profiles):
        # Piecewise-constant random drive: rich enough to excite all time constants.
        seg = 400
        k = n_rows // seg + 1
        rep = lambda a, seg=seg: np.repeat(a, seg)[:n_rows]  # noqa: E731
        i_q = rep(rng.uniform(-250, 250, k))
        w = rep(rng.uniform(0, 5000, k))
        df = pd.DataFrame(
            {
                "i_d": rep(rng.uniform(-150, 0, k)),
                "i_q": i_q,
                "u_d": rep(rng.uniform(-100, 0, k)),
                "u_q": rep(rng.uniform(0, 100, k)),
                "motor_speed": w,
                "coolant": rep(rng.uniform(20, 60, k)),
                "ambient": rep(rng.uniform(20, 28, k)),
            }
        )
        sim = lptn.simulate(df, p_true, theta0=dict.fromkeys(NODES, 30.0))
        sim = sim + rng.normal(0, noise, sim.shape)
        df[list(NODES)] = sim.to_numpy()
        df["profile_id"] = pid
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _true_params() -> lptn.LPTNParams:
    p = lptn.default_params()
    return lptn.LPTNParams(
        C={"pm": 8.0e3, "stator_yoke": 2.5e4, "stator_tooth": 1.2e4, "stator_winding": 4.0e3},
        R={
            ("stator_winding", "stator_tooth"): 0.06,
            ("stator_tooth", "stator_yoke"): 0.05,
            ("stator_yoke", "coolant"): 0.05,
            ("pm", "stator_tooth"): 0.15,
            ("pm", "ambient"): 0.8,
            ("stator_winding", "ambient"): 1.2,
        },
        k_cu=6.0e-3,
        alpha_cu=p.alpha_cu,
        k_fe1=0.3,
        k_fe2=0.3,
        k_pm=0.15,
    )


@pytest.mark.slow
def test_identify_recovers_known_parameters():
    truth = _true_params()
    df = _synthetic_profiles(truth)
    p0 = lptn.default_params()
    fitted, info = lptn.identify(df, p0, {}, seed=0, max_nfev=60)
    assert all(np.isfinite(v) for v in info["mse_train"].values())
    # A single dominant path per node is well identified; compare the ones the data constrain.
    for node in NODES:
        assert fitted.C[node] == pytest.approx(truth.C[node], rel=0.10), node
    for pair, r in truth.R.items():
        assert fitted.R[pair] == pytest.approx(r, rel=0.10), pair


def test_identify_is_deterministic_and_subsamples():
    df = _synthetic_profiles(_true_params(), n_profiles=3, n_rows=1200)
    a, ia = lptn.identify(df, lptn.default_params(), {}, max_profiles=2, seed=1, max_nfev=3)
    b, ib = lptn.identify(df, lptn.default_params(), {}, max_profiles=2, seed=1, max_nfev=3)
    assert a == b
    assert len(ia["profiles"]) == 2 and ia["profiles"] == ib["profiles"]


def test_model_form_band_zero_for_exact_model():
    truth = _true_params()
    df = _synthetic_profiles(truth, n_profiles=2, n_rows=2000, noise=0.0)
    # Simulate at the same initial state the band uses (measured t=0), so the model is exact.
    band = lptn.model_form_band(truth, df, window_rows=500)
    assert set(band) == set(NODES)
    assert all(v < 1e-6 for v in band.values())


@pytest.mark.data
@pytest.mark.slow
def test_identify_real_data_end_to_end():
    if not PARQUET.exists():
        pytest.skip("parquet absent")
    df = pd.read_parquet(PARQUET)
    ids = sorted(df["profile_id"].unique())[:3]
    sub = df[df["profile_id"].isin(ids)]
    fitted, info = lptn.identify(sub, lptn.default_params(), {}, max_profiles=3, max_nfev=5)
    assert all(np.isfinite(v) for v in info["mse_train"].values())
    band = lptn.model_form_band(fitted, sub, window_rows=1200)
    assert all(np.isfinite(v) for v in band.values())
