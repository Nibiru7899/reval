"""build_snapshot: determinism, id sensitivity, derived-hash folding."""

from typing import Any

import yaml


def test_same_inputs_same_id_and_git_rev_ignored(mini: Any) -> None:
    a, b = mini.snapshot(), mini.snapshot(git_rev="abc123")
    assert a.id == b.id and b.git_rev == "abc123"
    assert set(a.producers) == {
        f"mini.producers:{n}" for n in ("predict_temp", "sim_temp", "measure_temp", "shaft_check")
    }
    assert set(a.policies) >= {"low", "medium", "high"}
    assert a.artifacts["surrogate"].hasher == "model" and a.artifacts["data"].hasher == "dataframe"


def test_editing_a_field_changes_id(mini: Any) -> None:
    before = mini.snapshot()
    p = mini.root / "params" / "params.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["shaft"]["d_mm"] = 30.1
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    after = mini.snapshot()
    assert after.id != before.id
    assert (
        after.versions["params"].field_hashes["/shaft/d_mm"]
        != before.versions["params"].field_hashes["/shaft/d_mm"]
    )
    assert (
        after.versions["params"].field_hashes["/sim/gain"]
        == before.versions["params"].field_hashes["/sim/gain"]
    )


def test_derived_surrogate_hash_follows_data(mini: Any) -> None:
    before = mini.snapshot()
    d = mini.root / "data" / "data.csv"
    d.write_text(d.read_text(encoding="utf-8") + "g9,9.9,99.0\n", encoding="utf-8")
    after = mini.snapshot()
    assert after.versions["data"].content_hash != before.versions["data"].content_hash
    assert after.versions["surrogate"].content_hash != before.versions["surrogate"].content_hash
