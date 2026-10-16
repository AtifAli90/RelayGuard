"""RelayGuard: replay-safe handling for a single synthetic agent-tool action."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
import psycopg

from app.storage import connect, initialize_database

logger = logging.getLogger("relayguard.api")


class ActionRequest(BaseModel):
    """Validated request for the one supported synthetic tool action."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    action_type: Literal["publish_update"]
    content: str = Field(min_length=1, max_length=1000)


def _stable_payload_hash(request: ActionRequest) -> str:
    """Compute a deterministic SHA-256 hash of the canonical request payload.

    Excludes the idempotency key itself to test whether the same key is being
    reused for identical vs conflicting payload contents.
    """
    canonical = json.dumps(
        {"action_type": request.action_type, "content": request.content},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_app(db_url: str | None = None) -> FastAPI:
    """Application factory allowing tests and CLI to specify an isolated database URL."""
    application = FastAPI(
        title="RelayGuard",
        description="A synthetic, replay-safe execution gateway for AI-agent tool calls using PostgreSQL.",
        version="0.2.0",
    )
    application.state.db_url = db_url

    # Deterministic schema setup on startup
    initialize_database(db_url)

    @application.get("/healthz", tags=["operations"])
    def healthz() -> dict[str, str]:
        """Verify database connectivity and service health."""
        try:
            with connect(application.state.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            return {"status": "ok", "database": "connected"}
        except Exception as exc:
            logger.error("Health check failed: %s", exc)
            raise HTTPException(status_code=503, detail="Database health check failed.") from exc

    @application.post("/v1/actions", tags=["synthetic action"])
    def execute_action(request: ActionRequest) -> dict[str, object]:
        """Execute or replay the synthetic publish_update action.

        Guarantees atomicity and idempotency in a single PostgreSQL transaction:
        1. Claims the idempotency key via INSERT ... ON CONFLICT DO NOTHING.
        2. If key exists: verifies payload hash; returns cached result (409 on conflict).
        3. If key is new: creates action ledger entry and synthetic effect row atomically.
        """
        payload_hash = _stable_payload_hash(request)
        connection = connect(application.state.db_url)

        try:
            with connection.transaction():
                # Step 1: Concurrency-safe atomic key claim.
                # Avoids check-then-act race conditions under concurrent requests.
                cur = connection.execute(
                    """
                    INSERT INTO actions (idempotency_key, payload_hash, result_json)
                    VALUES (%s, %s, '{}'::jsonb)
                    ON CONFLICT (idempotency_key) DO NOTHING;
                    """,
                    (request.idempotency_key, payload_hash),
                )

                if cur.rowcount == 0:
                    # Key was already claimed by a prior or concurrent transaction.
                    # Lock row and inspect stored payload hash.
                    existing = connection.execute(
                        """
                        SELECT payload_hash, result_json
                        FROM actions
                        WHERE idempotency_key = %s
                        FOR UPDATE;
                        """,
                        (request.idempotency_key,),
                    ).fetchone()

                    if existing is None:
                        raise HTTPException(
                            status_code=503,
                            detail="Action ledger lock conflict; please retry.",
                        )

                    if existing["payload_hash"] != payload_hash:
                        raise HTTPException(
                            status_code=409,
                            detail="Idempotency key was already used with a different payload.",
                        )

                    # Exact replay: return stored canonical outcome with replayed flag.
                    response = dict(existing["result_json"])
                    response["replayed"] = True
                    return response

                # Step 2: Key was successfully claimed. Insert synthetic effect.
                # Notice: this is a local synthetic effect stored in PostgreSQL.
                # It does not perform live network calls, payments, or emails.
                cursor = connection.execute(
                    """
                    INSERT INTO effects (idempotency_key, action_type, content)
                    VALUES (%s, %s, %s)
                    RETURNING effect_id;
                    """,
                    (request.idempotency_key, request.action_type, request.content),
                )
                effect_row = cursor.fetchone()
                if effect_row is None:
                    raise HTTPException(status_code=503, detail="Failed to create synthetic effect.")

                effect_id = effect_row["effect_id"]
                result: dict[str, object] = {
                    "action_id": request.idempotency_key,
                    "status": "completed",
                    "effect_id": effect_id,
                    "replayed": False,
                }

                # Step 3: Record finalized outcome in ledger within the same transaction.
                connection.execute(
                    """
                    UPDATE actions
                    SET result_json = %s::jsonb
                    WHERE idempotency_key = %s;
                    """,
                    (json.dumps(result, sort_keys=True), request.idempotency_key),
                )
                return result

        except HTTPException:
            raise
        except psycopg.Error as exc:
            logger.error("Database transaction failed for key '%s': %s", request.idempotency_key, exc)
            raise HTTPException(
                status_code=503,
                detail="Action ledger is temporarily unavailable.",
            ) from exc
        finally:
            connection.close()

    return application


# Default application instance using environment DATABASE_URL
app = create_app()
