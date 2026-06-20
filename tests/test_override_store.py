"""G5 人工否决反馈 store：记录 / 查询 / pending / 标记已提炼。"""

from __future__ import annotations

import uuid

from server.stores.override_store import (
    get_override,
    list_pending_overrides,
    mark_distilled,
    record_override,
)


def test_record_and_get_override():
    rid = f"req-{uuid.uuid4().hex}"
    record_override(
        rid, human_verdict="rejected", original_verdict="approved", reason="人工核实发票造假"
    )
    rec = get_override(rid)
    assert rec is not None
    assert rec["human_verdict"] == "rejected"
    assert rec["original_verdict"] == "approved"
    assert rec["reason"] == "人工核实发票造假"
    assert rec["distilled"] == 0


def test_pending_then_mark_distilled():
    rid = f"req-{uuid.uuid4().hex}"
    record_override(rid, human_verdict="approved")
    assert any(o["request_id"] == rid for o in list_pending_overrides())
    mark_distilled(rid)
    assert get_override(rid)["distilled"] == 1
    assert not any(o["request_id"] == rid for o in list_pending_overrides())
