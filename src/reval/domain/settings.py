"""Engine knobs shared by core, the SDK and benchmark ablations (docs/10 §2, settings.py)."""

from typing import Literal

from reval.domain.base import Frozen


class ReValSettings(Frozen):
    """Ablation switches; defaults are the full method."""

    field_level_selectors: bool = True
    tolerance_carry_forward: bool = True
    scope_freshness: bool = True
    ad_gate: Literal["strict", "relaxed", "off"] = "strict"
    interval_method: Literal["conformal", "fixed_margin", "cqr"] = "conformal"
    planner: Literal["ilp", "greedy"] = "ilp"
    kappa_override: float | None = None


DEFAULT_SETTINGS = ReValSettings()
