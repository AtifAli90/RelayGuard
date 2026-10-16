"""INTENTIONALLY DEFECTIVE baseline for the local Quest demonstration.

Do not use this implementation in production. It creates an effect on every
request and ignores the idempotency key, reproducing a duplicate-action defect.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from app.storage import connect


class BaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    idempotency_key: str = Field(min_length=8, max_length=128)
    action_type: str = "publish_update"
    content: str = Field(min_length=1, max_length=1000)


def create_baseline_app(db_path: str | Path) -> FastAPI:
    app = FastAPI(title="RelayGuard baseline (intentionally defective)")
    app.state.db_path = Path(db_path)
    connection = connect(app.state.db_path)
    try:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS baseline_effects (
                effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL,
                action_type TEXT NOT NULL,
                content TEXT NOT NULL
            )"""
        )
        connection.commit()
    finally:
        connection.close()

    @app.post("/v1/actions")
    def execute_baseline(request: BaselineRequest) -> dict[str, object]:
        # DEFECT: every delivery creates a new effect, including replays.
        connection = connect(app.state.db_path)
        try:
            cursor = connection.execute(
                "INSERT INTO baseline_effects (idempotency_key, action_type, content) VALUES (?, ?, ?)",
                (request.idempotency_key, request.action_type, request.content),
            )
            connection.commit()
            return {
                "action_id": request.idempotency_key,
                "status": "completed",
                "effect_id": cursor.lastrowid,
                "replayed": False,
            }
        finally:
            connection.close()

    return app
