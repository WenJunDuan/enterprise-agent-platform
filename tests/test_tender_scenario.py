from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


_TOKEN = "test-fake-token-acme-tender-scenario"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def test_create_project_scenario_roundtrip_and_filter(monkeypatch):
    client = _client(monkeypatch)
    unique = f"S6-BIDDER-SELF-CHECK-{uuid.uuid4().hex}"
    create_resp = client.post(
        "/tender/projects",
        json={
            "tender_no": unique,
            "title": "S6 投标自查项目",
            "scenario": "bidder_self_check",
        },
        headers=_AUTH,
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    assert created["scenario"] == "bidder_self_check"

    detail_resp = client.get(f"/tender/projects/{created['project_id']}", headers=_AUTH)
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["scenario"] == "bidder_self_check"

    filtered_resp = client.get(
        "/tender/projects?scenario=bidder_self_check&limit=100", headers=_AUTH
    )
    assert filtered_resp.status_code == 200, filtered_resp.text
    filtered = filtered_resp.json()
    assert any(item["project_id"] == created["project_id"] for item in filtered)
    assert all(item["scenario"] == "bidder_self_check" for item in filtered)

    expert_resp = client.get(
        "/tender/projects?scenario=expert_assist&limit=100", headers=_AUTH
    )
    assert expert_resp.status_code == 200, expert_resp.text
    assert all(item["project_id"] != created["project_id"] for item in expert_resp.json())


def test_create_project_defaults_to_expert_assist(monkeypatch):
    client = _client(monkeypatch)
    unique = f"S6-DEFAULT-EXPERT-{uuid.uuid4().hex}"
    create_resp = client.post(
        "/tender/projects",
        json={"tender_no": unique, "title": "S6 默认专家辅助"},
        headers=_AUTH,
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    assert created["scenario"] == "expert_assist"

    filtered_resp = client.get(
        "/tender/projects?scenario=expert_assist&limit=100", headers=_AUTH
    )
    assert filtered_resp.status_code == 200, filtered_resp.text
    assert any(item["project_id"] == created["project_id"] for item in filtered_resp.json())


def test_same_tender_no_is_idempotent_inside_scenario_not_across_scenarios(monkeypatch):
    client = _client(monkeypatch)
    tender_no = f"S6-SHARED-NO-{uuid.uuid4().hex}"

    expert_resp = client.post(
        "/tender/projects",
        json={
            "tender_no": tender_no,
            "title": "S6 专家辅助",
            "scenario": "expert_assist",
        },
        headers=_AUTH,
    )
    assert expert_resp.status_code == 200, expert_resp.text
    expert = expert_resp.json()

    self_check_resp = client.post(
        "/tender/projects",
        json={
            "tender_no": tender_no,
            "title": "S6 投标自查",
            "scenario": "bidder_self_check",
        },
        headers=_AUTH,
    )
    assert self_check_resp.status_code == 200, self_check_resp.text
    self_check = self_check_resp.json()

    repeated_self_check_resp = client.post(
        "/tender/projects",
        json={
            "tender_no": tender_no,
            "title": "S6 投标自查重复提交",
            "scenario": "bidder_self_check",
        },
        headers=_AUTH,
    )
    assert repeated_self_check_resp.status_code == 200, repeated_self_check_resp.text

    assert expert["project_id"] != self_check["project_id"]
    assert expert["scenario"] == "expert_assist"
    assert self_check["scenario"] == "bidder_self_check"
    assert repeated_self_check_resp.json()["project_id"] == self_check["project_id"]
