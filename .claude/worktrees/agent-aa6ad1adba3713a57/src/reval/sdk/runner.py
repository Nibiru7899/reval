"""Run a registered producer on a subject and turn its output into Evidence (docs/10 §7, D9, D10)."""

from importlib import metadata
from pathlib import Path

from reval.core.canonical import content_id
from reval.core.selectors import selector_hash
from reval.domain.engineering import Subject
from reval.domain.evidence import Dependency, Evidence, ProducerKind, Provenance, Scope
from reval.domain.settings import DEFAULT_SETTINGS
from reval.domain.snapshot import Snapshot
from reval.errors import ProducerError, RevalError
from reval.sdk.context import Context
from reval.sdk.output import ProducerOutput
from reval.sdk.registry import PLACEHOLDER_CODE_HASH, ProducerRegistry

_ENV_PACKAGES = ("reval", "numpy", "scipy", "scikit-learn", "pandas")


def _env() -> dict[str, str]:
    """Installed versions of the packages that can influence numeric results."""
    out: dict[str, str] = {}
    for name in _ENV_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return out


def run_producer(
    registry: ProducerRegistry,
    producer_id: str,
    subject: Subject,
    snapshot: Snapshot,
    project_root: Path,
) -> tuple[Evidence, ...]:
    """Call the producer and return one Evidence per result, sorted by id.

    Raises ProducerError for a result quantity/unit the producer or snapshot does not declare, for an
    unavailable subject, a missing/mismatched waiver, or any unexpected exception inside the producer.
    """
    rp = registry.get(producer_id)
    meta = rp.meta
    if meta.code_hash == PLACEHOLDER_CODE_HASH:
        raise ProducerError(f"producer {producer_id!r} has no code hash; call registry.load_modules first")
    if rp.available_for is not None and not rp.available_for(subject):
        raise ProducerError(f"producer {producer_id!r} is not available for subject {subject.id!r}")

    ctx = Context(Path(project_root), snapshot, meta, DEFAULT_SETTINGS)
    try:
        output = rp.fn(subject, ctx)
    except RevalError:
        raise
    except Exception as exc:
        raise ProducerError(f"producer {producer_id!r} failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(output, ProducerOutput):
        raise ProducerError(
            f"producer {producer_id!r} must return ProducerOutput, got {type(output).__name__}"
        )

    if (meta.kind is ProducerKind.WAIVER) != (output.waiver is not None):
        raise ProducerError(f"producer {producer_id!r}: a waiver is required iff the producer kind is waiver")
    if output.waiver is not None:
        claim = snapshot.claims.get(output.waiver.claim_id)
        if claim is None:
            raise ProducerError(f"waiver refers to unknown claim {output.waiver.claim_id!r}")
        req = snapshot.requirements[claim.requirement_id]
        if output.waiver.requirement_hash != content_id(req):
            raise ProducerError(f"waiver for {claim.id!r} was written against a different requirement")

    # D10 asks for the union of the claim's current evidence deps; the runner cannot see that evidence,
    # so a waiver gets its producer's declared deps and services must widen them (fail-closed gap noted).
    deps = tuple(
        Dependency(selector=sel, version_hash=selector_hash(snapshot, sel)) for sel in sorted(meta.depends_on)
    )
    scope = Scope(
        box=output.scope.box,
        assumption_ids=tuple(sorted(set(output.scope.assumption_ids) | set(meta.assumes))),  # D9
    )
    provenance = Provenance(
        producer_code_hash=meta.code_hash, snapshot_id=snapshot.id, env=_env(), seed=ctx.seed
    )

    items: list[Evidence] = []
    for result in output.results:
        if result.quantity not in meta.quantities:
            raise ProducerError(
                f"producer {producer_id!r} returned quantity {result.quantity!r}; declared: {meta.quantities}"
            )
        expected_unit = snapshot.quantities.get(result.quantity)
        if expected_unit is not None and result.unit != expected_unit:
            raise ProducerError(
                f"producer {producer_id!r}: {result.quantity!r} must be reported in {expected_unit!r}, "
                f"got {result.unit!r}"
            )
        items.append(
            Evidence.create(
                producer_id=meta.id,
                producer_kind=meta.kind,
                fidelity=meta.fidelity,
                subject_id=subject.id,
                result=result,
                deps=deps,
                scope=scope,
                tolerances=output.tolerances,
                provenance=provenance,
                cost=meta.cost,
                waiver=output.waiver,
            )
        )
    return tuple(sorted(items, key=lambda e: e.id))
