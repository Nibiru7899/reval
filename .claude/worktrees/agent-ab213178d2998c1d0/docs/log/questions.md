# Open questions

Agents append here instead of guessing on semantics (see `.claude/skills/next-task`). A human or Opus resolves them
(`.claude/skills/phase-refine`) and writes the decision under the question. Never delete entries.

## Template

```
### Q-NNN (task P?-??) — <short title>            status: open | resolved
- Context: <what you were implementing, file/function>
- Question: <the exact ambiguity>
- Options: (a) … (b) …
- Recommendation: <option + one-line reason>
- Decision (filled by resolver, date): …
```

### Q-P5-19 (task P5-19) — CQR needs quantile models in the uq artifacts            status: open
- Context: `interval_method="cqr"` (A8) in `examples/motor_thermal/motor/producers.py` raises `ProducerError("interval_method=cqr needs quantile models; see Q-P5-19")`: CQR needs lower/upper quantile predictions of the peak, and none exist at predict time.
- Question: `scripts/calibrate.py` fits no lower/upper quantile models, so the A8 config raises until it does. Who extends calibrate.py (quantile HGB at alpha/2, 1-alpha/2 on peaks) and with what interface?
- Options: (a) extend calibrate.py in a follow-up task; (b) use `NormalizedConformal` with a local difficulty estimate instead.
- Recommendation: (a), because CQR is the documented A8 method.
- Decision (filled by resolver, date): …

### Q-P5-19b (task P5-19) — spec names and the missing A4 `off` arm            status: open
- Context: the P5-19 spec calls the switches `ad_mode` / `uncertainty`; the existing binding names in `ReValSettings` (docs/10) are `ad_gate` / `interval_method`. They were kept.
- Question: (1) confirm the spec names are updated to the docs/10 names. (2) `bench/configs/ablations/a4_ad_modes.yaml` covers only the `relaxed` arm; the `off` arm needs a second config (`settings: {ad_gate: off}`, run with `REVAL_BENCH=1`), not yet added.
- Recommendation: update the spec; add `a4_ad_off.yaml` when the pilot (P5-17) needs it.
- Decision (filled by resolver, date): …
