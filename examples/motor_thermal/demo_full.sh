#!/usr/bin/env bash
# M4 demo (P4-15): baseline -> coolant change -> diff -> plan -> run --plan latest -> status -> report --html + explain.
# Usage: bash examples/motor_thermal/demo_full.sh   (needs data/ and models/ present; see README.md)
# Env: REVAL (cli path), DEMO_FULL=1 (keep all ~170 claims; takes hours), DEMO_KEEP=<dir> (copy transcript, JSON and
# the HTML report there), DEMO_LOG=<file> (also write a generated markdown summary of the run).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
if [ -n "${REVAL:-}" ]; then R="$REVAL"
elif [ -x "$REPO/.venv/Scripts/reval.exe" ]; then R="$REPO/.venv/Scripts/reval.exe"
elif [ -x "$REPO/.venv/bin/reval" ]; then R="$REPO/.venv/bin/reval"
else R="reval"; fi
if [ -x "$REPO/.venv/Scripts/python.exe" ]; then PY="$REPO/.venv/Scripts/python.exe"
elif [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"
else PY="python"; fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PROJ="$WORK/motor"
OUT="$WORK/demo_output.txt"
mkdir -p "$PROJ"
(cd "$HERE" && tar --exclude='.reval' --exclude='__pycache__' --exclude='notebooks' -cf - .) | (cd "$PROJ" && tar -xf -)

export GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.com GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.com
cd "$PROJ"
git init -q
git config core.autocrlf false
printf '.reval/\n__pycache__/\ndata/\nmodels/\n' > .gitignore

# Trim the COPY's claims to a few subjects (ML producers take ~6 s each); the real reval.yaml is untouched.
if [ -z "${DEMO_FULL:-}" ]; then
  awk '/^claims:/{c=1} c && /^  - \{id/ && $0 !~ /subject: (DC-P01|DC-R01|SHAFT-1)\}/ {next} {print}' reval.yaml >reval.yaml.new
  mv reval.yaml.new reval.yaml
fi

set_flow() { sed -i.bak "s/^flow_scale: .*/flow_scale: $1/" params/cooling.yaml && rm -f params/cooling.yaml.bak; }
commit() { git add -A && git commit -q -m "$1"; }
# Exit codes 1/2 (stale/violated) are expected results of diff/status, not failures.
rv() { "$R" "$@" --project "$PROJ" || echo "(exit code $?)"; }
step() { { echo; echo "\$ $*"; } >>"$OUT"; }

step "reval snapshot --write ; reval run --all   (baseline, flow_scale: 1.0)"
{ rv snapshot --write; rv run --all; } >>"$OUT" 2>&1
commit "baseline lock"

set_flow 0.95
step "flow_scale 1.0 -> 0.95 ; reval snapshot --write ; reval diff HEAD~1 HEAD"
rv snapshot --write >>"$OUT" 2>&1
commit "flow_scale 0.95"
rv diff HEAD~1 HEAD >>"$OUT" 2>&1

step "reval status   (before restoration)"
rv status >>"$OUT" 2>&1
"$R" status --format json --project "$PROJ" >"$WORK/status_before.json" || true

step "reval plan"
rv plan >>"$OUT" 2>&1
"$R" plan --format json --project "$PROJ" >"$WORK/plan.json"

step "reval run --plan latest"
rv run --plan latest >>"$OUT" 2>&1

step "reval status   (after restoration)"
rv status >>"$OUT" 2>&1
"$R" status --format json --project "$PROJ" >"$WORK/status_after.json" || true

step "reval report --html --out report.html"
"$R" report --html --out "$WORK/report.html" --project "$PROJ" >>"$OUT" 2>&1
test -s "$WORK/report.html"
echo "report.html: $(wc -c <"$WORK/report.html") bytes" >>"$OUT"

CLAIM="${DEMO_CLAIM:-C-R01-PM}"
step "reval explain $CLAIM"
rv explain "$CLAIM" >>"$OUT" 2>&1

cat "$OUT"
if [ -n "${DEMO_KEEP:-}" ]; then
  mkdir -p "$DEMO_KEEP"
  cp "$OUT" "$DEMO_KEEP/demo_output.txt"
  cp "$WORK"/*.json "$WORK/report.html" "$DEMO_KEEP/"
  echo "kept transcript, JSON and report.html in $DEMO_KEEP"
fi
if [ -n "${DEMO_LOG:-}" ]; then
  "$PY" "$HERE/scripts/demo_log.py" --plan "$WORK/plan.json" --before "$WORK/status_before.json" \
    --after "$WORK/status_after.json" --transcript "$OUT" --out "$DEMO_LOG"
fi
echo "demo_full: OK"
