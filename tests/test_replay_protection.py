"""Automated verification suite for RelayGuard PostgreSQL replay protection.

Covers:
1. Baseline defect reproduction (10 requests -> 10 effects)
2. Exact sequential replay (10 requests -> 1 effect, 1 fresh, 9 replayed)
3. Payload conflict detection (same key, different content -> HTTP 409)
4. Comprehensive input validation & extra-field rejection (HTTP 422)
5. Concurrency safety (10 concurrent threads -> 1 effect, no race conditions)
6. Transactional failure atomicity (PostgreSQL trigger fault injection & recovery)
7. Operational health endpoint verification (GET /healthz)
8. End-to-end repeatability and database state assertion
9. Database unavailability returns HTTP 503 without leaking credentials
10. Connection URL credential redaction (mask_database_url helper)
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
import psycopg

from app.storage import connect
from app.main import create_app


def _get_count(db_url: str, table: str, key: str | None = None) -> int:
    """Helper to query row count in a given table, optionally filtered by idempotency_key."""
    with connect(db_url) as conn:
        with conn.cursor() as cur:
            if key is not None:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE idempotency_key = %s;", (key,))
            else:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table};")
            row = cur.fetchone()
            return int(row["c"]) if row else 0


def _sample_action(key_suffix: str = "0001", content: str = "Synthetic customer update.") -> dict[str, str]:
    return {
        "idempotency_key": f"update-demo-{key_suffix}",
        "action_type": "publish_update",
        "content": content,
    }


def test_baseline_reproduces_duplicate_effects(baseline_client, db_url):
    """Confirm the defective baseline creates 10 duplicate effects for 10 identical requests."""
    action = _sample_action("baseline-test")
    responses = [baseline_client.post("/v1/actions", json=action) for _ in range(10)]

    assert all(r.status_code == 200 for r in responses)
    # The intentional defect: every replay creates a brand new synthetic effect
    assert _get_count(db_url, "baseline_effects", action["idempotency_key"]) == 10
    effect_ids = [r.json()["effect_id"] for r in responses]
    assert len(set(effect_ids)) == 10  # 10 distinct effect IDs


def test_exact_replays_create_one_effect_and_return_cached_result(fixed_client, db_url):
    """Exact replays with the same key and payload create 1 effect and return cached outcome."""
    action = _sample_action("exact-replay")
    responses = [fixed_client.post("/v1/actions", json=action) for _ in range(10)]

    assert all(r.status_code == 200 for r in responses)
    # Database assertion: exactly 1 effect row created in PostgreSQL
    assert _get_count(db_url, "effects", action["idempotency_key"]) == 1
    assert _get_count(db_url, "actions", action["idempotency_key"]) == 1

    # Response assertions: 1 fresh execution, 9 replays
    fresh = [r.json() for r in responses if r.json()["replayed"] is False]
    replayed = [r.json() for r in responses if r.json()["replayed"] is True]
    assert len(fresh) == 1
    assert len(replayed) == 9

    # All responses share identical action_id and effect_id
    all_effect_ids = {r.json()["effect_id"] for r in responses}
    assert len(all_effect_ids) == 1


def test_reusing_key_with_different_payload_is_rejected(fixed_client, db_url):
    """Reusing an existing key with different content must return HTTP 409 Conflict."""
    action_orig = _sample_action("conflict-key", content="Original content payload.")
    action_conflict = _sample_action("conflict-key", content="Tampered / different content payload.")

    first = fixed_client.post("/v1/actions", json=action_orig)
    assert first.status_code == 200
    assert first.json()["replayed"] is False

    second = fixed_client.post("/v1/actions", json=action_conflict)
    assert second.status_code == 409
    assert "different payload" in second.json()["detail"].lower()

    # Verify no second effect was created in the database
    assert _get_count(db_url, "effects", "update-demo-conflict-key") == 1


def test_invalid_requests_are_rejected_and_create_no_effects(fixed_client, db_url):
    """Pydantic validation must reject malformed requests with 422 and persist zero effects."""
    base_key = f"invalid-key-{uuid.uuid4().hex[:6]}"

    # 1. Invalid action_type
    bad_action = {"idempotency_key": base_key, "action_type": "send_email", "content": "hello"}
    assert fixed_client.post("/v1/actions", json=bad_action).status_code == 422

    # 2. Key too short (<8 chars)
    short_key = {"idempotency_key": "short", "action_type": "publish_update", "content": "hello"}
    assert fixed_client.post("/v1/actions", json=short_key).status_code == 422

    # 3. Key with forbidden special characters
    illegal_key = {"idempotency_key": "bad key!@#$", "action_type": "publish_update", "content": "hello"}
    assert fixed_client.post("/v1/actions", json=illegal_key).status_code == 422

    # 4. Content empty or whitespace-only (stripped to empty)
    empty_content = {"idempotency_key": base_key, "action_type": "publish_update", "content": "   "}
    assert fixed_client.post("/v1/actions", json=empty_content).status_code == 422

    # 5. Extra fields rejected (extra="forbid")
    extra_field = {
        "idempotency_key": base_key,
        "action_type": "publish_update",
        "content": "valid",
        "admin": True,
    }
    assert fixed_client.post("/v1/actions", json=extra_field).status_code == 422

    # No effects or action records should have been written
    assert _get_count(db_url, "effects", base_key) == 0
    assert _get_count(db_url, "actions", base_key) == 0


def test_concurrent_replays_create_one_effect(db_url):
    """Simultaneous requests with the same key and payload must produce exactly one effect in PostgreSQL."""
    action = _sample_action("concurrent-pgrun")
    app = create_app(db_url)

    # Use separate TestClient connections to test genuine concurrent HTTP transactions
    def send_request(_i: int):
        with TestClient(app) as client:
            return client.post("/v1/actions", json=action)

    workers = 10
    with ThreadPoolExecutor(max_workers=workers) as executor:
        responses = list(executor.map(send_request, range(workers)))

    # Every concurrent request must succeed with 200 (no 500s or unhandled lock errors)
    assert all(r.status_code == 200 for r in responses)

    # Database assertion: exactly 1 effect row exists in PostgreSQL
    assert _get_count(db_url, "effects", action["idempotency_key"]) == 1
    assert _get_count(db_url, "actions", action["idempotency_key"]) == 1

    # Exactly 1 fresh response and 9 replay responses
    fresh = [r.json() for r in responses if r.json()["replayed"] is False]
    replayed = [r.json() for r in responses if r.json()["replayed"] is True]
    assert len(fresh) == 1
    assert len(replayed) == 9

    # All responses must share the exact same effect_id
    effect_ids = {r.json()["effect_id"] for r in responses}
    assert len(effect_ids) == 1


def test_database_failure_atomicity_and_recovery(db_url):
    """Inject a DB-level fault between action claim and effect insert; confirm atomic rollback and recovery.

    Verifies that when effect persistence fails, the entire transaction rolls back,
    leaving NEITHER the actions record nor the effects record committed.
    Then verifies that when the fault is removed, the same idempotency key succeeds cleanly.
    """
    key = "update-demo-fault-injection"
    action = {
        "idempotency_key": key,
        "action_type": "publish_update",
        "content": "Payload before fault injection.",
    }
    app = create_app(db_url)

    # 1. Install a PostgreSQL trigger function that deliberately raises an exception on effects insert
    with connect(db_url) as conn:
        with conn.transaction():
            conn.execute(
                """
                CREATE OR REPLACE FUNCTION fail_effect_insert()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'Simulated database failure during effect insertion';
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_fault_effect ON effects;
                CREATE TRIGGER trg_fault_effect
                BEFORE INSERT ON effects
                FOR EACH ROW EXECUTE FUNCTION fail_effect_insert();
                """
            )

    try:
        # 2. Attempt the request: must fail with HTTP 503 Service Unavailable
        with TestClient(app) as client:
            fault_response = client.post("/v1/actions", json=action)

        assert fault_response.status_code == 503
        assert "temporarily unavailable" in fault_response.json()["detail"].lower()

        # 3. ATOMICITY VERIFICATION:
        # Neither the action claim nor the effect row must be committed in PostgreSQL!
        assert _get_count(db_url, "actions", key) == 0
        assert _get_count(db_url, "effects", key) == 0

    finally:
        # 4. Remove the injected fault trigger
        with connect(db_url) as conn:
            with conn.transaction():
                conn.execute("DROP TRIGGER IF EXISTS trg_fault_effect ON effects;")
                conn.execute("DROP FUNCTION IF EXISTS fail_effect_insert();")

    # 5. RECOVERY VERIFICATION:
    # Resubmit with the exact same idempotency key.
    # Because the transaction rolled back cleanly, the key is not poisoned and succeeds!
    with TestClient(app) as client:
        recovery_response = client.post("/v1/actions", json=action)

    assert recovery_response.status_code == 200
    assert recovery_response.json()["status"] == "completed"
    assert recovery_response.json()["replayed"] is False

    # Database now reflects exactly 1 action and 1 effect
    assert _get_count(db_url, "actions", key) == 1
    assert _get_count(db_url, "effects", key) == 1


def test_healthz_endpoint(fixed_client):
    """Operational health check must confirm database connectivity."""
    response = fixed_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_repeatability_with_multiple_actions(fixed_client, db_url):
    """Verifies that multiple distinct action keys coexist without cross-key interference."""
    keys = [f"update-demo-rep-{i:04d}" for i in range(5)]
    for key in keys:
        res = fixed_client.post(
            "/v1/actions",
            json={"idempotency_key": key, "action_type": "publish_update", "content": f"Content for {key}"},
        )
        assert res.status_code == 200
        assert res.json()["replayed"] is False

    # Replay all 5
    for key in keys:
        res = fixed_client.post(
            "/v1/actions",
            json={"idempotency_key": key, "action_type": "publish_update", "content": f"Content for {key}"},
        )
        assert res.status_code == 200
        assert res.json()["replayed"] is True

    # 5 actions and 5 effects in total
    assert _get_count(db_url, "actions") == 5
    assert _get_count(db_url, "effects") == 5


def test_database_unavailability_returns_503_and_masks_secrets():
    """When the database is unreachable, requests must return HTTP 503 without leaking credentials."""
    unreachable_url = "postgresql://user_test:super_secret_pw_999@127.0.0.1:59998/testdb"
    unreachable_app = create_app(unreachable_url, init_schema=False)

    with TestClient(unreachable_app) as client:
        # 1. Action endpoint returns HTTP 503
        action = _sample_action("db-down-test")
        res = client.post("/v1/actions", json=action)
        assert res.status_code == 503
        assert res.json()["detail"] == "Action ledger is temporarily unavailable."
        assert "super_secret_pw_999" not in res.text
        assert "59998" not in res.text

        # 2. Healthz endpoint returns HTTP 503
        health_res = client.get("/healthz")
        assert health_res.status_code == 503
        assert health_res.json()["detail"] == "Database health check failed."
        assert "super_secret_pw_999" not in health_res.text


def test_mask_database_url_helper_redacts_credentials():
    """Verify mask_database_url redacts passwords across various connection URL formats."""
    from app.storage import mask_database_url, connect

    url_with_password = "postgresql://relayguard:my_sensitive_password@localhost:5434/relayguard"
    masked = mask_database_url(url_with_password)
    assert "my_sensitive_password" not in masked
    assert masked == "postgresql://relayguard:***@localhost:5434/relayguard"

    url_without_password = "postgresql://localhost:5434/relayguard"
    assert mask_database_url(url_without_password) == url_without_password

    # Verify connect() raises psycopg.OperationalError without exposing credentials
    with pytest.raises(psycopg.OperationalError) as exc_info:
        connect("postgresql://test_user:ultra_secret_123@127.0.0.1:59998/relayguard")
    assert "ultra_secret_123" not in str(exc_info.value)
    assert "***" in str(exc_info.value)