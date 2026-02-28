#!/usr/bin/env bash
set -euo pipefail

ORIGIN="full_test"
COLOR_ORIGIN="\033[90m"
COLOR_STAGE="\033[94m"
COLOR_RESET="\033[0m"

color_enabled() {
  [[ -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]
}

log_with_color() {
  local level="$1"
  shift
  local message="$*"
  local ts
  ts="$(date +"%Y-%m-%d %H:%M:%S")"
  local prefix="[$ts] [$ORIGIN] [$level]"
  local line="${prefix} ${message}"
  if color_enabled; then
    local color="${COLOR_ORIGIN}"
    if [[ "${level^^}" == "STEP" && ! "${message}" == Running\ * && ! "${message}" == Executing\ * ]]; then
      color="${COLOR_STAGE}"
    fi
    echo -e "${color}${line}${COLOR_RESET}"
  else
    echo "${line}"
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/artifacts"
LOG_FILE="${LOG_DIR}/orchestrate.log"

mkdir -p "${LOG_DIR}"
log_with_color STEP "Wrapper starting log_file=${LOG_FILE}"

set +e
"${SCRIPT_DIR}/orchestrate.sh" 2>&1 | tee "${LOG_FILE}"
ORCH_RC=${PIPESTATUS[0]}
set -e

log_with_color INFO "orchestrate.sh finished rc=${ORCH_RC}"
if [[ "${ORCH_RC}" -ne 0 ]]; then
  log_with_color ERROR "orchestrate.sh failed rc=${ORCH_RC} log_file=${LOG_FILE}"
  exit "${ORCH_RC}"
fi

EXPECTED_PATTERNS=(
  "============================="
  "Starting isolated cycle run=1; provisioning and mounting volume"
  "Cycle complete; unmounting and detaching loop device run=1"
  "Post-unmount directory proof run=1"
  "Post-unmount image-folder proof run=1"
  "Starting isolated cycle run=2; provisioning and mounting volume"
  "Mounted volume state before external run run=2"
  "Cycle complete; unmounting and detaching loop device run=2"
  "Post-unmount directory proof run=2"
  "Post-unmount image-folder proof run=2"
  "Volume provisioned"
  "No space left on device; volume is full"
  "Edge node runner completed successfully"
  "Orchestration complete rc=0"
)

missing=()
for pattern in "${EXPECTED_PATTERNS[@]}"; do
  if ! grep -q "${pattern}" "${LOG_FILE}"; then
    missing+=("${pattern}")
  fi
done

if [[ "${#missing[@]}" -ne 0 ]]; then
  log_with_color ERROR "Expected output missing count=${#missing[@]}"
  for pattern in "${missing[@]}"; do
    log_with_color ERROR "Missing pattern=${pattern}"
  done
  log_with_color ERROR "Wrapper status=FAIL log_file=${LOG_FILE}"
  exit 1
fi

log_with_color INFO "Wrapper status=PASS log_file=${LOG_FILE}"
