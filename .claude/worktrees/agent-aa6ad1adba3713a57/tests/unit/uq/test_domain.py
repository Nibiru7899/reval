import json

import numpy as np

from reval.uq.domain import ApplicabilityDomain, DomainReport

NAMES = ["a", "b", "c"]


def _data(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.normal(size=(3000, 3)), rng.normal(size=(1000, 3))


def test_training_points_inside_relaxed_and_central_strict() -> None:
    xt, xc = _data()
    ad = ApplicabilityDomain(NAMES).fit(xt, xc)
    assert ad.check(xt, min_inside_frac=0.95).inside
    central = xt[np.all(np.abs(xt) < 1.0, axis=1)][:200]
    assert ad.check(central).inside


def test_far_point_flags_feature_and_first_violation() -> None:
    xt, xc = _data()
    ad = ApplicabilityDomain(NAMES).fit(xt, xc)
    X = np.zeros((5, 3))
    X[3, 1] = 10.0
    X[4, 2] = 10.0
    rep = ad.check(X)
    assert not rep.inside
    assert rep.first_violation == 3
    assert rep.violating_features == ("b",)
    assert rep.frac_outside == 2 / 5
    assert rep.max_knn_distance > rep.threshold
    assert set(rep.box) == set(NAMES)


def test_relaxed_fraction() -> None:
    xt, xc = _data()
    ad = ApplicabilityDomain(NAMES).fit(xt, xc)
    X = np.zeros((100, 3))
    X[0, 0] = 10.0
    assert not ad.check(X).inside
    assert ad.check(X, min_inside_frac=0.99).inside


def test_roundtrip_and_determinism() -> None:
    xt, xc = _data()
    ad1 = ApplicabilityDomain(NAMES, max_train_rows=500).fit(xt, xc)
    ad2 = ApplicabilityDomain(NAMES, max_train_rows=500).fit(xt, xc)
    ad3 = ApplicabilityDomain.from_dict(json.loads(json.dumps(ad1.to_dict())))
    X = np.random.default_rng(5).normal(scale=2.0, size=(50, 3))
    r1 = ad1.check(X).to_dict()
    assert r1 == ad2.check(X).to_dict() == ad3.check(X).to_dict()
    assert isinstance(ad1.check(X), DomainReport)


def test_zero_variance_feature() -> None:
    xt, xc = _data()
    xt[:, 0] = 5.0
    xc[:, 0] = 5.0
    ad = ApplicabilityDomain(NAMES).fit(xt, xc)
    assert ad.check(np.array([[5.0, 0.0, 0.0]])).inside
    assert ad.check(np.array([[6.0, 0.0, 0.0]])).violating_features == ("a",)
