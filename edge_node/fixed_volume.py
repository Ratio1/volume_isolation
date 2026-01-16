#!/usr/bin/env python3
"""Fixed-size volume helper for the edge_node container."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

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


@dataclass
class FixedVolume:
  """Fixed-size file-backed volume specification.

  Parameters
  ----------
  name : str
      Logical volume name.
  container_name : str
      Container name used to scope paths.
  size : str
      Size string accepted by fallocate (e.g., "100M", "1G").
  root : pathlib.Path
      Root directory where volume artifacts live.
  fs_type : str, optional
      Filesystem type to use for formatting.
  owner_uid : int, optional
      UID to chown the mount path to after mount.
  owner_gid : int, optional
      GID to chown the mount path to after mount.
  """

  name: str
  container_name: str
  size: str
  root: Path
  fs_type: str = "ext4"
  owner_uid: Optional[int] = None
  owner_gid: Optional[int] = None

  @property
  def img_path(self) -> Path:
    """Path to the file-backed image.

    Returns
    -------
    pathlib.Path
        Image file path.
    """
    return self.root / "images" / self.container_name / f"{self.name}.img"

  @property
  def mount_path(self) -> Path:
    """Path to the mountpoint directory.

    Returns
    -------
    pathlib.Path
        Mountpoint path.
    """
    return self.root / "mounts" / self.container_name / self.name

  @property
  def meta_path(self) -> Path:
    """Path to the metadata JSON file.

    Returns
    -------
    pathlib.Path
        Metadata file path.
    """
    return self.root / "meta" / self.container_name / f"{self.name}.json"


def _run(cmd: list[str], capture: bool = False) -> str:
  """Run a command with logging and optional output capture.

  Parameters
  ----------
  cmd : list[str]
      Command and arguments to execute.
  capture : bool, optional
      Whether to return stdout as a string.

  Returns
  -------
  str
      Captured stdout when capture is True, otherwise an empty string.

  Raises
  ------
  subprocess.CalledProcessError
      If the command exits with a non-zero status.
  """
  cmd_str = shlex.join(cmd)
  log_with_color("STEP", f"Executing command cmd={cmd_str} capture={capture}")

  # Capture output so we can include it in detailed logs for debugging.
  result = subprocess.run(cmd, text=True, capture_output=True)
  log_with_color(
    "INFO",
    "Command finished "
    f"rc={result.returncode} stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
  )
  if result.stdout:
    for line in result.stdout.strip().splitlines():
      log_with_color("INFO", f"stdout: {line}")
  if result.stderr:
    for line in result.stderr.strip().splitlines():
      log_with_color("WARN", f"stderr: {line}")
  if result.returncode != 0:
    raise subprocess.CalledProcessError(
      result.returncode, cmd, output=result.stdout, stderr=result.stderr
    )
  if capture:
    return result.stdout.strip()
  return ""


def _require_tools() -> None:
  """Ensure required host tools are installed.

  Returns
  -------
  None

  Raises
  ------
  RuntimeError
      If any required tool is missing.
  """
  tools = ["fallocate", "mkfs.ext4", "losetup", "mount", "umount", "blkid"]
  missing = [t for t in tools if shutil.which(t) is None]
  log_with_color("INFO", f"Tool check required={tools} missing={missing}")
  if missing:
    raise RuntimeError(
      "Missing required tools in edge_node: "
      + ", ".join(missing)
      + ". Install util-linux + e2fsprogs."
    )


def ensure_created(vol: FixedVolume, force_recreate: bool = False) -> None:
  """Create the image file and filesystem if needed.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.
  force_recreate : bool, optional
      Whether to delete and recreate the image file.

  Returns
  -------
  None
  """
  _require_tools()

  log_with_color(
    "STEP",
    "Ensuring volume image exists "
    f"container={vol.container_name} volume={vol.name} size={vol.size} "
    f"img_path={vol.img_path} mount_path={vol.mount_path} meta_path={vol.meta_path} "
    f"force_recreate={force_recreate}",
  )

  vol.img_path.parent.mkdir(parents=True, exist_ok=True)
  vol.mount_path.mkdir(parents=True, exist_ok=True)
  vol.meta_path.parent.mkdir(parents=True, exist_ok=True)

  if force_recreate and vol.img_path.exists():
    log_with_color("WARN", f"Removing existing image file path={vol.img_path}")
    vol.img_path.unlink()

  if not vol.img_path.exists():
    # Allocate and format the file-backed filesystem.
    _run(["fallocate", "-l", vol.size, str(vol.img_path)])
    _run(["mkfs.ext4", "-F", str(vol.img_path)])
    return

  log_with_color("INFO", f"Image file already exists path={vol.img_path}")
  try:
    _run(["blkid", "-p", str(vol.img_path)])
  except subprocess.CalledProcessError:
    log_with_color("WARN", f"No filesystem detected, formatting path={vol.img_path}")
    _run(["mkfs.ext4", "-F", str(vol.img_path)])


def attach_loop(vol: FixedVolume) -> str:
  """Attach the image file to a loop device.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.

  Returns
  -------
  str
      Loop device path (e.g., /dev/loop2).
  """
  log_with_color("STEP", f"Attaching loop device img_path={vol.img_path}")
  existing = _run(["losetup", "-j", str(vol.img_path)], capture=True)
  if existing:
    loop_dev = existing.split(":")[0]
    log_with_color("INFO", f"Existing loop device found loop_dev={loop_dev}")
    return loop_dev
  loop_dev = _run(["losetup", "-f", "--show", str(vol.img_path)], capture=True)
  log_with_color("INFO", f"Loop device attached loop_dev={loop_dev}")
  return loop_dev


def mount_volume(vol: FixedVolume, loop_dev: str) -> None:
  """Mount a loop device at the volume mount path.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.
  loop_dev : str
      Loop device path.

  Returns
  -------
  None
  """
  log_with_color(
    "STEP",
    "Mounting loop device "
    f"loop_dev={loop_dev} mount_path={vol.mount_path} fs_type={vol.fs_type}",
  )
  with open("/proc/mounts", "r", encoding="utf-8") as f:
    mounts = f.read()
  # Avoid remounting if already mounted.
  if str(vol.mount_path) in mounts:
    log_with_color("INFO", f"Mount already present mount_path={vol.mount_path}")
    return

  _run(["mount", "-t", vol.fs_type, loop_dev, str(vol.mount_path)])

  if vol.owner_uid is not None and vol.owner_gid is not None:
    os.chown(vol.mount_path, vol.owner_uid, vol.owner_gid)
    log_with_color(
      "INFO",
      "Adjusted ownership "
      f"mount_path={vol.mount_path} uid={vol.owner_uid} gid={vol.owner_gid}",
    )


def write_meta(vol: FixedVolume, loop_dev: str) -> None:
  """Write metadata describing the provisioned volume.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.
  loop_dev : str
      Loop device path.

  Returns
  -------
  None
  """
  data = {
    "container_name": vol.container_name,
    "volume_name": vol.name,
    "size": vol.size,
    "fs_type": vol.fs_type,
    "img_path": str(vol.img_path),
    "mount_path": str(vol.mount_path),
    "loop_dev": loop_dev,
  }
  vol.meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
  log_with_color(
    "INFO",
    "Wrote metadata "
    f"meta_path={vol.meta_path} loop_dev={loop_dev} size={vol.size}",
  )


def provision(vol: FixedVolume, force_recreate: bool = False) -> FixedVolume:
  """Provision a volume by creating, attaching, and mounting it.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.
  force_recreate : bool, optional
      Whether to delete and recreate the image file.

  Returns
  -------
  FixedVolume
      The same volume specification.
  """
  log_with_color(
    "STEP",
    "Provisioning volume "
    f"container={vol.container_name} volume={vol.name} size={vol.size} root={vol.root}",
  )
  ensure_created(vol, force_recreate=force_recreate)
  loop_dev = attach_loop(vol)
  mount_volume(vol, loop_dev)
  write_meta(vol, loop_dev)
  log_with_color(
    "INFO",
    "Volume provisioned "
    f"img_path={vol.img_path} mount_path={vol.mount_path} loop_dev={loop_dev}",
  )
  return vol


def cleanup(vol: FixedVolume) -> None:
  """Unmount and detach the loop device for a volume.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.

  Returns
  -------
  None
  """
  log_with_color(
    "STEP",
    "Cleaning up volume "
    f"container={vol.container_name} volume={vol.name} mount_path={vol.mount_path}",
  )
  loop_dev = None
  if vol.meta_path.exists():
    try:
      meta = json.loads(vol.meta_path.read_text(encoding="utf-8"))
      loop_dev = meta.get("loop_dev")
      log_with_color("INFO", f"Loaded metadata loop_dev={loop_dev}")
    except Exception as exc:
      log_with_color("WARN", f"Failed to read metadata error={exc}")
      loop_dev = None

  try:
    _run(["umount", str(vol.mount_path)])
  except Exception as exc:
    log_with_color("WARN", f"Unmount failed mount_path={vol.mount_path} error={exc}")

  if loop_dev:
    try:
      _run(["losetup", "-d", loop_dev])
    except Exception as exc:
      log_with_color("WARN", f"Detach loop failed loop_dev={loop_dev} error={exc}")

  log_with_color(
    "INFO",
    "Cleanup complete "
    f"mount_path={vol.mount_path} loop_dev={loop_dev}",
  )


def docker_bind_spec(vol: FixedVolume, container_target: str) -> Dict[str, Dict[str, str]]:
  """Build docker-py bind mount specification for the volume.

  Parameters
  ----------
  vol : FixedVolume
      Volume specification.
  container_target : str
      Target path inside the container.

  Returns
  -------
  dict
      Mapping suitable for docker-py volumes argument.
  """
  spec = {str(vol.mount_path): {"bind": container_target, "mode": "rw"}}
  log_with_color(
    "INFO",
    "Docker bind spec created "
    f"host_path={vol.mount_path} container_target={container_target}",
  )
  return spec
