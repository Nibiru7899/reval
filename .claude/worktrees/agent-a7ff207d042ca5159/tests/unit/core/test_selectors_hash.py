from reval.core.selectors import derived_closure, selector_hash
from reval.domain import Artifact, ArtifactKind, ArtifactVersion, Snapshot


def _snap(**versions: ArtifactVersion) -> Snapshot:
    arts = {
        "params": Artifact(id="params", kind=ArtifactKind.PARAMS, path="p.yaml", hasher="yaml-fields"),
        "data": Artifact(id="data", kind=ArtifactKind.DATASET, path="d.csv", hasher="dataframe", key=("g",)),
        "gone": Artifact(id="gone", kind=ArtifactKind.CODE, path="x", hasher="file"),
        "m1": Artifact(id="m1", kind=ArtifactKind.MODEL, path="m1", hasher="model", derived_from=("data",)),
        "m2": Artifact(
            id="m2", kind=ArtifactKind.MODEL, path="m2", hasher="model", derived_from=("m1", "params")
        ),
    }
    return Snapshot.create(
        manifest_hash="m",
        quantities={},
        artifacts=arts,
        versions=versions,
        assumptions={},
        requirements={},
        subjects={},
        claims={},
        policies={},
        producers={},
    )


def _params(**fh: str) -> ArtifactVersion:
    return ArtifactVersion(artifact_id="params", content_hash="P", field_hashes=fh)


def test_pointer_subtree_is_segmentwise() -> None:
    base = {"/coolant/flow": "1", "/coolant/flow_lpm": "2", "/coolant/t": "3", "/other": "4"}
    s = _snap(params=_params(**base))
    h = selector_hash(s, "params#/coolant/flow")
    # flow_lpm is a sibling, not part of the /coolant/flow subtree
    s2 = _snap(params=_params(**{**base, "/coolant/flow_lpm": "X", "/other": "Y"}))
    assert selector_hash(s2, "params#/coolant/flow") == h
    s3 = _snap(params=_params(**{**base, "/coolant/flow": "X"}))
    assert selector_hash(s3, "params#/coolant/flow") != h
    # subtree: a deeper leaf changes the parent's hash
    sub = _snap(params=_params(**{"/a/b": "1", "/a/c": "2"}))
    sub2 = _snap(params=_params(**{"/a/b": "1", "/a/c": "9"}))
    assert selector_hash(sub, "params#/a") != selector_hash(sub2, "params#/a")
    assert selector_hash(sub, "params#/a/b") == selector_hash(sub2, "params#/a/b")


def test_columns() -> None:
    def v(t: str, x: str) -> ArtifactVersion:
        return ArtifactVersion(
            artifact_id="data",
            content_hash="D" + t + x,
            field_hashes={"c=temp": t, "c=x": x, "g=1/c=temp": "q"},
        )

    a, b = _snap(data=v("1", "1")), _snap(data=v("2", "1"))
    assert selector_hash(a, "data[x]") == selector_hash(b, "data[x]")
    assert selector_hash(a, "data[temp]") != selector_hash(b, "data[temp]")
    assert selector_hash(a, "data[temp,x]") != selector_hash(b, "data[temp,x]")
    assert selector_hash(a, "data[x,temp]") == selector_hash(a, "data[temp,x]")


def test_whole_and_missing() -> None:
    s = _snap(params=_params(**{"/a": "1"}), gone=ArtifactVersion(artifact_id="gone", content_hash="missing"))
    assert selector_hash(s, "params") == "P"
    assert selector_hash(s, "gone") == "missing"
    assert selector_hash(s, "gone#/a") == "missing"
    assert selector_hash(s, "data[temp]") == "missing"  # no version recorded
    assert selector_hash(s, "nonexistent") == "missing"


def test_derived_closure_transitive() -> None:
    s = _snap()
    assert derived_closure(s, "m2") == frozenset({"m1", "data", "params"})
    assert derived_closure(s, "m1") == frozenset({"data"})
    assert derived_closure(s, "data") == frozenset()
    assert derived_closure(s, "unknown") == frozenset()
