# volume_isolation

## Overview

This repo demonstrates a fixed-size, file-backed volume for nested containers in a
Docker-in-Docker (DIND) environment. The "edge_node" container is privileged and
hosts a Docker daemon that runs a non-privileged "external_container" app. The app
writes 10 MB batches to a bind-mounted directory until the volume is full, proving
ENOSPC behavior. The edge_node runs two isolated cycles, where each cycle mounts,
runs, logs stats, and then unmounts/detaches; cycle 2 proves data persistence by
re-mounting the same image file and observing existing data.

## Theory and approach (why it works)

The fixed-size volume is a regular file on the edge node filesystem:

1) Allocate a file of a fixed size (e.g., 100M).
2) Format it as ext4.
3) Attach it to a loop device (e.g., /dev/loop2).
4) Mount that loop device to a host mountpoint directory.
5) Bind-mount the mountpoint into the inner container as a normal directory.

When the inner container writes beyond the file-backed filesystem size, the kernel
returns "No space left on device" (ENOSPC). The inner container does not need any
special privileges or mount tools; only the privileged edge node container does.

This is a PoC pattern based on the Docker storage volume "loop device" example and
is intentionally simple and deterministic.

## Architecture

- edge_node (privileged DIND container)
  - starts dockerd
  - performs 2 isolated cycles: provision/mount -> run external_container -> log volume state -> unmount/detach
  - uses a per-run external container scope name `external_app_<4hex>` for container + volume paths
  - on cycle 2, re-provisions from the existing image and logs pre-existing files
  - prints `=============================` between cycles for readability
- external_container (non-privileged app)
  - logs existing volume contents on startup
  - writes 10 MB files until ENOSPC
  - logs the "volume full" message and exits cleanly

## Repo layout

- `edge_node/`: DIND container implementation (provisioning + runner)
- `external_container/`: PoC app that fills the volume
- `orchestrate.sh`: builds/pushes both images and runs the PoC
- `full_test.sh`: runs orchestration, validates output, PASS/FAIL
- `TODO.md`: step-by-step PoC plan (source of truth for approach details)
- `AGENTS.md`: living doc with vital PoC facts

## Fixed-size volume layout

The edge node stores one file per volume and mounts it via loop device:

- image file: `/edge_node/_local_cache/_data/fixed_volumes/images/<container>/<vol>.img`
- mountpoint: `/edge_node/_local_cache/_data/fixed_volumes/mounts/<container>/<vol>/`
- metadata: `/edge_node/_local_cache/_data/fixed_volumes/meta/<container>/<vol>.json`

The inner container sees the bind mount at:

- `/external_container/fixed_size_volume/`

## Logging

All scripts define `log_with_color` and emit maximally detailed logs. Each log line
includes timestamp + origin + level and details such as inputs, paths, image tags,
volume sizes, and exit codes. Stage-oriented `STEP` logs are blue to make boundaries
obvious, while action-oriented `STEP` messages that start with `Running`/`Executing`
use origin color. Non-`STEP` logs are colored by origin:

- external app (`external_app_<4hex>`): magenta
- edge_node: white
- orchestrator/full_test: gray

Color is enabled by default (including piped logs) and can be disabled via
`NO_COLOR=1` or `TERM=dumb`.

## How to run (end-to-end)

1) Ensure Docker is installed and you are logged into DockerHub (`docker login`).
2) Run the full test:
   - `./full_test.sh`

This script:
- Builds and pushes `ratio1/volume_isolation:external_container`
- Builds and pushes `ratio1/volume_isolation:edge_node`
- Runs the edge_node container in privileged mode
- Verifies expected output and reports PASS/FAIL

## Expected results

- The external container logs show `df -h` for the target mount (~100 MB).
- Writes stop with "No space left on device; volume is full".
- The external container logs existing volume contents at startup.
- The edge_node logs volume stats before and after each run.
- The edge node unmounts and detaches the loop device after each cycle.
- After unmount/detach, edge_node runs `ls -la` on the previous mount path as proof.
- After unmount/detach, edge_node also runs `ls -la` on the image folder as proof.
- Cycle 2 starts by re-mounting the existing image and showing prior data.
- `full_test.sh` ends with PASS and writes `artifacts/orchestrate.log`.

## Troubleshooting

- DockerHub login detection:
  - Ensure `docker login` succeeded and `~/.docker/config.json` contains docker.io auths.
- `mount: permission denied`:
  - The edge_node container must run with `--privileged`.
- `losetup: cannot find an unused loop device`:
  - Increase loop devices on the host if needed (e.g., `modprobe loop max_loop=256`).
