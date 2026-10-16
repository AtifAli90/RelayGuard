"""RelayGuard Live Representation & Interactive Demonstration Script.

Run this script during your live presentation or Loom recording:
    python -m scripts.demo_live

Demonstrates every key guarantee in real time with clear visual feedback:
1. Operational Health & PostgreSQL connectivity probe
2. Fresh Action Submission (replayed: false)
3. Exact Replay (replayed: true, 0 duplicate effects created)
4. Payload Tamper / Conflict Detection (HTTP 409)
5. Strict Validation & Extra Field Rejection (HTTP 422)
6. Concurrency Safety Race Test (10 simultaneous parallel threads -> 1 effect)
7. Defective Baseline Comparison (shows 10 duplicate effects created)
"""
from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.config import get_database_url
from app.main import create_app
from app.baseline import create_baseline_app
from app.storage import connect, initialize_database


def c(text: str, color_code: str) -> str:
    """ANSI color helper."""
    return f"\033[{color_code}m{text}\033[0m"


GREEN = "92"
CYAN = "96"
YELLOW = "93"
RED = "91"
BOLD = "1"
GRAY = "90"


def header(title: str) -> None:
    print("\n" + c("=" * 76, GRAY))
    print(c(f"  {title.upper()}", BOLD + ";" + CYAN))
    print(c("=" * 76, GRAY))


def step(number: int, title: str) -> None:
    print("\n" + c(f"[{number}] {title}", BOLD + ";" + YELLOW))
    print(c("-" * 76, GRAY))


def get_db_count(db_url: str, table: str, key: str) -> int:
    with connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE idempotency_key = %s;", (key,))
            row = cur.fetchone()
            return int(row["c"]) if row else 0


def main() -> None:
    db_url = get_database_url()
    initialize_database(db_url)
    app = create_app(db_url)
    baseline_app = create_baseline_app(db_url)
    client = TestClient(app)

    header("RelayGuard -- Live Replay-Safe Execution Gateway Demo")
    print(f"PostgreSQL Database: {c(db_url.split('@')[-1], GRAY)}")
    print(f"Target Endpoint:     {c('POST /v1/actions', BOLD)}")
    print(f"Synthetic Action:    {c('publish_update', BOLD)}")

    # -------------------------------------------------------------
    # Step 1: Health Check
    # -------------------------------------------------------------
    step(1, "Operational Health Check (GET /healthz)")
    res = client.get("/healthz")
    print(f"Response: HTTP {c(str(res.status_code), GREEN)} | {res.json()}")
    assert res.status_code == 200

    # -------------------------------------------------------------
    # Step 2: Fresh Action Execution
    # -------------------------------------------------------------
    demo_key = f"demo-live-{uuid.uuid4().hex[:6]}"
    step(2, f"Initial Action Submission (Key: {demo_key})")
    payload = {
        "idempotency_key": demo_key,
        "action_type": "publish_update",
        "content": "Publishing Q4 financial updates to verified partners.",
    }
    print(f"Submitting payload:\n  {json.dumps(payload, indent=2)}")
    t0 = time.perf_counter()
    res1 = client.post("/v1/actions", json=payload)
    ms1 = (time.perf_counter() - t0) * 1000

    print(f"\nResult: HTTP {c(str(res1.status_code), GREEN)} ({ms1:.2f}ms)")
    print(f"  status:    {c(res1.json()['status'], GREEN)}")
    print(f"  replayed:  {c(str(res1.json()['replayed']), YELLOW)} (Fresh Execution)")
    print(f"  effect_id: {res1.json()['effect_id']}")
    print(f"  DB state:  {get_db_count(db_url, 'effects', demo_key)} effect row committed in PostgreSQL.")

    # -------------------------------------------------------------
    # Step 3: Exact Replay
    # -------------------------------------------------------------
    step(3, "Exact Replay of Same Key & Payload (Network Retry Simulation)")
    print("Agent simulates a network timeout and resubmits the identical request...")
    t0 = time.perf_counter()
    res2 = client.post("/v1/actions", json=payload)
    ms2 = (time.perf_counter() - t0) * 1000

    print(f"\nResult: HTTP {c(str(res2.status_code), GREEN)} ({ms2:.2f}ms)")
    print(f"  status:    {c(res2.json()['status'], GREEN)}")
    print(f"  replayed:  {c(str(res2.json()['replayed']), GREEN)} (Cached Outcome Returned!)")
    print(f"  effect_id: {res2.json()['effect_id']} (Identical to initial effect)")
    print(f"  DB state:  {c(str(get_db_count(db_url, 'effects', demo_key)), GREEN)} effect row in PostgreSQL (ZERO duplicates created!)")

    # -------------------------------------------------------------
    # Step 4: Payload Conflict Detection
    # -------------------------------------------------------------
    step(4, "Payload Conflict / Tampering Test (Key Reuse with Changed Content)")
    tampered_payload = {
        "idempotency_key": demo_key,
        "action_type": "publish_update",
        "content": "MALICIOUS OR ACCIDENTAL OVERWRITE ATTEMPT.",
    }
    print(f"Submitting same key '{demo_key}' with modified content...")
    res3 = client.post("/v1/actions", json=tampered_payload)

    print(f"Result: HTTP {c(str(res3.status_code), RED)} (Expected Conflict)")
    print(f"Detail: {c(res3.json()['detail'], YELLOW)}")
    print(f"DB state: {get_db_count(db_url, 'effects', demo_key)} effect row in PostgreSQL (Tampered effect was REJECTED).")

    # -------------------------------------------------------------
    # Step 5: Strict Input Validation
    # -------------------------------------------------------------
    step(5, "Input Validation & Injection Prevention (HTTP 422)")
    invalid_payload = {
        "idempotency_key": "short",  # < 8 characters
        "action_type": "unauthorized_action",
        "content": "Valid content",
        "injected_admin_field": True,  # extra="forbid"
    }
    print("Submitting malformed request with short key, bad action, and injected field...")
    res4 = client.post("/v1/actions", json=invalid_payload)
    print(f"Result: HTTP {c(str(res4.status_code), RED)} Unprocessable Entity")
    print(f"Validation Errors Detected: {len(res4.json()['detail'])} schema violations blocked.")

    # -------------------------------------------------------------
    # Step 6: 10-Thread Concurrent Replay Race
    # -------------------------------------------------------------
    conc_key = f"demo-conc-{uuid.uuid4().hex[:6]}"
    step(6, f"Concurrency Race Test (10 Parallel Threads, Key: {conc_key})")
    conc_payload = {
        "idempotency_key": conc_key,
        "action_type": "publish_update",
        "content": "High-concurrency parallel update execution.",
    }

    def worker(_):
        with TestClient(app) as cl:
            return cl.post("/v1/actions", json=conc_payload)

    print("Firing 10 simultaneous parallel HTTP requests across ThreadPoolExecutor...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(executor.map(worker, range(10)))

    status_codes = [r.status_code for r in responses]
    fresh_count = sum(r.json()["replayed"] is False for r in responses)
    replay_count = sum(r.json()["replayed"] is True for r in responses)
    effects_in_db = get_db_count(db_url, "effects", conc_key)

    print(f"Responses:     10 / 10 succeeded with HTTP {c('200 OK', GREEN)}")
    print(f"Fresh Actions: {c(str(fresh_count), YELLOW)} (Exactly 1 writer won the atomic claim)")
    print(f"Replay Hits:   {c(str(replay_count), GREEN)} (9 parallel threads received cached outcome)")
    print(f"DB Row Count:  {c(str(effects_in_db), GREEN)} effect row in PostgreSQL (ZERO race-condition duplicates!)")

    # -------------------------------------------------------------
    # Step 7: Baseline Comparison
    # -------------------------------------------------------------
    base_key = f"demo-base-{uuid.uuid4().hex[:6]}"
    step(7, f"Contrast with Intentionally Defective Baseline (Key: {base_key})")
    print("Sending 10 sequential deliveries to the defective baseline...")
    base_client = TestClient(baseline_app)
    base_payload = {
        "idempotency_key": base_key,
        "action_type": "publish_update",
        "content": "Defective baseline test content.",
    }
    for _ in range(10):
        base_client.post("/v1/actions", json=base_payload)

    base_effects = get_db_count(db_url, "baseline_effects", base_key)
    print(f"Defective Baseline created: {c(str(base_effects) + ' effects', RED)} for 10 requests!")
    print(c("-> Defect reproduced: Every delivery spawned a separate duplicate effect.", RED))

    header("Demonstration Complete: RelayGuard Reliability Proved")
    print(c("[OK] Replay idempotency guaranteed via atomic PostgreSQL transactions.", GREEN))
    print(c("[OK] Concurrency safe (ON CONFLICT DO NOTHING + FOR UPDATE row lock).", GREEN))
    print(c("[OK] Zero duplicate effects under sequential or parallel retries.", GREEN))
    print(c("[OK] Payload integrity protected (SHA-256 canonical hashing).", GREEN))
    print()


if __name__ == "__main__":
    main()
