"""INTENTIONALLY DEFECTIVE baseline for the local Quest demonstration.

Do not use this implementation in production. It creates a synthetic effect on every
request and ignores the idempotency key, reproducing a duplicate-action defect.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
import psycopg

from app.storage import connect, initialize_database

logger = logging.getLogger("relayguard.baseline")


class BaselineRequest(BaseModel):
    """Permissive request model for the intentionally defective baseline."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    action_type: Literal["publish_update"] = "publish_update"
    content: str = Field(min_length=1, max_length=1000)


def create_baseline_app(db_url: str | None = None) -> FastAPI:
    """Application factory for the intentionally defective baseline."""
    app = FastAPI(
        title="RelayGuard baseline (intentionally defective)",
        description="Deliberately creates a synthetic effect on every request to reproduce the duplicate effect defect.",
        version="0.2.0-defective-baseline",
    )
    app.state.db_url = db_url

    # Ensure baseline_effects table exists
    initialize_database(db_url)

    @app.post("/v1/actions")
    def execute_baseline(request: BaselineRequest) -> dict[str, object]:
        """DEFECT: every delivery creates a new effect, ignoring previous executions."""
        connection = connect(app.state.db_url)
        try:
            with connection.transaction():
                cursor = connection.execute(
                    """
                    INSERT INTO baseline_effects (idempotency_key, action_type, content)
                    VALUES (%s, %s, %s)
                    RETURNING effect_id;
                    """,
                    (request.idempotency_key, request.action_type, request.content),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=503, detail="Baseline insertion failed.")
                return {
                    "action_id": request.idempotency_key,
                    "status": "completed",
                    "effect_id": row["effect_id"],
                    "replayed": False,
                }
        except psycopg.Error as exc:
            logger.error("Baseline database error: %s", exc)
            raise HTTPException(status_code=503, detail="Baseline database error.") from exc
        finally:
            connection.close()

    return app
