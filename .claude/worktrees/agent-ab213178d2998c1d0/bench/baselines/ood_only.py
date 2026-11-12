"""B2: keep all old evidence; rerun ML only where the subject is out of the (new) model domain."""

from __future__ import annotations

from collections.abc import Callable

from bench.baselines.base import PostState, PreState, Run
from bench.harness.cache import ProducerResultCache
from reval.domain.evidence import ProducerKind

# (post state, producer id, subject id) -> True if the subject is inside the new model's domain.
DomainCheck = Callable[[PostState, str, str], bool]


def domain_check_via_producer(cache: ProducerResultCache) -> DomainCheck:
    """Default check: evaluate the ML producer in S' (cached) and read its ``in_domain`` flag.

    The check itself is not charged to B2's cost (a real AD query is far cheaper than a bench run); this
    favours B2 and is stated in the report. A missing flag counts as not inside (fail closed).
    """

    def check(post: PostState, producer_id: str, subject_id: str) -> bool:
        evidence, _ = cache.run(post.project, post.snapshot, producer_id, subject_id)
        return all(e.result.in_domain is True for e in evidence)

    return check


class OodOnly:
    id = "B2"

    def __init__(self, domain_check: DomainCheck) -> None:
        self._inside = domain_check

    def select_runs(self, pre: PreState, post: PostState) -> list[Run]:
        out: list[Run] = []
        for (pid, sid), e in sorted(pre.latest().items()):
            if e.producer_kind is not ProducerKind.ML_PREDICTION:
                continue
            if pid not in post.snapshot.producers or sid not in post.snapshot.subjects:
                continue
            if not self._inside(post, pid, sid):
                out.append((pid, sid))
        return out
