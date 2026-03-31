# Audit Result And Directory Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make audit results return both machine-friendly structured data and Chinese audit-opinion fields (`result`, `conclusion`, `explanation`), and make the audit entrypoint explicitly support submitting a directory path so Claude inspects files under that directory.

**Architecture:** Keep the existing internal `approved / rejected / manual_review` verdict and existing structured fields, then extend the audit result schema with three display-oriented fields used by the frontend. Enforce the new contract in three places: Claude-side result-format skill, Python-side semantic validation, and write-time hook validation. For directory input, keep the Python CLI/API path argument shape unchanged and move the behavior guarantee into the Claude audit command plus regression tests.

**Tech Stack:** JSON Schema, Markdown skills, Python, Typer, FastAPI tests, Claude Agent SDK semantic validation hooks

---

### Task 1: Lock The New Audit Result Contract In Tests

**Files:**
- Modify: `tests/test_bootstrap.py`
- Modify: `.claude/contracts/common/audit-result.schema.json`
- Modify: `server/core.py`

- [ ] **Step 1: Write the failing structured-result payload expectations**

Add the new audit fields to the mocked audit payload used by the HTTP audit endpoint test:

```python
        return {
            "claim_id": "CLAIM-001",
            "verdict": "manual_review",
            "result": False,
            "conclusion": "待人工复核",
            "explanation": "根据《差旅费报销管理制度》相关条款，现有材料不足以完成自动审核，缺少关键附件。",
            "reasons": ["缺少附件"],
            "policy_refs": ["expense.travel.001"],
            "risk_score": 70,
            "extracted_data": {},
            "evidence_chain": [],
            "reviewed_by": "expense-auditor",
            "timestamp": "2026-03-31T00:00:00+00:00",
        }, AgentRunMeta(
```

Also assert the new fields are present:

```python
    assert payload["response"]["result"] is False
    assert payload["response"]["conclusion"] == "待人工复核"
    assert "根据《差旅费报销管理制度》" in payload["response"]["explanation"]
```

- [ ] **Step 2: Add semantic-validation unit tests for verdict mapping**

Add one passing test and two failing tests around `validate_structured_output_semantics()`:

```python
def test_validate_audit_semantics_accepts_manual_review_display_fields() -> None:
    payload = {
        "claim_id": "CLAIM-001",
        "verdict": "manual_review",
        "result": False,
        "conclusion": "待人工复核",
        "explanation": "根据《差旅费报销管理制度》相关条款，现有材料不足以判断该事项合规，缺少出差申请单。",
        "reasons": ["缺少出差申请单"],
        "policy_refs": ["expense.travel.001"],
        "risk_score": 70,
        "extracted_data": {},
        "evidence_chain": [{"source": "附件检查", "finding": "缺少出差申请单", "conclusion": "需人工复核"}],
        "reviewed_by": "expense-auditor",
        "timestamp": "2026-03-31T00:00:00+00:00",
    }
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_validate_audit_semantics_rejects_manual_review_with_wrong_conclusion() -> None:
    payload = {
        "claim_id": "CLAIM-001",
        "verdict": "manual_review",
        "result": False,
        "conclusion": "不合规",
        "explanation": "根据《差旅费报销管理制度》相关条款，现有材料不足以判断该事项合规，缺少出差申请单。",
        "reasons": ["缺少出差申请单"],
        "policy_refs": ["expense.travel.001"],
        "risk_score": 70,
        "extracted_data": {},
        "evidence_chain": [{"source": "附件检查", "finding": "缺少出差申请单", "conclusion": "需人工复核"}],
        "reviewed_by": "expense-auditor",
        "timestamp": "2026-03-31T00:00:00+00:00",
    }
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_semantics or audit_endpoint_returns_structured_json" -v
```

Expected:
- the endpoint test fails because `result`, `conclusion`, and `explanation` are not yet in the schema
- the semantic-validation tests fail because audit-result semantic validation does not yet exist

### Task 2: Extend The Audit Result Schema And Semantic Validation

**Files:**
- Modify: `.claude/contracts/common/audit-result.schema.json`
- Modify: `server/core.py`

- [ ] **Step 1: Extend the audit result schema with the three opinion fields**

Update the schema `properties` block with:

```json
    "result": {
      "type": "boolean"
    },
    "conclusion": {
      "type": "string",
      "enum": ["合规", "不合规", "待人工复核"]
    },
    "explanation": {
      "type": "string",
      "minLength": 1
    },
```

And add them to `required` immediately after `verdict`:

```json
    "verdict",
    "result",
    "conclusion",
    "explanation",
    "reasons",
```

- [ ] **Step 2: Add audit-result semantic validation in Python**

Extend `validate_structured_output_semantics()` in `server/core.py` with an audit-result branch:

```python
    if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
        if not isinstance(structured_output, dict):
            raise JSONContractError("audit result must be a JSON object.")

        verdict = structured_output.get("verdict")
        result = structured_output.get("result")
        conclusion = structured_output.get("conclusion")
        explanation = str(structured_output.get("explanation") or "").strip()

        expected = {
            "approved": (True, "合规"),
            "rejected": (False, "不合规"),
            "manual_review": (False, "待人工复核"),
        }
        if verdict not in expected:
            raise JSONContractError("audit result returned an unknown verdict.")

        expected_result, expected_conclusion = expected[verdict]
        if result is not expected_result:
            raise JSONContractError("audit result field 'result' does not match verdict.")
        if conclusion != expected_conclusion:
            raise JSONContractError("audit result field 'conclusion' does not match verdict.")
        if not explanation:
            raise JSONContractError("audit result must include a non-empty explanation.")
        return
```

- [ ] **Step 3: Run the focused tests and verify they pass**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_semantics or audit_endpoint_returns_structured_json" -v
```

Expected:
- all selected tests PASS

### Task 3: Solidify The New Output Rules In Claude Skills And Hooks

**Files:**
- Modify: `.claude/skills/common/result-format/SKILL.md`
- Modify: `.claude/agents/expense/auditor.md`
- Modify: `.claude/hooks/check-before-write.py`

- [ ] **Step 1: Rewrite the result-format skill so it requires both structured data and audit-opinion fields**

Update the field requirements section with the new mapping rules:

```markdown
- 继续保留完整结构化字段：`claim_id`、`verdict`、`reasons`、`policy_refs`、`risk_score`、`extracted_data`、`evidence_chain`、`reviewed_by`、`timestamp`
- 必须新增审核意见字段：`result`、`conclusion`、`explanation`
- `approved -> result=true, conclusion=合规`
- `rejected -> result=false, conclusion=不合规`
- `manual_review -> result=false, conclusion=待人工复核`
- `explanation` 必须使用中文，并明确写成“根据……规定，判断……”的句式
- `manual_review` 时必须在 `explanation` 中写清为什么不能自动放行、缺少什么材料或哪条规则无法闭合
```

Update the output example to:

```json
{
  "claim_id": "",
  "verdict": "approved | rejected | manual_review",
  "result": true,
  "conclusion": "合规 | 不合规 | 待人工复核",
  "explanation": "根据《费用报销管理制度》相关条款，结合已提交材料，判断该事项合规。",
  "reasons": [],
  "policy_refs": [],
  "risk_score": 0,
  "extracted_data": {},
  "evidence_chain": [],
  "reviewed_by": "",
  "timestamp": ""
}
```

- [ ] **Step 2: Tighten the expense auditor instructions**

Append explicit output-language guidance in `.claude/agents/expense/auditor.md`:

```markdown
## 输出要求

- 最终结果必须通过 `common-result-format`
- 保留完整结构化字段，供页面直接消费
- 同时输出 `result`、`conclusion`、`explanation`
- `result/conclusion/explanation` 必须全部使用中文
- `manual_review` 时，`conclusion` 必须固定为 `待人工复核`
```

- [ ] **Step 3: Expand the write-time hook validation**

Update `required_fields` and add mapping checks in `.claude/hooks/check-before-write.py`:

```python
    required_fields = [
        "claim_id",
        "verdict",
        "result",
        "conclusion",
        "explanation",
        "reasons",
        "policy_refs",
        "evidence_chain",
    ]
```

Add the mapping validation:

```python
    expected = {
        "approved": (True, "合规"),
        "rejected": (False, "不合规"),
        "manual_review": (False, "待人工复核"),
    }
    verdict = result.get("verdict")
    if verdict in expected:
        expected_result, expected_conclusion = expected[verdict]
        if result.get("result") is not expected_result or result.get("conclusion") != expected_conclusion:
            print(json.dumps({"error": "Audit opinion fields do not match verdict mapping."}))
            return 2
```

- [ ] **Step 4: Run the full bootstrap test suite**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -v
```

Expected:
- all tests PASS

### Task 4: Support Directory-Path Submission In The Audit Entry

**Files:**
- Modify: `.claude/commands/audit.md`
- Modify: `server/cli.py`
- Modify: `server/api.py`
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Add failing tests that treat directory paths as first-class audit input**

Add CLI and HTTP tests that pass a directory instead of a single file:

```python
def test_build_command_prompt_allows_directory_path() -> None:
    assert build_command_prompt("audit", "data/case1") == "/audit data/case1"


def test_audit_endpoint_accepts_directory_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_run_command_json(command_name: str, *args: Any, **kwargs: Any):
        captured["args"] = args
        return {
            "claim_id": "CASE-001",
            "verdict": "manual_review",
            "result": False,
            "conclusion": "待人工复核",
            "explanation": "根据《费用报销管理制度》相关条款，现有材料不足以自动判断，缺少关键行程凭证。",
            "reasons": ["缺少关键行程凭证"],
            "policy_refs": ["expense.travel.001"],
            "risk_score": 70,
            "extracted_data": {},
            "evidence_chain": [{"source": "目录检查", "finding": "缺少关键行程凭证", "conclusion": "需人工复核"}],
            "reviewed_by": "expense-auditor",
            "timestamp": "2026-03-31T00:00:00+00:00",
        }, AgentRunMeta(
            request_id="req-audit-dir-1",
            conversation_id="conv-audit-dir-1",
            claude_session_id="sess-audit-dir-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            log_file="logs/sessions/events/audit-dir.jsonl",
            result_file="results/by-request/req-audit-dir-1.json",
            result_subtype="success",
            cost_usd=0.3,
            finished_at="2026-03-31T00:00:00+00:00",
        )

    monkeypatch.setattr(api_module, "run_command_json", fake_run_command_json)
    client = TestClient(api_module.app)
    response = client.post("/audit", headers={"Authorization": "Bearer sk-demo"}, json={"path": "data/case1"})
    assert response.status_code == 200
    assert captured["args"] == ("data/case1",)
```

- [ ] **Step 2: Rewrite the Claude audit command to support either a file path or a directory path**

Replace `.claude/commands/audit.md` body with guidance like:

```markdown
读取指定输入路径，路径既可以是单个文件，也可以是一个目录。

- 如果输入是单个文件：直接读取该文件并进入 `expense-extractor` → `expense-auditor`
- 如果输入是目录：先枚举目录下文件，识别申请单、报销单、发票、行程单、酒店单据等材料，再把同一目录下的相关材料一起送入审核流程
- 对目录输入，不要只审核第一个文件；应尽量综合目录内可用材料形成结论
- 最终结果写入 `logs/results/`

参数: $ARGUMENTS
用法:
- `/audit data/case1/invoice.pdf`
- `/audit data/case1`
```

- [ ] **Step 3: Align CLI/API help text with directory input**

Update the CLI and API argument descriptions from “single payload” phrasing to “file or directory path”:

```python
path: str = typer.Argument(..., help="Path to a source file or directory.")
```

```python
class AuditRequest(CommandRequest):
    path: str
```

and make the endpoint docstring mention file-or-directory audit input.

- [ ] **Step 4: Run the directory-input regression tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "directory_path or audit_endpoint_accepts_directory_path or build_command_prompt_allows_directory_path" -v
```

Expected:
- all selected tests PASS

### Task 5: Final Verification On The Real Case Directory

**Files:**
- Verify only: `data/case1/`

- [ ] **Step 1: Run the full bootstrap test suite**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -v
```

Expected:
- all tests PASS

- [ ] **Step 2: Run the real audit command with a directory path**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m server.cli audit-json data/case1
```

Expected:
- output includes original structured fields such as `extracted_data`, `policy_refs`, and `evidence_chain`
- output also includes `result`, `conclusion`, and `explanation`
- `conclusion` is Chinese
- if verdict is `manual_review`, `conclusion` must be `待人工复核`

- [ ] **Step 3: Commit the implementation**

```bash
git add .claude/contracts/common/audit-result.schema.json .claude/skills/common/result-format/SKILL.md .claude/agents/expense/auditor.md .claude/hooks/check-before-write.py .claude/commands/audit.md server/core.py server/cli.py server/api.py tests/test_bootstrap.py .ai_state/docs/superpowers/specs/2026-03-31-audit-result-chinese-display-design.md .ai_state/docs/superpowers/plans/2026-03-31-audit-result-and-directory-input-plan.md
git commit -m "feat: add chinese audit opinions and directory audit input"
```
