# Motor-thermal reference project

The reference engineering project that ReVal validates (see `docs/05-motor-domain.md`). It is built in Phase 1 (tasks `P1-*` in `docs/tasks/`).

Planned layout:

```
reval.yaml            manifest (claims, requirements, assumptions, artifacts)
splits.yaml           fixed profile-level splits (committed)
params/               lptn.yaml, cooling.yaml, limits.yaml (committed, small)
motor/                python package: data, features, models, conformal, domain, lptn, drive_map, cycles, optimizer, producers
scripts/              download_data.py, prepare.py, train.py, calibrate_lptn.py, sensitivities.py
data/ models/         generated, git-ignored
```
