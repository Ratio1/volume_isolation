# AGENTS

## Purpose

This is a living doc. Every agent should keep it continuously updated with vital repo/project/PoC information (decisions, commands, paths, gotchas). Keep updates short, factual, and current.

## Repo map (current)

- `agent/SPECS.md`: primary requirements and technical approach.
- `agent/TODO1.md`: original step-1 requirements.
- `TODO.md`: step-2 implementation plan.
- `README.md`: theory/approach and end-to-end run instructions.
- `edge_node/`: privileged DIND container implementation.
- `external_container/`: child app container implementation.
- `orchestrate.sh`: builds/pushes images and runs end-to-end.
- `full_test.sh`: runs orchestration, validates output, PASS/FAIL.

## PoC facts to keep in sync

- DockerHub tags: `ratio1/volume_isolation:edge_node` and `ratio1/volume_isolation:external_container`.
- Child container mount target: `/external_container/fixed_size_volume/`.
- Fixed-size volumes are file-backed ext4 mounted via loop devices under `/edge_node/_local_cache/_data/fixed_volumes/`.
- Default external app scope name is generated per run as `external_app_<4hex>` and is reused across both cycles.
- All executable scripts must implement `log_with_color` with timestamp + origin + level; stage-oriented `STEP` logs are blue for visibility, while action-oriented `STEP` messages starting with `Running`/`Executing` keep origin color; non-`STEP` logs keep origin colors (external_app_<4hex> magenta, edge_node white, orchestrator/full_test gray).
- End-to-end orchestration is expected to build/push both images and then run `edge_node`.
- `orchestrate.sh` keeps `docker build`/`docker push` output minimal: success lines only, and concise failure reason + saved log path on error.
- A wrapper script should validate orchestration output and report clear PASS/FAIL status.
- Wrapper log file: `artifacts/orchestrate.log` (colorized output is preserved unless `NO_COLOR=1` is explicitly set).
- edge_node runs two isolated cycles; each cycle mounts, runs the external_container, logs stats, and unmounts/detaches loop devices before the next cycle.
- edge_node emits `=============================` between cycles for readability.
- After each cycle unmount/detach, edge_node logs `ls -la` on the previous mount path as unmounted-state proof.
- After each cycle unmount/detach, edge_node logs `ls -la` on the image folder as proof the backing image is present.

## Update protocol

- Append new vital info or changes here and remove or amend stale notes.
- If you restructure folders, update the repo map above.

## Updates

- Added repo map entries for `edge_node/`, `external_container/`, and orchestration scripts.
- README updated with theory/approach and run instructions.
- Updated child container mount target to `/external_container/fixed_size_volume/` to avoid path ambiguity.
- Updated cycle flow to unmount/detach between runs and remount from existing image to prove separated persistence.
- Updated wrapper/orchestration logging to avoid forcing `NO_COLOR`; color output is enabled by default.
- Updated logging policy so stage `STEP` lines are blue while `Running`/`Executing` action lines keep origin color.
- Added post-unmount `ls -la` proof step before cycle end.
- Updated default external app/container scope naming to `external_app_<4hex>` per run.
- Added post-unmount image-folder `ls -la` proof step before cycle end.
- Updated orchestration so image build/push steps run quietly with minimal output and explicit failure reason on errors.
- Updated inner container log prefix to use dynamic `external_app_<4hex>` via `LOG_ORIGIN`.
