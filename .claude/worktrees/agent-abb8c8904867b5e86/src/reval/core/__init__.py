"""Pure, deterministic engines (evidence graph, change impact, validity, planner).

Rule (ADR 0001): nothing in this package may perform I/O, read clocks, use unseeded randomness,
or call a network service or LLM. `tests/unit/test_architecture.py` enforces the import side of this.
"""
