"""Producer result cache shared by B0, ReVal and the baselines (docs/08 R8, Phase 5 refinement).

Key = (producer code hash, sorted declared-dependency selector hashes, assumption hashes, subject
id, settings hash). Evidence ids are content-derived, so a hit returns the byte-identical Evidence
that the original run produced; it keeps the provenance of the snapshot that first computed it.
Nothing but the key decides a hit: a changed dependency, code, subject or setting is a different key.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from reval.core.canonical import canonical_json, content_id, sha256_hex
from reval.core.selectors import selector_hash
from reval.domain.engineering import Subject
from reval.domain.evidence import Evidence
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.domain.snapshot import Snapshot
from reval.sdk.runner import run_producer
from reval.services.project import Project

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"  # git-ignored


def cache_key(
    snapshot: Snapshot,
    producer_id: str,
    subject_id: str,
    settings: ReValSettings = DEFAULT_SETTINGS,
) -> str:
    """Content key of one producer run. Missing dependencies hash as ``missing`` (a distinct key)."""
    meta = snapshot.producers[producer_id]
    deps = sorted((sel, selector_hash(snapshot, sel)) for sel in meta.depends_on)
    assumptions = sorted(
        (a, content_id(snapshot.assumptions[a])) for a in meta.assumes if a in snapshot.assumptions
    )
    # The subject definition (generator, params) is an input of the producer, not only its id.
    subject = snapshot.subjects[subject_id]
    payload = {
        "code": meta.code_hash,
        "deps": deps,
        "assumptions": assumptions,
        "subject": [subject_id, content_id(subject)],
        "settings": content_id(settings, exclude=frozenset()),
    }
    return sha256_hex(canonical_json(payload))


@dataclass
class ProducerResultCache:
    """Directory of cached evidence; safe for concurrent writers (atomic rename)."""

    root: Path = DEFAULT_CACHE_DIR
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> tuple[Evidence, ...] | None:
        path = self._path(key)
        raw: list[str] = []
        for attempt in range(8):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                break
            except FileNotFoundError:
                return None
            except PermissionError:  # Windows: the entry is being replaced by a concurrent writer
                if attempt == 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
        # Evidence validates id == content_id, so a corrupted file raises instead of being trusted.
        return tuple(Evidence.model_validate_json(x) for x in raw)

    def put(self, key: str, evidence: tuple[Evidence, ...]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([e.model_dump_json() for e in evidence], fh)
        # Windows refuses os.replace while another process has the target open (a concurrent reader or
        # writer of the same key). The content is a pure function of the key, so retry, and if the entry
        # exists after the retries the other writer already stored the identical evidence.
        for attempt in range(8):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 7:
                    break
                time.sleep(0.05 * (attempt + 1))
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        if not path.exists():
            raise PermissionError(f"could not store cache entry {path}")

    def run(
        self,
        project: Project,
        snapshot: Snapshot,
        producer_id: str,
        subject_id: str,
        settings: ReValSettings = DEFAULT_SETTINGS,
    ) -> tuple[tuple[Evidence, ...], bool]:
        """Evidence of one producer on one subject and whether it came from the cache."""
        key = cache_key(snapshot, producer_id, subject_id, settings)
        cached = self.get(key)
        if cached is not None:
            self.hits += 1
            return cached, True
        subject: Subject = snapshot.subjects[subject_id]
        evidence = run_producer(project.registry, producer_id, subject, snapshot, project.root, settings)
        self.put(key, evidence)
        self.misses += 1
        return evidence, False
