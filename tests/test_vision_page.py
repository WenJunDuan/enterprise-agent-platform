"""vision-page（判定时刻带图问答）三件套：skill 行为 / Bash 白名单 / 命令层接线。

**为什么有这个工具**（纠偏令 v2 二节）：像素必需的判定点——证书有效期、公章归属、大写金额、
检测报告标识——目前只能靠 OCR 转写，而扫描盖章页的转写常为空。把这些判定从"读转写文字"改成
"判定时刻带图问 VLM"，避免先把图降维成有损文字再去检索。

三节各自的判据：
- **skill**：只渲染被问的那一页、答案原样透传、三类失败给结构化错误（**不外泄堆栈**）；
- **白名单**：vision.py 的 Bash 调用面与 ocr-page 同闸同型——越界一律拒（评标子进程处理的是
  攻击者可控的投标 PDF，工具面松一寸就是命令注入面）；
- **接线**：命令文件里写给模型的调用式，必须**就是**闸真正放行的那一条（两处各写一份必然漂移）。
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import sys
from pathlib import Path

import pytest

from server.common.agent_bridge import build_options
from server.ocr import OcrDependencyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPT = PROJECT_ROOT / ".claude/skills/vision-page/vision.py"
COMMAND = PROJECT_ROOT / ".claude/commands/tender-evaluate.md"

_VISION_PREFIX = "uv run python .claude/skills/vision-page/vision.py"
_OCR_PREFIX = "uv run python .claude/skills/ocr-page/ocr.py"


@pytest.fixture(scope="module")
def vision():
    """按路径加载 skill 脚本（它以独立脚本分发，不是可 import 的包）。"""
    spec = importlib.util.spec_from_file_location("vision_page_skill", SKILL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    target = tmp_path / "bid.pdf"
    target.write_bytes(b"%PDF-fake; the skill never parses it in tests")
    return target


@pytest.fixture
def backend(monkeypatch, tmp_path):
    """把渲染与 VLM 两端换成可观测替身，返回记录了调用参数的 dict。

    替身挂在**真实模块对象**上（``server.ocr.engine`` / ``vlm_client`` / ``cloud_chunk``），
    故这里验证的是 skill 真的走了这两条既有链路，而不是测试自造的接口。
    """
    from server.ocr import cloud_chunk, engine, vlm_client

    seen: dict = {"subset_calls": [], "rendered": [], "vlm": None}
    subset_path = tmp_path / "single-page-subset.pdf"
    subset_path.write_bytes(b"%PDF-subset")

    def fake_subset(path, page_indices):
        seen["subset_calls"].append((Path(path), list(page_indices)))
        return subset_path

    def fake_iter(path):
        seen["rendered"].append(Path(path))
        return iter([{"page_number": 1, "mime_type": "image/png", "content": b"PNGBYTES"}])

    def fake_call_vlm(**kwargs):
        seen["vlm"] = kwargs
        return "有效期至 2027 年 6 月 30 日"

    monkeypatch.setattr(cloud_chunk, "pdf_page_count", lambda path: 12)
    monkeypatch.setattr(engine, "extract_pdf_subset", fake_subset)
    monkeypatch.setattr(engine, "_iter_pdf_pages", fake_iter)
    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", "http://litellm:4000/v1")
    monkeypatch.setattr(engine, "OCR_VL_MODEL_NAME", "vision-model")
    monkeypatch.setattr(engine, "OCR_VL_API_KEY", "test-fake-key-not-real")
    monkeypatch.setattr(vlm_client, "call_vlm", fake_call_vlm)
    monkeypatch.delenv("VISION_PAGE_URL", raising=False)
    monkeypatch.delenv("VISION_PAGE_MODEL", raising=False)
    monkeypatch.delenv("VISION_PAGE_API_KEY", raising=False)
    seen["subset_path"] = subset_path
    return seen


# ── skill：渲染 → 带图问 → 答案透传 ────────────────────────────────────────────


def test_only_the_asked_page_is_rendered_and_sent_as_an_image(vision, backend, pdf):
    """被问第 7 页就只抽第 7 页（0-based 6）渲染成图——不是整份渲染后挑一页。"""
    answer = vision.answer_page_question(pdf, 7, "证书有效期截止到哪天？")

    assert backend["subset_calls"] == [(pdf, [6])]
    assert backend["rendered"] == [backend["subset_path"]]
    expected_data_url = "data:image/png;base64," + base64.b64encode(b"PNGBYTES").decode("ascii")
    assert backend["vlm"]["data_url"] == expected_data_url
    assert answer == "有效期至 2027 年 6 月 30 日"


def test_question_and_page_are_carried_into_the_vlm_prompt(vision, backend, pdf):
    """问题原文必须进 prompt，且 prompt 要求只依据图中可见内容作答（防 VLM 自由发挥）。"""
    vision.answer_page_question(pdf, 7, "这一页的公章是哪家单位的？")

    prompt = backend["vlm"]["prompt"]
    assert "这一页的公章是哪家单位的？" in prompt
    assert "7" in prompt
    assert "图" in prompt


def test_temporary_single_page_pdf_is_removed(vision, backend, pdf):
    """抽页产生的临时 PDF 由本 skill 负责删（extract_pdf_subset 的契约）。"""
    vision.answer_page_question(pdf, 7, "大写金额是多少？")

    assert not backend["subset_path"].exists()


def test_answer_is_printed_verbatim_on_stdout(vision, backend, pdf, capsys):
    code = vision.main([str(pdf), "--page", "7", "--question", "证书有效期截止到哪天？"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "有效期至 2027 年 6 月 30 日"
    assert captured.err == ""


def test_vision_page_env_overrides_the_ocr_transcription_endpoint(
    vision, backend, pdf, monkeypatch
):
    """OCR_CLOUD=1 部署里 OCR_VL_SERVER_URL 是云 job API（不是 chat/completions），
    故 vision-page 必须能被单独指到一个 OpenAI 兼容端点；未设时才回落 OCR_VL_*。"""
    monkeypatch.setenv("VISION_PAGE_URL", "http://vlm-gateway:8000/v1")
    monkeypatch.setenv("VISION_PAGE_MODEL", "qwen-vl")
    monkeypatch.setenv("VISION_PAGE_API_KEY", "test-fake-vision-key")

    vision.answer_page_question(pdf, 3, "检测报告上的标识是什么？")

    assert backend["vlm"]["url"] == "http://vlm-gateway:8000/v1/chat/completions"
    assert backend["vlm"]["model"] == "qwen-vl"
    assert backend["vlm"]["api_key"] == "test-fake-vision-key"


def test_falls_back_to_the_ocr_vlm_endpoint_when_unset(vision, backend, pdf):
    vision.answer_page_question(pdf, 3, "检测报告上的标识是什么？")

    assert backend["vlm"]["url"] == "http://litellm:4000/v1/chat/completions"
    assert backend["vlm"]["model"] == "vision-model"


# ── skill：三类失败都给结构化错误，且不外泄堆栈 ────────────────────────────────


def _stderr_is_structured(text: str) -> bool:
    return text.startswith("[错误]") and "Traceback" not in text and 'File "' not in text


def test_missing_file_is_a_structured_error(vision, backend, tmp_path, capsys):
    code = vision.main([str(tmp_path / "nope.pdf"), "--page", "1", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 2
    assert _stderr_is_structured(captured.err)
    assert backend["subset_calls"] == []


def test_page_beyond_the_document_is_rejected_before_rendering(vision, backend, pdf, capsys):
    """页码越界要在渲染前拦下并说明总页数——渲染层的"抽不出页"错误看不出是越界还是坏文件。"""
    code = vision.main([str(pdf), "--page", "99", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 2
    assert _stderr_is_structured(captured.err)
    assert "12" in captured.err and "99" in captured.err
    assert backend["subset_calls"] == []


def test_non_positive_page_is_rejected(vision, backend, pdf, capsys):
    code = vision.main([str(pdf), "--page", "0", "--question", "有效期？"])

    assert code == 2
    assert _stderr_is_structured(capsys.readouterr().err)
    assert backend["subset_calls"] == []


def test_non_pdf_input_is_rejected_and_points_at_ocr_page(vision, backend, tmp_path, capsys):
    """本 skill 只渲染 PDF 页；其它形态不假装能做，指回 ocr-page。"""
    docx = tmp_path / "bid.docx"
    docx.write_bytes(b"PK-fake")

    code = vision.main([str(docx), "--page", "1", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 2
    assert _stderr_is_structured(captured.err)
    assert "ocr-page" in captured.err


def test_render_failure_is_structured(vision, backend, pdf, monkeypatch, capsys):
    """抽页失败（缺 pymupdf / 文件损坏）→ 结构化错误，不抛栈。"""
    from server.ocr import engine

    monkeypatch.setattr(engine, "extract_pdf_subset", lambda path, indices: None)

    code = vision.main([str(pdf), "--page", "7", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 4
    assert _stderr_is_structured(captured.err)


def test_vlm_failure_is_structured_and_never_leaks_a_traceback(
    vision, backend, pdf, monkeypatch, capsys
):
    from server.ocr import vlm_client

    def boom(**kwargs):
        raise OcrDependencyError("OCR VLM 远端调用失败：HTTP Error 502: Bad Gateway")

    monkeypatch.setattr(vlm_client, "call_vlm", boom)

    code = vision.main([str(pdf), "--page", "7", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 5
    assert _stderr_is_structured(captured.err)
    assert not backend["subset_path"].exists()  # 失败也要清临时文件


def test_unconfigured_endpoint_is_structured_and_never_networks(
    vision, backend, pdf, monkeypatch, capsys
):
    from server.ocr import engine, vlm_client

    def must_not_be_called(**kwargs):
        raise AssertionError("端点未配置时不得发请求")

    monkeypatch.setattr(engine, "OCR_VL_SERVER_URL", None)
    monkeypatch.setattr(vlm_client, "call_vlm", must_not_be_called)

    code = vision.main([str(pdf), "--page", "7", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 5
    assert _stderr_is_structured(captured.err)
    assert "VISION_PAGE_URL" in captured.err


def test_dependency_import_failure_is_structured(vision, pdf, monkeypatch, capsys):
    """服务端包加载不了（skill 以独立脚本分发）→ 明确报错供 agent 回落，不抛 ImportError 栈。"""
    monkeypatch.setitem(sys.modules, "server.ocr.engine", None)

    code = vision.main([str(pdf), "--page", "7", "--question", "有效期？"])

    captured = capsys.readouterr()
    assert code == 3
    assert _stderr_is_structured(captured.err)


# ── Bash 白名单：与 ocr-page 同闸，越界一律拒 ──────────────────────────────────


@pytest.fixture
def case_paths(tmp_path: Path) -> dict[str, Path]:
    case_root = tmp_path / "case-a"
    case_root.mkdir()
    inside = case_root / "bid.pdf"
    inside.write_bytes(b"not a real PDF; the hook only checks the boundary")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    escaped = case_root / "escaped.pdf"
    escaped.symlink_to(outside)
    return {"root": case_root, "inside": inside, "outside": outside, "escaped": escaped}


def _hook(options):
    matchers = options.hooks["PreToolUse"]
    assert len(matchers) == 1 and matchers[0].matcher == "Bash"
    return matchers[0].hooks[0]


def _decision(options, command: str) -> str:
    response = asyncio.run(
        _hook(options)(
            {"tool_name": "Bash", "tool_input": {"command": command}},
            "test-tool-use-id",
            {"signal": None},
        )
    )
    return response["hookSpecificOutput"]["permissionDecision"]


def _vision_command(file_path: Path, page: str = "7", question: str = "这一页的公章是哪家单位的") -> str:
    return f'{_VISION_PREFIX} {file_path} --page {page} --question "{question}"'


def test_hook_allows_a_well_formed_vision_command(case_paths):
    options = build_options(case_root=case_paths["root"])

    assert _decision(options, _vision_command(case_paths["inside"])) == "allow"


def test_hook_allows_both_flag_orders_and_single_quotes(case_paths):
    options = build_options(case_root=case_paths["root"])
    file_path = case_paths["inside"]

    for command in (
        f'{_VISION_PREFIX} {file_path} --page 7 --question "证书有效期截止到哪天"',
        f'{_VISION_PREFIX} {file_path} --question "证书有效期截止到哪天" --page 7',
        f"{_VISION_PREFIX} {file_path} --page 7 --question '大写金额与小写是否一致'",
        f'{_VISION_PREFIX} "{file_path}" --page 315 --question "检测报告上的标识是什么"',
    ):
        assert _decision(options, command) == "allow", command


def test_hook_still_allows_ocr_page_commands(case_paths):
    """扩白名单不得把既有 ocr-page 调用面挤掉（转写仍是 vision 不可用时的次选）。"""
    options = build_options(case_root=case_paths["root"])

    assert _decision(options, f"{_OCR_PREFIX} {case_paths['inside']} --pages 7 --seal") == "allow"


def test_hook_denies_shell_injection_in_the_question(case_paths, tmp_path):
    options = build_options(case_root=case_paths["root"])
    marker = tmp_path / "must-not-be-created"
    file_path = case_paths["inside"]

    for command in (
        f'{_VISION_PREFIX} {file_path} --page 7 --question "公章"; touch {marker}',
        f'{_VISION_PREFIX} {file_path} --page 7 --question "$(touch {marker})"',
        f"{_VISION_PREFIX} {file_path} --page 7 --question \"`touch {marker}`\"",
        f'{_VISION_PREFIX} {file_path} --page 7 --question "公章" | touch {marker}',
        f'{_VISION_PREFIX} {file_path} --page 7 --question "公章" && touch {marker}',
        f'{_VISION_PREFIX} {file_path} --page 7 --question "公章"\ntouch {marker}',
        f'{_VISION_PREFIX} {file_path} --page 7 --question "公章 " -o {marker}',
    ):
        assert _decision(options, command) == "deny", command
        assert not marker.exists(), command


def test_hook_denies_unquoted_or_quote_breaking_questions(case_paths):
    """问句必须是**单个带引号**的词——裸问句会被 shell 分词，内嵌引号会提前闭合。"""
    options = build_options(case_root=case_paths["root"])
    file_path = case_paths["inside"]

    for command in (
        f"{_VISION_PREFIX} {file_path} --page 7 --question 公章是哪家",
        f'{_VISION_PREFIX} {file_path} --page 7 --question "公章"是"哪家"',
        f'{_VISION_PREFIX} {file_path} --page 7 --question ""',
        f"{_VISION_PREFIX} {file_path} --page 7",
        f'{_VISION_PREFIX} {file_path} --question "公章是哪家"',
    ):
        assert _decision(options, command) == "deny", command


def test_hook_denies_an_oversized_question(case_paths):
    """问句有长度上界：判定时刻的问答是一问一点，不是把整段提示词塞进命令行。"""
    from server.common.agent_bridge import VISION_PAGE_MAX_QUESTION_CHARS

    options = build_options(case_root=case_paths["root"])
    oversized = "问" * (VISION_PAGE_MAX_QUESTION_CHARS + 1)

    assert _decision(options, _vision_command(case_paths["inside"], question=oversized)) == "deny"
    assert (
        _decision(
            options,
            _vision_command(
                case_paths["inside"], question="问" * VISION_PAGE_MAX_QUESTION_CHARS
            ),
        )
        == "allow"
    )


def test_hook_denies_paths_outside_the_case(case_paths):
    options = build_options(case_root=case_paths["root"])

    for target in (
        case_paths["outside"],
        case_paths["escaped"],
        case_paths["root"] / ".." / "outside.pdf",
        case_paths["root"] / "missing.pdf",
    ):
        assert _decision(options, _vision_command(target)) == "deny", target


def test_hook_denies_invalid_pages(case_paths):
    options = build_options(case_root=case_paths["root"])

    for page in ("0", "-1", "abc", "7-9", str(2**63), "9" * 5000):
        assert _decision(options, _vision_command(case_paths["inside"], page=page)) == "deny", page


def test_hook_denies_a_neighbouring_script_under_the_same_skill_dir(case_paths):
    """白名单钉的是**这一个脚本**，不是 skills 目录——换个脚本名即越界。"""
    options = build_options(case_root=case_paths["root"])
    command = (
        "uv run python .claude/skills/vision-page/other.py "
        f'{case_paths["inside"]} --page 7 --question "公章"'
    )

    assert _decision(options, command) == "deny"


# ── 命令层接线：写给模型的调用式必须就是闸放行的那一条 ─────────────────────────


def _command_text() -> str:
    return COMMAND.read_text(encoding="utf-8")


def _a2_row() -> str:
    rows = [line for line in _command_text().splitlines() if line.startswith("| A2 |")]
    assert len(rows) == 1, "决策表须有且只有一行 A2"
    return rows[0]


def test_a2_escalates_to_vision_page_before_ocr_page():
    """A2（读不清）的首选升级路径 = 带图问；转写降为次选（纠偏令 v2 二节）。"""
    row = _a2_row()

    assert "vision-page" in row, "A2 未接 vision-page"
    assert "ocr-page" in row, "A2 仍须保留 ocr-page 作次选（vision 端点不可用时）"
    assert row.index("vision-page") < row.index("ocr-page"), "vision-page 必须写在 ocr-page 之前"


def test_pixel_judgment_points_are_directed_at_vision_page():
    """证书有效期 / 公章归属 / 大写金额 / 检测报告标识：优先带图问，而非采信 OCR 文字。"""
    lines = [line for line in _command_text().splitlines() if "vision-page" in line]
    assert lines, "命令文件未提到 vision-page"

    joined = "\n".join(lines)
    for marker in ("有效期", "公章", "大写", "检测报告"):
        assert marker in joined, f"像素判定点「{marker}」未指向 vision-page"


def test_documented_invocation_is_exactly_what_the_hook_allows(case_paths):
    """命令文件里的调用式与闸的文法是同一件事——两处各写一份必然漂移（先例：页锚正则）。"""
    text = _command_text()
    assert _VISION_PREFIX in text, "命令文件未写出 vision.py 的调用式"
    assert "--page" in text and "--question" in text

    options = build_options(case_root=case_paths["root"])
    assert _decision(options, _vision_command(case_paths["inside"])) == "allow"
