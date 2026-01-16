#!/usr/bin/env python3

import errno
import os
import sys
import time
from pathlib import Path
import subprocess

COLOR_RESET = "\033[0m"
COLORS = {
    "STEP": "\033[36m",
    "INFO": "\033[32m",
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
}


def _color_enabled() -> bool:
    if os.getenv("NO_COLOR") or os.getenv("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def log_with_color(level: str, message: str) -> None:
    level = level.upper()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{ts}] [{level}]"
    if _color_enabled() and level in COLORS:
        line = f"{COLORS[level]}{prefix}{COLOR_RESET} {message}"
    else:
        line = f"{prefix} {message}"
    print(line, flush=True)


def _log_df(target_dir: Path) -> None:
    result = subprocess.run(
        ["df", "-h", str(target_dir)],
        text=True,
        capture_output=True,
        check=False,
    )
    log_with_color(
        "INFO",
        f"df -h exit_code={result.returncode} stdout_lines={len(result.stdout.splitlines())} stderr_lines={len(result.stderr.splitlines())}",
    )
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            log_with_color("INFO", f"df -h stdout: {line}")
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            log_with_color("WARN", f"df -h stderr: {line}")


def main() -> int:
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

    _log_df(target_dir)

    total_files = 0
    total_bytes = 0
    file_index = 1

    while True:
        filename = target_dir / f"chunk_{file_index:04d}.bin"
        try:
            with open(filename, "wb") as f:
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
                return 0
            log_with_color(
                "ERROR",
                "Write failed "
                f"path={filename} errno={exc.errno} strerror={exc.strerror}",
            )
            return 1


if __name__ == "__main__":
    sys.exit(main())
