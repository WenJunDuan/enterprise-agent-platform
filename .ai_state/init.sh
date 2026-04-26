#!/usr/bin/env bash
set -euo pipefail

echo "[ai_state:init] project=$(pwd)"

if [[ -f .ai_state/project.json ]]; then
  python - <<'PY'
import json
from pathlib import Path

project = json.loads(Path(".ai_state/project.json").read_text())
print(
    "[ai_state:init] "
    f"path_kind={project.get('path_kind')} "
    f"stage={project.get('stage')} "
    f"sprint={project.get('sprint')}"
)
PY
fi

if [[ -f .ai_state/tasks.md ]]; then
  total="$(grep -E '^- \[[ x~]\]' .ai_state/tasks.md | wc -l | tr -d ' ')"
  done_count="$(grep -E '^- \[x\]' .ai_state/tasks.md | wc -l | tr -d ' ')"
  echo "[ai_state:init] tasks=${done_count}/${total}"
fi
