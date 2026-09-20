#!/usr/bin/env bash
# Score the pipeline on freshly generated inboxes it has never seen.
#
# The sample data comes from a deterministic generator. A different --seed keeps the
# email templates and document layouts but redraws every company, port, weight and
# defect placement — which is the closest thing we have to "the judges run us on their
# own data". Any rule that quietly memorised an instance value shows up here.
#
#   ./scripts/check_robustness.sh /path/to/data_v2            # the generator's folder
#   ./scripts/check_robustness.sh /path/to/data_v2 "7 1234"   # specific seeds
#
# Runs rules-only (LLM_MAX_CALLS=0) so it costs nothing and measures the deterministic
# path on its own.
set -euo pipefail

GEN="${1:?usage: check_robustness.sh <path to data_v2 with generate.py> [seeds]}"
SEEDS="${2:-7 1234 20260920 99999}"
PY="${PYTHON:-python}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "generator: $GEN"
echo "seeds:     $SEEDS"
echo

for seed in $SEEDS; do
    out="$WORK/seed-$seed"
    mkdir -p "$out"
    ( cd "$GEN" && "$PY" generate.py --seed "$seed" --n 250 --out "$out" ) >/dev/null 2>&1
    ( cd "$ROOT" && LLM_MAX_CALLS=0 "$PY" -m src.pipeline \
        --data-dir "$out" --out "$out/submission.json" ) >/dev/null 2>&1
    ( cd "$ROOT" && "$PY" scripts/evaluate.py \
        --ground-truth "$out/ground_truth.json" \
        --submission "$out/submission.json" ) \
      | grep -E "FINAL SCORE|end-to-end|emails wrong|no errors" \
      | sed "s/^/  seed $seed  /"
    echo
done
