"""Tender (招投标评标) feature domain.

镜像 ``server/audit/`` 的先例形态：纯评分/编排逻辑落 feature 层，routes 层只留 HTTP/任务调度壳。
D1（本包新建）先落 ``eval.py``（golden-case 回归评测核）+ ``runner.py``（评标核心，从
``server/routes/tender_worker.py`` 下沉，见 D1 design T2）；D2 会继续把 tender 摄取/输出后处理
等模块迁入本包，见 ``.ai_state/sprints/2026-07-02-eval-tender-scaffold/design.md``。

分层：tender（feature）可 import ocr（feature，服务层，2026-07-15 方案 i 拍板）与 common/core/
stores/platform；禁止 import routes/app/audit（见 ``tests/test_layering.py``）。
"""

from __future__ import annotations
