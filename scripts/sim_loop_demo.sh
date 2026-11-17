#!/usr/bin/env bash
# End-to-end simulation loop demo (PART S11).
#
# On development seeds only: generates a small set of plants, runs the referee on a small
# development exam, runs one breaker round, records findings, replays the regression suite,
# and prints the round report. Finishes quickly on a laptop.
#
# Output makes clear: results are SIMULATED and from development seeds.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WORK_DIR="${WORK_DIR:-/tmp/phos-sim-loop-demo-$$}"
mkdir -p "$WORK_DIR"

echo "=== PHOS Sim Loop Demo (PART S11) ==="
echo "Work dir: $WORK_DIR"
echo "All results are SIMULATED on development seeds only."
echo

# 1. Set up seed vaults (development only)
export PHOS_SEEDS_DEV="$WORK_DIR/dev.seedvault.json"
export PHOS_SEEDS_PUBLIC="$WORK_DIR/public.seedvault.json"
export PHOS_SEEDS_PRIVATE="$WORK_DIR/private.seedvault.json"
export PHOS_SEEDS_RETIRED="$WORK_DIR/retired.seedvault.json"

echo "[1/6] Seeding development pool..."
echo '[{"family": "level_flow", "seed": 4242}, {"family": "water", "seed": 7101}]' > "$PHOS_SEEDS_DEV"
touch "$PHOS_SEEDS_PUBLIC" "$PHOS_SEEDS_PRIVATE" "$PHOS_SEEDS_RETIRED"

# 2. Generate a small development exam
echo "[2/6] Making a small development exam (2 plants)..."
phos-referee make-exam \
    --pool dev \
    --scorer-version "s11-demo" \
    --size 2 \
    --hours 1.0 \
    --out "$WORK_DIR/exam.json"

# 3. Run the referee on the exam with the threshold detector
echo "[3/6] Running the referee on the exam..."
phos-referee run \
    --exam "$WORK_DIR/exam.json" \
    --detector "phos.referee.demo:threshold_detector" \
    --work-dir "$WORK_DIR/work" \
    --out "$WORK_DIR/scores.json"

# 4. Render the report
echo "[4/6] Rendering the referee report..."
phos-referee report \
    --exam "$WORK_DIR/exam.json" \
    --run "$WORK_DIR/scores.json" \
    --out "$WORK_DIR/report"

# 5. Run one breaker round
echo "[5/6] Running one breaker round (development seeds only)..."
phos-breaker round \
    --detector "phos.eval:ThresholdDetector" \
    --strategy random \
    --budget 10 \
    --plants 2 \
    --seed 20261116 \
    --work-dir "$WORK_DIR/breaker"

# 6. Print the round report
echo "[6/6] Round report summary..."
echo
echo "=== RESULTS (SIMULATED, development seeds only) ==="
echo
cat "$WORK_DIR/report"/*.md 2>/dev/null || echo "(markdown report at $WORK_DIR/report)"
echo
echo "=== Demo complete. All results are SIMULATED. ==="
