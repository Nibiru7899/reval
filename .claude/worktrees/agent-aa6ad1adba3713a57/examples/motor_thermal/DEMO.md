# Interim demo: a coolant-flow change on the motor project

`demo_change.sh` (bash) and `demo_change.ps1` (PowerShell) run this on a **throwaway copy** of the motor project in a
temporary git repository; the real `params/` are never touched.

1. Baseline: `reval snapshot --write`, `reval run --all`, commit the lock.
2. Small change: `params/cooling.yaml` `flow_scale` 1.00 to 0.95, re-lock, commit, `reval diff HEAD~1 HEAD`.
   Expected at the evidence level:
   - `lptn_sim` evidence is carried forward, with its interval widened by κ·s·|Δ| (about 1.6 K). It declares a sensitivity tolerance on
     `cooling#/flow_scale`.
   - Bench measurements are invalidated: a measurement taken at the old flow doesn't support a claim at the new flow.
   - ML evidence is invalidated too. It depends on `flow_scale` without a tolerance, so it fails closed.

   At the claim level, the recorded-cycle claims go STALE. Their high and medium policies need either a fresh measurement or
   physics **plus** independent ML, and carried-forward physics alone isn't enough. `reval plan` then picks the cheapest restoration.
   `C-SHAFT` is untouched.
3. Large change: `flow_scale` 0.95 to 0.75, re-lock, commit, `reval diff HEAD~1 HEAD`. Expected: the change exceeds the
   tolerance's valid range, so the carried evidence is invalidated as well.

Requires the processed data and trained models (see `README.md`). Exit code of `reval diff` is 1 (stale or inconclusive) or
2 (violated) by design; the scripts do not treat that as failure. Statuses are "supported by recorded evidence against the
declared requirement", not a safety statement.

<!-- demo-output:start -->
```text
$ reval snapshot --write ; reval run --all   (baseline, flow_scale: 1.0)
snapshot e46165147d70c52bf75f4b185fc3099e2b60fd7423d092ead9ef4ced3e05b132
wrote C:\Users\SAI KRISHNA\AppData\Local\Temp\reval-demo-b10a1828fa88431190a36fc409cdfa51\motor\reval.lock.json
ran 20 producer results
CLAIM     BEFORE        AFTER         CLAUSE
C-P01-IS  INCONCLUSIVE  SUPPORTED     2
C-P01-PM  INCONCLUSIVE  INCONCLUSIVE  -
C-P01-SW  INCONCLUSIVE  INCONCLUSIVE  -
C-R01-PM  INCONCLUSIVE  SUPPORTED     0
C-R01-SW  INCONCLUSIVE  SUPPORTED     1
C-SHAFT   INCONCLUSIVE  SUPPORTED     3
(exit code 1)

$ flow_scale 1.0 -> 0.95 ; reval snapshot --write ; reval diff HEAD~1 HEAD
snapshot ed8401efad9fc44de6b7b93ad5fa9a8dd1e5089a81ad8d6d2cf1476387267dc5
wrote C:\Users\SAI KRISHNA\AppData\Local\Temp\reval-demo-b10a1828fa88431190a36fc409cdfa51\motor\reval.lock.json
KIND           TARGET               DETAIL
FIELD_CHANGED  cooling#/flow_scale  1.0 -> 0.95; delta -0.05

CLAIM     BEFORE        AFTER         AFFECTED  REASONS
C-P01-IS  SUPPORTED     SUPPORTED     no        policy_satisfied
C-P01-PM  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-P01-SW  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-R01-PM  SUPPORTED     STALE         yes       evidence_invalidated
C-R01-SW  SUPPORTED     STALE         yes       evidence_invalidated
C-SHAFT   SUPPORTED     SUPPORTED     no        policy_satisfied
(exit code 1)

$ flow_scale 0.95 -> 0.75 ; reval snapshot --write ; reval diff HEAD~1 HEAD
snapshot d40d2ec38e5dfbb61baa574203d37410e140a283f116dfebd7a9ab298ca90a81
wrote C:\Users\SAI KRISHNA\AppData\Local\Temp\reval-demo-b10a1828fa88431190a36fc409cdfa51\motor\reval.lock.json
KIND           TARGET               DETAIL
FIELD_CHANGED  cooling#/flow_scale  0.95 -> 0.75; delta -0.2

CLAIM     BEFORE        AFTER         AFFECTED  REASONS
C-P01-IS  SUPPORTED     SUPPORTED     no        policy_satisfied
C-P01-PM  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-P01-SW  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-R01-PM  STALE         STALE         yes       evidence_invalidated
C-R01-SW  STALE         STALE         yes       evidence_invalidated
C-SHAFT   SUPPORTED     SUPPORTED     no        policy_satisfied
(exit code 1)
```
<!-- demo-output:end -->
