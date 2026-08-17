"""契约失败的 resume 修补轮（D：消灭"整单从头重跑"这个 20 分钟档）。

原实现在模型写坏 JSON 时把整个 prompt（命令正文 + 数十 KB 底稿）原样重发，模型从头再评
一遍标。但失败的只是**最后一步的 JSON 序列化**——评标结论本身已经在那个会话里。改为
``resume`` 同一会话、只发一条常数级短指令让它把 JSON 改对，代价从"再跑一整单"降到"再吐
一次结论"。

一个变更理由：**怎么向模型描述这次契约失败**（提示词文案 + 从异常里取会话 id 的判据）。
真正的调用由 ``runner`` 发起——它持有本次评标的全套 kwargs（schema / evidence_source /
case_root / 工具面），把它们再传一遍只会制造第二份必须同步的参数表。
"""

from __future__ import annotations

from server.common.contract import JSONContractError

# 错误原文截断长度：网关透出的错误偶尔挂着整段响应体，原样回灌等于又把底稿发回去一次。
# 取 800 字符——足够包住契约校验器的具体指摘（缺哪个字段 / 哪个枚举越界），远小于任何底稿。
_ERROR_EXCERPT_CHARS = 800

_REPAIR_PROMPT = """上一轮回复未通过服务端 JSON 契约校验：

{error}

**不要重新评标、不要重新读取任何文件**——你上一轮得出的评标结论仍然有效，本轮只修正输出格式：

- 整个回复必须是**单个 JSON 对象**（首字符 `{{`、末字符 `}}`）；分析只能写在 `<think></think>` 内，`</think>` 之后不得有任何其它文字。
- 字符串值内引用项目名 / 投标人 / 评分项时**一律用中文引号「」**，严禁半角双引号（会提前闭合字符串）。
- 各字段内容与上一轮保持一致，只改上面指出的那处契约 / 语法问题。
"""


def build_repair_prompt(error: Exception) -> str:
    """Compose the short "fix your JSON" turn sent into the resumed session.

    Args:
        error: 上一轮抛出的契约失败，其消息即向模型陈述的失败事实。

    Returns:
        常数级大小的修补指令（含截断后的错误原文）。
    """
    return _REPAIR_PROMPT.format(error=str(error)[:_ERROR_EXCERPT_CHARS])


def repair_session_id(error: Exception) -> str | None:
    """Return the CLI session to resume for a repair turn, or ``None`` to rerun in full.

    Args:
        error: 契约重试环刚捕获的异常。

    Returns:
        非空会话 id；异常不是契约失败、或失败发生在会话建立之前时返回 ``None``。
    """
    if not isinstance(error, JSONContractError):
        return None
    return error.session_id or None
