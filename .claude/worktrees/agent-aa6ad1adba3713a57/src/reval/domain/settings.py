"""Engine knobs shared by core, the SDK and benchmark ablations (docs/10 §2, settings.py)."""

from typing import Literal

from pydantic import Field

from reval.domain.base import Frozen


class ReValSettings(Frozen):
    """Ablation switches for the benchmark; defaults are the full method. Non-default values: bench only."""

    field_level_selectors: bool = True
    tolerance_carry_forward: bool = True
    scope_freshness: bool = True
    ad_gate: Literal["strict", "relaxed", "off"] = "strict"
    interval_method: Literal["conformal", "fixed_margin", "cqr"] = "conformal"
    planner: Literal["ilp", "greedy"] = "ilp"
    # A7 sweeps kappa and may be BELOW a tolerance's own safety_factor (less conservative): bench only.
    kappa_override: float | None = Field(default=None, ge=1)


DEFAULT_SETTINGS = ReValSettings()
