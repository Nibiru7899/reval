"""Evidence freshness across a change set (docs/10 §4.3, docs/03 §4, docs/04 A3, ADR 0002). Pure.

Fail closed: evidence is fresh only when a positive rule proves it. Every path that is unsure, inconsistent or
unclassifiable ends in INVALIDATED.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from reval.core.canonical import content_id, difference_unit
from reval.core.selectors import derived_closure, selector_hash
from reval.domain.artifacts import ArtifactKind
from reval.domain.assessment import Reason
from reval.domain.changes import Change, ChangeKind, ChangeSet
from reval.domain.evidence import Dependency, Evidence, Tolerance
from reval.domain.selectors import Selector
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, ReasonCode
from reval.errors import ManifestError

_K = ChangeKind
_ROWS = frozenset({_K.ROWS_ADDED, _K.ROWS_MODIFIED, _K.ROWS_REMOVED})
# Kinds whose target is an artifact selector (rules (a) and (f)); entity kinds target entity ids instead.
_ARTIFACT_KINDS = frozenset(
    {
        _K.FIELD_CHANGED,
        _K.FIELD_ADDED,
        _K.FIELD_REMOVED,
        *_ROWS,
        _K.ARTIFACT_ADDED,
        _K.ARTIFACT_REMOVED,
        _K.ARTIFACT_CHANGED,
    }
)


@dataclass(frozen=True)
class FreshnessResult:
    evidence_id: str
    cls: FreshnessClass
    reasons: tuple[Reason, ...]
    inflation: float  # 0.0 unless CARRY_FORWARD; in the quantity's difference unit
    relevant_changes: tuple[Change, ...]


def _parse(text: str) -> Selector | None:
    try:
        return Selector.parse(text)
    except (ManifestError, ValueError):
        return None


def _overlaps(a: Selector, b: Selector) -> bool:
    # Mixed pointer/column selectors on one artifact are ill-formed; treat them as overlapping (fail closed).
    if a.artifact_id == b.artifact_id and (a.pointer is None) != (b.pointer is None):
        return True
    return a.covers(b)


def _invalid(
    e: Evidence, code: ReasonCode, message: str, relevant: tuple[Change, ...] = ()
) -> FreshnessResult:
    reason = Reason(code=code, message=message, evidence_ids=(e.id,))
    return FreshnessResult(e.id, FreshnessClass.INVALIDATED, (reason,), 0.0, relevant)


def _change_reason(e: Evidence, c: Change, why: str) -> Reason:
    if c.kind is _K.UNKNOWN:
        code = ReasonCode.UNKNOWN_CHANGE
    elif c.kind is _K.FIELD_CHANGED:
        code = ReasonCode.MISSING_TOLERANCE
    else:
        code = ReasonCode.EVIDENCE_INVALIDATED
    return Reason(
        code=code,
        message=f"{c.kind.value} on {c.target}: {why}",
        evidence_ids=(e.id,),
        detail={"change_kind": c.kind.value, "target": c.target},
    )


@dataclass(frozen=True)
class _Ctx:
    e: Evidence
    old: Snapshot
    new: Snapshot
    deps: tuple[tuple[Dependency, Selector | None], ...]
    deps_star: frozenset[str]  # artifacts of deps plus their derived closures (old and new)
    upstream: frozenset[str]  # derived closures of dep artifacts only (rule (f))
    scoped_assumptions: frozenset[str]
    settings: ReValSettings


def _dep_selector(text: str, settings: ReValSettings) -> Selector | None:
    sel = _parse(text)
    # A1 (bench only): without field-level selectors every dependency is the whole artifact.
    if sel is not None and not settings.field_level_selectors:
        return Selector(artifact_id=sel.artifact_id)
    return sel


def _dep_changed(d: Dependency, s: Selector | None, x: _Ctx) -> bool:
    """True when what the dependency refers to differs between the recorded and the new snapshot."""
    if s is None:
        return True
    if x.settings.field_level_selectors:
        return d.version_hash != selector_hash(x.new, d.selector)
    # A1: the recorded hash is field-level, so compare the whole artifact at the evidence's own snapshot.
    return selector_hash(x.old, s.render()) != selector_hash(x.new, s.render())


def _context(e: Evidence, old: Snapshot, new: Snapshot, settings: ReValSettings) -> _Ctx:
    deps = tuple((d, _dep_selector(d.selector, settings)) for d in e.deps)
    arts = {s.artifact_id for _, s in deps if s is not None}
    upstream: set[str] = set()
    for a in arts:
        upstream |= derived_closure(old, a) | derived_closure(new, a)
    scoped = set(e.scope.assumption_ids) | {t.assumption_id for t in e.tolerances}
    return _Ctx(
        e, old, new, deps, frozenset(arts | upstream), frozenset(upstream), frozenset(scoped), settings
    )


@dataclass(frozen=True)
class _Match:
    """Why a change is relevant: rule (a) dependencies it overlaps, plus whether any other rule fired."""

    via_a: tuple[Selector, ...]
    other: tuple[str, ...]  # rule letters (b)-(f), or "a?" for an unparseable dependency

    @property
    def relevant(self) -> bool:
        return bool(self.via_a or self.other)


def _match(c: Change, x: _Ctx) -> _Match:
    e = x.e
    target = _parse(c.target)
    via_a: list[Selector] = []
    other: list[str] = []
    if c.kind in _ARTIFACT_KINDS:
        for _d, s in x.deps:
            if s is None:
                # An unparseable dependency can't be shown to be untouched (fail closed).
                other.append("a?")
            elif target is None or _overlaps(target, s):
                via_a.append(s)
        if target is None or target.artifact_id in x.upstream:
            other.append("f")
    if c.kind is _K.ASSUMPTION_CHANGED and c.target in x.scoped_assumptions:
        other.append("b")
    if c.kind is _K.PRODUCER_CODE_CHANGED and c.target == e.producer_id:
        other.append("c")
    if c.kind is _K.UNKNOWN and (target is None or target.artifact_id in x.deps_star):
        other.append("d")
    if c.kind is _K.SUBJECT_CHANGED and c.target == e.subject_id:
        other.append("e")
    return _Match(tuple(via_a), tuple(other))


def _exact(x: _Ctx, changes: ChangeSet) -> bool:
    e, new = x.e, x.new
    for d, s in x.deps:
        if _dep_changed(d, s, x):
            return False
    producer = new.producers[e.producer_id]
    if producer.code_hash != e.provenance.producer_code_hash:
        return False
    for c in changes.changes:
        m = _match(c, x)
        # Rules (b)-(f) block the shortcut outright: (b), (e), (d) as listed in §4.3 step 1, plus (c) and (f)
        # because an upstream change of a derived artifact can leave own-only field hashes equal (D3).
        if m.other:
            return False
    return True


def _disjoint(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[1] < b[0] or b[1] < a[0]


def _excuse_rows(c: Change, m: _Match, x: _Ctx) -> str | None:
    """None if excused (out of scope), else why not."""
    if not x.settings.scope_freshness:
        return "scope-based excuses are disabled (ablation A3)"
    for s in m.via_a:
        if not s.columns:
            return f"matched by non-column dependency {s.render()}"
        for snap in (x.old, x.new):
            art = snap.artifacts.get(s.artifact_id)
            if art is not None and art.kind is not ArtifactKind.DATASET:
                return f"dependency {s.render()} is not on a dataset"
    if c.rows_bbox is None:
        return "row change has no bounding box"
    box = x.e.scope.box
    shared = sorted(set(c.rows_bbox) & set(box))
    if not any(_disjoint(c.rows_bbox[v], box[v]) for v in shared):
        return (
            "changed rows overlap the evidence scope"
            if shared
            else "no scope variable bounds the changed rows"
        )
    return None


def _number(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _excuse_field(c: Change, m: _Match, x: _Ctx) -> tuple[str | None, float]:
    """(None, inflation) if excused by a tolerance, else (why not, 0)."""
    if not x.settings.tolerance_carry_forward:
        return "tolerance carry-forward is disabled (ablation A2)", 0.0
    for s in m.via_a:
        if s.pointer is None:
            return f"matched by non-pointer dependency {s.render()}", 0.0
    old, new = _number(c.old), _number(c.new)
    if old is None or new is None or c.delta is None:
        return "non-numeric field change", 0.0
    target = _parse(c.target)
    if target is None:
        return "unparseable target", 0.0
    tols: list[Tolerance] = [
        t for t in x.e.tolerances if (ts := _parse(t.selector)) is not None and ts == target
    ]
    if not tols:
        return "no tolerance declared for this field", 0.0
    want = difference_unit(x.e.result.unit)
    for t in tols:
        if t.output_unit != want:
            raise ValueError(
                f"tolerance on {t.selector}: output_unit {t.output_unit!r} != difference unit {want!r} "
                f"of evidence {x.e.id}"
            )
    for t in tols:
        lo, hi = t.valid_range
        if not (lo <= old <= hi and lo <= new <= hi):
            return f"value {old} -> {new} outside tolerance valid_range [{lo}, {hi}]", 0.0
    step = max(abs(new - old), abs(c.delta))
    # Several tolerances on one field: take the most conservative one. kappa is applied exactly once (D14).
    kappa = x.settings.kappa_override
    return None, max((t.safety_factor if kappa is None else kappa) * t.sensitivity * step for t in tols)


def classify_evidence(
    e: Evidence,
    old: Snapshot,
    new: Snapshot,
    changes: ChangeSet,
    *,
    settings: ReValSettings = DEFAULT_SETTINGS,
) -> FreshnessResult:
    """Freshness class of ``e`` (recorded at ``old``) at ``new``, given ``changes = diff(old, new)``.

    ``settings`` only ever disables excuses or replaces kappa (benchmark ablations A1-A3, A7); the defaults
    are the full method. A1-A3 are never more permissive than the default; A7 (kappa) is a bench-only sweep
    and may be less conservative. Non-default settings are forbidden for real use.
    """
    # Step 0: hard failures, including inputs that don't belong together.
    if e.provenance.snapshot_id != old.id or changes.from_snapshot != old.id or changes.to_snapshot != new.id:
        return _invalid(
            e, ReasonCode.UNKNOWN_CHANGE, "old snapshot or change set does not match the evidence"
        )
    if e.producer_id not in new.producers:
        return _invalid(
            e, ReasonCode.UNKNOWN_CHANGE, f"producer {e.producer_id} is missing in the new snapshot"
        )
    if e.waiver is not None:
        claim = new.claims.get(e.waiver.claim_id)
        req = None if claim is None else new.requirements.get(claim.requirement_id)
        if req is None:
            return _invalid(
                e, ReasonCode.REQUIREMENT_CHANGED, f"claim {e.waiver.claim_id} or its requirement is gone"
            )
        if content_id(req) != e.waiver.requirement_hash:
            return _invalid(
                e, ReasonCode.REQUIREMENT_CHANGED, f"requirement {req.id} changed since the waiver"
            )

    x = _context(e, old, new, settings)
    # Step 1: exact shortcut.
    if _exact(x, changes):
        return FreshnessResult(e.id, FreshnessClass.FRESH_EXACT, (), 0.0, ())

    # Step 2: relevance.
    matched = [(c, m) for c in changes.changes if (m := _match(c, x)).relevant]
    relevant = tuple(c for c, _ in matched)

    # Every changed dependency hash and a changed code hash must be explained by some relevant change.
    reasons: list[Reason] = []
    explained = {s for _, m in matched for s in m.via_a}
    for d, s in x.deps:
        if s is None:
            reasons.append(
                Reason(
                    code=ReasonCode.UNKNOWN_CHANGE,
                    message=f"unparseable dependency {d.selector}",
                    evidence_ids=(e.id,),
                )
            )
        elif _dep_changed(d, s, x) and s not in explained:
            reasons.append(
                Reason(
                    code=ReasonCode.UNKNOWN_CHANGE,
                    message=f"dependency {d.selector} changed without a matching change",
                    evidence_ids=(e.id,),
                )
            )
    if new.producers[e.producer_id].code_hash != e.provenance.producer_code_hash:
        reasons.append(
            Reason(
                code=ReasonCode.EVIDENCE_INVALIDATED,
                message=f"code hash of producer {e.producer_id} differs from the recorded provenance",
                evidence_ids=(e.id,),
            )
        )

    # Step 3: excuse each relevant change individually.
    inflation = 0.0
    for c, m in matched:
        why: str | None
        if m.other:
            why = "never excused (rule " + ",".join(sorted(set(m.other))) + ")"
        elif c.kind in _ROWS:
            why = _excuse_rows(c, m, x)
        elif c.kind is _K.FIELD_CHANGED:
            why, add = _excuse_field(c, m, x)
            if why is None:
                inflation += add
        else:
            why = "this change kind is never excused"
        if why is not None:
            reasons.append(_change_reason(e, c, why))

    # Step 4: result.
    if not reasons and not relevant:
        # The shortcut failed yet nothing explains why: fail closed.
        reasons.append(
            Reason(
                code=ReasonCode.UNKNOWN_CHANGE,
                message="freshness could not be established",
                evidence_ids=(e.id,),
            )
        )
    if reasons:
        ordered = tuple(sorted(reasons, key=lambda r: (r.code.value, r.message)))
        return FreshnessResult(e.id, FreshnessClass.INVALIDATED, ordered, 0.0, relevant)
    if inflation > 0:
        if e.result.interval is None:
            return _invalid(
                e, ReasonCode.MISSING_TOLERANCE, "carry-forward needs a recorded interval", relevant
            )
        return FreshnessResult(e.id, FreshnessClass.CARRY_FORWARD, (), inflation, relevant)
    return FreshnessResult(e.id, FreshnessClass.FRESH_OUT_OF_SCOPE, (), 0.0, relevant)


def classify_all(
    evidence: Sequence[Evidence],
    snapshots: Mapping[str, Snapshot],
    new: Snapshot,
    changesets: Mapping[str, ChangeSet],
    *,
    settings: ReValSettings = DEFAULT_SETTINGS,
) -> dict[str, FreshnessResult]:
    """Classify every item; ``snapshots``/``changesets`` are keyed by ``provenance.snapshot_id``."""
    out: dict[str, FreshnessResult] = {}
    for e in sorted(evidence, key=lambda ev: ev.id):
        sid = e.provenance.snapshot_id
        old, cs = snapshots.get(sid), changesets.get(sid)
        if old is None or cs is None:
            out[e.id] = _invalid(e, ReasonCode.UNKNOWN_CHANGE, f"snapshot {sid} or its change set is missing")
        else:
            out[e.id] = classify_evidence(e, old, new, cs, settings=settings)
    return out


def carry_forward(e: Evidence, fr: FreshnessResult, new: Snapshot) -> Evidence:
    """Derived evidence: interval widened by ``fr.inflation``, deps re-hashed at ``new``. Never stored.."""
    if fr.cls is not FreshnessClass.CARRY_FORWARD or fr.evidence_id != e.id:
        raise ValueError(f"carry_forward needs a CARRY_FORWARD result for evidence {e.id}")
    interval = e.result.interval
    if interval is None:
        raise ValueError(f"evidence {e.id} has no interval to carry forward")
    result = e.result.model_copy(update={"interval": interval.widen(fr.inflation)})
    deps = tuple(
        Dependency(selector=d.selector, version_hash=selector_hash(new, d.selector))
        for d in sorted(e.deps, key=lambda d: d.selector)
    )
    provenance = e.provenance.model_copy(update={"snapshot_id": new.id})
    fields = {k: getattr(e, k) for k in type(e).model_fields if k != "id"}
    fields.update(result=result, deps=deps, provenance=provenance, derived_from_evidence=e.id)
    return Evidence.create(**fields)
