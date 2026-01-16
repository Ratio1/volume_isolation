#!/usr/bin/env bash
set -euo pipefail

ORIGIN="edge_node"
COLOR_ORIGIN="\033[97m"
COLOR_RESET="\033[0m"

color_enabled() {
  [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]
}

log_with_color() {
  local level="$1"
  shift
  local message="$*"
  local ts
  ts="$(date +"%Y-%m-%d %H:%M:%S")"
  local prefix="[$ts] [$level] [$ORIGIN]"
  local line="${prefix} ${message}"
  if color_enabled; then
    echo -e "${COLOR_ORIGIN}${line}${COLOR_RESET}"
  else
    echo "${line}"
  fi
}

trap 'log_with_color ERROR "Command failed rc=$? line=$LINENO cmd=$BASH_COMMAND"' ERR

DOCKERD_ARGS="${DOCKERD_ARGS:---host=unix:///var/run/docker.sock}"
DOCKERD_LOG="${DOCKERD_LOG:-/var/log/dockerd.log}"

log_with_color STEP "Starting dockerd cmd=dockerd ${DOCKERD_ARGS} log=${DOCKERD_LOG}"
mkdir -p "$(dirname "$DOCKERD_LOG")"
dockerd ${DOCKERD_ARGS} >"$DOCKERD_LOG" 2>&1 &
DOCKERD_PID=$!
log_with_color INFO "dockerd started pid=${DOCKERD_PID}"

log_with_color STEP "Waiting for docker daemon to become ready"
READY=0
for i in $(seq 1 60); do
  if docker info >/tmp/docker_info.out 2>&1; then
    log_with_color INFO "Docker ready after attempts=${i}"
    READY=1
    break
  else
    last_line=$(tail -n 1 /tmp/docker_info.out 2>/dev/null || true)
    log_with_color WARN "Docker not ready attempt=${i} last_error=${last_line}"
    sleep 1
  fi
done

if [[ "$READY" -ne 1 ]]; then
  log_with_color ERROR "Docker daemon not ready after 60 attempts; see ${DOCKERD_LOG}"
  exit 1
fi

log_with_color STEP "Running edge node runner cmd=python3 /opt/edge_node/run_edge_node.py"
set +e
python3 /opt/edge_node/run_edge_node.py
RC=$?
set -e
log_with_color INFO "Edge node runner exited rc=${RC}"
exit "$RC"
