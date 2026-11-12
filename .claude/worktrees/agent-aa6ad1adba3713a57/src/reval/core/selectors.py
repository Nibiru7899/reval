"""Selector hashing and derivation closure over a Snapshot (docs/10-interfaces.md §4.0). Pure."""

from reval.core.canonical import canonical_json, sha256_hex
from reval.domain.selectors import Selector
from reval.domain.snapshot import Snapshot

MISSING = "missing"


def selector_hash(snapshot: Snapshot, selector: str) -> str:
    """Hash of the part of the snapshot a selector refers to; ``"missing"`` if the artifact is absent."""
    sel = Selector.parse(selector)
    version = snapshot.versions.get(sel.artifact_id)
    if version is None or version.content_hash == MISSING:
        return MISSING
    if sel.is_whole:
        return version.content_hash
    if sel.pointer is not None:
        ptr = sel.pointer
        items = sorted((k, h) for k, h in version.field_hashes.items() if k == ptr or k.startswith(ptr + "/"))
    else:
        wanted = {f"c={c}" for c in sel.columns}
        items = sorted((k, h) for k, h in version.field_hashes.items() if k in wanted)
    return sha256_hex(canonical_json(items))


def derived_closure(snapshot: Snapshot, artifact_id: str) -> frozenset[str]:
    """Transitive upstream artifact ids via ``derived_from`` (excluding ``artifact_id`` itself)."""
    seen: set[str] = set()
    stack = [artifact_id]
    while stack:
        art = snapshot.artifacts.get(stack.pop())
        if art is None:
            continue
        for up in art.derived_from:
            if up not in seen:
                seen.add(up)
                stack.append(up)
    seen.discard(artifact_id)
    return frozenset(seen)
