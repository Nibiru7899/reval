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
