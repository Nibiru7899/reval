"""Derived and EWMA features for the trajectory models (docs/05 §3)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

# Torque is not an input: it is itself an estimate derived from currents and voltages.
INPUT_COLUMNS = ("u_q", "u_d", "i_q", "i_d", "motor_speed", "coolant", "ambient")
DERIVED = ("i_s", "u_s", "p_el", "i_s_x_w")
# Samples at 2 Hz (about 11 min to 79 min). A parameter; the final choice is recorded in the log.
EWMA_SPANS: tuple[int, ...] = (1320, 3360, 6360, 9480)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with i_s, u_s, p_el and i_s_x_w added."""
    out = df.copy()
    out["i_s"] = np.hypot(out["i_d"], out["i_q"])
    out["u_s"] = np.hypot(out["u_d"], out["u_q"])
    out["p_el"] = out["i_s"] * out["u_s"]
    out["i_s_x_w"] = out["i_s"] * out["motor_speed"]
    return out


def add_ewma(df: pd.DataFrame, cols: Sequence[str], spans: Sequence[int]) -> pd.DataFrame:
    """Add causal per-profile EWMAs named ``{col}_ewm{span}``.

    ``adjust=False`` makes the filter recursive, so it matches real-time estimation and
    never looks at later samples or at other profiles.
    """
    out = df.copy()
    grouped = out.groupby("profile_id", sort=False)
    new: dict[str, pd.Series] = {}
    for col in cols:
        for span in spans:
            new[f"{col}_ewm{span}"] = grouped[col].transform(
                lambda s, span=span: s.ewm(span=span, adjust=False).mean()
            )
    return pd.concat([out, pd.DataFrame(new, index=out.index)], axis=1)


def make_features(df: pd.DataFrame, spans: Sequence[int] = EWMA_SPANS) -> tuple[pd.DataFrame, list[str]]:
    """Return the frame and the ordered feature names (inputs, derived, then EWMAs)."""
    out = add_derived(df)
    base = [*INPUT_COLUMNS, *DERIVED]
    out = add_ewma(out, base, spans)
    names = [*base, *(f"{c}_ewm{s}" for c in base for s in spans)]
    return out, names
