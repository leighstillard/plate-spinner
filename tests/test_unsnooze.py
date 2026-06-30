"""Snoozed items live in their own per-column section and can be unsnoozed."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from plate_spinner.api import create_app
from plate_spinner.board import BoardService
from plate_spinner.connectors.base import NormalizedCandidate
from plate_spinner.store import Store, init_db


def _svc(tmp_path):
    db = tmp_path / "ps.sqlite"
    store = Store(str(db)); init_db(str(db))
    return store, BoardService(store, now=lambda: datetime(2026, 6, 30, 12, tzinfo=timezone.utc))


def test_snoozed_item_leaves_queue_for_snoozed_section(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    a = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="a", dedupe_key="todo:t:a", title="Alpha", concern_hint="project"), now=svc.now())
    svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="b", dedupe_key="todo:t:b", title="Bravo", concern_hint="project"), now=svc.now())
    svc.snooze_item(a.id, "2027-01-01T00:00:00+00:00")
    col = svc.get_snapshot().columns[0].to_dict()
    assert [i["id"] for i in col["snoozed"]] == [a.id]
    assert a.id not in [i["id"] for i in col["queue"]]
    assert col["next_item"]["id"] != a.id  # snoozed item is never the headline


def test_unsnooze_endpoint_restores_item(tmp_path):
    store, svc = _svc(tmp_path)
    svc.create_column("Project", id="project")
    a = svc.upsert_candidate(NormalizedCandidate(source_type="todo", source_id="t", external_id="a", dedupe_key="todo:t:a", title="Alpha", concern_hint="project"), now=svc.now())
    svc.snooze_item(a.id, "2027-01-01T00:00:00+00:00")
    client = TestClient(create_app(store=store, service=svc))
    out = client.post(f"/api/items/{a.id}/unsnooze").json()
    assert out["snoozed_until"] is None
    col = svc.get_snapshot().columns[0].to_dict()
    assert col["snoozed"] == []
    assert a.id in ([col["next_item"]["id"]] if col["next_item"] else []) + [i["id"] for i in col["queue"]]


def test_dashboard_has_snoozed_section_and_unsnooze_button(tmp_path):
    store, svc = _svc(tmp_path)
    html = TestClient(create_app(store=store, service=svc)).get("/").text
    assert "Snoozed (" in html and "/unsnooze" in html
