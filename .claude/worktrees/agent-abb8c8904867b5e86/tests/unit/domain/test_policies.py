from reval.domain import DEFAULT_FIDELITY, DEFAULT_POLICIES, Policy, ProducerKind


def test_default_policies_shape() -> None:
    assert set(DEFAULT_POLICIES) == {"low", "medium", "high"}
    assert len(DEFAULT_POLICIES["low"].alternatives) == 4
    assert len(DEFAULT_POLICIES["medium"].alternatives) == 3
    assert len(DEFAULT_POLICIES["high"].alternatives) == 3
    for p in DEFAULT_POLICIES.values():
        assert p.id in DEFAULT_POLICIES
        assert all(1 <= len(c) <= 3 for c in p.alternatives)
        assert Policy.model_validate(p.model_dump()) == p


def test_analytic_clauses() -> None:
    low = DEFAULT_POLICIES["low"]
    assert any([c.kind for c in clause] == [ProducerKind.ANALYTIC] for clause in low.alternatives)
    for pid in ("medium", "high"):
        analytic = [
            c for cl in DEFAULT_POLICIES[pid].alternatives for c in cl if c.kind is ProducerKind.ANALYTIC
        ]
        assert analytic and analytic[0].min_fidelity == 3


def test_medium_independence_clause() -> None:
    ml, sim = DEFAULT_POLICIES["medium"].alternatives[0]
    assert ml.kind is ProducerKind.ML_PREDICTION and ml.in_domain
    assert sim.independent_of == (ProducerKind.ML_PREDICTION,)


def test_default_fidelity() -> None:
    assert DEFAULT_FIDELITY[ProducerKind.WAIVER] == 0
    assert DEFAULT_FIDELITY[ProducerKind.MEASUREMENT] == 3
