"""Build a Snapshot from a loaded manifest, the files on disk and the producer registry (docs/10 §3)."""

from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from reval.core.canonical import canonical_json, sha256_hex
from reval.domain.artifacts import Artifact, ArtifactKind, ArtifactVersion
from reval.domain.engineering import Assumption, Claim, Requirement, Subject
from reval.domain.evidence import Producer
from reval.domain.policies import DEFAULT_POLICIES, Policy
from reval.domain.snapshot import Snapshot
from reval.errors import ManifestError
from reval.hashing import hash_artifact
from reval.manifest.schema import ManifestModel
from reval.sdk.registry import PLACEHOLDER_CODE_HASH

if TYPE_CHECKING:
    from reval.sdk.registry import ProducerRegistry

# Hasher used when the manifest does not name one (docs/10 §3.1).
_DEFAULT_HASHER: dict[ArtifactKind, Literal["file", "yaml-fields", "dataframe", "model"]] = {
    ArtifactKind.PARAMS: "yaml-fields",
    ArtifactKind.DATASET: "dataframe",
    ArtifactKind.MODEL: "model",
    ArtifactKind.CODE: "file",
    ArtifactKind.DOCUMENT: "file",
}


def build_snapshot(
    project_root: Path,
    manifest: ManifestModel,
    registry: "ProducerRegistry",
    *,
    git_rev: str | None = None,
) -> Snapshot:
    """Hash every artifact (upstream first), collect producers and policies, and compute ``Snapshot.id``.

    ``registry`` must already have had ``load_modules`` called so that producer code hashes are real.
    ``git_rev`` is informational and never part of the id.
    """
    root = Path(project_root)
    artifacts: dict[str, Artifact] = {}
    for aid in sorted(manifest.artifacts):
        spec = manifest.artifacts[aid]
        hasher = spec.hasher or _DEFAULT_HASHER[spec.kind]
        artifacts[aid] = Artifact(
            id=aid,
            kind=spec.kind,
            path=Path(spec.path).as_posix(),
            hasher=hasher,
            derived_from=tuple(sorted(spec.derived_from)),
            key=spec.key,
        )

    order = TopologicalSorter({aid: set(a.derived_from) for aid, a in artifacts.items()}).static_order()
    versions: dict[str, ArtifactVersion] = {}
    for aid in order:
        art = artifacts[aid]
        versions[aid] = hash_artifact(art, root, {u: versions[u] for u in art.derived_from})

    producers: dict[str, Producer] = {}
    for rp in registry.all():
        if rp.meta.code_hash == PLACEHOLDER_CODE_HASH:
            raise ManifestError(
                f"producer {rp.meta.id!r} has no code hash; call registry.load_modules() first"
            )
        producers[rp.meta.id] = rp.meta

    policies: dict[str, Policy] = dict(DEFAULT_POLICIES)
    for pid, alternatives in manifest.policies.items():
        policies[pid] = Policy(id=pid, alternatives=alternatives)

    return Snapshot.create(
        git_rev=git_rev,
        # Hash of the loaded (unit-normalised, subjects-resolved) manifest; independent of file formatting.
        manifest_hash=sha256_hex(canonical_json(manifest)),
        quantities=dict(sorted(manifest.quantities.items())),
        artifacts=artifacts,
        versions=dict(sorted(versions.items())),
        assumptions={k: Assumption(id=k, **v.model_dump()) for k, v in sorted(manifest.assumptions.items())},
        requirements={
            k: Requirement(id=k, **v.model_dump()) for k, v in sorted(manifest.requirements.items())
        },
        subjects={k: Subject(id=k, **v.model_dump()) for k, v in sorted(manifest.subjects.items())},
        claims={
            c.id: Claim(id=c.id, requirement_id=c.requirement, subject_id=c.subject, policy_id=c.policy)
            for c in sorted(manifest.claims, key=lambda c: c.id)
        },
        policies=dict(sorted(policies.items())),
        producers=dict(sorted(producers.items())),
    )
