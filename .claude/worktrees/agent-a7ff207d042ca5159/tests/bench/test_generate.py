"""P5-03: the scenario generator is deterministic and spreads over >= 30 base snapshots."""

from typing import Any

from bench.scenarios.generate import TIER_TYPES, generate
from bench.scenarios.model import GenerateConfig


def test_same_seed_gives_identical_lists_and_other_seeds_differ() -> None:
    cfg = GenerateConfig()
    a, b, c = generate(cfg, 7), generate(cfg, 7), generate(cfg, 8)
    assert a == b
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]
    assert a != c


def test_counts_ids_and_tiers() -> None:
    cfg = GenerateConfig(instances_per_type=5)
    scs = generate(cfg, 0)
    assert len(scs) == 5 * (len(TIER_TYPES["A"]) + len(TIER_TYPES["B"]))
    assert len({s.id for s in scs}) == len(scs)
    assert {s.change_type for s in scs if s.tier == "B"} == {"T6", "T7", "T8", "T9", "T12"}
    assert {s.change_type for s in scs if s.tier == "A"} == {
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
        "T10",
        "T11",
        "T12",
    }


def test_at_least_30_base_snapshots_per_tier() -> None:
    scs = generate(GenerateConfig(instances_per_type=10), 0)
    for tier in ("A", "B"):
        assert len({s.base_snapshot for s in scs if s.tier == tier}) >= 30


def test_parameter_ranges_follow_the_taxonomy() -> None:
    scs = generate(GenerateConfig(instances_per_type=40), 1)
    by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for s in scs:
        by.setdefault((s.tier, s.change_type), []).append(s.params)
    assert all(2.0 <= abs(p["delta_k"]) <= 10.0 for p in by[("A", "T5")])
    assert all(0.5 <= abs(p["offset_k"]) <= 3.0 for p in by[("A", "T3")])
    assert all(-0.08 <= p["flow_change"] <= -0.02 for p in by[("B", "T7")])
    assert all(-0.35 <= p["flow_change"] <= -0.15 for p in by[("B", "T8")])
    assert all(1.1 <= p["r_ic_scale"] <= 1.4 for p in by[("B", "T9")])
    assert {p["flavor"] for p in by[("A", "T11")]} == {"refactor", "fix"}
    for tier in ("A", "B"):
        for p in by[(tier, "T12")]:
            types = [c["change_type"] for c in p["components"]]
            assert 2 <= len(types) <= 3 and len(set(types)) == len(types)
            assert not {"T7", "T8"} <= set(types) and not {"T1", "T2"} <= set(types)


def test_t9_declares_only_the_world_change() -> None:
    scs = [s for s in generate(GenerateConfig(instances_per_type=3), 0) if s.change_type == "T9"]
    assert scs and all(set(s.params) == {"r_ic_scale"} for s in scs)
