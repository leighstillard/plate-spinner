
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from plate_spinner.board import BoardService
from plate_spinner.connectors.base import NormalizedCandidate
from plate_spinner.store import Store, init_db
from plate_spinner.prioritization import select_next_item
from plate_spinner.api import create_app


def test_domain_deterministic_and_no_importance_or_snoozed_status(tmp_path):
    db = tmp_path / "ps.sqlite"
    store = Store(str(db)); init_db(str(db))
    svc = BoardService(store, now=lambda: datetime(2026, 6, 30, 12, tzinfo=timezone.utc))
    col = svc.create_column("Project", id="project")
    later = datetime(2026, 7, 1, tzinfo=timezone.utc).isoformat()
    a = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="todos", external_id="a", dedupe_key="todo:todos:a", title="Zulu", concern_hint="project", urgency=1), now=svc.now())
    b = svc.upsert_candidate(NormalizedCandidate(source_type="project_plan", source_id="plan", external_id="b", dedupe_key="project_plan:plan:b", title="Alpha", concern_hint="project", urgency=5, due_at=later), now=svc.now())
    svc.snooze_item(a.id, "2026-07-02T00:00:00+00:00")
    s1 = svc.get_snapshot().to_dict()
    s2 = svc.get_snapshot().to_dict()
    assert s1 == s2
    assert s1["columns"][0]["next_item"]["id"] == b.id
    assert "why" in s1["columns"][0]["next_explanation"]["reasons"][0].lower()
    assert all("importance" not in json.dumps(x) for x in [s1])
    assert store.get_item(a.id).status == "candidate"
    assert store.get_item(a.id).snoozed_until is not None


def test_scan_cursors_attention_and_within_source_dedup(tmp_path):
    db = tmp_path / "ps.sqlite"
    store = Store(str(db)); init_db(str(db))
    svc = BoardService(store, now=lambda: datetime(2026, 6, 30, 12, tzinfo=timezone.utc), stale_after_seconds=60)
    svc.create_column("Project", id="project")
    blocker = svc.upsert_candidate(NormalizedCandidate(source_type="project_plan", source_id="plan", external_id="block", dedupe_key="project_plan:plan:block", title="Blocking dependency", concern_hint="project", status="ready"), now=svc.now())
    blocked = svc.upsert_candidate(NormalizedCandidate(source_type="project_plan", source_id="plan", external_id="blocked", dedupe_key="project_plan:plan:blocked", title="Blocked task", concern_hint="project", status="blocked", blocked_by=(blocker.id,)), now=svc.now())
    svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="todos", external_id="u", dedupe_key="todo:todos:u", title="Unmapped thing"), now=svc.now())
    # same external id/dedupe within the same source updates, not duplicates
    svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="todos", external_id="u", dedupe_key="todo:todos:u", title="Unmapped thing updated"), now=svc.now())
    # same external id in a different source remains a different item
    svc.upsert_candidate(NormalizedCandidate(source_type="github", source_id="repo", external_id="u", dedupe_key="github:repo:u", title="Unmapped gh"), now=svc.now())
    store.record_scan_health("todo", "todos", None, "ok", None, {"seen": 2}, "2026-06-30T11:58:00+00:00")
    store.record_scan_health("github", "repo", None, "error", "boom", {"errors": 1}, "2026-06-30T11:00:00+00:00")
    snap = svc.get_snapshot().to_dict()
    att = snap["attention"]
    assert len([i for i in store.list_items() if i.primary_ref.source_type == "todo"]) == 1
    assert len(att["unmapped_candidates"]) >= 2
    assert att["blocked_items"][0]["blocked_by"] == [blocker.id]
    gh = [h for h in att["connector_health"] if h["source_type"] == "github"][0]
    assert gh["last_status"] == "error" and gh["stale"] is True and gh["last_error"] == "boom"
    assert "project" not in att["empty_active_columns"]


def test_api_and_web_dashboard_with_temp_db(tmp_path):
    db = tmp_path / "ps.sqlite"
    store = Store(str(db)); init_db(str(db))
    svc = BoardService(store, now=lambda: datetime(2026, 6, 30, 12, tzinfo=timezone.utc))
    svc.create_column("Project", id="project")
    item = svc.upsert_candidate(NormalizedCandidate(source_type="project_plan", source_id="plan", external_id="1", dedupe_key="project_plan:plan:1", title="Ship dashboard", concern_hint="project", urgency=50), now=svc.now())
    app = create_app(store=store, service=svc)
    client = TestClient(app)
    board = client.get("/api/board").json()
    assert board["columns"][0]["next_item"]["title"] == "Ship dashboard"
    assert client.get("/api/attention").status_code == 200
    assert client.get("/api/columns/project").json()["next_item"]["id"] == item.id
    assert client.post(f"/api/items/{item.id}/pin", json={"rank": 0}).status_code == 200
    assert client.post(f"/api/items/{item.id}/snooze", json={"until": "2026-07-01T00:00:00+00:00"}).status_code == 200
    assert client.post(f"/api/items/{item.id}/dismiss", json={}).status_code == 200
    assert client.post(f"/api/items/{item.id}/assign", json={"concern_id": "project"}).status_code == 200
    assert client.post("/api/columns", json={"id": "personal", "name": "Personal"}).status_code == 200
    assert client.patch("/api/columns/personal", json={"name": "Life"}).json()["name"] == "Life"
    assert "Plate Spinner" in client.get("/").text
    assert "/api/board" in client.get("/").text


def test_cli_and_e2e_fixture_demo(tmp_path, capsys):
    from plate_spinner.cli import main
    db = str(tmp_path / "demo.sqlite")
    assert main(["init", "--db", db]) == 0
    assert main(["column", "add", "Project", "--id", "project", "--db", db]) == 0
    assert main(["column", "add", "Day Job", "--id", "day-job", "--db", db]) == 0
    assert main(["scan", "--config", "examples/plate-spinner.yaml", "--db", db]) == 0
    assert main(["board", "--json", "--db", db]) == 0
    board = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert board["attention"]["unmapped_candidates"]
    assert board["attention"]["blocked_items"]
    assert board["attention"]["connector_health"]
    assert main(["attention", "--json", "--db", db]) == 0
