"""P5-02: producer result cache (keys, byte-identical hits, invalidation)."""

from pathlib import Path

from bench.harness.cache import ProducerResultCache, cache_key
from tests.bench._mini import copy_mini, edit, open_project

PID = "mini.producers:sim_temp"


def test_hit_is_byte_identical_and_key_tracks_dependencies(tmp_path: Path) -> None:
    root = copy_mini(tmp_path)
    cache = ProducerResultCache(tmp_path / "c")
    proj = open_project(root)
    snap = proj.snapshot()
    first, hit1 = cache.run(proj, snap, PID, "S1")
    second, hit2 = cache.run(proj, snap, PID, "S1")
    assert (hit1, hit2) == (False, True)
    assert [e.model_dump_json() for e in first] == [e.model_dump_json() for e in second]

    # an unrelated field change keeps the key; a dependency change moves it
    edit(root, "params/params.yaml", "d_mm: 30.00", "d_mm: 30.01")
    proj2 = open_project(root)
    snap2 = proj2.snapshot()
    assert cache_key(snap, PID, "S1") == cache_key(snap2, PID, "S1")
    assert cache.run(proj2, snap2, PID, "S1")[1] is True
    edit(root, "params/params.yaml", "gain: 2.0", "gain: 2.5")
    snap3 = open_project(root).snapshot()
    assert cache_key(snap, PID, "S1") != cache_key(snap3, PID, "S1")
    assert cache_key(snap, PID, "S1") != cache_key(snap, PID, "S2")


def test_put_retries_when_windows_denies_the_rename(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A concurrent reader/writer can make os.replace raise PermissionError on Windows; retry, never fail."""
    import os

    root = copy_mini(tmp_path)
    cache = ProducerResultCache(tmp_path / "c")
    proj = open_project(root)
    snap = proj.snapshot()
    ev, _ = cache.run(proj, snap, PID, "S1")
    key = cache_key(snap, PID, "S1")
    real, calls = os.replace, []

    def flaky(src, dst):  # type: ignore[no-untyped-def]
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("denied")
        real(src, dst)

    monkeypatch.setattr("bench.harness.cache.os.replace", flaky)
    cache.put(key, ev)
    assert len(calls) == 3
    assert cache.get(key) is not None
