import importlib.util
from pathlib import Path

import joblib
from motor.models import TrajectoryModel, save
from motor.splits import Splits, save_splits

SCRIPT = Path("examples/motor_thermal/scripts/calibrate.py")


def test_calibrate_main_writes_artifact(synthetic_measures, tmp_path):
    df = synthetic_measures(n_profiles=6, n_rows=1500, seed=3)
    df.to_parquet(tmp_path / "m.parquet")
    splits = Splits(train=(10, 11, 12), calib=(13, 14), test=(15,), reserve=())
    save_splits(splits, tmp_path / "splits.yaml", seed=0, source_note="synthetic")
    models = tmp_path / "models"
    model = TrajectoryModel("ridge", targets=("pm",)).fit(df[df.profile_id.isin(splits.train)])
    save(model, models / "tpm_ridge.joblib", meta={})

    spec = importlib.util.spec_from_file_location("calibrate_script", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.main(
        [
            "--model-artifact", "tpm_ridge",
            "--data", str(tmp_path / "m.parquet"),
            "--splits", str(tmp_path / "splits.yaml"),
            "--models-dir", str(models),
        ]
    )  # fmt: skip
    art = joblib.load(out)
    assert set(art) == {"conformal", "ad", "meta"}
    assert {"alpha", "split_hash", "model_hash"} <= set(art["meta"])
    assert art["meta"]["alpha"] == 0.1
    assert ("pm", "short") in art["conformal"].conformal
    assert isinstance(art["ad"], dict)
