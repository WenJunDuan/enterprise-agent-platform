# Enterprise Agent Platform

Claude Agent SDK based enterprise agent scaffold with business logic kept in `.claude/` and Python limited to serving, persistence, and runtime control.

## Quick Start

```bash
uv sync
uv run pytest
uv run app-server start
uv run app-server status
```

## Python Layer

- `server/api.py`: HTTP API, auth, health/readiness, query endpoints
- `server/core.py`: Claude SDK bridge, structured output enforcement, session control
- `server/app_server.py`: Python process manager for start/stop/restart/logs/maintain
- `server/platform/`: paths, config, diagnostics, maintenance, storage
- `server/stores/`: request/session/result/runtime persistence

## Local Storage Layout

```text
logs/
  runtime/app-server/
    server.pid
    server.status.json
    stdout.log
    stderr.log
  service/requests/
    requests-YYYY-MM.jsonl
  sessions/
    index/sessions-YYYY-MM.jsonl
    events/YYYY/MM/DD/*.jsonl
  results/
    index/results-YYYY-MM.jsonl
    by-request/YYYY/MM/DD/{request_id}.json
```

## Main Commands

Foreground debug server:

```bash
uv run python -m server.cli serve
```

Rule initialization:

```bash
uv run python -m server.cli init-rules knowledge/external/数睿员工手册.pdf hr
```

Managed background server:

```bash
uv run app-server start
uv run app-server status
uv run app-server inspect
uv run app-server doctor --strict
uv run app-server logs --lines 100
uv run app-server stop
```

Local maintenance:

```bash
uv run app-server maintain
```

## Notes

- Structured JSON output is enforced through Claude Agent SDK `output_format`, not prompt wording.
- Request audit, session index, raw event stream, and archived result are linked by `request_id`.
- Business rules stay in `.claude/` and `knowledge/`; Python does not own business decisions.
- Rule source materials live under `knowledge/external/`, and `init-rules` writes structured outputs back to `knowledge/{domain}/`.
- The runtime maps local `MODEL_BASE_URL / MODEL_API_KEY / MODEL_NAME` env vars to Claude-compatible `ANTHROPIC_*` env vars automatically. When `MODEL_NAME` is a custom gateway model such as `gpt-5.4`, the runtime pins Claude aliases like `sonnet` to that backend model.
- If your gateway exposes Anthropic Messages endpoints with an access-token scheme, set `MODEL_AUTH_TOKEN`; the runtime will map it to `ANTHROPIC_AUTH_TOKEN`.
- If your gateway requires extra routing or auth headers, set `MODEL_CUSTOM_HEADERS` either as JSON or raw `Name: Value` lines; the runtime will translate it to Claude Code's `ANTHROPIC_CUSTOM_HEADERS`.
- The post-write review hook now follows the same external gateway by default. If you do not set `SECOND_REVIEW_MODEL`, it falls back to the mapped haiku alias for custom gateways instead of hard-coding a Claude-native review model.

## External Models Through Claude Code SDK

For an Anthropic-compatible gateway, you can keep using Claude Code SDK and point it at an external model backend through `.env`:

```bash
MODEL_BASE_URL=https://your-gateway.example.com
MODEL_API_KEY=sk-your-gateway-key
MODEL_NAME=gpt-5.4
MODEL_CUSTOM_HEADERS={"HTTP-Referer":"https://your-app.example.com","X-Title":"enterprise-agent-platform"}
```

What this project does with that configuration:

- Claude Code SDK still runs normally, with `setting_sources=["project"]` so `.claude/` stays active.
- `sonnet / opus / haiku` aliases are pinned to your external `MODEL_NAME` when it is not a native Claude model id.
- The second-pass review hook uses the same gateway path by default, so the main run and the review run stay on one provider.
