#!/usr/bin/env python3
"""Edge node runner that provisions volumes and launches the external app."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import docker

from fixed_volume import FixedVolume, cleanup, docker_bind_spec, provision

ORIGIN = "edge_node"
COLOR_ORIGIN = "\033[97m"
COLOR_RESET = "\033[0m"


def _color_enabled() -> bool:
  """Determine if color output should be enabled.

  Returns
  -------
  bool
      True if ANSI colors should be used, False otherwise.
  """
  if os.getenv("NO_COLOR") or os.getenv("TERM") == "dumb":
    return False
  return sys.stdout.isatty()


def log_with_color(level: str, message: str) -> None:
  """Log a message with origin, timestamp, and optional color.

  Parameters
  ----------
  level : str
      Severity level for the log message.
  message : str
      Message payload to emit.

  Returns
  -------
  None
  """
  level = level.upper()
  ts = time.strftime("%Y-%m-%d %H:%M:%S")
  prefix = f"[{ts}] [{level}] [{ORIGIN}]"
  line = f"{prefix} {message}"
  if _color_enabled():
    line = f"{COLOR_ORIGIN}{line}{COLOR_RESET}"
  print(line, flush=True)


def _safe_get_env(name: str, default: str) -> str:
  """Read an environment variable and log its value.

  Parameters
  ----------
  name : str
      Environment variable name.
  default : str
      Default value if not set.

  Returns
  -------
  str
      The resolved value.
  """
  value = os.getenv(name, default)
  log_with_color("INFO", f"Env var {name}={value}")
  return value


def _remove_existing_container(client: docker.DockerClient, name: str) -> None:
  """Remove a container if it already exists.

  Parameters
  ----------
  client : docker.DockerClient
      Docker client instance.
  name : str
      Container name.

  Returns
  -------
  None
  """
  try:
    existing = client.containers.get(name)
  except docker.errors.NotFound:
    log_with_color("INFO", f"No existing container name={name}")
    return
  log_with_color(
    "WARN",
    f"Removing existing container name={name} id={existing.id}",
  )
  existing.remove(force=True)
  log_with_color("INFO", f"Existing container removed name={name}")


def _run_command(cmd: list[str], label: str) -> int:
  """Run a shell command and log stdout/stderr.

  Parameters
  ----------
  cmd : list[str]
      Command and arguments to execute.
  label : str
      Human-friendly label for log context.

  Returns
  -------
  int
      Exit code of the command.
  """
  cmd_str = shlex.join(cmd)
  log_with_color("STEP", f"Running command label={label} cmd={cmd_str}")

  # Capture output so volume stats are visible in the logs.
  result = subprocess.run(cmd, text=True, capture_output=True)
  log_with_color(
    "INFO",
    "Command result "
    f"label={label} rc={result.returncode} stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
  )
  if result.stdout:
    for line in result.stdout.strip().splitlines():
      log_with_color("INFO", f"{label} stdout: {line}")
  if result.stderr:
    for line in result.stderr.strip().splitlines():
      log_with_color("WARN", f"{label} stderr: {line}")
  return result.returncode


def _log_volume_stats(mount_path: Path) -> None:
  """Log size and content information for a mounted volume.

  Parameters
  ----------
  mount_path : pathlib.Path
      Path to the mounted volume.

  Returns
  -------
  None
  """
  log_with_color("STEP", f"Collecting volume stats mount_path={mount_path}")
  _run_command(["df", "-h", str(mount_path)], "df -h")
  _run_command(["du", "-sh", str(mount_path)], "du -sh")
  _run_command(["ls", "-la", str(mount_path)], "ls -la")


def _run_external_container(
  client: docker.DockerClient,
  image: str,
  name: str,
  target_dir: str,
  mounts: dict,
  env: dict,
  run_label: str,
) -> tuple[docker.models.containers.Container, int]:
  """Run the external container, stream logs, and wait for exit.

  Parameters
  ----------
  client : docker.DockerClient
      Docker client instance.
  image : str
      Image tag to run.
  name : str
      Container name.
  target_dir : str
      Target directory inside the container.
  mounts : dict
      Bind mount specification for docker-py.
  env : dict
      Environment variables for the container.
  run_label : str
      Label for the run (e.g., "run=1" or "run=2").

  Returns
  -------
  tuple
      (container, status_code)
  """
  log_with_color(
    "STEP",
    "Running external container "
    f"{run_label} image={image} name={name} target_dir={target_dir} mounts={mounts}",
  )

  container = client.containers.run(
    image=image,
    name=name,
    detach=True,
    environment=env,
    volumes=mounts,
  )
  log_with_color(
    "INFO",
    f"External container started {run_label} id={container.id} name={container.name}",
  )

  log_with_color("STEP", f"Streaming logs {run_label} container_id={container.id}")
  for line in container.logs(stream=True, follow=True):
    sys.stdout.buffer.write(line)
    sys.stdout.flush()

  result = container.wait()
  status_code = result.get("StatusCode")
  log_with_color(
    "INFO",
    f"External container exited {run_label} status_code={status_code} result={result}",
  )
  return container, status_code


def _remove_container(container: docker.models.containers.Container, name: str) -> None:
  """Remove a container with detailed logging.

  Parameters
  ----------
  container : docker.models.containers.Container
      Container object to remove.
  name : str
      Container name.

  Returns
  -------
  None
  """
  try:
    log_with_color("STEP", f"Removing container name={name} id={container.id}")
    container.remove(force=True)
    log_with_color("INFO", f"Container removed name={name}")
  except Exception as exc:
    log_with_color(
      "WARN",
      f"Failed to remove container name={name} error={exc}",
    )


def main() -> int:
  """Run the end-to-end edge_node flow.

  Returns
  -------
  int
      Exit code for the process.
  """
  container_name = _safe_get_env("EXTERNAL_CONTAINER_NAME", "external_container_poc")
  external_image = _safe_get_env(
    "EXTERNAL_IMAGE", "ratio1/volume_isolation:external_container"
  )
  volume_size = _safe_get_env("VOLUME_SIZE", "100M")
  volume_name = _safe_get_env("VOLUME_NAME", "data")
  root_path = Path(
    _safe_get_env(
      "FIXED_VOLUME_ROOT", "/edge_node/_local_cache/_data/fixed_volumes"
    )
  )
  target_dir = _safe_get_env(
    "TARGET_DIR", "/edge_node/external_container_fixed_size_volume"
  )
  no_color = _safe_get_env("NO_COLOR", "")

  log_with_color(
    "STEP",
    "Edge node runner starting "
    f"container_name={container_name} external_image={external_image} "
    f"volume_name={volume_name} volume_size={volume_size} "
    f"root_path={root_path} target_dir={target_dir}",
  )

  client = docker.from_env()
  log_with_color("INFO", "Docker client created")
  try:
    version_info = client.version()
    log_with_color("INFO", f"Docker version info={version_info}")
  except Exception as exc:
    log_with_color("ERROR", f"Failed to read docker version error={exc}")
    return 1

  _remove_existing_container(client, container_name)

  log_with_color("STEP", f"Pulling external image tag={external_image}")
  image = client.images.pull(external_image)
  log_with_color("INFO", f"External image pulled id={image.id} tags={image.tags}")

  volume = FixedVolume(
    name=volume_name,
    container_name=container_name,
    size=volume_size,
    root=root_path,
  )

  provisioned: Optional[FixedVolume] = None
  container: Optional[docker.models.containers.Container] = None

  try:
    provisioned = provision(volume)
    log_with_color(
      "INFO",
      "Volume provisioned "
      f"img_path={provisioned.img_path} mount_path={provisioned.mount_path}",
    )

    mounts = docker_bind_spec(provisioned, target_dir)
    external_env = {"TARGET_DIR": target_dir}
    if no_color:
      external_env["NO_COLOR"] = "1"
      log_with_color(
        "INFO",
        "NO_COLOR detected; passing NO_COLOR=1 to external container",
      )

    # First run: fill the volume and trigger ENOSPC.
    container, status_code = _run_external_container(
      client,
      external_image,
      container_name,
      target_dir,
      mounts,
      external_env,
      "run=1",
    )
    _remove_container(container, container_name)
    container = None
    if status_code != 0:
      raise RuntimeError(f"External container run=1 exited status_code={status_code}")

    # After the first run, log volume stats before re-launching to prove persistence.
    _log_volume_stats(provisioned.mount_path)

    log_with_color(
      "STEP",
      "Re-launching external container to verify volume persistence run=2",
    )
    container, status_code = _run_external_container(
      client,
      external_image,
      container_name,
      target_dir,
      mounts,
      external_env,
      "run=2",
    )
    _remove_container(container, container_name)
    container = None
    if status_code != 0:
      raise RuntimeError(f"External container run=2 exited status_code={status_code}")

  except Exception as exc:
    log_with_color("ERROR", f"Runner failed error={exc}")
    return 1
  finally:
    if container is not None:
      _remove_container(container, container_name)
    if provisioned is not None:
      try:
        cleanup(provisioned)
      except Exception as exc:
        log_with_color("WARN", f"Cleanup failed error={exc}")

  log_with_color("INFO", "Edge node runner completed successfully")
  return 0


if __name__ == "__main__":
  sys.exit(main())
