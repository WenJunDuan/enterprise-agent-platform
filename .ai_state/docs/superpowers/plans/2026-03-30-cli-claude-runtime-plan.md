# CLI Claude Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python CLI process load `.env`, resolve Claude-compatible runtime variables deterministically, and expose enough runtime visibility to debug model invocation before the SDK call.

**Architecture:** Centralize runtime env loading, mapping, validation, and redacted snapshot generation in `server/platform/config.py`, then make `server/core.py` and `server/cli.py` consume that single runtime view. Keep this round CLI-only and do not expand into HTTP serve or audit flow changes.

**Tech Stack:** Python, Typer CLI, Claude Agent SDK, dotenv

---

### Task 1: Normalize Runtime Configuration Surface

**Files:**
- Modify: `server/platform/config.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Introduce one runtime config shape for CLI consumption**

Include fields for:

```python
{
    "anthropic_base_url": ...,
    "anthropic_api_key_configured": ...,
    "anthropic_auth_token_configured": ...,
    "anthropic_model": ...,
    "anthropic_default_sonnet_model": ...,
    "anthropic_default_opus_model": ...,
    "anthropic_default_haiku_model": ...,
    "anthropic_custom_headers_configured": ...,
    "second_review_model": ...,
}
```

- [ ] **Step 2: Add CLI-oriented validation**

Validation should report:

```python
[
    "MODEL_BASE_URL or ANTHROPIC_BASE_URL is required",
    "MODEL_API_KEY / MODEL_AUTH_TOKEN / ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is required",
    "MODEL_NAME or ANTHROPIC_MODEL is required",
]
```

- [ ] **Step 3: Align `.env.example` with the actual minimum CLI path**

Document the minimum viable `.env`:

```env
MODEL_BASE_URL=http://your-model-gateway.example.com
MODEL_API_KEY=your-model-api-key
MODEL_NAME=gpt-5.4
```

### Task 2: Make Core Use the Resolved Runtime Config

**Files:**
- Modify: `server/core.py`

- [ ] **Step 1: Replace direct scattered env reads with resolved config usage**

The current logic:

```python
"model": os.getenv("ANTHROPIC_MODEL", "sonnet")
```

Should instead use the normalized runtime config output from `server.platform.config`.

- [ ] **Step 2: Keep ClaudeAgentOptions construction deterministic**

Preserve:

```python
"cwd": str(PROJECT_ROOT),
"setting_sources": ["project"],
"allowed_tools": ["Read", "Glob", "Grep", "Write", "Skill", "Task"],
```

but resolve `model` from the normalized runtime config rather than raw env reads.

### Task 3: Add CLI Runtime Visibility

**Files:**
- Modify: `server/cli.py`
- Modify: `server/platform/diagnostics.py` if needed

- [ ] **Step 1: Add a lightweight runtime inspection command**

Example shape:

```json
{
  "status": "ok | degraded",
  "runtime": {
    "anthropic_base_url": "...",
    "anthropic_model": "sonnet",
    "anthropic_default_sonnet_model": "gpt-5.4",
    "second_review_model": "gpt-5.4-mini"
  },
  "errors": []
}
```

- [ ] **Step 2: Make `ask` fail fast on invalid runtime config**

Before calling Claude SDK, validate config and raise a CLI-readable error instead of letting the SDK fail opaquely.

### Task 4: Update Operator Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite the CLI startup path around `.env`**

Document:

1. Which keys are required
2. Which keys are optional
3. How `MODEL_*` maps to `ANTHROPIC_*`
4. How to inspect the active runtime config before calling `ask`

### Task 5: Manual Validation Checklist For The User

**Files:**
- Verify only, no test scripts added

- [ ] **Step 1: Inspect runtime**

User runs:

```bash
uv run python -m server.cli runtime
```

Expected:
- shows redacted active runtime config
- no missing required config errors

- [ ] **Step 2: Smoke test model invocation**

User runs:

```bash
uv run python -m server.cli ask "你好"
```

Expected:
- request enters Claude SDK call path using mapped runtime config
- if invocation fails, CLI error message is about upstream/provider failure, not missing local env mapping
