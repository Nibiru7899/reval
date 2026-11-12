#!/usr/bin/env bash
# Interim demo (P3-08): coolant flow_scale change on a throwaway copy of the motor project.
# Usage: bash examples/motor_thermal/demo_change.sh   (needs data/ and models/ present; see README.md)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
if [ -n "${REVAL:-}" ]; then R="$REVAL"
elif [ -x "$REPO/.venv/Scripts/reval.exe" ]; then R="$REPO/.venv/Scripts/reval.exe"
elif [ -x "$REPO/.venv/bin/reval" ]; then R="$REPO/.venv/bin/reval"
else R="reval"; fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PROJ="$WORK/motor"
OUT="$WORK/demo_output.txt"
mkdir -p "$PROJ"
# Copy the project (including git-ignored data/ and models/, which the lock hashes), minus caches and stores.
(cd "$HERE" && tar --exclude='.reval' --exclude='__pycache__' --exclude='notebooks' -cf - .) | (cd "$PROJ" && tar -xf -)

export GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.com GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.com
cd "$PROJ"
git init -q
git config core.autocrlf false
printf '.reval/\n__pycache__/\ndata/\nmodels/\n' > .gitignore

# The full manifest declares ~170 claims, and `run --all` over all of them takes hours. The demo trims the COPY's claim
# list to a few subjects (DEMO_FULL=1 keeps everything); the real reval.yaml is untouched.
if [ -z "${DEMO_FULL:-}" ]; then
  awk '/^claims:/{c=1} c && /^  - \{id/ && $0 !~ /subject: (DC-P01|DC-R01|SHAFT-1)\}/ {next} {print}' reval.yaml >reval.yaml.new
  mv reval.yaml.new reval.yaml
fi

set_flow() { sed -i.bak "s/^flow_scale: .*/flow_scale: $1/" params/cooling.yaml && rm -f params/cooling.yaml.bak; }
commit() { git add -A && git commit -q -m "$1"; }
# `reval diff` exits 1 or 2 when claims are stale or violated; that is the expected result here.
rv() { "$R" "$@" --project "$PROJ" || echo "(exit code $?)"; }

{
  echo '$ reval snapshot --write ; reval run --all   (baseline, flow_scale: 1.0)'
  rv snapshot --write
  rv run --all
} >"$OUT" 2>&1
commit "baseline lock"

set_flow 0.95
{
  echo
  echo '$ flow_scale 1.0 -> 0.95 ; reval snapshot --write ; reval diff HEAD~1 HEAD'
  rv snapshot --write
} >>"$OUT" 2>&1
commit "flow_scale 0.95"
rv diff HEAD~1 HEAD >>"$OUT" 2>&1

set_flow 0.75
{
  echo
  echo '$ flow_scale 0.95 -> 0.75 ; reval snapshot --write ; reval diff HEAD~1 HEAD'
  rv snapshot --write
} >>"$OUT" 2>&1
commit "flow_scale 0.75"
rv diff HEAD~1 HEAD >>"$OUT" 2>&1

cat "$OUT"

# Fill the marked block of DEMO.md with this output (the only file of the real project this script edits).
awk -v out="$OUT" '
  /<!-- demo-output:start -->/ { print; print "```text"; while ((getline line < out) > 0) print line; print "```"; skip=1; next }
  /<!-- demo-output:end -->/ { skip=0 }
  !skip { print }
' "$HERE/DEMO.md" >"$WORK/DEMO.new" && cp "$WORK/DEMO.new" "$HERE/DEMO.md"
echo "demo output written to $HERE/DEMO.md"
