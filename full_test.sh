#!/usr/bin/env bash
set -euo pipefail

COLOR_RESET="\033[0m"
COLOR_STEP="\033[36m"
COLOR_INFO="\033[32m"
COLOR_WARN="\033[33m"
COLOR_ERROR="\033[31m"

color_enabled() {
  [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]
}

log_with_color() {
  local level="$1"
  shift
  local message="$*"
  local ts
  ts="$(date +"%Y-%m-%d %H:%M:%S")"
  local prefix="[$ts] [$level]"
  local color=""
  case "$level" in
    STEP) color="$COLOR_STEP" ;;
    INFO) color="$COLOR_INFO" ;;
    WARN) color="$COLOR_WARN" ;;
    ERROR) color="$COLOR_ERROR" ;;
  esac
  if color_enabled && [[ -n "$color" ]]; then
    echo -e "${color}${prefix}${COLOR_RESET} ${message}"
  else
    echo "${prefix} ${message}"
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/artifacts"
LOG_FILE="${LOG_DIR}/orchestrate.log"

mkdir -p "${LOG_DIR}"
log_with_color STEP "Wrapper starting log_file=${LOG_FILE}"

set +e
NO_COLOR=1 "${SCRIPT_DIR}/orchestrate.sh" 2>&1 | tee "${LOG_FILE}"
ORCH_RC=${PIPESTATUS[0]}
set -e

log_with_color INFO "orchestrate.sh finished rc=${ORCH_RC}"
if [[ "${ORCH_RC}" -ne 0 ]]; then
  log_with_color ERROR "orchestrate.sh failed rc=${ORCH_RC} log_file=${LOG_FILE}"
  exit "${ORCH_RC}"
fi

EXPECTED_PATTERNS=(
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
