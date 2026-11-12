"""Truth oracles (docs/06 section 2): did the requirement actually hold?

Tier A: the measured peak of a recorded segment of a **test** profile, read from the S' data.
Every other subject (parametric, optimizer, reserve/train profiles, non-thermal claims) gets ``None`` and
is excluded from UAR_truth. Tier B: the world model's noise-free peak for every thermal subject.
Return value convention: ``True`` = the requirement is actually violated, ``False`` = it holds.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import pandas as pd
from motor import cycles

from bench.world.model import PhysicalParams, World
from reval.domain.engineering import Claim, Comparator, Requirement, Subject
from reval.domain.snapshot import Snapshot

_RECORDED = "motor.cycles:recorded"
# Thermal quantity -> observed node. Anything else has no temperature truth.
NODE_OF: Mapping[str, str] = {"pm_peak": "pm", "sw_peak": "stator_winding"}

Peaks = Mapping[str, Mapping[str, float]]  # subject_id -> quantity -> peak (degC)


def violated(req: Requirement, peak: float) -> bool:
    """Strict violation of ``req`` by ``peak`` (hitting the limit exactly satisfies it)."""
    return peak > req.limit if req.op is Comparator.LE else peak < req.limit


def tier_a_peaks(
    subjects: Mapping[str, Subject], measures: pd.DataFrame, test_profiles: Collection[int]
) -> Peaks:
    """Measured peaks of the recorded segments of ``test_profiles`` in the S' data ``measures``."""
    allowed = {int(p) for p in test_profiles}
    out: dict[str, dict[str, float]] = {}
    for sid in sorted(subjects):
        s = subjects[sid]
        if s.generator != _RECORDED or int(s.params["profile_id"]) not in allowed:
            continue
        temps = cycles.recorded_temperatures(
            int(s.params["profile_id"]), float(s.params["start_s"]), float(s.params["duration_s"]), measures
        )
        out[sid] = {q: float(temps[node].max()) for q, node in NODE_OF.items()}
    return out


def tier_b_peaks(world: World, physical: PhysicalParams, trajectories: Mapping[str, pd.DataFrame]) -> Peaks:
    """Noise-free world peaks per subject; ``trajectories`` holds each subject's input frame."""
    out: dict[str, dict[str, float]] = {}
    for sid in sorted(trajectories):
        sim = world.simulate(trajectories[sid], physical)
        out[sid] = {q: float(sim[node].max()) for q, node in NODE_OF.items()}
    return out


def truth_from_peaks(
    claims: Mapping[str, Claim], requirements: Mapping[str, Requirement], peaks: Peaks
) -> dict[str, bool | None]:
    """``{claim_id: violated | None}``; ``None`` where no peak exists for the claim's subject/quantity."""
    out: dict[str, bool | None] = {}
    for cid in sorted(claims):
        claim = claims[cid]
        req = requirements[claim.requirement_id]
        peak = peaks.get(claim.subject_id, {}).get(req.quantity)
        out[cid] = None if peak is None else violated(req, peak)
    return out


def truth_tier_a(
    snapshot: Snapshot, measures: pd.DataFrame, test_profiles: Collection[int]
) -> dict[str, bool | None]:
    """Tier A truth for the post-change snapshot S' from its own (post-change) measured data."""
    return truth_from_peaks(
        snapshot.claims, snapshot.requirements, tier_a_peaks(snapshot.subjects, measures, test_profiles)
    )


def truth_tier_b(
    snapshot: Snapshot, world: World, physical: PhysicalParams, trajectories: Mapping[str, pd.DataFrame]
) -> dict[str, bool | None]:
    """Tier B truth: every subject with a trajectory and a thermal quantity is decided."""
    return truth_from_peaks(
        snapshot.claims, snapshot.requirements, tier_b_peaks(world, physical, trajectories)
    )


def none_share(truth: Mapping[str, bool | None]) -> float:
    """Share of claims without truth (reported next to UAR_truth); 0.0 for an empty mapping."""
    return sum(v is None for v in truth.values()) / len(truth) if truth else 0.0
