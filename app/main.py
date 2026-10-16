"""RelayGuard: replay-safe handling for a single synthetic agent-tool action."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.storage import connect, initialize


class ActionRequest(BaseModel):
    """Validated request for the one supported synthetic tool action."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    action_type: Literal["publish_update"]
    content: str = Field(min_length=1, max_length=1000)


def _stable_payload_hash(request: ActionRequest) -> str:
    canonical = json.dumps(
        {"action_type": request.action_type, "content": request.content},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create an app, allowing tests to give each case an isolated database."""
    if db_path is None:
        configured = os.getenv("RELAYGUARD_DB_PATH")
        if configured:
            resolved_db_path = Path(configured)
        else:
            resolved_db_path = Path(tempfile.gettempdir()) / "relayguard-demo.sqlite3"
    else:
        resolved_db_path = Path(db_path)

    initialize(resolved_db_path)
    application = FastAPI(
        title="RelayGuard",
        description="A synthetic, replay-safe execution gateway for AI-agent tool calls.",
        version="0.1.0",
    )
    application.state.db_path = resolved_db_path

    @application.get("/healthz", tags=["operations"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/v1/actions", tags=["synthetic action"])
    def execute_action(request: ActionRequest) -> dict[str, object]:
        payload_hash = _stable_payload_hash(request)
        connection = connect(application.state.db_path)
        try:
            # Reserve the write lock before checking for an existing key. This
            # makes the check-and-create sequence serial within this SQLite DB.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT payload_hash, result_json FROM actions WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()

            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    connection.rollback()
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency key was already used with a different payload.",
                    )
                response = json.loads(existing["result_json"])
                response["replayed"] = True
                connection.commit()
                return response

            # This is a local synthetic effect. It deliberately has no network
            # call, payment, email, or other real-world side effect.
            connection.execute(
                "INSERT INTO actions (idempotency_key, payload_hash, result_json) VALUES (?, ?, ?)",
                (request.idempotency_key, payload_hash, "{}"),
            )
            cursor = connection.execute(
                "INSERT INTO effects (idempotency_key, action_type, content) VALUES (?, ?, ?)",
                (request.idempotency_key, request.action_type, request.content),
            )
            result = {
                "action_id": request.idempotency_key,
                "status": "completed",
                "effect_id": cursor.lastrowid,
                "replayed": False,
            }
            connection.execute(
                "UPDATE actions SET result_json = ? WHERE idempotency_key = ?",
                (json.dumps(result, sort_keys=True), request.idempotency_key),
            )
            connection.commit()
            return result
        except HTTPException:
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise HTTPException(status_code=503, detail="Action ledger is temporarily unavailable.") from exc
        finally:
            connection.close()

    return application


app = create_app()
