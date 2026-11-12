"""Tier A appliers (T1-T6, T10, T11) and the bench-subset transform (P5-03, P5-04).

Tier A truth is real measured data only. Appliers edit a *workspace copy* of the motor project (never the
real one) and describe, in an ``AppliedChange``, which models an engineer would refit; ``apply_scenario``
then refits them with the project's own scripts (hgb only: the bench project has one ML model kind).
Edits that touch a file the workspace may share by hardlink with the data cache replace the file
(write + ``os.replace``) instead of rewriting it in place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from bench.scenarios.model import AppliedChange, GenerateConfig, Scenario, SubsetConfig, register

MEASURES = "data/processed/measures.parquet"
SPLITS = "splits.yaml"
MANIFEST = "reval.yaml"
SUBJECTS = "subjects.yaml"
HYPERPARAMS_FILE = "bench_hyperparams.json"  # engineer's record of non-default hgb settings (undeclared)
TARGETS: tuple[str, ...] = ("pm", "stator_winding")
PREFIX = {"pm": "tpm", "stator_winding": "tsw"}
LPTN_ARGS: tuple[str, ...] = ("--max-profiles", "12", "--max-nfev", "60")  # same as the Tier B base build
_OUTSIDE_EVERY = 5  # motor.cycles._OUTSIDE_EVERY: every 5th parametric cycle is outside the train envelope


def crn_seed(*parts: object) -> int:
    """Deterministic 32-bit seed from hashable parts (same recipe as the common random numbers)."""
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


# --- small file helpers ---------------------------------------------------------------------------------
def _root(ws: Any) -> Path:
    return Path(ws) if isinstance(ws, (str, Path)) else Path(ws.root)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, obj: Any) -> None:
    text = yaml.safe_dump(obj, sort_keys=False, default_flow_style=None, width=140, allow_unicode=True)
    path.write_bytes(text.encode("utf-8"))


def replace_parquet(path: Path, df: pd.DataFrame) -> None:
    """Write-then-replace: the file may be a hardlink into the shared data cache."""
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def edit_manifest(root: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    manifest = load_yaml(root / MANIFEST)
    fn(manifest)
    dump_yaml(root / MANIFEST, manifest)


# --- the bench subset (a transform of the workspace copy, driven by the bench config) -------------------
def _length_class(duration_s: float) -> str:
    from motor.cycles import length_class

    return str(length_class(duration_s))


def _spread(items: Sequence[str], k: int) -> list[str]:
    """``k`` evenly spaced items of a sorted list (all of them when fewer are available)."""
    if k >= len(items):
        return list(items)
    return [items[i] for i in sorted({round(x) for x in np.linspace(0, len(items) - 1, k)})]


def _split_evenly(total: int, parts: int) -> list[int]:
    return [total // parts + (1 if i < total % parts else 0) for i in range(parts)]


def select_subjects(subjects: dict[str, Any], subset: SubsetConfig) -> dict[str, list[str]]:
    """Pick the subset: ``recorded``, ``parametric`` (with ``ood`` flagged) and ``current_limit`` ids.

    Recorded cycles are test-profile segments only; reserve profiles are never subjects.
    """
    classes = ("short", "medium", "long")
    recorded: dict[str, list[str]] = {c: [] for c in classes}
    param_in: dict[str, list[str]] = {c: [] for c in classes}
    param_out: dict[str, list[str]] = {c: [] for c in classes}
    for sid in sorted(subjects):
        spec = subjects[sid]
        gen = spec.get("generator", "")
        if gen.endswith(":recorded"):
            recorded[_length_class(float(spec["params"]["duration_s"]))].append(sid)
        elif gen.endswith(":blocks"):
            cls = _length_class(float(sum(b[2] for b in spec["params"]["blocks"])))
            idx = int(re.sub(r"\D", "", sid)) - 1
            (param_out if idx % _OUTSIDE_EVERY == _OUTSIDE_EVERY - 1 else param_in)[cls].append(sid)
    rec_n = _split_evenly(subset.n_recorded, 3)
    par_n = _split_evenly(subset.n_parametric, 3)
    ood_n = _split_evenly(subset.parametric_out_of_domain, 3)
    picked_rec: list[str] = []
    picked_in: list[str] = []
    picked_out: list[str] = []
    for c, nr, n_par, no in zip(classes, rec_n, par_n, ood_n, strict=True):
        if len(recorded[c]) < nr or len(param_out[c]) < no or len(param_in[c]) < n_par - no:
            raise ValueError(f"not enough {c!r} subjects for the requested subset")
        picked_rec += _spread(recorded[c], nr)
        picked_out += _spread(param_out[c], no)
        picked_in += _spread(param_in[c], n_par - no)
    current = _spread(sorted(picked_in), subset.n_current_limit)
    return {
        "recorded": sorted(picked_rec),
        "parametric": sorted(picked_in + picked_out),
        "ood": sorted(picked_out),
        "current_limit": current,
    }


def apply_subset(root: Path, subset: SubsetConfig) -> dict[str, list[str]]:
    """Rewrite ``reval.yaml`` / ``subjects.yaml`` of a workspace copy to the bench subset.

    Keeps the selected subjects and the shaft subject, regenerates the claims (PM and SW per cycle, the
    shaft claim, ``n_current_limit`` current-limit claims), drops the artifacts of the other ML kinds and
    restricts ``motor.producers`` to ``subset.model_kind``. Raises (fail closed) if a patch target is missing.
    """
    subjects = load_yaml(root / SUBJECTS)
    chosen = select_subjects(subjects, subset)
    keep = set(chosen["recorded"]) | set(chosen["parametric"])
    shaft_ids = [s for s, v in subjects.items() if v.get("kind") == "design"]
    dump_yaml(root / SUBJECTS, {s: v for s, v in subjects.items() if s in keep or s in shaft_ids})

    def short(sid: str) -> str:
        return sid.removeprefix("DC-")

    def edit(m: dict[str, Any]) -> None:
        claims: list[dict[str, str]] = []
        for sid in chosen["recorded"] + chosen["parametric"]:
            claims.append({"id": f"C-{short(sid)}-PM", "requirement": "R-PM-MAX", "subject": sid})
            claims.append({"id": f"C-{short(sid)}-SW", "requirement": "R-SW-MAX", "subject": sid})
        claims += [
            {"id": f"C-{short(s)}-IS", "requirement": "R-IS-MAX", "subject": s}
            for s in chosen["current_limit"]
        ]
        claims += [c for c in m["claims"] if c["subject"] in shaft_ids]
        m["claims"] = claims
        m["artifacts"] = {
            a: v
            for a, v in m["artifacts"].items()
            if not (re.search(r"_(ridge|hgb|mlp)$", a) and not a.endswith(f"_{subset.model_kind}"))
        }

    edit_manifest(root, edit)
    prod = root / "motor" / "producers.py"
    if prod.exists():
        src = prod.read_bytes().decode("utf-8")
        old = '_ML_KINDS = ("ridge", "hgb", "mlp")'
        if old not in src:
            raise ValueError("motor/producers.py: _ML_KINDS definition not found")
        prod.write_bytes(src.replace(old, f'_ML_KINDS = ("{subset.model_kind}",)').encode("utf-8"))
    return chosen


# --- base-snapshot variants (different limits, reserve in train, hyperparameters) -----------------------
@dataclass(frozen=True)
class BaseVariant:
    """How base snapshot ``cluster_id`` differs from the unmodified project (cluster 0 is neutral)."""

    cluster_id: int
    pm_limit_delta_k: float
    sw_limit_delta_k: float
    reserve_to_train: tuple[int, ...]  # indices into splits['reserve']
    hgb: dict[str, Any] | None

    @property
    def neutral(self) -> bool:
        return not (self.pm_limit_delta_k or self.sw_limit_delta_k or self.reserve_to_train or self.hgb)


def base_variant(cluster_id: int) -> BaseVariant:
    """Deterministic variant of base snapshot ``cluster_id`` (limit levels, reserve split, model set)."""
    if cluster_id == 0:
        return BaseVariant(0, 0.0, 0.0, (), None)
    rng = np.random.default_rng(crn_seed("base", cluster_id))
    pm = float(rng.choice([-5.0, 0.0, 5.0]))
    sw = float(rng.choice([-5.0, 0.0, 5.0]))
    reserve = (int(rng.integers(0, 3)),) if rng.random() < 0.4 else ()
    hgb = (
        {"learning_rate": float(rng.choice([0.06, 0.15])), "max_iter": int(rng.choice([80, 150]))}
        if rng.random() < 0.5
        else None
    )
    return BaseVariant(cluster_id, pm, sw, reserve, hgb)


def apply_base_variant(ws: Any, variant: BaseVariant) -> AppliedChange:
    """Edit the workspace to the variant; the caller refits (``retrain_*`` fields say what)."""
    root = _root(ws)
    out = AppliedChange(notes={"base_variant": variant.cluster_id})
    if variant.pm_limit_delta_k or variant.sw_limit_delta_k:
        deltas = {"R-PM-MAX": variant.pm_limit_delta_k, "R-SW-MAX": variant.sw_limit_delta_k}

        def edit(m: dict[str, Any]) -> None:
            for req, d in deltas.items():
                m["requirements"][req]["limit"] = m["requirements"][req]["limit"] + d

        edit_manifest(root, edit)
        out.declared.append(MANIFEST)
    if variant.reserve_to_train:
        splits = load_yaml(root / SPLITS)
        moved = [splits["reserve"][i] for i in variant.reserve_to_train]
        splits["reserve"] = [p for p in splits["reserve"] if p not in moved]
        splits["train"] = sorted([*splits["train"], *moved])
        dump_yaml(root / SPLITS, splits)
        out.declared.append(SPLITS)
    if variant.reserve_to_train or variant.hgb:
        out.retrain_targets = {t: variant.hgb for t in TARGETS}
        out.retrain_lptn = bool(variant.reserve_to_train)
    return out


# --- retraining (the engineer's scripts) ---------------------------------------------------------------
_TRAIN_HP = r"""
import hashlib, json, sys, time
from pathlib import Path
root = Path.cwd()
sys.path[:0] = [str(root), str(root / "scripts")]
import pandas as pd
import train as t
from motor.models import TrajectoryModel, evaluate, save
from motor.splits import load_splits, split_frame
target, hp = sys.argv[1], json.loads(sys.argv[2])
df = pd.read_parquet(t.ROOT / "data" / "processed" / "measures.parquet")
splits_path = t.ROOT / "splits.yaml"
splits = load_splits(splits_path)
train, test = split_frame(df, splits, "train"), split_frame(df, splits, "test")
model = TrajectoryModel("hgb", targets=(target,), **hp)
t0 = time.time()
model.fit(train)
fit_s = time.time() - t0
digest = hashlib.sha256(splits_path.read_bytes()).hexdigest()
meta = {"split_hash": digest, "train_profiles": list(splits.train),
        "train_rows": len(train), "fit_seconds": round(fit_s, 1), "hyperparams": hp,
        "metrics_test": evaluate(model, test, t.WINDOW_ROWS), "window_rows": t.WINDOW_ROWS}
save(model, t.ROOT / "models" / f"{t.PREFIX[target]}_hgb.joblib", meta=meta)
"""


def _run(root: Path, args: Sequence[str]) -> None:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)[:120]} failed:\n{proc.stdout[-600:]}\n{proc.stderr[-1500:]}")


def _unlink_outputs(root: Path, patterns: Sequence[str]) -> None:
    """Remove outputs first: they may be hardlinks into the shared cache and must not be written in place."""
    for pat in patterns:
        for f in (root / "models").glob(pat):
            f.unlink()


def retrain(root: Path, change: AppliedChange, kind: str = "hgb") -> None:
    """Refit what ``change`` asks for: per-target model + conformal/AD artifact, and the LPTN."""
    outs = [f"{PREFIX[t]}_{kind}.*" for t in change.retrain_targets]
    outs += [f"uq_{PREFIX[t]}_{kind}.*" for t in change.retrain_targets]
    if change.retrain_lptn:
        outs.append("lptn_report.json")
    _unlink_outputs(root, outs)

    def fit_target(target: str) -> None:
        hp = change.retrain_targets[target]
        if hp:
            _run(root, ["-c", _TRAIN_HP, target, json.dumps(hp, sort_keys=True)])
        else:
            _run(root, ["scripts/train.py", "--model", kind, "--target", target])
        _run(root, ["scripts/calibrate.py", "--model-artifact", f"{PREFIX[target]}_{kind}"])

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fit_target, t) for t in change.retrain_targets]
        if change.retrain_lptn:
            futures.append(pool.submit(_run, root, ["scripts/calibrate_lptn.py", *LPTN_ARGS]))
        for f in futures:
            f.result()


def apply_scenario(ws: Any, scenario: Scenario, *, retrain_models: bool = True) -> AppliedChange:
    """Apply a scenario's change to the workspace (does not commit) and refit what it requires."""
    from bench.scenarios import tier_b  # noqa: F401  (registers the Tier B appliers)
    from bench.scenarios.model import APPLIERS

    change = APPLIERS[scenario.apply](ws, scenario)
    if retrain_models and (change.retrain_targets or change.retrain_lptn):
        retrain(_root(ws), change)
    return change


# --- T1 / T2: data append -------------------------------------------------------------------------------
_SHIFT_COLUMNS = ("coolant", "pm", "stator_yoke", "stator_tooth", "stator_winding")


def make_profile(src: pd.DataFrame, new_id: int, fraction: float, shift_k: float = 0.0) -> pd.DataFrame:
    """A new profile cut from ``src``: its first ``fraction`` of rows, relabelled, optionally warmer.

    ``shift_k`` raises the coolant and every temperature column by the same K (a hotter operating
    environment), which widens the coolant envelope.
    """
    ordered = src.sort_values("t")
    out = ordered.iloc[: max(2, int(len(ordered) * fraction))].copy()
    out["profile_id"] = new_id
    for c in _SHIFT_COLUMNS:
        if shift_k and c in out.columns:
            out[c] = out[c] + shift_k
    return out


def _append_profile(root: Path, reserve_index: int, fraction: float, shift_k: float) -> dict[str, Any]:
    splits = load_yaml(root / SPLITS)
    src_id = int(splits["reserve"][reserve_index % len(splits["reserve"])])
    df = pd.read_parquet(root / MEASURES)
    new_id = int(df["profile_id"].max()) + 1
    new = make_profile(df[df["profile_id"] == src_id], new_id, fraction, shift_k)
    replace_parquet(root / MEASURES, pd.concat([df, new], ignore_index=True))
    splits["train"] = [*splits["train"], new_id]
    dump_yaml(root / SPLITS, splits)
    return {"source_profile": src_id, "new_profile": new_id, "rows": len(new)}


def _sample_t1(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {"reserve_index": int(rng.integers(0, 3)), "fraction": round(float(rng.uniform(0.5, 1.0)), 2)}


def _sample_t2(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {**_sample_t1(rng, cfg), "shift_k": round(float(rng.uniform(8.0, 20.0)), 1)}


@register("T1", "A", "t1_data_append", _sample_t1)
def apply_t1(ws: Any, sc: Scenario) -> AppliedChange:
    """Append an in-envelope profile (a cut of a reserve profile) to the data and to ``train``."""
    p = sc.params
    info = _append_profile(_root(ws), p["reserve_index"], p["fraction"], 0.0)
    return AppliedChange([MEASURES, SPLITS], info, {t: None for t in TARGETS}, retrain_lptn=True)


@register("T2", "A", "t2_envelope_expand", _sample_t2)
def apply_t2(ws: Any, sc: Scenario) -> AppliedChange:
    """Append a profile with higher coolant temperature (expands the coolant envelope)."""
    p = sc.params
    info = _append_profile(_root(ws), p["reserve_index"], p["fraction"], p["shift_k"])
    return AppliedChange([MEASURES, SPLITS], info, {t: None for t in TARGETS}, retrain_lptn=True)


# --- T3: sensor correction ------------------------------------------------------------------------------
def _sample_t3(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    sign = 1.0 if rng.random() < 0.5 else -1.0
    offset = round(sign * float(rng.uniform(0.5, 3.0)), 2)
    return {"profile_index": int(rng.integers(0, 1000)), "offset_k": offset}


def correct_pm(df: pd.DataFrame, profile_id: int, offset_k: float) -> pd.DataFrame:
    """Copy of ``df`` with ``offset_k`` added to the ``pm`` column of one profile (K)."""
    out = df.copy()
    out.loc[out["profile_id"] == profile_id, "pm"] += offset_k
    return out


@register("T3", "A", "t3_sensor_correction", _sample_t3)
def apply_t3(ws: Any, sc: Scenario) -> AppliedChange:
    """Sensor-offset correction of one train/calib/test profile's ``pm`` column; truth follows S' data."""
    root = _root(ws)
    splits = load_yaml(root / SPLITS)
    eligible = sorted(int(p) for n in ("train", "calib", "test") for p in splits[n])
    pid = eligible[sc.params["profile_index"] % len(eligible)]
    df = pd.read_parquet(root / MEASURES)
    replace_parquet(root / MEASURES, correct_pm(df, pid, float(sc.params["offset_k"])))
    return AppliedChange(
        [MEASURES],
        {"profile": pid, "split": next(n for n in ("train", "calib", "test") if pid in splits[n])},
        {t: None for t in TARGETS},
        retrain_lptn=True,
    )


# --- T4: model change -----------------------------------------------------------------------------------
def _sample_t4(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    target = str(rng.choice(TARGETS))
    if rng.random() < 0.5:
        hp = {"learning_rate": float(rng.choice([0.05, 0.08, 0.2])), "max_iter": int(rng.choice([60, 150]))}
        return {"flavor": "hyperparameter", "target": target, "hp": hp}
    hp = {"max_leaf_nodes": int(rng.choice([7, 63])), "max_depth": int(rng.choice([4, 10])), "max_iter": 100}
    return {"flavor": "swap", "target": target, "hp": hp}


@register("T4", "A", "t4_model_change", _sample_t4)
def apply_t4(ws: Any, sc: Scenario) -> AppliedChange:
    """Refit one target's hgb model with different hyperparameters (M1 -> M2); data and LPTN unchanged."""
    root = _root(ws)
    target, hp = sc.params["target"], dict(sc.params["hp"])
    path = root / HYPERPARAMS_FILE
    record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    record[target] = hp
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return AppliedChange([], {"target": target, "hp": hp}, {target: hp})


# --- T5: requirement limit ------------------------------------------------------------------------------
def _sample_t5(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    sign = 1.0 if rng.random() < 0.5 else -1.0
    return {
        "requirement": str(rng.choice(cfg.t5_requirements)),
        "delta_k": round(sign * float(rng.uniform(2.0, 10.0)), 1),
    }


@register("T5", "A", "t5_limit_change", _sample_t5)
def apply_t5(ws: Any, sc: Scenario) -> AppliedChange:
    """Move a requirement limit by ``delta_k`` (K added to a degC limit); no file but the manifest changes."""
    req, delta = sc.params["requirement"], float(sc.params["delta_k"])
    seen: dict[str, float] = {}

    def edit(m: dict[str, Any]) -> None:
        r = m["requirements"][req]
        seen["old"] = float(r["limit"])
        r["limit"] = round(seen["old"] + delta, 3)
        seen["new"] = r["limit"]

    edit_manifest(_root(ws), edit)
    return AppliedChange([MANIFEST], {"requirement": req, **seen})


# --- T6: assumption range -------------------------------------------------------------------------------
def _sample_t6(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {
        "assumption": str(rng.choice(cfg.t6_assumptions)),
        "side": str(rng.choice(["upper", "lower"])),
        "tighten": bool(rng.random() < 0.6),
        "frac": round(float(rng.uniform(0.1, 0.4)), 2),
    }


def change_bounds(bounds: Sequence[float], side: str, tighten: bool, frac: float) -> list[float]:
    """Move one end of ``bounds`` by ``frac`` of the range width, inward (tighten) or outward."""
    lo, hi = float(bounds[0]), float(bounds[1])
    step = frac * (hi - lo) * (-1.0 if tighten else 1.0)
    if side == "upper":
        hi += step
    else:
        lo -= step
    if not lo < hi:
        raise ValueError("assumption range collapsed")
    return [round(lo, 6), round(hi, 6)]


def edit_assumption(root: Path, p: dict[str, Any]) -> AppliedChange:
    """Rewrite the bounds of one assumption in the manifest (shared by T6 and T6-B)."""
    seen: dict[str, Any] = {}

    def edit(m: dict[str, Any]) -> None:
        a = m["assumptions"][p["assumption"]]
        if "bounds" not in a:
            raise ValueError(f"assumption {p['assumption']} has no bounds")
        seen["old"] = list(a["bounds"])
        a["bounds"] = change_bounds(a["bounds"], p["side"], p["tighten"], p["frac"])
        seen["new"] = a["bounds"]

    edit_manifest(root, edit)
    return AppliedChange([MANIFEST], {"assumption": p["assumption"], **seen})


@register("T6", "A", "t6_assumption", _sample_t6)
def apply_t6(ws: Any, sc: Scenario) -> AppliedChange:
    """Change the range of one assumption (e.g. coolant 10-100 -> 10-80 degC)."""
    return edit_assumption(_root(ws), sc.params)


# --- T10: unrelated change ------------------------------------------------------------------------------
def _sample_t10(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    sign = 1.0 if rng.random() < 0.5 else -1.0
    return {
        "flavor": str(rng.choice(["readme", "shaft"])),
        "delta_mm": round(sign * float(rng.uniform(0.005, 0.03)), 3),
    }


_SHAFT_FILES = (
    ("params/shaft.yaml", r"(?m)^(nominal_d_mm:\s*)([0-9.]+)"),
    ("params/params.yaml", r"(?m)^(\s+d_mm:\s*)([0-9.]+)"),
)


@register("T10", "A", "t10_unrelated", _sample_t10)
def apply_t10(ws: Any, sc: Scenario) -> AppliedChange:
    """README edit, or a shaft nominal-diameter revision: only the shaft claim (or nothing) is affected."""
    root = _root(ws)
    if sc.params["flavor"] == "readme":
        readme = root / "README.md"
        old = readme.read_bytes() if readme.exists() else b""
        readme.write_bytes(old + f"\nBench note ({sc.id}): documentation only.\n".encode())
        return AppliedChange(["README.md"], {"flavor": "readme"})
    for rel, pattern in _SHAFT_FILES:
        f = root / rel
        if f.exists() and re.search(pattern, f.read_text(encoding="utf-8")):
            text = f.read_bytes().decode("utf-8")
            new = re.sub(
                pattern,
                lambda m: f"{m.group(1)}{float(m.group(2)) + float(sc.params['delta_mm']):.3f}",
                text,
                count=1,
            )
            f.write_bytes(new.encode("utf-8"))
            return AppliedChange([rel], {"flavor": "shaft", "delta_mm": sc.params["delta_mm"]})
    raise ValueError("no shaft parameter file found")


# --- T11: producer code change --------------------------------------------------------------------------
@dataclass(frozen=True)
class CodeTarget:
    """Where the T11 patches go: the file, one function in it, a local rename and a 1.01 output scaling."""

    file: str
    function: str
    rename: tuple[str, str]
    fix: tuple[str, str]


CODE_TARGETS: tuple[CodeTarget, ...] = (
    CodeTarget(
        "motor/producers.py",
        "lptn_sim",
        ("sim", "trajectory"),
        ("peak = float(sim[node].max())", "peak = 1.01 * float(sim[node].max())"),
    ),
    CodeTarget(
        "mini/producers.py",
        "sim_temp",
        ("peak", "peak_load_value"),
        ("point = 20.0 + 10.0 * gain * scale * peak", "point = 1.01 * (20.0 + 10.0 * gain * scale * peak)"),
    ),
)


def _sample_t11(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {"flavor": str(rng.choice(["refactor", "fix"]))}


def patch_function(src: str, function: str, edit: Callable[[str], str]) -> str:
    """Apply ``edit`` to the source of one top-level function (def line up to the next blank-blank gap)."""
    m = re.search(rf"(?m)^def {re.escape(function)}\(", src)
    if m is None:
        raise ValueError(f"function {function} not found")
    end = src.find("\n\n\n", m.start())
    end = len(src) if end < 0 else end
    body = src[m.start() : end]
    new = edit(body)
    if new == body:
        raise ValueError(f"patch of {function} changed nothing")
    return src[: m.start()] + new + src[end:]


@register("T11", "A", "t11_code_change", _sample_t11)
def apply_t11(ws: Any, sc: Scenario) -> AppliedChange:
    """Producer code change. ``refactor`` renames a local (same behavior); ``fix`` scales the output by 1.01.

    Both change the producer's code hash, so both must invalidate its evidence (fail closed).
    """
    root = _root(ws)
    flavor = sc.params["flavor"]
    for tgt in CODE_TARGETS:
        f = root / tgt.file
        if not f.exists():
            continue
        old, new = tgt.rename
        fix_old, fix_new = tgt.fix

        def edit(body: str, old: str = old, new: str = new, fo: str = fix_old, fn: str = fix_new) -> str:
            if flavor == "refactor":
                return re.sub(r"\b" + re.escape(old) + r"\b", new, body)
            return body.replace(fo, fn, 1)

        src = f.read_bytes().decode("utf-8")
        f.write_bytes(patch_function(src, tgt.function, edit).encode("utf-8"))
        return AppliedChange([tgt.file], {"flavor": flavor, "function": tgt.function})
    raise ValueError("no known producer file to patch")
