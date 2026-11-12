import numpy as np
import pandas as pd
from motor.drive_map import DriveMap
from motor.features import INPUT_COLUMNS


def _linear_df(n_prof: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    frames = []
    for pid in range(n_prof):
        # Piecewise-constant torque/speed holds, so most rows are steady.
        torque = np.repeat(rng.uniform(0, 100, 40), 100)
        speed = np.repeat(rng.uniform(500, 3000, 40), 100)
        frames.append(
            pd.DataFrame(
                {
                    "profile_id": pid,
                    "torque": torque,
                    "motor_speed": speed,
                    "i_q": 2.0 * torque + 0.01 * speed,
                    "i_d": -0.5 * torque - 0.02 * speed,
                    "u_q": 0.03 * speed + 0.1 * torque,
                    "u_d": -0.01 * speed + 0.2 * torque,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_recovers_linear_map_and_domain() -> None:
    df = _linear_df()
    dm = DriveMap().fit(df)
    test = _linear_df(3).assign(profile_id=lambda d: d.profile_id + 100)
    r2 = dm.r2(test)
    assert all(r2[o] > 0.99 for o in ("i_d", "i_q", "u_d", "u_q"))
    inside = dm.domain_report(np.array([50.0] * 5), np.array([1500.0] * 5))
    assert inside.inside
    far = dm.domain_report(np.array([500.0]), np.array([20000.0]))
    assert not far.inside
    assert set(far.violating_features) == {"torque", "motor_speed"}


def test_to_inputs_columns_and_broadcast() -> None:
    dm = DriveMap().fit(_linear_df())
    x = dm.to_inputs(
        np.array([10.0, 20.0, 30.0]), np.array([1000.0, 1100.0, 1200.0]), 45.0, np.array([25.0] * 3)
    )
    assert list(x.columns) == list(INPUT_COLUMNS)
    assert len(x) == 3 and (x["coolant"] == 45.0).all()
    assert x["motor_speed"].tolist() == [1000.0, 1100.0, 1200.0]
