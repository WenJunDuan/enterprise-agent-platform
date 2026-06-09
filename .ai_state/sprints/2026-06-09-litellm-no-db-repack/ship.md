# LiteLLM No-DB Repack Ship Record

## Scope

- Update remote LiteLLM deployment at `admin@100.107.62.19:/opt/application/litellm`.
- Keep LiteLLM as a static OpenAI-compatible translation/model gateway.
- Remove DB-backed auth mode configuration and keep the active LiteLLM config in `litellm_config.yaml`.
- Pull/check `docker.litellm.ai/berriai/litellm:main-stable`, restart LiteLLM, validate, and export the image tar.

## Config Result

- Removed/confirmed absent: `DATABASE_URL`, `LITELLM_DATABASE_URL`, `database_url`, `master_key`, `LITELLM_MASTER_KEY`, and Postgres references.
- Kept static model aliases: `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5`, and `*`.
- Kept forwarding settings: `drop_params: true`, `num_retries: 2`.
- Docker daemon used the authenticated Clash proxy for the image pull.
- Docker daemon proxy credentials were removed after the pull; the daemon keeps only the unauthenticated proxy URL and `NO_PROXY`.
- `litellm_config.yaml` is the active LiteLLM config file and contains the provider base URL, API key, model aliases, and LiteLLM settings.
- `litellm.env` is no longer an active config file; it was moved under `/opt/application/litellm/backups/`.
- `docker-compose.yml` only starts LiteLLM and mounts `./litellm_config.yaml:/app/config.yaml:ro`; it does not embed model/provider config.
- Old compose/env backups were moved under `/opt/application/litellm/backups/`.

## Verification

- `docker pull docker.litellm.ai/berriai/litellm:main-stable` downloaded the current stable image.
- Image ID: `sha256:c98c9395c56a35b7abacff8269d43ff99aabacb62bbf42a04cc1514fcb9bde4a`
- Created: `2026-06-09T01:15:30Z`
- The old `main-latest` image and `litellm-main-latest.tar` were removed from the build host.
- `/health/liveliness` returned `"I'm alive!"`.
- `/v1/models` works without authorization and with arbitrary authorization; no `No connected db` error.
- `/v1/chat/completions` translation request returned HTTP 200.
- After restoring yaml-only active config, `ea-litellm` stayed healthy, mounted `/opt/application/litellm/litellm_config.yaml` to `/app/config.yaml:ro`, and `/v1/models` plus translation requests returned HTTP 200.

## Artifact

- Path: `/opt/application/litellm/litellm-main-stable.tar`
- Size: `378M`
- SHA256: `12cad221d8131e9f18bbbe4fc635e62d7f2c4e5b71bf9ad742a40628890995a7`

## Onsite Notes

- Copy `docker-compose.yml`, `litellm_config.yaml`, and `litellm-main-stable.tar`.
- Do not copy `litellm.env`; it is not active in this deployment.
- This no-DB mode does not enforce LiteLLM master-key authentication; protect access with network binding/firewall and the app-side tenant token.
