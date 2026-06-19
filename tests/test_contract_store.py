"""contract_store CRUD + JSON 列往返 + 租户隔离 + created_at 保留 + 持久化/回链测试。"""

from __future__ import annotations

import uuid
from pathlib import Path

from server.stores.contract_store import (
    get_contract,
    get_contract_admin,
    get_contract_by_request_id_admin,
    list_contracts,
    new_contract_id,
    persist_contract_from_result,
    upsert_contract,
)


def _sample(contract_id: str | None = None, tenant: str = "acme") -> dict:
    return {
        "contract_id": contract_id,
        "tenant": tenant,
        "title": "采购合同",
        "contract_no": "HT-2026-001",
        "sign_date": "2026-01-15",
        "amount": 120000.0,
        "currency": "CNY",
        "term": "1 年",
        "source_path": "data/contracts/x/source/contract.pdf",
        "parties": [{"name": "甲方公司", "role": "甲方"}, {"name": "乙方公司", "role": "乙方"}],
        "clauses": [{"clause_id": "3.1", "type": "付款", "text": "预付 30%", "page": 2}],
        "payment_nodes": [
            {
                "node_id": "p1",
                "name": "预付款",
                "amount": 36000.0,
                "ratio": 0.3,
                "due_condition": "签约后",
                "due_date": "2026-02-01",
                "page": 2,
            }
        ],
        "meta": {"source": "ocr"},
    }


def test_new_contract_id_unique():
    assert new_contract_id() != new_contract_id()


def test_upsert_generates_id_when_missing():
    cid = upsert_contract(_sample(contract_id=None, tenant="acme"))
    assert cid
    record = get_contract_admin(cid)
    assert record is not None and record["contract_id"] == cid


def test_roundtrip_preserves_json_fields():
    cid = new_contract_id()
    upsert_contract(_sample(contract_id=cid, tenant="acme"))
    record = get_contract(cid, tenant="acme")
    assert record is not None
    assert record["parties"] == [
        {"name": "甲方公司", "role": "甲方"},
        {"name": "乙方公司", "role": "乙方"},
    ]
    assert record["payment_nodes"][0]["ratio"] == 0.3
    assert record["clauses"][0]["clause_id"] == "3.1"
    assert record["meta"] == {"source": "ocr"}


def test_tenant_isolation():
    cid = new_contract_id()
    upsert_contract(_sample(contract_id=cid, tenant="acme"))
    assert get_contract(cid, tenant="acme") is not None
    assert get_contract(cid, tenant="other") is None


def test_created_at_preserved_on_reupsert():
    cid = new_contract_id()
    upsert_contract(_sample(contract_id=cid, tenant="acme"))
    first = get_contract_admin(cid)
    upsert_contract({**_sample(contract_id=cid, tenant="acme"), "title": "采购合同(修订)"})
    second = get_contract_admin(cid)
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]
    assert second["title"] == "采购合同(修订)"


def test_list_contracts_returns_tenant_rows():
    cid = new_contract_id()
    upsert_contract(_sample(contract_id=cid, tenant="acme-list"))
    rows = list_contracts("acme-list")
    assert any(r["contract_id"] == cid for r in rows)


def _result_with_contract() -> dict:
    return {
        "verdict": "approved",
        "extracted_data": {
            "contract": {
                "contract_meta": {
                    "title": "采购合同",
                    "contract_no": "HT-9",
                    "amount": 99999.0,
                    "currency": "CNY",
                    "sign_date": "2026-03-01",
                    "term": "1 年",
                },
                "parties": [{"name": "甲", "role": "甲方"}],
                "clauses": [{"clause_id": "1", "type": "付款", "text": "...", "page": 1}],
                "payment_nodes": [
                    {
                        "node_id": "n1",
                        "name": "预付",
                        "amount": 30000.0,
                        "ratio": 0.3,
                        "due_condition": "签约",
                        "due_date": "2026-03-15",
                        "page": 1,
                    }
                ],
                "attachments": [],
            }
        },
    }


def test_persist_stores_structure_links_request_and_copies_source(tmp_path):
    src = tmp_path / "contract-case"
    src.mkdir()
    (src / "main.pdf").write_text("合同正文", encoding="utf-8")

    # 唯一 request_id 隔离共享 platform.sqlite3（避免跨运行累积 + 同秒排序不确定性）。
    request_id = f"req-{uuid.uuid4().hex}"
    cid = persist_contract_from_result(
        _result_with_contract(), request_id=request_id, tenant="acme-persist", source_path=str(src)
    )
    assert cid

    record = get_contract(cid, tenant="acme-persist")
    assert record is not None
    assert record["title"] == "采购合同"
    assert record["amount"] == 99999.0
    assert record["payment_nodes"][0]["ratio"] == 0.3
    assert record["request_id"] == request_id
    # result↔contract 回链
    by_req = get_contract_by_request_id_admin(request_id)
    assert by_req is not None and by_req["contract_id"] == cid
    # 原件已 copy 进合同库目录
    assert Path(record["source_path"]).exists()


def test_persist_skips_when_no_contract_structure():
    payload = {"verdict": "manual_review", "extracted_data": {}}
    assert (
        persist_contract_from_result(
            payload, request_id="req-x", tenant=None, source_path="/nonexistent", copy_source=False
        )
        is None
    )
