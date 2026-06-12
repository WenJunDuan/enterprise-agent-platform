"""Shared pytest configuration for the enterprise-agent-platform test suite.

Centralises env-var guards that prevent server-side module-level side effects
(offline_guard, configure_claude_runtime_env) from tripping during test
collection and import.  Previously these were scattered at the top of each
test file; they now live here so every test file automatically inherits them.
"""

from __future__ import annotations

import os

# ── Offline guard bypass ────────────────────────────────────────────────────
# server.core (and anything that imports it) calls configure_claude_runtime_env()
# at module level.  The offline guard inside build_options() checks that
# MODEL_BASE_URL is not pointing at api.anthropic.com.  Setting a fake
# gateway URL prevents the guard from aborting test collection.
os.environ.setdefault("ALLOW_ANTHROPIC_API", "1")
os.environ.setdefault("MODEL_BASE_URL", "http://test-gateway:4000")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-fake-api-key-not-real")
os.environ.setdefault("MODEL_NAME", "test-model")
