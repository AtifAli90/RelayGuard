"""Reproducible local before/after replay check; reports measured local values."""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.baseline import create_baseline_app
from app.main import create_app

REQUEST = {
    "idempotency_key": "measure-demo-0001",
    "action_type": "publish_update",
    "content": "Synthetic customer update for the RelayGuard measurement.",
}
REPEATS = 100


def count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def run_case(label: str, app, db_path: Path, table: str) -> dict[str, float | int | str]:
    started = time.perf_counter()
    status_codes: list[int] = []
    with TestClient(app) as client:
        for _ in range(REPEATS):
            response = client.post("/v1/actions", json=REQUEST)
            status_codes.append(response.status_code)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "case": label,
        "requests": REPEATS,
        "http_200_responses": sum(code == 200 for code in status_codes),
        "effects_created": count_rows(db_path, table),
        "elapsed_ms_local": round(elapsed_ms, 3),
        "scope": "single local process; synthetic SQLite effect; not a production benchmark",
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="relayguard-measure-") as folder:
        root = Path(folder)
        baseline_db = root / "baseline.sqlite3"
        fixed_db = root / "fixed.sqlite3"
        baseline = run_case(
            "baseline-intentionally-defective",
            create_baseline_app(baseline_db), baseline_db, "baseline_effects",
        )
        fixed = run_case(
            "fixed-idempotency-guard",
            create_app(fixed_db), fixed_db, "effects",
        )
        print("REPLAYGUARD LOCAL MEASUREMENT")
        for record in (baseline, fixed):
            print("-" * 72)
            for key, value in record.items():
                print(f"{key}: {value}")
        print("-" * 72)
        print(f"duplicate_effects_prevented_in_this_run: {baseline['effects_created'] - fixed['effects_created']}")
        print("Note: elapsed times are machine- and environment-specific; do not generalize them.")


if __name__ == "__main__":
    main()
