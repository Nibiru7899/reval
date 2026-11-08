"""ReValBench runner (P5-11): ``python -m bench.run --config bench/configs/<name>.yaml [--jobs N]``.

For every generated scenario the runner
1. clones the cached base snapshot of its cluster (built once per (tier, cluster) under ``<cache>/bases``),
2. records S: B0 runs every producer (through the shared producer-result cache); that evidence seeds
   ReVal's store and is every baseline's pre-change state,
3. applies the change (and the refits it implies), commits S',
4. runs B0 in S' (evidence oracle), ReVal (diff -> plan -> execute -> assess), B1-B4 and the truth oracle,
5. writes one ``ClaimRecord`` per (scenario, method, claim) to ``scenarios/<id>.parquet``.

Completed scenarios are skipped on a rerun (resumable). Scenarios run in joblib processes, each in its own
workspace; nothing a scenario computes depends on which worker ran it or in what order, so the combined
``rows.parquet`` / ``rows.sha256`` are identical for any ``--jobs``. Wall times go to ``timings.jsonl`` only.

ReVal's planned runs are executed through the same producer-result cache as B0 and the baselines
(docs/08 R8): a cache hit is the evidence an uncached run in that snapshot would produce (see
``BenchCache``), so this changes runtime, not results.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import gc
import hashlib
import importlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import traceback
from collections.abc import Iterable, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MOTOR_EXAMPLE = REPO / "examples" / "motor_thermal"
# `bench.oracles.truth` imports `motor`; appended so that a workspace's own copy (inserted in front by
# Project.open) always wins over the example.
if str(MOTOR_EXAMPLE) not in sys.path:
    sys.path.append(str(MOTOR_EXAMPLE))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from bench.analysis import metrics as M  # noqa: E402
from bench.baselines import (  # noqa: E402
    FileLevel,
    NaiveTrust,
    OodOnly,
    PostState,
    PreState,
    RandomBudget,
    domain_check_via_producer,
    execute_baseline,
)
from bench.harness.cache import ProducerResultCache, cache_key  # noqa: E402
from bench.harness.workspace import GIT_ENV, Workspace  # noqa: E402
from bench.metrics.records import ClaimRecord, to_frame  # noqa: E402
from bench.oracles.evidence import B0Result, run_b0, truly_affected  # noqa: E402
from bench.scenarios.generate import generate  # noqa: E402
from bench.scenarios.model import GenerateConfig, Scenario  # noqa: E402
from reval.core.canonical import canonical_json, sha256_hex  # noqa: E402
from reval.domain.assessment import Assessment  # noqa: E402
from reval.domain.evidence import Evidence, ProducerKind, Provenance  # noqa: E402
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings  # noqa: E402
from reval.domain.snapshot import Snapshot  # noqa: E402
from reval.domain.status import Status  # noqa: E402
from reval.sdk.context import Context  # noqa: E402
from reval.sdk.runner import run_producer  # noqa: E402
from reval.services.project import Project  # noqa: E402

DEFAULT_CACHE = REPO / "bench" / "cache"
DEFAULT_RESULTS = REPO / "bench" / "results"
MEASUREMENTS_ENV = "REVAL_BENCH_MEASUREMENTS"
METHODS: tuple[str, ...] = ("reval", "B0", "B1", "B2", "B3", "B4")
_DONE = ".bench_base_done"
_SKIP_PARTS = {".reval", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "notebooks", ".git"}
_PACKAGES = ("reval", "numpy", "pandas", "scipy", "scikit-learn", "joblib", "pyarrow", "ortools", "pydantic")


# --- configuration --------------------------------------------------------------------------------------
class RevalRunConfig(BaseModel):
    """How ReVal itself is driven in a scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    planner: str | None = None  # None: ``settings.planner`` (ablation A6)
    decisiveness_aware: bool = True
    max_rounds: int = Field(default=3, ge=1)  # plan -> execute rounds until nothing is left to run


class RunConfig(BaseModel):
    """A bench config file. Everything but ``jobs`` is hashed into the results directory name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    project: str = "examples/motor_thermal"  # relative to the repository root
    motor: bool = True  # motor project: bench subset, base variants, Tier B world and truth oracles
    seed: int = 0
    generate: GenerateConfig = GenerateConfig()
    epsilon: dict[str, float]  # pre-registered per quantity (docs/06 section 2)
    methods: tuple[str, ...] = METHODS
    reval: RevalRunConfig = RevalRunConfig()
    settings: ReValSettings = DEFAULT_SETTINGS  # ablation switches A1-A3, A6, A7 (bench/configs/ablations)
    lptn_args: tuple[str, ...] = ("--max-profiles", "12", "--max-nfev", "60")
    jobs: int = Field(default=4, ge=1)


def load_config(path: Path) -> RunConfig:
    return RunConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def config_hash(cfg: RunConfig) -> str:
    return sha256_hex(canonical_json(cfg.model_dump(mode="json", exclude={"jobs"})))[:16]


@dataclasses.dataclass(frozen=True)
class Paths:
    cache: Path
    results: Path  # results/<config hash>
    work: Path  # scenario workspaces

    @property
    def scenarios(self) -> Path:
        return self.results / "scenarios"


# --- producer-result cache adapted to the bench -------------------------------------------------------
class BenchCache(ProducerResultCache):
    """``ProducerResultCache`` with two corrections the bench needs.

    * **Undeclared inputs.** In Tier B ``bench_measure`` reads the undeclared measurement table (the
      "physical world"); its hash is folded into the key (``salt``), otherwise B0 in a T9 scenario would be
      served the pre-degradation measurement.
    * **Provenance.** A hit carries the provenance of the snapshot that first computed it. ReVal classifies
      evidence by diffing its provenance snapshot, and a snapshot missing from the store invalidates it
      (fail closed), so every result is re-bound to the requesting snapshot: exactly the evidence an
      uncached run there produces (same deps, code, subject, settings; seed recomputed).
    """

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.salt: dict[str, str] = {}

    def run(
        self,
        project: Project,
        snapshot: Snapshot,
        producer_id: str,
        subject_id: str,
        settings: ReValSettings = DEFAULT_SETTINGS,
    ) -> tuple[tuple[Evidence, ...], bool]:
        key = cache_key(snapshot, producer_id, subject_id, settings)
        if producer_id in self.salt:
            key = sha256_hex(f"{key}|{self.salt[producer_id]}".encode())
        cached = self.get(key)
        if cached is None:
            evidence = run_producer(
                project.registry, producer_id, snapshot.subjects[subject_id], snapshot, project.root
            )
            self.put(key, evidence)
            self.misses += 1
            hit = False
        else:
            evidence = cached
            self.hits += 1
            hit = True
        return rebind(evidence, project, snapshot), hit


def rebind(evidence: Sequence[Evidence], project: Project, snapshot: Snapshot) -> tuple[Evidence, ...]:
    """The evidence as produced in ``snapshot``: provenance snapshot id and seed replaced, id recomputed."""
    out: list[Evidence] = []
    for e in evidence:
        if e.provenance.snapshot_id == snapshot.id:
            out.append(e)
            continue
        meta = snapshot.producers[e.producer_id]
        seed = Context(project.root, snapshot, meta, DEFAULT_SETTINGS).seed
        prov = Provenance(
            producer_code_hash=e.provenance.producer_code_hash,
            snapshot_id=snapshot.id,
            env=dict(e.provenance.env),
            seed=seed,
        )
        fields = {k: getattr(e, k) for k in Evidence.model_fields if k not in ("id", "provenance")}
        out.append(Evidence.create(**fields, provenance=prov))
    return tuple(sorted(out, key=lambda x: x.id))


# --- base snapshots -----------------------------------------------------------------------------------
def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _skipped(rel: Path) -> bool:
    return bool(_SKIP_PARTS & set(rel.parts)) or rel.parts[:2] == ("data", "raw") or rel.suffix == ".pyc"


def project_hash(src: Path) -> str:
    """Content hash of everything a base snapshot is built from (code, manifest, data, models)."""
    h = hashlib.sha256()
    for f in sorted(p for p in src.rglob("*") if p.is_file() and not _skipped(p.relative_to(src))):
        h.update(f.relative_to(src).as_posix().encode() + b"\0")
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _copy_project(src: Path, dst: Path, *, tier: str, motor: bool) -> None:
    """Copy tracked-style files, hardlink ``data/`` and ``models/`` (Tier B keeps only the drive map)."""
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = f.relative_to(src)
        if _skipped(rel):
            continue
        top = rel.parts[0]
        if top in ("data", "models"):
            if motor and tier == "B" and top == "models" and not rel.name.startswith("drive_map"):
                continue  # retrained on world trajectories
            _link_or_copy(f, dst / rel)
        else:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)


def _rmtree(path: Path) -> None:
    def _writable(func, p, _exc):  # type: ignore[no-untyped-def]
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onexc=_writable)


def base_key(cfg: RunConfig, tier: str, cluster: int, src_hash: str, world_hash: str | None) -> str:
    from bench.scenarios.tier_a import base_variant

    payload = {
        "project": src_hash,
        "tier": tier,
        "cluster": cluster,
        "motor": cfg.motor,
        "subset": cfg.generate.subset.model_dump(mode="json") if cfg.motor else None,
        "variant": dataclasses.asdict(base_variant(cluster)) if cfg.motor else None,
        "world": world_hash if tier == "B" else None,
        "lptn_args": list(cfg.lptn_args),
    }
    return sha256_hex(canonical_json(payload))


def build_base(
    cfg: RunConfig, tier: str, cluster: int, src_hash: str, world: Any, world_hash: str | None, cache: Path
) -> Path:
    """Build (or reuse) the git repository of base snapshot ``(tier, cluster)`` under ``cache/bases``."""
    key = base_key(cfg, tier, cluster, src_hash, world_hash)
    final = cache / "bases" / f"{tier}{cluster:03d}-{key[:12]}"
    if (final / _DONE).exists():
        return final
    tmp = final.with_name(f"{final.name}.tmp{os.getpid()}")
    _rmtree(tmp)
    src = (REPO / cfg.project).resolve()
    _copy_project(src, tmp, tier=tier, motor=cfg.motor)
    if cfg.motor:
        from bench.scenarios.tier_a import apply_base_variant, apply_subset, base_variant, retrain
        from bench.world import PhysicalParams
        from bench.world.base import build_tier_b_base

        apply_subset(tmp, cfg.generate.subset)
        if tier == "B":
            build_tier_b_base(
                tmp,
                world,
                PhysicalParams(),
                0,
                models=(cfg.generate.subset.model_kind,),
                lptn_args=cfg.lptn_args,
                write_lock=False,
            )
        change = apply_base_variant(tmp, base_variant(cluster))
        if change.retrain_targets or change.retrain_lptn:
            retrain(tmp, change, cfg.generate.subset.model_kind)
    (tmp / ".gitignore").write_text("data/\nmodels/\n.reval/\n__pycache__/\n*.tmp\n", encoding="utf-8")
    _git(tmp, "init", "--quiet")
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "--quiet", "-m", f"bench base {tier}{cluster} {key[:12]}")
    (tmp / _DONE).write_text(key, encoding="utf-8")
    if final.exists():  # built concurrently by another run
        _rmtree(tmp)
    else:
        os.replace(tmp, final)
    return final


def _world_hash(world: Any) -> str | None:
    if world is None:
        return None
    p = world.params
    return sha256_hex(canonical_json({"v": dict(p.values), "e": p.model_form_error_w, "s": p.sigma_sensor_k}))


def load_bench_world(cfg: RunConfig, cache: Path) -> Any:
    """The calibrated Tier B world (``cache/world/world.json``; calibrated once if absent)."""
    from bench.world.calibrate import get_world, load_world

    path = cache / "world" / "world.json"
    if path.exists():
        return load_world(path)
    from motor.splits import load_splits

    src = (REPO / cfg.project).resolve()
    df = pd.read_parquet(src / "data" / "processed" / "measures.parquet")
    return get_world(cache / "world", df, load_splits(src / "splits.yaml"))


# --- one scenario -------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class MethodResult:
    runs: tuple[tuple[str, str], ...]
    cost: float
    before: Mapping[str, Status]
    after: Mapping[str, Status]
    predicted: frozenset[str]
    ilp_cost: float | None = None
    greedy_cost: float | None = None


def _statuses(a: Mapping[str, Assessment]) -> dict[str, Status]:
    return {cid: x.status for cid, x in a.items()}


def _values(evidence: Iterable[Evidence]) -> dict[tuple[str, str, str], float]:
    return {
        (e.producer_id, e.subject_id, e.result.quantity): float(e.result.point)
        for e in evidence
        if e.result.point is not None
    }


def _false_alarm_cost(
    snap: Snapshot,
    runs: Iterable[tuple[str, str]],
    before: Mapping[tuple[str, str, str], float],
    after: Mapping[tuple[str, str, str], float],
    eps: Mapping[str, float],
) -> float:
    """Cost of runs whose every comparable value moved by at most epsilon (the oracle's own threshold)."""
    total = 0.0
    for pid, sid in runs:
        keys = [k for k in before.keys() & after.keys() if k[0] == pid and k[1] == sid]
        if keys and all(abs(after[k] - before[k]) <= eps[k[2]] for k in keys):
            total += snap.producers[pid].cost
    return total


def _rerun_predicted(snap: Snapshot, runs: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
    return {(sid, q) for pid, sid in runs for q in snap.producers[pid].quantities}


def _baseline_predicted(
    snap: Snapshot, runs: Iterable[tuple[str, str]], before: Mapping[str, Status], after: Mapping[str, Status]
) -> frozenset[str]:
    touched = _rerun_predicted(snap, runs)
    out = set()
    for cid, c in snap.claims.items():
        q = snap.requirements[c.requirement_id].quantity
        if (c.subject_id, q) in touched or before.get(cid) != after.get(cid):
            out.add(cid)
    return frozenset(out)


def run_reval(
    post: Project, snap_s: Snapshot, snap: Snapshot, cache: BenchCache, rc: RevalRunConfig
) -> MethodResult:
    """ReVal as a user drives it: diff S -> S', then plan/execute rounds, then assess (all stored)."""
    diff = post.diff(snap_s, snap)
    executed: list[tuple[str, str]] = []
    ilp_cost = greedy_cost = None
    for rnd in range(rc.max_rounds):
        plan = post.plan(snap, planner=rc.planner, decisiveness_aware=rc.decisiveness_aware)
        if rnd == 0:
            greedy = post.plan(snap, planner="greedy", decisiveness_aware=rc.decisiveness_aware)
            ilp_cost, greedy_cost = float(plan.total_cost), float(greedy.total_cost)
        todo = [
            (r.producer_id, r.subject_id) for r in plan.runs if (r.producer_id, r.subject_id) not in executed
        ]
        if not todo:
            break
        for pid, sid in todo:
            evidence, _ = cache.run(post, snap, pid, sid)
            for e in evidence:
                post.store.put_evidence(e)
            executed.append((pid, sid))
    after = post.assess(snap)
    return MethodResult(
        tuple(executed),
        float(sum(snap.producers[p].cost for p, _ in executed)),
        _statuses(diff.before),
        _statuses(after),
        frozenset(diff.affected_claims),
        ilp_cost,
        greedy_cost,
    )


def _tier_b_truth(root: Path, snap: Snapshot, sc: Scenario, world: Any) -> dict[str, bool | None]:
    """World noise-free peaks under the S' plant: recorded segments from the full-profile trajectory (the
    same one the measurement table is cut from), parametric cycles from a cold start through the drive map."""
    import joblib
    from motor import cycles

    from bench.oracles.truth import NODE_OF, truth_from_peaks
    from bench.scenarios.tier_b import world_physical_params
    from bench.world.base import world_trajectories

    phys = world_physical_params(sc)
    subjects = snap.subjects
    claim_subjects = {c.subject_id for c in snap.claims.values()}
    recorded = {s for s in claim_subjects if subjects[s].generator == "motor.cycles:recorded"}
    blocks = {s for s in claim_subjects if subjects[s].generator == "motor.cycles:blocks"}
    peaks: dict[str, dict[str, float]] = {}
    if recorded:
        df = pd.read_parquet(root / "data" / "processed" / "measures.parquet")
        pids = {int(subjects[s].params["profile_id"]) for s in recorded}
        traj = world_trajectories(world, df[df["profile_id"].isin(pids)], phys)
        for sid in sorted(recorded):
            p = subjects[sid].params
            seg = cycles._segment(int(p["profile_id"]), float(p["start_s"]), float(p["duration_s"]), traj)
            peaks[sid] = {q: float(seg[node].max()) for q, node in NODE_OF.items()}
    if blocks:
        drive_map = joblib.load(root / "models" / "drive_map.joblib")
        for sid in sorted(blocks):
            cyc = cycles.blocks(subjects[sid].params)
            inputs = drive_map.to_inputs(
                cyc["torque"].to_numpy(),
                cyc["motor_speed"].to_numpy(),
                cyc["coolant"].to_numpy(),
                cyc["ambient"].to_numpy(),
            )
            sim = world.simulate(inputs.reset_index(drop=True), phys)
            peaks[sid] = {q: float(sim[node].max()) for q, node in NODE_OF.items()}
    return truth_from_peaks(snap.claims, snap.requirements, peaks)


def _truth(root: Path, snap: Snapshot, sc: Scenario, cfg: RunConfig, world: Any) -> dict[str, bool | None]:
    if not cfg.motor:
        return dict.fromkeys(snap.claims)
    if sc.tier == "B":
        return _tier_b_truth(root, snap, sc, world)
    from bench.oracles.truth import truth_tier_a

    splits = yaml.safe_load((root / "splits.yaml").read_text(encoding="utf-8"))
    df = pd.read_parquet(root / "data" / "processed" / "measures.parquet")
    return truth_tier_a(snap, df, [int(p) for p in splits["test"]])


def _write_table(root: Path, sc: Scenario, world: Any) -> str:
    """Tier B S table: the base plant measured with this scenario's common random numbers."""
    from bench.scenarios.tier_a import SUBJECTS, load_yaml
    from bench.world import PhysicalParams
    from bench.world.base import MEASUREMENTS_FILE, bench_measurements

    df = pd.read_parquet(root / "data" / "processed" / "measures.parquet")  # already the world plant
    table = bench_measurements(world, df, load_yaml(root / SUBJECTS), PhysicalParams(), sc.id)
    (root / MEASUREMENTS_FILE).write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    return str(root / MEASUREMENTS_FILE)


def _salt(root: Path, tier: str, motor: bool) -> dict[str, str]:
    from bench.world.base import MEASUREMENTS_FILE

    if not (motor and tier == "B"):
        return {}
    return {"bench_measure": hashlib.sha256((root / MEASUREMENTS_FILE).read_bytes()).hexdigest()}


def _close(project: Project) -> None:
    engine = getattr(project.store, "_engine", None)
    if engine is not None:
        engine.dispose()


def scenario_records(
    sc: Scenario, cfg: RunConfig, ws: Workspace, cache: BenchCache, world: Any, timings: dict[str, float]
) -> list[ClaimRecord]:
    from bench.scenarios.tier_a import apply_scenario

    root = ws.root
    # ProducerRegistry.load_modules only inserts the project root if it is not on sys.path yet, so a root
    # left over from an earlier scenario (this process, or inherited from the parent) could shadow this
    # clone's producer package. Drop every workspace path and stale finder before opening the project.
    work = str(ws.clone.parent.resolve())
    sys.path[:] = [p for p in sys.path if not p.startswith(work)]
    for key in [k for k in sys.path_importer_cache if k.startswith(work)]:
        del sys.path_importer_cache[key]
    importlib.invalidate_caches()
    t = time.perf_counter()
    os.environ.pop(MEASUREMENTS_ENV, None)
    if cfg.motor and sc.tier == "B":
        from bench.scenarios.tier_b import use_world

        use_world(world)
        os.environ[MEASUREMENTS_ENV] = _write_table(root, sc, world)

    # --- S: the validated state before the change -----------------------------------------------------
    pre_project = Project.open(root)
    snap_s = pre_project.snapshot(write_lock=True)
    ws.commit(f"S {sc.id}", lock=False)
    cache.salt = _salt(root, sc.tier, cfg.motor)
    b0_s = run_b0(pre_project, snap_s, cache)
    for e in b0_s.evidence:
        pre_project.store.put_evidence(e)
    pre_project.assess(snap_s)
    pre = PreState.capture(root, snap_s, b0_s.evidence)
    _close(pre_project)
    timings["S"] = time.perf_counter() - t

    # --- the change -----------------------------------------------------------------------------------
    t = time.perf_counter()
    apply_scenario(ws, sc)
    timings["apply"] = time.perf_counter() - t

    t = time.perf_counter()
    post = Project.open(root, settings=cfg.settings)
    snap = post.snapshot(write_lock=True)
    ws.commit(f"S' {sc.id}", lock=False)
    cache.salt = _salt(root, sc.tier, cfg.motor)
    b0: B0Result = run_b0(post, snap, cache)
    labels = truly_affected(b0_s.outcomes, b0.outcomes, cfg.epsilon)
    timings["b0"] = time.perf_counter() - t

    results: dict[str, MethodResult] = {}
    before_b0 = _statuses(b0_s.assessments)
    after_b0 = _statuses(b0.assessments)
    t = time.perf_counter()
    if "reval" in cfg.methods:
        results["reval"] = run_reval(post, snap_s, snap, cache, cfg.reval)
    timings["reval"] = time.perf_counter() - t
    t = time.perf_counter()
    results["B0"] = MethodResult(b0.runs, b0.cost, before_b0, after_b0, frozenset(snap.claims))
    post_state = PostState(post, snap)
    baselines: dict[str, Any] = {
        "B1": FileLevel(),
        "B2": OodOnly(domain_check_via_producer(cache)),
        "B3": NaiveTrust(),
    }
    if "B4" in cfg.methods:
        if "reval" not in results:
            raise ValueError("B4 needs ReVal's cost as its budget: keep 'reval' in methods")
        baselines["B4"] = RandomBudget(sc.id, results["reval"].cost)
    for mid, baseline in baselines.items():
        if mid not in cfg.methods:
            continue
        res = execute_baseline(baseline, pre, post_state, cache)
        after = _statuses(res.assessments)
        results[mid] = MethodResult(
            res.runs, res.cost, before_b0, after, _baseline_predicted(snap, res.runs, before_b0, after)
        )
    timings["baselines"] = time.perf_counter() - t

    t = time.perf_counter()
    truth = _truth(root, snap, sc, cfg, world)
    timings["truth"] = time.perf_counter() - t
    _close(post)

    v_before, v_after = _values(b0_s.evidence), _values(b0.evidence)
    b0_accepted = {cid for cid, s in after_b0.items() if s is Status.SUPPORTED}
    records: list[ClaimRecord] = []
    for mid in cfg.methods:
        r = results[mid]
        fa = _false_alarm_cost(snap, r.runs, v_before, v_after, cfg.epsilon)
        n_bench = sum(snap.producers[p].kind is ProducerKind.MEASUREMENT for p, _ in r.runs)
        for cid in sorted(snap.claims):
            before = r.before.get(cid)
            after = r.after[cid]
            records.append(
                ClaimRecord(
                    scenario_id=sc.id,
                    change_type=sc.change_type,
                    tier=sc.tier,
                    base_snapshot=f"{sc.tier}{sc.base_snapshot:03d}",
                    method=mid,
                    claim_id=cid,
                    status_before=before.value if before is not None else "absent",
                    status_after=after.value,
                    accepted=after is Status.SUPPORTED,
                    b0_accepted=cid in b0_accepted,
                    truly_affected=labels[cid],
                    predicted_affected=cid in r.predicted,
                    truth_violated=truth.get(cid),
                    cost=r.cost,
                    b0_cost=b0.cost,
                    false_alarm_cost=fa,
                    n_bench_runs=int(n_bench),
                    ilp_cost=r.ilp_cost,
                    greedy_cost=r.greedy_cost,
                )
            )
    return records


def _atomic_parquet(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def run_scenario(
    sc: Scenario, cfg: RunConfig, base: Path, paths: Paths, world: Any, threads: int
) -> dict[str, Any]:
    """Worker entry point: run one scenario in its own workspace and write its rows. Never raises."""
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = str(threads)
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    cache = BenchCache(paths.cache / "producers")
    info: dict[str, Any] = {"scenario_id": sc.id, "tier": sc.tier, "change_type": sc.change_type}
    ws: Workspace | None = None
    try:
        _rmtree(paths.work / sc.id)  # left over from an interrupted run
        ws = Workspace.create(base, paths.work, base, scenario_id=sc.id)
        records = scenario_records(sc, cfg, ws, cache, world, timings)
        _atomic_parquet(to_frame(records), paths.scenarios / f"{sc.id}.parquet")
        (paths.results / "failures" / f"{sc.id}.txt").unlink(missing_ok=True)
        info["ok"] = True
        info["rows"] = len(records)
    except Exception:
        info["ok"] = False
        info["error"] = traceback.format_exc()
        fail = paths.results / "failures" / f"{sc.id}.txt"
        fail.parent.mkdir(parents=True, exist_ok=True)
        fail.write_text(info["error"], encoding="utf-8")
    finally:
        gc.collect()
        if ws is not None:
            # A Windows file handle may still be open; the next run removes a leftover workspace.
            with contextlib.suppress(OSError):
                ws.cleanup()
    info["wall_s"] = round(time.perf_counter() - t0, 2)
    info["phases_s"] = {k: round(v, 2) for k, v in timings.items()}
    info["cache_hits"], info["cache_misses"] = cache.hits, cache.misses
    return info


# --- whole run ----------------------------------------------------------------------------------------
def _log(paths: Paths, msg: str) -> None:
    line = f"[bench] {msg}"
    print(line, flush=True)
    with (paths.results / "run.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for name in _PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return out


def _git_rev() -> str:
    try:
        rev = _git(REPO, "rev-parse", "HEAD")
        dirty = _git(REPO, "status", "--porcelain", "--", "bench", "src", "examples/motor_thermal")
        return rev + ("+dirty" if dirty else "")
    except RuntimeError:
        return "unknown"


def combine(paths: Paths, scenarios: Sequence[Scenario]) -> tuple[pd.DataFrame, str]:
    """Concatenate completed scenarios in a fixed order; hash a canonical CSV rendering of the rows."""
    frames = [
        pd.read_parquet(paths.scenarios / f"{s.id}.parquet")
        for s in sorted(scenarios, key=lambda s: s.id)
        if (paths.scenarios / f"{s.id}.parquet").exists()
    ]
    df = pd.concat(frames, ignore_index=True) if frames else to_frame([])
    df = df.sort_values(["scenario_id", "method", "claim_id"], kind="stable").reset_index(drop=True)
    _atomic_parquet(df, paths.results / "rows.parquet")
    digest = hashlib.sha256(df.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()
    (paths.results / "rows.sha256").write_text(digest + "\n", encoding="utf-8")
    return df, digest


def summarize(df: pd.DataFrame, methods: Sequence[str]) -> pd.DataFrame:
    """Per tier and method: impact recall/precision, UAR_truth, decision coverage, cost vs B0 and B1."""
    rows = []
    for tier in sorted(df["tier"].unique()):
        d = df[df["tier"] == tier]
        for m in methods:
            if m not in set(d["method"]):
                continue
            lr = M.log_cost_ratio(m, "B1")(d) if "B1" in set(d["method"]) else float("nan")
            rows.append(
                {
                    "tier": tier,
                    "method": m,
                    "scenarios": d.loc[d["method"] == m, "scenario_id"].nunique(),
                    "impact_recall": M.impact_recall(m)(d),
                    "impact_precision": M.impact_precision(m)(d),
                    "uar_truth": M.uar_truth(m)(d),
                    "uar_evidence": M.uar_evidence(m)(d),
                    "decision_coverage": M.decision_coverage(m)(d),
                    "cost_ratio_vs_B0": M.cost_ratio(m)(d),
                    "mean_log_cost_ratio_vs_B1": lr,
                    "mean_cost": M.mean_cost(m)(d),
                }
            )
    return pd.DataFrame(rows)


def run_bench(
    cfg: RunConfig,
    *,
    jobs: int | None = None,
    cache_dir: Path = DEFAULT_CACHE,
    results_root: Path = DEFAULT_RESULTS,
    work_dir: Path | None = None,
    only: str | None = None,
    limit: int | None = None,
) -> Path:
    """Run (or resume) every scenario of ``cfg``; return the results directory."""
    from joblib import Parallel, delayed

    jobs = jobs or cfg.jobs
    h = config_hash(cfg)
    cache_dir = Path(cache_dir).resolve()
    paths = Paths(
        cache_dir, Path(results_root).resolve() / h, Path(work_dir or cache_dir / "work" / h).resolve()
    )
    paths.scenarios.mkdir(parents=True, exist_ok=True)
    paths.work.mkdir(parents=True, exist_ok=True)
    (paths.results / "config.json").write_text(
        json.dumps(cfg.model_dump(mode="json", exclude={"jobs"}), indent=2, sort_keys=True), encoding="utf-8"
    )
    t_start = time.perf_counter()

    scenarios = generate(cfg.generate, cfg.seed)
    if only:
        scenarios = [s for s in scenarios if only in s.id]
    if limit is not None:
        scenarios = scenarios[:limit]
    todo = [s for s in scenarios if not (paths.scenarios / f"{s.id}.parquet").exists()]
    _log(paths, f"config {cfg.name} hash {h}: {len(scenarios)} scenarios, {len(todo)} to run, jobs={jobs}")

    src_hash = project_hash((REPO / cfg.project).resolve())
    need_world = cfg.motor and any(s.tier == "B" for s in todo)
    world = load_bench_world(cfg, cache_dir) if need_world else None
    w_hash = _world_hash(world)
    clusters = sorted({(s.tier, s.base_snapshot) for s in todo})
    t = time.perf_counter()
    built = Parallel(n_jobs=max(1, min(jobs, len(clusters) or 1)), backend="loky")(
        delayed(build_base)(cfg, tier, c, src_hash, world, w_hash, cache_dir) for tier, c in clusters
    )
    bases = dict(zip(clusters, built, strict=True))
    _log(paths, f"{len(clusters)} base snapshots ready in {time.perf_counter() - t:.0f} s")

    threads = max(1, (os.cpu_count() or 4) // jobs)
    n_ok = n_fail = 0
    with (paths.results / "timings.jsonl").open("a", encoding="utf-8") as tl:
        for info in Parallel(n_jobs=jobs, backend="loky", return_as="generator_unordered")(
            delayed(run_scenario)(s, cfg, bases[(s.tier, s.base_snapshot)], paths, world, threads)
            for s in todo
        ):
            tl.write(json.dumps({k: v for k, v in info.items() if k != "error"}, sort_keys=True) + "\n")
            tl.flush()
            if info["ok"]:
                n_ok += 1
                _log(paths, f"done {info['scenario_id']} in {info['wall_s']:.0f} s {info['phases_s']}")
            else:
                n_fail += 1
                last = info["error"].strip().splitlines()[-1]
                _log(paths, f"FAILED {info['scenario_id']} after {info['wall_s']:.0f} s: {last}")

    df, digest = combine(paths, scenarios)
    completed = sorted(df["scenario_id"].unique()) if len(df) else []
    manifest = {
        "config_name": cfg.name,
        "config_hash": h,
        "git_rev": _git_rev(),
        "project_hash": src_hash,
        "world_hash": w_hash,
        "packages": _versions(),
        "seed": cfg.seed,
        "scenario_seeds": {s.id: s.seed for s in scenarios},
        "epsilon": cfg.epsilon,
        "n_scenarios": len(scenarios),
        "n_completed": len(completed),
        "failed": sorted(set(s.id for s in scenarios) - set(completed)),
        "rows": len(df),
        "rows_sha256": digest,
    }
    (paths.results / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    _log(
        paths,
        f"finished in {time.perf_counter() - t_start:.0f} s: this run {n_ok} ok, {n_fail} failed; "
        f"{len(completed)}/{len(scenarios)} complete; rows.sha256 {digest[:16]}",
    )
    return paths.results


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.run", description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--only", default=None, help="run only scenarios whose id contains this string")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N scenarios (debugging)")
    ap.add_argument("--summary", action="store_true", help="print the metrics table at the end")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = run_bench(
        cfg,
        jobs=args.jobs,
        cache_dir=args.cache_dir,
        results_root=args.results_dir,
        only=args.only,
        limit=args.limit,
    )
    if args.summary:
        df = pd.read_parquet(out / "rows.parquet")
        if len(df):
            table = summarize(df, cfg.methods)
            table.to_csv(out / "summary.csv", index=False)
            with pd.option_context("display.width", 200, "display.max_columns", 20, "display.precision", 3):
                print(f"\n{cfg.name.upper()} metrics (not results; descriptive only)\n{table}")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    return 0 if not manifest["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
