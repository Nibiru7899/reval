"""B1: Make/DVC-style file-level dependencies. No field hashing, scope or tolerance."""

from __future__ import annotations

from bench.baselines.base import MISSING, PostState, PreState, Run, file_hashes
from reval.core.canonical import content_id
from reval.domain.selectors import Selector


class FileLevel:
    """Rerun an evidence item's producer if any file it reads changed byte-wise.

    "Reads" = the files of the artifacts named in the producer's ``depends_on`` (a selector is reduced to its
    file), plus the producer's code and the subject definition. The derivation trace is NOT followed: a
    Make-style tool only knows the files the command lists.
    """

    id = "B1"

    def select_runs(self, pre: PreState, post: PostState) -> list[Run]:
        now = file_hashes(post.root, post.snapshot)
        out: list[Run] = []
        for pid, sid in sorted(pre.latest()):
            old_meta = pre.snapshot.producers.get(pid)
            new_meta = post.snapshot.producers.get(pid)
            if new_meta is None or sid not in post.snapshot.subjects:
                continue  # cannot be rerun in S'
            if old_meta is None or old_meta.code_hash != new_meta.code_hash:
                out.append((pid, sid))
                continue
            old_subject = pre.snapshot.subjects.get(sid)
            if old_subject is None or content_id(old_subject) != content_id(post.snapshot.subjects[sid]):
                out.append((pid, sid))
                continue
            for artifact_id in sorted({Selector.parse(d).artifact_id for d in new_meta.depends_on}):
                art = post.snapshot.artifacts.get(artifact_id)
                if art is None or pre.files.get(art.path, MISSING) != now.get(art.path, MISSING):
                    out.append((pid, sid))
                    break
        return out
