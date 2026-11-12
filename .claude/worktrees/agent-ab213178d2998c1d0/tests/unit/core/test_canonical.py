import pytest

from reval.core.canonical import canonical_json, content_id, difference_unit, sha256_hex
from reval.domain.quantities import Interval


def test_key_order_does_not_matter() -> None:
    assert canonical_json({"a": 1, "b": [1, 2]}) == canonical_json({"b": [1, 2], "a": 1})


def test_bytes_are_compact_and_sorted() -> None:
    assert canonical_json({"b": (1, 2), "a": "é"}) == '{"a":"é","b":[1,2]}'.encode()


def test_two_constructions_identical() -> None:
    a = Interval(lo=1.0, hi=2.0, unit="K")
    b = Interval(unit="K", hi=2.0, lo=1.0)
    assert canonical_json(a) == canonical_json(b)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": bad})
    with pytest.raises(ValueError):
        canonical_json([bad])


def test_sha256_hex() -> None:
    digest = sha256_hex(b"")
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert len(digest) == 64


def test_content_id_excludes_id_by_default() -> None:
    assert content_id({"id": "x", "v": 1}) == content_id({"id": "y", "v": 1})
    assert content_id({"id": "x", "v": 1}) != content_id({"id": "x", "v": 2})
    keep = frozenset[str]()
    assert content_id({"id": "x", "v": 1}, exclude=keep) != content_id({"id": "y", "v": 1}, exclude=keep)


def test_content_id_of_model() -> None:
    iv = Interval(lo=1.0, hi=2.0, unit="K")
    assert content_id(iv) == sha256_hex(canonical_json(iv))


def test_difference_unit() -> None:
    assert difference_unit("degC") == "K"
    assert difference_unit("mm") == "mm"
