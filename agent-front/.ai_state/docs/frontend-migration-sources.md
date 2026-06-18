# Frontend Migration Source Map

## Created From

Source state directory:

`/Users/mi_manchi/workspace/enterprise-agent-platform/.ai_state`

Target state directory:

`/Users/mi_manchi/workspace/enterprise-agent-platform/agent-front/.ai_state`

## Why These Files Were Migrated

The selected files are the pieces that affect the standalone frontend project:

- frontend/API integration contract
- historical UI rewrite plan
- audit submit and polling behavior
- audit result display contract
- OCR HTTP and OCR page integration
- deployment notes that mention frontend build artifacts
- OCR lessons that affect timeout/error expectations in the UI

Files about pure backend refactors, tender rules, system rule initialization, and
general agent skill setup were left in the parent project state because they are
not direct frontend project state.

## Created Item Check

The following parent-level paths were already untracked before this migration
step and were not copied into `agent-front/.ai_state`:

- `/Users/mi_manchi/workspace/enterprise-agent-platform/.agents`
- `/Users/mi_manchi/workspace/enterprise-agent-platform/.codex`
- `/Users/mi_manchi/workspace/enterprise-agent-platform/AGENTS.md`

They are treated as parent-project agent configuration, not frontend migration
state.
