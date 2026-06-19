"""contract_store CRUD + JSON 列往返 + 租户隔离 + created_at 保留测试。"""

from __future__ import annotations

from server.stores.contract_store import (
    get_contract,
    get_contract_admin,
    list_contracts,
    new_contract_id,
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
