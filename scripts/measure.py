"""Reproducible local before/after replay measurement for RelayGuard on PostgreSQL.

Reports measured local values comparing the intentionally defective baseline against
the fixed replay-safe implementation across 100 identical requests.
"""
from __future__ import annotations

import platform
import sys
import time
import uuid

from fastapi.testclient import TestClient

from app.config import get_database_url
from app.baseline import create_baseline_app
from app.main import create_app
from app.storage import connect, initialize_database

REPEATS = 100


def count_effects(db_url: str, table: str, idempotency_key: str) -> int:
    """Query row count in PostgreSQL for a specific idempotency key."""
    with connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE idempotency_key = %s;", (idempotency_key,))
            row = cur.fetchone()
            return int(row["c"]) if row else 0


def get_pg_version(db_url: str) -> str:
    """Retrieve PostgreSQL server version string."""
    try:
        with connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                row = cur.fetchone()
                return str(row["version"]) if row else "unknown"
    except Exception as exc:
        return f"Error retrieving version: {exc}"


def run_case(label: str, app, db_url: str, table: str, idempotency_key: str) -> dict[str, float | int | str]:
    request_body = {
        "idempotency_key": idempotency_key,
        "action_type": "publish_update",
        "content": "Synthetic customer update for the RelayGuard measurement.",
    }
    started = time.perf_counter()
    status_codes: list[int] = []
    with TestClient(app) as client:
        for _ in range(REPEATS):
            response = client.post("/v1/actions", json=request_body)
            status_codes.append(response.status_code)
    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "case": label,
        "idempotency_key": idempotency_key,
        "requests_attempted": REPEATS,
        "http_200_responses": sum(code == 200 for code in status_codes),
        "effects_created": count_effects(db_url, table, idempotency_key),
        "elapsed_ms_local": round(elapsed_ms, 3),
        "avg_ms_per_request": round(elapsed_ms / REPEATS, 3),
    }


def main() -> None:
    db_url = get_database_url()
    initialize_database(db_url)

    # Use unique run identifiers to prevent cross-run test data contamination
    run_id = uuid.uuid4().hex[:8]
    baseline_key = f"measure-base-{run_id}"
    fixed_key = f"measure-fixed-{run_id}"

    baseline_app = create_baseline_app(db_url)
    fixed_app = create_app(db_url)

    baseline = run_case(
        "baseline-intentionally-defective",
        baseline_app,
        db_url,
        "baseline_effects",
        baseline_key,
    )
    fixed = run_case(
        "fixed-idempotency-guard",
        fixed_app,
        db_url,
        "effects",
        fixed_key,
    )

    prevented = int(baseline["effects_created"]) - int(fixed["effects_created"])
    pg_version = get_pg_version(db_url)

    print("========================================================================")
    print("                RELAYGUARD POSTGRESQL LOCAL MEASUREMENT                 ")
    print("========================================================================")
    print(f"Environment context:")
    print(f"  OS:              {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  Python:          {sys.version.split()[0]}")
    print(f"  Database engine: PostgreSQL ({pg_version.split(',')[0]})")
    print(f"  Measurement ID:  {run_id}")
    print("------------------------------------------------------------------------")
    for record in (baseline, fixed):
        print(f"Case: {record['case']}")
        print(f"  Idempotency Key:     {record['idempotency_key']}")
        print(f"  Requests Attempted:  {record['requests_attempted']}")
        print(f"  HTTP 200 Responses:  {record['http_200_responses']}")
        print(f"  Effects Created:     {record['effects_created']}")
        print(f"  Elapsed Time (ms):   {record['elapsed_ms_local']}")
        print(f"  Avg ms/request:      {record['avg_ms_per_request']}")
        print("------------------------------------------------------------------------")
    print(f"Duplicate effects prevented in this run: {prevented}")
    print("========================================================================")
    print("NOTE: Elapsed wall-clock times are local, environment-specific figures,")
    print("NOT a production benchmark. The primary correctness metric is duplicate")
    print("effect prevention (1 effect per logical action).")
    print("========================================================================")


if __name__ == "__main__":
    main()
