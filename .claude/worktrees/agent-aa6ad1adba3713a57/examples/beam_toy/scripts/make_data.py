"""Generate inputs/samples.csv and fitted/surrogate.json for the beam toy (deterministic, seed 0).

x = P L^3 / (E b h^3) in mm. The "experiment" is the analytic tip deflection 4x plus small noise, so the
fitted surrogate (a slope through the origin) is a stand-in for any learned model trained on test data.
Run from the repository root:  python examples/beam_toy/scripts/make_data.py
"""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    rng = np.random.default_rng(0)
    x = np.linspace(1.5, 12.0, 15)
    defl = 4.0 * x + rng.normal(0.0, 0.05, size=x.size)
    lines = ["sample,x_mm,defl_mm"] + [
        f"s{i:02d},{xi:.4f},{di:.4f}" for i, (xi, di) in enumerate(zip(x, defl, strict=True))
    ]
    (ROOT / "inputs" / "samples.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    slope = float(np.dot(x, defl) / np.dot(x, x))
    (ROOT / "fitted" / "surrogate.json").write_text(
        json.dumps({"slope": round(slope, 6)}) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
