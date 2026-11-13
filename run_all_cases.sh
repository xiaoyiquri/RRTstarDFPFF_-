#!/usr/bin/env bash

set -uo pipefail

# Six benchmark environments
CASES=(
    uni_bugtrap
    uni_wall
    quad2d_bugtrap
    quad2d_hole
    quad3d_block
    quad3d_window
)

FAILED_CASES=()

for CASE_NAME in "${CASES[@]}"; do

    echo "============================================"
    echo "Running environment: $CASE_NAME"
    echo "============================================"

    if CASE="$CASE_NAME" bash ./run_one_case.sh; then
        echo "SUCCESS: $CASE_NAME"
    else
        echo "WARNING: $CASE_NAME failed"
        FAILED_CASES+=("$CASE_NAME")
    fi

done

echo "============================================"
echo "All six environments processed"
echo "============================================"

if (( ${#FAILED_CASES[@]} > 0 )); then
    printf 'Failed environments: %s\n' "${FAILED_CASES[@]}"
    exit 1
fi

echo "All environments completed successfully"
