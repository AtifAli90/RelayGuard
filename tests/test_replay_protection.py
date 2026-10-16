from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.baseline import create_baseline_app
from app.main import create_app


SAME_ACTION = {
    "idempotency_key": "update-demo-0001",
    "action_type": "publish_update",
    "content": "Synthetic customer update for the RelayGuard demo.",
}


def _fixed_effect_count(db_path) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]


def _baseline_effect_count(db_path) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM baseline_effects").fetchone()[0]


def test_baseline_reproduces_duplicate_effects(tmp_path):
    db_path = tmp_path / "baseline.sqlite3"
    app = create_baseline_app(db_path)
    with TestClient(app) as client:
        responses = [client.post("/v1/actions", json=SAME_ACTION) for _ in range(10)]
    assert all(response.status_code == 200 for response in responses)
    assert _baseline_effect_count(db_path) == 10


def test_replays_create_only_one_effect_and_return_cached_result(tmp_path):
    db_path = tmp_path / "fixed.sqlite3"
    app = create_app(db_path)
    with TestClient(app) as client:
        responses = [client.post("/v1/actions", json=SAME_ACTION) for _ in range(10)]
    assert all(response.status_code == 200 for response in responses)
    assert _fixed_effect_count(db_path) == 1
    assert sum(response.json()["replayed"] is False for response in responses) == 1
    assert sum(response.json()["replayed"] is True for response in responses) == 9
    effect_ids = {response.json()["effect_id"] for response in responses}
    assert len(effect_ids) == 1


def test_reusing_key_with_different_payload_is_rejected(fixed_client):
    first = fixed_client.post("/v1/actions", json=SAME_ACTION)
    changed = {**SAME_ACTION, "content": "A different action under the same key."}
    second = fixed_client.post("/v1/actions", json=changed)
    assert first.status_code == 200
    assert second.status_code == 409


def test_invalid_content_is_rejected(fixed_client):
    invalid = {**SAME_ACTION, "content": "   "}
    response = fixed_client.post("/v1/actions", json=invalid)
    assert response.status_code == 422


def test_concurrent_replays_create_one_effect(tmp_path):
    db_path = tmp_path / "concurrent.sqlite3"
    app = create_app(db_path)

    def send_once(_index: int):
        with TestClient(app) as client:
            return client.post("/v1/actions", json=SAME_ACTION)

    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(executor.map(send_once, range(10)))

    assert all(response.status_code == 200 for response in responses)
    assert _fixed_effect_count(db_path) == 1
    assert sum(response.json()["replayed"] is False for response in responses) == 1
    assert sum(response.json()["replayed"] is True for response in responses) == 9
