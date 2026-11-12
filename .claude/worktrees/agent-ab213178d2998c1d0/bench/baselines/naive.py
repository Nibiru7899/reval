"""B3: naive trust. Never revalidate."""

from __future__ import annotations

from bench.baselines.base import PostState, PreState, Run


class NaiveTrust:
    id = "B3"

    def select_runs(self, pre: PreState, post: PostState) -> list[Run]:
        return []
