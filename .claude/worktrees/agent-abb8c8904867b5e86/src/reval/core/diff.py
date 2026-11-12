"""Snapshot diff -> ChangeSet (docs/10-interfaces.md §4.2, docs/04 A2). Pure.

Everything that differs between two snapshots must surface as some change; whatever cannot be classified
becomes ``UNKNOWN`` so that freshness fails closed (ADR 0002).
"""

from collections.abc import Iterable, Mapping

from reval.core.canonical import canonical_json
from reval.domain.artifacts import Artifact, ArtifactVersion, RowGroupInfo
from reval.domain.base import Frozen
from reval.domain.changes import Change, ChangeKind, ChangeSet
from reval.domain.selectors import Selector
from reval.domain.snapshot import Snapshot

MISSING = "missing"

_K = ChangeKind
Scalar = float | int | str | bool | None


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _delta(old: Scalar, new: Scalar) -> float | None:
    if _is_number(old) and _is_number(new):
        assert isinstance(old, (int, float)) and isinstance(new, (int, float))
        return float(new) - float(old)
    return None


def _present(v: ArtifactVersion | None) -> bool:
    return v is not None and v.content_hash != MISSING


def _hull(bboxes: list[dict[str, tuple[float, float]]]) -> dict[str, tuple[float, float]] | None:
    """Component-wise hull over the variables present in every bbox; None if there is nothing to hull."""
    if not bboxes:
        return None
    common = set(bboxes[0])
    for b in bboxes[1:]:
        common &= set(b)
    return {v: (min(b[v][0] for b in bboxes), max(b[v][1] for b in bboxes)) for v in sorted(common)}


def _columns(v: ArtifactVersion) -> set[str]:
    return {k[2:] for k in v.field_hashes if k.startswith("c=")}


def _group_hashes(v: ArtifactVersion) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Per-group column hashes plus any field-hash keys that fit neither ``c=`` nor ``g=/c=``."""
    groups: dict[str, dict[str, str]] = {g: {} for g in v.row_groups}
    odd: set[str] = set()
    for k, h in v.field_hashes.items():
        if k.startswith("c="):
            continue
        if k.startswith("g=") and "/c=" in k:
            g, col = k[2:].rsplit("/c=", 1)
            groups.setdefault(g, {})[col] = h
        else:
            odd.add(k)
    return groups, odd


def _bbox(v: ArtifactVersion, g: str) -> dict[str, tuple[float, float]] | None:
    info: RowGroupInfo | None = v.row_groups.get(g)
    return None if info is None else dict(info.bbox)


def _rows_change(
    kind: ChangeKind,
    art_id: str,
    groups: list[str],
    columns: set[str],
    bboxes: list[dict[str, tuple[float, float]] | None],
) -> Change:
    cols = tuple(sorted(columns))
    target = Selector(artifact_id=art_id, columns=cols).render() if cols else art_id
    # A group without bbox info makes the hull unknowable: leave it None so no scope excuse applies.
    hull = None if any(b is None for b in bboxes) else _hull([b for b in bboxes if b is not None])
    return Change(kind=kind, target=target, groups=tuple(sorted(groups)), columns=cols, rows_bbox=hull)


def _diff_dataframe(art_id: str, old: ArtifactVersion, new: ArtifactVersion) -> list[Change]:
    old_cols, new_cols = _columns(old), _columns(new)
    if old_cols != new_cols:
        added = sorted(new_cols - old_cols)
        removed = sorted(old_cols - new_cols)
        detail = "column set changed: " + " ".join([f"+{c}" for c in added] + [f"-{c}" for c in removed])
        return [Change(kind=_K.ARTIFACT_CHANGED, target=art_id, detail=detail)]
    og, odd_o = _group_hashes(old)
    ng, odd_n = _group_hashes(new)
    if odd_o or odd_n:
        return [
            Change(
                kind=_K.UNKNOWN,
                target=art_id,
                detail="unrecognised dataframe field hashes: " + ",".join(sorted(odd_o | odd_n)),
            )
        ]
    out: list[Change] = []
    added_g = sorted(set(ng) - set(og))
    removed_g = sorted(set(og) - set(ng))
    if added_g:
        out.append(_rows_change(_K.ROWS_ADDED, art_id, added_g, new_cols, [_bbox(new, g) for g in added_g]))
    if removed_g:
        out.append(
            _rows_change(_K.ROWS_REMOVED, art_id, removed_g, old_cols, [_bbox(old, g) for g in removed_g])
        )
    modified: list[str] = []
    mod_cols: set[str] = set()
    for g in sorted(set(og) & set(ng)):
        cols = {c for c in set(og[g]) | set(ng[g]) if og[g].get(c) != ng[g].get(c)}
        if cols or old.row_groups.get(g) != new.row_groups.get(g):
            modified.append(g)
            # A group whose metadata changed but no column hash did is still a change of all its columns.
            mod_cols |= cols or new_cols
    if modified:
        bbs = [b for g in modified for b in (_bbox(old, g), _bbox(new, g))]
        out.append(_rows_change(_K.ROWS_MODIFIED, art_id, modified, mod_cols, bbs))
    return out


def _diff_yaml(art_id: str, old: ArtifactVersion, new: ArtifactVersion) -> list[Change]:
    out: list[Change] = []
    for ptr in sorted(set(old.field_hashes) | set(new.field_hashes)):
        target = f"{art_id}#{ptr}" if ptr else art_id
        if ptr not in old.field_hashes:
            out.append(Change(kind=_K.FIELD_ADDED, target=target, new=new.field_values.get(ptr)))
        elif ptr not in new.field_hashes:
            out.append(Change(kind=_K.FIELD_REMOVED, target=target, old=old.field_values.get(ptr)))
        elif old.field_hashes[ptr] != new.field_hashes[ptr]:
            o, n = old.field_values.get(ptr), new.field_values.get(ptr)
            out.append(Change(kind=_K.FIELD_CHANGED, target=target, old=o, new=n, delta=_delta(o, n)))
    return out


def _upstream_changed(art: Artifact, old: Snapshot, new: Snapshot) -> bool:
    for up in art.derived_from:
        ov, nv = old.versions.get(up), new.versions.get(up)
        if (ov is None) != (nv is None) or (
            ov is not None and nv is not None and ov.content_hash != nv.content_hash
        ):
            return True
    return False


def _diff_artifact(art_id: str, old: Snapshot, new: Snapshot) -> list[Change]:
    oa, na = old.artifacts.get(art_id), new.artifacts.get(art_id)
    if oa is None and na is not None:
        return [Change(kind=_K.ARTIFACT_ADDED, target=art_id)]
    if na is None and oa is not None:
        return [Change(kind=_K.ARTIFACT_REMOVED, target=art_id)]
    assert oa is not None and na is not None
    ov, nv = old.versions.get(art_id), new.versions.get(art_id)
    if not _present(ov) and not _present(nv):
        return []
    if not _present(ov):
        return [Change(kind=_K.ARTIFACT_ADDED, target=art_id, detail="file appeared")]
    if not _present(nv):
        return [Change(kind=_K.ARTIFACT_REMOVED, target=art_id, detail="file missing")]
    assert ov is not None and nv is not None
    if oa != na:
        fields = sorted(f for f in Artifact.model_fields if getattr(oa, f) != getattr(na, f))
        return [
            Change(kind=_K.ARTIFACT_CHANGED, target=art_id, detail="definition changed: " + ",".join(fields))
        ]
    if ov == nv:
        return []
    if na.hasher == "yaml-fields":
        out = _diff_yaml(art_id, ov, nv)
    elif na.hasher == "dataframe":
        out = _diff_dataframe(art_id, ov, nv)
    elif na.hasher in ("model", "file"):
        return (
            [Change(kind=_K.ARTIFACT_CHANGED, target=art_id)]
            if ov.content_hash != nv.content_hash
            else [
                Change(
                    kind=_K.UNKNOWN, target=art_id, detail="version metadata changed with equal content hash"
                )
            ]
        )
    else:  # pragma: no cover - Literal-typed, kept for fail-closed safety
        return [Change(kind=_K.UNKNOWN, target=art_id, detail=f"unknown hasher {na.hasher!r}")]
    if not out and not (ov.content_hash != nv.content_hash and _upstream_changed(na, old, new)):
        # The version differs but no own field explains it, and no upstream change does either.
        out = [
            Change(kind=_K.UNKNOWN, target=art_id, detail="version changed without a classifiable difference")
        ]
    return out


def _diff_entities[M: Frozen](kind: ChangeKind, old: Mapping[str, M], new: Mapping[str, M]) -> list[Change]:
    out: list[Change] = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            out.append(Change(kind=kind, target=k, detail="added"))
        elif k not in new:
            out.append(Change(kind=kind, target=k, detail="removed"))
        elif canonical_json(old[k]) != canonical_json(new[k]):
            fields = sorted(f for f in type(old[k]).model_fields if getattr(old[k], f) != getattr(new[k], f))
            out.append(Change(kind=kind, target=k, detail="changed: " + ",".join(fields)))
    return out


def _diff_requirements(old: Snapshot, new: Snapshot) -> list[Change]:
    out: list[Change] = []
    for c in _diff_entities(_K.REQUIREMENT_CHANGED, old.requirements, new.requirements):
        o, n = old.requirements.get(c.target), new.requirements.get(c.target)
        if o is not None and n is not None and o.limit != n.limit:
            c = Change(
                kind=c.kind,
                target=c.target,
                old=o.limit,
                new=n.limit,
                delta=_delta(o.limit, n.limit),
                detail=c.detail,
            )
        out.append(c)
    return out


def _diff_orphan_versions(old: Snapshot, new: Snapshot) -> list[Change]:
    # A version without an artifact entry cannot be classified.
    ids = (set(old.versions) - set(old.artifacts)) | (set(new.versions) - set(new.artifacts))
    return [
        Change(kind=_K.UNKNOWN, target=i, detail="version without artifact entry")
        for i in sorted(ids)
        if old.versions.get(i) != new.versions.get(i)
    ]


def _diff_producers(old: Snapshot, new: Snapshot) -> list[Change]:
    out: list[Change] = []
    for pid in sorted(set(old.producers) | set(new.producers)):
        op, np_ = old.producers.get(pid), new.producers.get(pid)
        if op is None:
            out.append(Change(kind=_K.PRODUCER_CODE_CHANGED, target=pid, detail="added"))
        elif np_ is None:
            out.append(Change(kind=_K.PRODUCER_CODE_CHANGED, target=pid, detail="removed"))
        elif op != np_:
            # code_hash/depends_on are the spec's triggers; any other metadata change is treated the same way
            # (targeted at this producer's evidence) instead of a project-wide UNKNOWN.
            fields = sorted(f for f in type(op).model_fields if getattr(op, f) != getattr(np_, f))
            out.append(
                Change(kind=_K.PRODUCER_CODE_CHANGED, target=pid, detail="changed: " + ",".join(fields))
            )
    return out


def _diff_quantities(old: Snapshot, new: Snapshot) -> list[Change]:
    # Not a manifest entity kind: a canonical-unit change is unclassifiable, so UNKNOWN (unparseable target).
    return [
        Change(kind=_K.UNKNOWN, target=f"quantity:{q}", old=old.quantities.get(q), new=new.quantities.get(q))
        for q in sorted(set(old.quantities) | set(new.quantities))
        if old.quantities.get(q) != new.quantities.get(q)
    ]


def _sorted(changes: Iterable[Change]) -> tuple[Change, ...]:
    return tuple(sorted(changes, key=lambda c: (c.kind.value, c.target, canonical_json(c))))


def diff_snapshots(old: Snapshot, new: Snapshot) -> ChangeSet:
    """All differences from ``old`` to ``new`` as a ChangeSet sorted by (kind, target).

    ``manifest_hash`` and ``git_rev`` are not compared: every manifest edit surfaces through the entity,
    artifact or producer it touches.
    """
    changes: list[Change] = []
    for art_id in sorted(set(old.artifacts) | set(new.artifacts)):
        changes += _diff_artifact(art_id, old, new)
    changes += _diff_orphan_versions(old, new)
    changes += _diff_requirements(old, new)
    changes += _diff_entities(_K.ASSUMPTION_CHANGED, old.assumptions, new.assumptions)
    changes += _diff_entities(_K.POLICY_CHANGED, old.policies, new.policies)
    changes += _diff_entities(_K.SUBJECT_CHANGED, old.subjects, new.subjects)
    changes += _diff_entities(_K.CLAIM_CHANGED, old.claims, new.claims)
    changes += _diff_producers(old, new)
    changes += _diff_quantities(old, new)
    return ChangeSet(from_snapshot=old.id, to_snapshot=new.id, changes=_sorted(changes))
