"""Regression tests for the Codex review findings (F1-F4, F6)."""
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from plate_spinner.api import create_app
from plate_spinner.board import BoardService
from plate_spinner.connectors.base import NormalizedCandidate
from plate_spinner.errors import StorageError
from plate_spinner.store import Store, init_db


def _svc(tmp_path):
    db = tmp_path / "ps.sqlite"
    store = Store(str(db)); init_db(str(db))
    return store, BoardService(store, now=lambda: datetime(2026, 6, 30, 12, tzinfo=timezone.utc))


def test_f3_blocked_item_without_named_blocker_is_skipped(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    blocked = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="b", dedupe_key="todo:t:b", title="Blocked, no blocker named", concern_hint="project", status="blocked", blocked_by=()), now=svc.now())
    good = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="g", dedupe_key="todo:t:g", title="Actionable", concern_hint="project"), now=svc.now())
    nxt = svc.get_snapshot().columns[0].next_item
    assert nxt is not None and nxt.id == good.id
    # even as the only item in a column, a blocked item must not surface as the next action
    store2, svc2 = _svc(tmp_path / "x")
    svc2.create_column("Solo", id="solo")
    svc2.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="b", dedupe_key="todo:t:b", title="Only, blocked", concern_hint="solo", status="blocked", blocked_by=()), now=svc2.now())
    assert svc2.get_snapshot().columns[0].next_item is None
    _ = blocked


def test_f4_invalid_snooze_rejected_and_board_survives(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    item = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="a", dedupe_key="todo:t:a", title="Thing", concern_hint="project"), now=svc.now())
    with pytest.raises(ValueError):
        svc.snooze_item(item.id, "tomorrow")
    with pytest.raises(ValueError):
        svc.snooze_item(item.id, None)
    client = TestClient(create_app(store=store, service=svc))
    assert client.post(f"/api/items/{item.id}/snooze", json={"until": "not-a-date"}).status_code == 422
    # the bad value was never stored, so the board still renders
    assert client.get("/api/board").status_code == 200
    assert store.get_item(item.id).snoozed_until is None


def test_f1_scan_endpoint_runs_real_scan(tmp_path):
    store, svc = _svc(tmp_path)
    app = create_app(store=store, service=svc, config_path="examples/plate-spinner.yaml")
    client = TestClient(app)
    resp = client.post("/api/scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True and body["summary"]["seen"] > 0
    assert len(store.list_items()) > 0
    # source filter only scans the named source
    store2, svc2 = _svc(tmp_path / "x")
    client2 = TestClient(create_app(store=store2, service=svc2, config_path="examples/plate-spinner.yaml"))
    only = client2.post("/api/scan?source=todo").json()["summary"]
    assert only["seen"] > 0
    assert {i.primary_ref.source_type for i in store2.list_items()} == {"todo"}


def test_f1_scan_endpoint_missing_config_returns_503(tmp_path):
    store, svc = _svc(tmp_path)
    client = TestClient(create_app(store=store, service=svc, config_path=str(tmp_path / "nope.yaml")))
    assert client.post("/api/scan").status_code == 503


def test_f6_duplicate_column_id_rejected(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    with pytest.raises(StorageError):
        svc.create_column("Project Again", id="project")
    client = TestClient(create_app(store=store, service=svc))
    assert client.post("/api/columns", json={"id": "project", "name": "Dup"}).status_code == 409
    # original column metadata is untouched
    assert store.get_concern("project").name == "Project"


def test_f2_dashboard_escapes_source_strings(tmp_path):
    store, svc = _svc(tmp_path)
    html = TestClient(create_app(store=store, service=svc)).get("/").text
    assert "function esc(" in html
    assert "esc(c.next_item.title)" in html and "esc(i.title)" in html


def test_cr_patch_applies_name_and_other_fields(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    client = TestClient(create_app(store=store, service=svc))
    out = client.patch("/api/columns/project", json={"name": "Renamed", "description": "desc"}).json()
    assert out["name"] == "Renamed" and out["description"] == "desc"


def test_cr_malformed_bodies_return_422(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    item = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="a", dedupe_key="todo:t:a", title="X", concern_hint="project"), now=svc.now())
    client = TestClient(create_app(store=store, service=svc))
    assert client.post(f"/api/items/{item.id}/assign", json={}).status_code == 422
    assert client.post("/api/columns", json={}).status_code == 422


def test_cr_reorder_keeps_positions_unique(tmp_path):
    store, svc = _svc(tmp_path)
    for c in ("a", "b", "c"):
        svc.create_column(c.upper(), id=c)
    svc.reorder_columns(["c", "a"])  # partial payload omits "b"
    positions = [col.position for col in store.list_concerns()]
    assert len(positions) == len(set(positions))  # no duplicates


def test_cr_unknown_source_type_is_an_error(tmp_path):
    from plate_spinner.cli import run_scan
    store, svc = _svc(tmp_path)
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("sources:\n  - id: oops\n    type: bogus\n    path: nope\n")
    summary = run_scan(svc, str(cfg))
    assert summary["errors"] == 1
    health = store.list_scan_health()
    assert health and health[0]["last_status"] == "error"


def test_cr_manual_assignment_survives_rescan(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    svc.create_column("Other", id="other")
    cand = NormalizedCandidate(source_type="todo", source_id="t", external_id="a", dedupe_key="todo:t:a", title="Movable", concern_hint="project")
    item = svc.upsert_candidate(cand, now=svc.now())
    svc.assign_item(item.id, "other")  # manual override
    svc.upsert_candidate(cand, now=svc.now())  # rescan re-maps hint to "project"
    assert store.get_item(item.id).concern_id == "other"
