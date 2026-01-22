#!/usr/bin/env python3
"""External container app for fixed-size volume validation.

Notes
-----
The app writes 10 MB files to a target directory until the filesystem
returns ENOSPC, proving that the file-backed volume limit is enforced.
"""

import errno
import os
import subprocess
import sys
import time
from pathlib import Path

ORIGIN = "external_container"
COLOR_ORIGIN = "\033[35m"
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
  prefix = f"[{ts}] [{ORIGIN}] [{level}]"
  line = f"{prefix} {message}"
  if _color_enabled():
    line = f"{COLOR_ORIGIN}{line}{COLOR_RESET}"
  print(line, flush=True)


def _log_df(target_dir: Path) -> None:
  """Log filesystem usage for the target directory.

  Parameters
  ----------
  target_dir : pathlib.Path
      Path to the mounted volume.

  Returns
  -------
  None
  """
  result = subprocess.run(
    ["df", "-h", str(target_dir)],
    text=True,
    capture_output=True,
    check=False,
  )
  log_with_color(
    "INFO",
    "df -h result "
    f"path={target_dir} exit_code={result.returncode} "
    f"stdout_lines={len(result.stdout.splitlines())} stderr_lines={len(result.stderr.splitlines())}",
  )
  if result.stdout:
    for line in result.stdout.strip().splitlines():
      log_with_color("INFO", f"df -h stdout: {line}")
  if result.stderr:
    for line in result.stderr.strip().splitlines():
      log_with_color("WARN", f"df -h stderr: {line}")


def _log_volume_contents(target_dir: Path) -> None:
  """Log the current contents of the target directory.

  Parameters
  ----------
  target_dir : pathlib.Path
      Path to the mounted volume.

  Returns
  -------
  None
  """
  if not target_dir.exists():
    log_with_color("WARN", f"Volume path does not exist path={target_dir}")
    return
  if not target_dir.is_dir():
    log_with_color("WARN", f"Volume path is not a directory path={target_dir}")
    return

  entries = sorted(target_dir.iterdir(), key=lambda p: p.name)
  total_bytes = 0
  log_with_color(
    "INFO",
    f"Listing volume contents path={target_dir} entries={len(entries)}",
  )

  for entry in entries:
    if entry.is_file():
      size = entry.stat().st_size
      total_bytes += size
      log_with_color(
        "INFO",
        f"volume entry type=file name={entry.name} size_bytes={size}",
      )
    elif entry.is_dir():
      log_with_color(
        "INFO",
        f"volume entry type=dir name={entry.name}",
      )
    else:
      log_with_color(
        "INFO",
        f"volume entry type=other name={entry.name}",
      )

  log_with_color(
    "INFO",
    f"Volume contents summary entries={len(entries)} total_bytes={total_bytes}",
  )


def main() -> int:
  """Run the write-until-full loop.

  Returns
  -------
  int
      Exit code for the process.
  """
  target_dir = Path(
    os.getenv("TARGET_DIR", "/edge_node/external_container_fixed_size_volume")
  )
  chunk_size = 1024 * 1024
  chunks_per_file = 10
  bytes_per_file = chunk_size * chunks_per_file

  log_with_color(
    "STEP",
    "External app starting "
    f"pid={os.getpid()} target_dir={target_dir} "
    f"chunk_size={chunk_size} chunks_per_file={chunks_per_file} bytes_per_file={bytes_per_file}",
  )

  target_dir.mkdir(parents=True, exist_ok=True)
  log_with_color("INFO", f"Ensured target directory exists path={target_dir}")

  _log_volume_contents(target_dir)
  _log_df(target_dir)

  total_files = 0
  total_bytes = 0
  file_index = 1

  while True:
    filename = target_dir / f"chunk_{file_index:04d}.bin"
    try:
      with open(filename, "wb") as f:
        # Write in 1 MB chunks to keep memory usage predictable.
        for _ in range(chunks_per_file):
          f.write(b"\0" * chunk_size)
      total_files += 1
      total_bytes += bytes_per_file
      log_with_color(
        "INFO",
        "Wrote file "
        f"path={filename} file_index={file_index} "
        f"file_bytes={bytes_per_file} total_files={total_files} total_bytes={total_bytes}",
      )
      file_index += 1
    except OSError as exc:
      if exc.errno == errno.ENOSPC:
        log_with_color(
          "WARN",
          "No space left on device; volume is full "
          f"after_files={total_files} total_bytes={total_bytes} last_path={filename}",
        )
        _log_df(target_dir)
        _log_volume_contents(target_dir)
        return 0
      log_with_color(
        "ERROR",
        "Write failed "
        f"path={filename} errno={exc.errno} strerror={exc.strerror}",
      )
      return 1


if __name__ == "__main__":
  sys.exit(main())
