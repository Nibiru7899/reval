import importlib.util
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from motor.data import EXPECTED_COLUMNS, load_raw, prepare, validate

from reval.errors import SchemaError

ROOT = Path(__file__).resolve().parents[3] / "examples" / "motor_thermal"


def _load_script():
    spec = importlib.util.spec_from_file_location("download_data", ROOT / "scripts" / "download_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_valid_synthetic_frame_passes(synthetic_measures):
    df = synthetic_measures()
    assert tuple(df.columns) == EXPECTED_COLUMNS
    validate(df)


def test_synthetic_is_deterministic_and_realistic(synthetic_measures):
    a, b = synthetic_measures(seed=3), synthetic_measures(seed=3)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(synthetic_measures(seed=4))
    assert a["i_q"].abs().max() <= 250
    assert a["motor_speed"].between(0, 6000).all()
    assert a["coolant"].between(18, 70).all()


def test_missing_column_raises(synthetic_measures):
    with pytest.raises(SchemaError, match="pm"):
        validate(synthetic_measures().drop(columns=["pm"]))


def test_extra_column_raises(synthetic_measures):
    with pytest.raises(SchemaError, match="bogus"):
        validate(synthetic_measures().assign(bogus=1.0))


def test_nan_raises(synthetic_measures):
    df = synthetic_measures()
    df.loc[5, "coolant"] = float("nan")
    with pytest.raises(SchemaError, match="coolant"):
        validate(df)


def test_non_integer_profile_id_raises(synthetic_measures):
    with pytest.raises(SchemaError, match="profile_id"):
        validate(synthetic_measures().astype({"profile_id": float}))


def test_empty_frame_raises(synthetic_measures):
    with pytest.raises(SchemaError):
        validate(synthetic_measures().iloc[0:0])


def test_load_raw_order_insensitive(synthetic_measures, tmp_path):
    csv = tmp_path / "m.csv"
    synthetic_measures()[list(reversed(EXPECTED_COLUMNS))].to_csv(csv, index=False)
    assert set(load_raw(csv).columns) == set(EXPECTED_COLUMNS)


def test_prepare_t_restarts_per_profile(synthetic_measures, tmp_path):
    csv = tmp_path / "m.csv"
    synthetic_measures(n_profiles=3, n_rows=50).to_csv(csv, index=False)
    out = prepare(csv, tmp_path / "out" / "m.parquet")
    df = pd.read_parquet(out)
    assert df.groupby("profile_id")["t"].min().eq(0.0).all()
    assert (df.groupby("profile_id")["t"].diff().dropna() == 0.5).all()
    assert df["profile_id"].is_monotonic_increasing


def test_extract_and_skip_logic(tmp_path, capsys):
    mod = _load_script()
    raw = tmp_path / "raw"
    raw.mkdir()
    with zipfile.ZipFile(raw / "archive.zip", "w") as zf:
        zf.writestr("measures_v2.csv", "a,b\n1,2\n")
        zf.writestr("other.txt", "x")
    csv = mod.extract_csv(raw / "archive.zip", raw)
    assert csv.read_text() == "a,b\n1,2\n"
    assert not (raw / "archive.zip").exists()
    # CSV present -> no download is attempted (would hit the network otherwise).
    assert mod.ensure_raw_csv(raw) == csv
    assert "skipping download" in capsys.readouterr().out


def test_two_csvs_rejected(tmp_path):
    mod = _load_script()
    (tmp_path / "measures_v2.csv").write_text("a\n")
    (tmp_path / "extra.csv").write_text("a\n")
    with pytest.raises(SystemExit):
        mod.ensure_raw_csv(tmp_path)


@pytest.mark.data
def test_real_parquet():
    path = ROOT / "data" / "processed" / "measures.parquet"
    if not path.exists():
        pytest.skip("run scripts/download_data.py first")
    df = pd.read_parquet(path)
    assert df.shape[1] == 14
    assert len(df) > 1_000_000
