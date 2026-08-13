"""文档识别流水线（确定性、进程内）：分类 → 直读/OCR → 组装识别底稿。

设计目标：把"分类 + 原生直读 + 调 OCR 引擎"这些**确定性、无判断**的步骤放在 Python
进程内一次跑完，避免像 agent 逐文件 Bash 那样每步一次网关往返（每跳 17-48s）。对齐
`server.audit.runner` 的"内联、单跳"哲学。

同一份逻辑两处复用：
- 服务端热路径 `server.ocr.runner` 进程内直接调 `pipeline.extract_dir`（0 网关往返）；
- 交互式 `python -m server.ocr <dir>` 供 multi-ocr skill 用（agent 1 次 Bash 往返）。

第三方依赖（openpyxl / python-docx / pypdf / paddleocr / paddlex）一律在函数内导入，
缺失时抛 `OcrDependencyError`，便于无引擎环境也能 import 本包做单测。
"""

from __future__ import annotations


class OcrError(RuntimeError):
    """OCR 流水线错误基类。"""


class OcrDependencyError(OcrError):
    """缺少第三方依赖（按需安装）。"""


__all__ = ["OcrDependencyError", "OcrError"]
