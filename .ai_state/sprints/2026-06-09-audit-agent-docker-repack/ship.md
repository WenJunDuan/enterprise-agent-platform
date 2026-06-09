# Audit Agent Docker Repack Ship Record

## Scope

- Read latest Athena/Claude state from `.ai_state/_index.md`, `.ai_state/.snapshots/turn-history.log`, and `.claude/CLAUDE.md`.
- Re-sync the backend Docker build context to `/opt/application/audit-agent` on the ARM64 build host.
- Preserve runtime configuration and state during sync: `audit-agent.env`, `logs/`, `data/`, and existing image tar files.
- Rebuild and export the offline backend image for onsite deployment.

## Packaging Change

- Compose image changed from `audit-agent:offline` / `audit-agent:offline-latest` to `audit-agent`.
- Docker treats bare `audit-agent` as `audit-agent:latest`.
- Export artifact name changed to `audit-agent.tar`.
- The image startup model remains: root entrypoint fixes mounted `logs/` and `data/` ownership, then drops to the `app` user via `gosu`.

## Verification Plan

- Run remote `docker compose build --no-cache audit-agent`.
- Run the rebuilt image on the build host with `docker compose up -d`.
- Export with `docker save -o /opt/application/audit-agent/audit-agent.tar audit-agent`.
- Validate image entrypoint and root-owned bind mount permission repair using a temporary runtime test.

## Result

- Build host: `admin@100.107.62.19:/opt/application/audit-agent`
- Architecture: `aarch64`
- Image: `audit-agent`
- Image ID: `sha256:4e7662695cf61d3a3e3d70890cf10b41ff27f60af1bfdb67a052290c1c777503`
- Artifact: `/opt/application/audit-agent/audit-agent.tar`
- Artifact size: `314M`
- Artifact SHA256: `9aed4a65c6356e69b11732581c33c8d3ffe9bb869d2677821feb8ab6f1bf6e51`
- Created: `2026-06-09T10:15:43+08:00`
- Runtime env was updated item-by-item on the build host, preserving secrets.
- Build host container was replaced with the rebuilt `audit-agent` image and `/health` returned `ok`.
- Validation: temporary root-owned bind mounts for `logs/` and `data/` were repaired to UID/GID `1000:1000`, and writes as `app` succeeded.
- Verified runtime env keys: `MODEL_BASE_URL`, `MODEL_NAME`, `AUDIT_TIMEOUT_SEC`, `AUDIT_TASK_RUNNING_TIMEOUT_SECONDS`, `NO_PROXY`, and `no_proxy`.

## Onsite Notes

- Keep `docker-compose.yml` from this package; do not override `entrypoint`.
- `knowledge/` must be copied as data; `logs/` and `data/` can be created by Docker and will be repaired at container startup.
