"""Tender evaluation routes: /tender/evaluate, /tender/tasks/*, /tender/projects/*.

D2（design T4）把原 912 行单文件 ``routes/tender.py`` 按既有 banner 分节拆薄为本 package：

- ``tasks``: 单投标人评标提交/查询/重试/删除三件套（``/evaluate``、``/tasks/*``）。
- ``compare``: 招标项目价格横比（``/projects/{id}/compare``）。
- ``projects``: 招标项目实体 CRUD + 投标人名册 + 结果回看（``/projects*``）。
- ``docs``: 招标/投标文件上传 + OCR 预热编排（``/projects/{id}/tender-doc``、``/bids``、
  ``/docs-status``）。

本模块只建 ``router`` 并按依赖顺序 import 四个分节模块（各自用 ``@router.xxx`` 装饰器把路由
挂到同一个 router 上）——纯路由分组，业务逻辑已在 D2 T1-T3 下沉 ``server.tender.*``。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["tender"])

# 依赖顺序：tasks 无内部依赖；compare 用到 tasks.TenderSubmitAcceptedResponse；
# projects 用到 tasks._submit_bid_evaluation 与 compare._current_compare_signature；
# docs 无内部依赖。装饰器在各模块 import 时执行，把路由挂到上面的 router 对象上。
from server.routes.tender import tasks as _tasks  # noqa: E402,F401
from server.routes.tender import compare as _compare  # noqa: E402,F401
from server.routes.tender import projects as _projects  # noqa: E402,F401
from server.routes.tender import docs as _docs  # noqa: E402,F401
