import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DIR = PROJECT_ROOT / ".claude"


def read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_claude_non_business_files_exist() -> None:
    required_paths = [
        ".claude/CLAUDE.md",
        ".claude/settings.json",
        ".claude/commands/help-claude.md",
        ".claude/commands/list-domains.md",
    ]

    for relative_path in required_paths:
        assert (PROJECT_ROOT / relative_path).is_file(), relative_path


def test_settings_json_is_parseable_and_safe() -> None:
    settings = json.loads(read_text(".claude/settings.json"))

    assert settings["permissions"]["deny"] == ["Bash"]
    assert settings["permissions"]["allow"] == ["Read", "Glob", "Grep", "Task", "Skill"]
    assert settings["hooks"] == {}


def test_commands_use_basic_frontmatter() -> None:
    command_paths = [
        ".claude/commands/help-claude.md",
        ".claude/commands/list-domains.md",
    ]

    for relative_path in command_paths:
        content = read_text(relative_path)
        assert content.startswith("---\n"), relative_path
        assert "description:" in content, relative_path
        assert "allowed-tools:" in content, relative_path


def test_non_business_scaffold_avoids_specific_domain_keywords() -> None:
    banned_keywords = [
        "expense",
        "legal",
        "travel",
        "invoice",
        "报销",
        "差旅",
        "招待",
        "发票",
        "合同",
        "法务",
        "考勤",
        "请假",
    ]
    allowed_files = [
        ".claude/CLAUDE.md",
        ".claude/commands/help-claude.md",
        ".claude/commands/list-domains.md",
    ]

    for relative_path in allowed_files:
        content = read_text(relative_path).lower()
        for keyword in banned_keywords:
            assert keyword not in content, f"{relative_path} contains banned keyword: {keyword}"


def test_agents_and_skills_remain_empty_scaffolds() -> None:
    for relative_dir in [".claude/agents", ".claude/skills"]:
        files = sorted(path.name for path in (PROJECT_ROOT / relative_dir).iterdir())
        assert files == [".gitkeep"], relative_dir


def test_env_example_documents_optional_gateway_api_key() -> None:
    env_example = read_text(".env.example")

    assert "MODEL_BASE_URL=http://your-model-gateway.example.com" in env_example
    assert "# MODEL_API_KEY=your-model-api-key" in env_example
    assert "MODEL_NAME=your-model-name" in env_example
    assert "APP_LOG_LEVEL=INFO" in env_example
    assert "APP_LOG_FILE=logs/service.log" in env_example
    assert "APP_MEMORY_ROOT=knowledge/memory" in env_example
    assert "SLOW_REQUEST_THRESHOLD_SECONDS=10" in env_example
    assert "UPSTREAM_TIMEOUT_SECONDS=60" in env_example
    assert "MODEL_API_KEY=your-model-api-key" not in [
        line for line in env_example.splitlines() if not line.startswith("#")
    ]


def test_knowledge_memory_scaffold_exists_with_clear_template() -> None:
    readme_path = PROJECT_ROOT / "knowledge" / "memory" / "README.md"
    daily_memory_path = PROJECT_ROOT / "knowledge" / "memory" / "2026" / "03" / "2026-03-20.md"

    assert readme_path.is_file()
    assert daily_memory_path.is_file()

    readme = readme_path.read_text(encoding="utf-8")
    daily_memory = daily_memory_path.read_text(encoding="utf-8")

    assert "knowledge/memory/YYYY/MM/YYYY-MM-DD.md" in readme
    assert "这不是开发日志目录" in readme
    assert "## 当日概览" in daily_memory
    assert "## 业务事件记录" in daily_memory
    assert "## 规则命中与处理" in daily_memory
    assert "## 可沉淀业务记忆" in daily_memory
