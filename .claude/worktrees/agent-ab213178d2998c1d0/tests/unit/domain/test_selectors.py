import pytest
from hypothesis import given
from hypothesis import strategies as st

from reval.domain import Selector
from reval.errors import ManifestError


@pytest.mark.parametrize(
    ("text", "pointer", "columns", "rendered"),
    [
        ("tpm_model", None, (), "tpm_model"),
        ("cooling#/flow_scale", "/flow_scale", (), "cooling#/flow_scale"),
        ("cooling#/a/b/0", "/a/b/0", (), "cooling#/a/b/0"),
        ("measures[pm,coolant]", None, ("coolant", "pm"), "measures[coolant,pm]"),
        ("measures[pm]", None, ("pm",), "measures[pm]"),
        ("measures[ pm , coolant ]", None, ("coolant", "pm"), "measures[coolant,pm]"),
        ("a-b.c_1", None, (), "a-b.c_1"),
    ],
)
def test_parse_valid(text: str, pointer: str | None, columns: tuple[str, ...], rendered: str) -> None:
    s = Selector.parse(text)
    assert s.pointer == pointer
    assert s.columns == columns
    assert s.render() == rendered
    assert Selector.parse(s.render()) == s


@pytest.mark.parametrize(
    "text",
    [
        "",
        "#/a",
        "art#",
        "art#a",
        "art#/a/",
        "art#//a",
        "art[]",
        "art[a,]",
        "art[a",
        "art]a[",
        "a b",
        "art[a,,b]",
    ],
)
def test_parse_invalid(text: str) -> None:
    with pytest.raises(ManifestError):
        Selector.parse(text)


def test_is_whole() -> None:
    assert Selector.parse("a").is_whole
    assert not Selector.parse("a#/x").is_whole
    assert not Selector.parse("a[x]").is_whole


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("a", "a#/x", True),
        ("a[c]", "a", True),
        ("a", "b", False),
        ("a#/coolant", "a#/coolant/flow", True),
        ("a#/coolant/flow", "a#/coolant/flow_lpm", False),
        ("a#/coolant/flow", "a#/coolant/flow", True),
        ("a#/x", "a#/y", False),
        ("a[p,q]", "a[q,r]", True),
        ("a[p]", "a[q]", False),
        ("a#/x", "a[x]", False),
    ],
)
def test_covers(a: str, b: str, expected: bool) -> None:
    assert Selector.parse(a).covers(Selector.parse(b)) is expected
    assert Selector.parse(b).covers(Selector.parse(a)) is expected


_ident = st.sampled_from(["a", "b"])
_seg = st.sampled_from(["x", "xy", "y", "0"])
_selectors = st.one_of(
    _ident.map(Selector.parse),
    st.tuples(_ident, st.lists(_seg, min_size=1, max_size=3)).map(
        lambda t: Selector.parse(f"{t[0]}#/{'/'.join(t[1])}")
    ),
    st.tuples(_ident, st.lists(_seg, min_size=1, max_size=3)).map(
        lambda t: Selector.parse(f"{t[0]}[{','.join(t[1])}]")
    ),
)


@given(_selectors, _selectors)
def test_covers_symmetric(a: Selector, b: Selector) -> None:
    assert a.covers(b) == b.covers(a)


@given(_selectors)
def test_roundtrip_and_reflexive(s: Selector) -> None:
    assert Selector.parse(s.render()) == s
    assert s.covers(s)
