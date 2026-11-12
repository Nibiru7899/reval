"""P5-08: truth oracles on synthetic data (Tier A measured test cycles, Tier B noise-free world peak)."""

import numpy as np
import pandas as pd
import pytest

from bench.oracles import truth as T
from bench.world.model import PhysicalParams, World
from reval.domain.engineering import Claim, Comparator, Requirement, Subject, SubjectKind

REC = "motor.cycles:recorded"


def req(rid: str, quantity: str, limit: float, op: Comparator = Comparator.LE) -> Requirement:
    return Requirement(
        id=rid, text="t", quantity=quantity, op=op, limit=limit, unit="degC", criticality="medium"
    )  # type: ignore[arg-type]


def subj(sid: str, profile: int, start: float = 0.0, dur: float = 10.0, gen: str = REC) -> Subject:
    return Subject(
        id=sid, kind=SubjectKind.DUTY_CYCLE, generator=gen,
        params={"profile_id": profile, "start_s": start, "duration_s": dur},
    )  # fmt: skip


def measures() -> pd.DataFrame:
    """Profile 7 (test) peaks pm=95/sw=80 in its first 10 s (20 rows) and 120 later; profile 3 is reserve."""
    rows = []
    for pid in (7, 3):
        for k in range(60):
            first = k < 20
            rows.append({
                "profile_id": pid, "t": k * 0.5,
                "pm": (95.0 if k == 5 else 50.0) if first else 120.0,
                "stator_winding": (80.0 if k == 5 else 40.0) if first else 100.0,
            })  # fmt: skip
    return pd.DataFrame(rows)


REQS = {
    "R-PM": req("R-PM", "pm_peak", 100.0),
    "R-SW": req("R-SW", "sw_peak", 75.0),
    "R-GE": req("R-GE", "pm_peak", 90.0, Comparator.GE),
    "R-SHAFT": req("R-SHAFT", "shaft_d", 30.0),
}
CLAIMS = {
    "pm-test": Claim(id="pm-test", requirement_id="R-PM", subject_id="REC7"),
    "sw-test": Claim(id="sw-test", requirement_id="R-SW", subject_id="REC7"),
    "ge-test": Claim(id="ge-test", requirement_id="R-GE", subject_id="REC7"),
    "pm-reserve": Claim(id="pm-reserve", requirement_id="R-PM", subject_id="REC3"),
    "pm-param": Claim(id="pm-param", requirement_id="R-PM", subject_id="PARAM"),
    "shaft": Claim(id="shaft", requirement_id="R-SHAFT", subject_id="D1"),
}
SUBJECTS = {
    "REC7": subj("REC7", 7),
    "REC3": subj("REC3", 3),
    "PARAM": Subject(id="PARAM", kind=SubjectKind.DUTY_CYCLE, generator="motor.cycles:blocks", params={}),
    "D1": Subject(id="D1", kind=SubjectKind.DESIGN),
}


def test_violated_boundaries_are_strict() -> None:
    assert not T.violated(REQS["R-PM"], 100.0) and T.violated(REQS["R-PM"], 100.01)
    assert not T.violated(REQS["R-GE"], 90.0) and T.violated(REQS["R-GE"], 89.99)


def test_tier_a_uses_only_test_profiles_and_the_recorded_segment() -> None:
    peaks = T.tier_a_peaks(SUBJECTS, measures(), test_profiles=[7])
    assert peaks == {"REC7": {"pm_peak": 95.0, "sw_peak": 80.0}}  # segment only: the 120 later is outside
    truth = T.truth_from_peaks(CLAIMS, REQS, peaks)
    assert truth == {
        "pm-test": False,  # 95 <= 100
        "sw-test": True,  # 80 > 75
        "ge-test": False,  # 95 >= 90
        "pm-reserve": None,  # reserve profile is never a truth subject
        "pm-param": None,  # parametric subject has no measurement in Tier A
        "shaft": None,  # non-thermal claim
    }
    assert T.none_share(truth) == pytest.approx(3 / 6)


def test_tier_a_truth_comes_from_the_post_change_data() -> None:
    after = measures()
    after.loc[(after["profile_id"] == 7) & (after["t"] == 2.5), "pm"] = 105.0  # S' data moved
    peaks = T.tier_a_peaks(SUBJECTS, after, [7])
    assert T.truth_from_peaks(CLAIMS, REQS, peaks)["pm-test"] is True


def test_empty_truth_has_zero_none_share() -> None:
    assert T.none_share({}) == 0.0


def test_tier_b_noise_free_peak_for_every_subject() -> None:
    n = 120
    traj = pd.DataFrame({
        "i_d": np.full(n, -50.0), "i_q": np.full(n, 100.0), "u_d": np.full(n, -20.0), "u_q": np.full(n, 40.0),
        "motor_speed": np.full(n, 2000.0), "coolant": np.full(n, 30.0), "ambient": np.full(n, 25.0),
        "pm": np.full(n, 40.0), "stator_yoke": np.full(n, 38.0), "stator_tooth": np.full(n, 39.0),
        "stator_winding": np.full(n, 41.0),
    })  # fmt: skip
    world, phys = World(), PhysicalParams()
    peaks = T.tier_b_peaks(world, phys, {"PARAM": traj, "REC3": traj})
    sim = world.simulate(traj, phys)
    assert peaks["PARAM"] == {
        "pm_peak": float(sim["pm"].max()),
        "sw_peak": float(sim["stator_winding"].max()),
    }
    assert (
        peaks["PARAM"] == peaks["REC3"] == T.tier_b_peaks(world, phys, {"PARAM": traj})["PARAM"]
    )  # deterministic
    limit = peaks["PARAM"]["pm_peak"]
    reqs = {"R-PM": req("R-PM", "pm_peak", limit - 1.0), "R-SW": req("R-SW", "sw_peak", 1e6)}
    claims = {
        "a": Claim(id="a", requirement_id="R-PM", subject_id="PARAM"),
        "b": Claim(id="b", requirement_id="R-SW", subject_id="REC3"),
        "c": Claim(id="c", requirement_id="R-SW", subject_id="NOTRAJ"),
    }
    truth = T.truth_from_peaks(claims, reqs, peaks)
    assert truth == {"a": True, "b": False, "c": None}  # Tier B decides every subject that has a trajectory
