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
- Child container mount target: `/edge_node/external_container_fixed_size_volume/`.
- Fixed-size volumes are file-backed ext4 mounted via loop devices under `/edge_node/_local_cache/_data/fixed_volumes/`.
- All executable scripts must implement `log_with_color` with timestamp + level + origin; full-line color by origin (external_container magenta, edge_node white, orchestrator/full_test gray).
- End-to-end orchestration is expected to build/push both images and then run `edge_node`.
- A wrapper script should validate orchestration output and report clear PASS/FAIL status.
- Wrapper log file: `artifacts/orchestrate.log` (captured with `NO_COLOR=1` for matching).
- edge_node runs the external_container twice to demonstrate volume persistence; volume stats are logged between runs.

## Update protocol

- Append new vital info or changes here and remove or amend stale notes.
- If you restructure folders, update the repo map above.

## Updates

- Added repo map entries for `edge_node/`, `external_container/`, and orchestration scripts.
- README updated with theory/approach and run instructions.
