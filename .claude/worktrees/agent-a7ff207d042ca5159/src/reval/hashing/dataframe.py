"""``dataframe`` hasher: per-group, per-column hashes (docs/10 §6)."""

import importlib
from collections.abc import Mapping
from pathlib import Path

from reval.core.canonical import sha256_hex
from reval.domain.artifacts import Artifact, ArtifactVersion, RowGroupInfo
from reval.errors import MissingExtraError
from reval.hashing.base import MISSING, fold_upstream, resolve


def hash_dataframe(
    artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]
) -> ArtifactVersion:
    """Hash a parquet/csv table grouped by ``artifact.key[0]``.

    Row order within a group is part of the hash on purpose: the data are time series, so a reordering
    is a real change. Group order does not matter (groups are processed in sorted order).
    """
    try:
        pd = importlib.import_module("pandas")  # untyped; keeps mypy independent of pandas-stubs
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise MissingExtraError("motor") from exc

    path = resolve(artifact, root)
    if path is None:
        return ArtifactVersion(artifact_id=artifact.id, content_hash=MISSING)
    if not artifact.key:
        raise ValueError(f"artifact {artifact.id!r}: dataframe hasher requires key[0] (the group column)")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"artifact {artifact.id!r}: unsupported dataframe format {suffix!r}")
    group_col = artifact.key[0]
    if group_col not in df.columns:
        raise ValueError(f"artifact {artifact.id!r}: group column {group_col!r} not in table")

    labels = df[group_col].astype(str)
    field_hashes: dict[str, str] = {}
    row_groups: dict[str, RowGroupInfo] = {}
    per_col: dict[str, list[str]] = {str(c): [] for c in df.columns}
    numeric = [
        str(c)
        for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
    ]
    for g in sorted(labels.unique()):
        sub = df[(labels == g).to_numpy()]
        for c in df.columns:
            h = sha256_hex(pd.util.hash_pandas_object(sub[c], index=False).to_numpy().tobytes())
            field_hashes[f"g={g}/c={c}"] = h
            per_col[str(c)].append(h)
        bbox: dict[str, tuple[float, float]] = {}
        for c in numeric:
            lo, hi = sub[c].min(), sub[c].max()
            if lo == lo and hi == hi:  # skip all-NaN columns
                bbox[c] = (float(lo), float(hi))
        row_groups[g] = RowGroupInfo(n_rows=len(sub), bbox=bbox)
    for c, hashes in per_col.items():
        field_hashes[f"c={c}"] = sha256_hex("".join(hashes).encode("ascii"))
    own = sha256_hex("".join(f"{k}={v}\n" for k, v in sorted(field_hashes.items())).encode("utf-8"))
    return ArtifactVersion(
        artifact_id=artifact.id,
        content_hash=fold_upstream(artifact, own, upstream),
        field_hashes=field_hashes,
        row_groups=row_groups,
    )
