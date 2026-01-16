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

trap 'log_with_color ERROR "Command failed rc=$? line=$LINENO cmd=$BASH_COMMAND"' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="ratio1/volume_isolation"
EXTERNAL_TAG="${REPO_NAME}:external_container"
EDGE_TAG="${REPO_NAME}:edge_node"
EXTERNAL_DIR="${SCRIPT_DIR}/external_container"
EDGE_DIR="${SCRIPT_DIR}/edge_node"
EXTERNAL_DOCKERFILE="${EXTERNAL_DIR}/Dockerfile"
EDGE_DOCKERFILE="${EDGE_DIR}/Dockerfile"

log_with_color STEP "Orchestration starting repo=${REPO_NAME} script_dir=${SCRIPT_DIR}"
log_with_color INFO "External image tag=${EXTERNAL_TAG} dockerfile=${EXTERNAL_DOCKERFILE} context=${EXTERNAL_DIR}"
log_with_color INFO "Edge image tag=${EDGE_TAG} dockerfile=${EDGE_DOCKERFILE} context=${EDGE_DIR}"

log_with_color STEP "Checking DockerHub login"
if docker info >/tmp/docker_info.txt 2>&1; then
  log_with_color INFO "docker info succeeded output_lines=$(wc -l </tmp/docker_info.txt | tr -d ' ')"
else
  rc=$?
  log_with_color ERROR "docker info failed rc=${rc} output=$(cat /tmp/docker_info.txt)"
  exit 1
fi

DOCKER_USER=""
LOGGED_IN=0

if grep -q "Username:" /tmp/docker_info.txt; then
  DOCKER_USER=$(grep -m1 "Username:" /tmp/docker_info.txt | awk '{print $2}')
  LOGGED_IN=1
  log_with_color INFO "DockerHub login detected via docker info username=${DOCKER_USER}"
fi

CONFIG_PATH=""
CONFIG_EXISTS="false"
CREDS_STORE=""
AUTH_MATCHES=""
while IFS= read -r line; do
  case "${line}" in
    config_path=*) CONFIG_PATH="${line#config_path=}" ;;
    config_exists=*) CONFIG_EXISTS="${line#config_exists=}" ;;
    creds_store=*) CREDS_STORE="${line#creds_store=}" ;;
    auth_matches=*) AUTH_MATCHES="${line#auth_matches=}" ;;
  esac
done < <(python3 - <<'PY'
import json
import os
from pathlib import Path

cfg_dir = Path(os.getenv("DOCKER_CONFIG", Path.home() / ".docker"))
path = cfg_dir / "config.json"
exists = path.exists()
creds_store = ""
auth_matches = []

if exists:
    with path.open() as f:
        data = json.load(f)
    creds_store = data.get("credsStore") or ""
    auths = data.get("auths", {})
    for key in auths.keys():
        if "docker.io" in key or "index.docker.io" in key or "registry-1.docker.io" in key:
            auth_matches.append(key)

print(f"config_path={path}")
print(f"config_exists={str(exists).lower()}")
print(f"creds_store={creds_store}")
print(f"auth_matches={','.join(auth_matches)}")
PY
)

log_with_color INFO "Docker config check path=${CONFIG_PATH} exists=${CONFIG_EXISTS} creds_store=${CREDS_STORE} auth_matches=${AUTH_MATCHES}"

if [[ "${LOGGED_IN}" -eq 0 ]]; then
  if [[ "${CONFIG_EXISTS}" == "true" && -n "${AUTH_MATCHES}" ]]; then
    LOGGED_IN=1
    log_with_color INFO "DockerHub login detected via config auths registries=${AUTH_MATCHES}"
  fi
fi

if [[ "${LOGGED_IN}" -ne 1 ]]; then
  log_with_color ERROR "DockerHub login not detected. Run 'docker login' and retry."
  exit 1
fi

log_with_color STEP "Building external image"
log_with_color INFO "docker build tag=${EXTERNAL_TAG} dockerfile=${EXTERNAL_DOCKERFILE} context=${EXTERNAL_DIR}"
docker build -t "${EXTERNAL_TAG}" -f "${EXTERNAL_DOCKERFILE}" "${EXTERNAL_DIR}"
log_with_color INFO "External image build complete tag=${EXTERNAL_TAG} rc=$?"

log_with_color STEP "Pushing external image"
log_with_color INFO "docker push tag=${EXTERNAL_TAG}"
docker push "${EXTERNAL_TAG}"
log_with_color INFO "External image push complete tag=${EXTERNAL_TAG} rc=$?"

log_with_color STEP "Building edge_node image"
log_with_color INFO "docker build tag=${EDGE_TAG} dockerfile=${EDGE_DOCKERFILE} context=${EDGE_DIR}"
docker build -t "${EDGE_TAG}" -f "${EDGE_DOCKERFILE}" "${EDGE_DIR}"
log_with_color INFO "Edge_node image build complete tag=${EDGE_TAG} rc=$?"

log_with_color STEP "Pushing edge_node image"
log_with_color INFO "docker push tag=${EDGE_TAG}"
docker push "${EDGE_TAG}"
log_with_color INFO "Edge_node image push complete tag=${EDGE_TAG} rc=$?"

log_with_color STEP "Running edge_node container"
RUN_ENV_ARGS=()
if [[ -n "${NO_COLOR:-}" ]]; then
  RUN_ENV_ARGS+=("-e" "NO_COLOR=1")
  log_with_color INFO "Passing NO_COLOR=1 into container"
fi
log_with_color INFO "docker run --rm --privileged --name edge_node ${RUN_ENV_ARGS[*]} ${EDGE_TAG}"
set +e
docker run --rm --privileged --name edge_node "${RUN_ENV_ARGS[@]}" "${EDGE_TAG}"
RUN_RC=$?
set -e
log_with_color INFO "edge_node container finished rc=${RUN_RC}"

if [[ "${RUN_RC}" -ne 0 ]]; then
  log_with_color ERROR "edge_node run failed rc=${RUN_RC}"
  exit "${RUN_RC}"
fi

log_with_color INFO "Orchestration complete rc=0"
