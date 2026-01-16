#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

import docker

from fixed_volume import FixedVolume, cleanup, docker_bind_spec, provision

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


def _safe_get_env(name: str, default: str) -> str:
    value = os.getenv(name, default)
    log_with_color("INFO", f"Env var {name}={value}")
    return value


def _remove_existing_container(client: docker.DockerClient, name: str) -> None:
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


def main() -> int:
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
    container = None

    try:
        provisioned = provision(volume)
        log_with_color(
            "INFO",
            "Volume provisioned "
            f"img_path={provisioned.img_path} mount_path={provisioned.mount_path}",
        )

        mounts = docker_bind_spec(provisioned, target_dir)
        log_with_color(
            "STEP",
            "Running external container "
            f"image={external_image} name={container_name} target_dir={target_dir} "
            f"mounts={mounts}",
        )

        container = client.containers.run(
            image=external_image,
            name=container_name,
            detach=True,
            environment={"TARGET_DIR": target_dir},
            volumes=mounts,
        )
        log_with_color(
            "INFO",
            f"External container started id={container.id} name={container.name}",
        )

        log_with_color("STEP", f"Streaming logs container_id={container.id}")
        for line in container.logs(stream=True, follow=True):
            sys.stdout.buffer.write(line)
            sys.stdout.flush()

        result = container.wait()
        status_code = result.get("StatusCode")
        log_with_color(
            "INFO",
            f"External container exited status_code={status_code} result={result}",
        )
    except Exception as exc:
        log_with_color("ERROR", f"Runner failed error={exc}")
        return 1
    finally:
        if container is not None:
            try:
                log_with_color(
                    "STEP",
                    f"Removing container name={container_name} id={container.id}",
                )
                container.remove(force=True)
                log_with_color("INFO", f"Container removed name={container_name}")
            except Exception as exc:
                log_with_color(
                    "WARN",
                    f"Failed to remove container name={container_name} error={exc}",
                )
        if provisioned is not None:
            try:
                cleanup(provisioned)
            except Exception as exc:
                log_with_color("WARN", f"Cleanup failed error={exc}")

    log_with_color("INFO", "Edge node runner completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
