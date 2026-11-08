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
- Context: `interval_method="cqr"` (A8) in `examples/motor_thermal/motor/producers.py` reads `uq["cqr"]`, a fitted `reval.uq.CQR` on per-length-class peak quantile predictions.
- Question: `scripts/calibrate.py` fits no lower/upper quantile models, so the A8 config raises until it does. Who extends calibrate.py (quantile HGB at alpha/2, 1-alpha/2 on peaks) and with what interface?
- Options: (a) extend calibrate.py in a follow-up task; (b) use `NormalizedConformal` with a local difficulty estimate instead.
- Recommendation: (a), because CQR is the documented A8 method.
- Decision (filled by resolver, date): …
