# AI Code-Review Evidence & Human Engineering Judgment

> **Status:** Captured Engineering Review & Decision Artifact
> **Evaluator:** Lead Software Engineer & AI Code Reviewer
> **Model Context:** AI-Assisted Implementation Review (Gemini 3.8 Flash / Claude Thinking)
> **Provenance Note:** The candidate code evaluated below is a **reconstructed review archetype** capturing the common check-then-act anti-pattern produced during AI code-generation sessions. It is documented here for rigorous technical analysis and architectural evaluation, rather than presented as an unedited raw session export.

---

## 1. Context and Objective

During the migration to PostgreSQL, an AI coding assistant was asked to implement concurrency-safe replay protection for the `POST /v1/actions` endpoint (`publish_update` synthetic action).

Below is the proposal evaluated during review, the human engineering analysis across the three quality dimensions (User Impact, Maintainability, Operating Cost), the technical reasons for rejecting it, and the implemented atomic correction.

---

## 2. The AI Candidate Proposal Evaluated

### Prompt Archetype:
> *"Implement the PostgreSQL storage and transaction handling for `execute_action` to prevent duplicate effects on replay."*

### Candidate Code Excerpt Reviewed:

```python
# --- RECONSTRUCTED AI REVIEW CANDIDATE (Vulnerable Check-Then-Act Pattern) ---
def execute_action(request: ActionRequest) -> dict[str, object]:
    payload_hash = _stable_payload_hash(request)
    connection = connect()
    try:
        # Step 1: Check if key exists
        existing = connection.execute(
            "SELECT payload_hash, result_json FROM actions WHERE idempotency_key = %s",
            (request.idempotency_key,),
        ).fetchone()

        if existing is not None:
            if existing["payload_hash"] != payload_hash:
                raise HTTPException(status_code=409, detail="Payload mismatch.")
            res = existing["result_json"]
            res["replayed"] = True
            return res

        # Step 2: Key not found, execute effect and save
        cursor = connection.execute(
            "INSERT INTO effects (idempotency_key, action_type, content) VALUES (%s, %s, %s) RETURNING effect_id",
            (request.idempotency_key, request.action_type, request.content),
        )
        effect_id = cursor.fetchone()["effect_id"]

        result = {
            "action_id": request.idempotency_key,
            "status": "completed",
            "effect_id": effect_id,
            "replayed": False,
        }
        connection.execute(
            "INSERT INTO actions (idempotency_key, payload_hash, result_json) VALUES (%s, %s, %s)",
            (request.idempotency_key, payload_hash, json.dumps(result)),
        )
        connection.commit()
        return result
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
```

---

## 3. Engineering Evaluation Against the Quality Rubric

### Dimension 1: User Impact (Correctness, Safety & Schema Integrity)
- **Defect A: Immediate Foreign-Key Schema Violation.**
  In RelayGuard's PostgreSQL schema (`app/storage.py`), the `effects` table defines a strict foreign key:
  ```sql
  idempotency_key TEXT NOT NULL UNIQUE REFERENCES actions(idempotency_key)
  ```
  The candidate attempts to insert into `effects` at Step 2 *before* any corresponding record exists in `actions`. In PostgreSQL, this immediately triggers a `ForeignKeyViolation` (`psycopg.errors.ForeignKeyViolation: Key (idempotency_key)=(...) is not present in table "actions"`).
  **Impact:** Fresh actions would fail immediately with HTTP 500 on their first attempt, breaking the service completely.
- **Defect B: Theoretical Check-Then-Act Concurrency Race.**
  Even if insertion order were inverted or foreign keys omitted, the naive check-then-act pattern (`SELECT` followed by `INSERT`) contains an unprotected race window. If two concurrent agent workers submit requests with the same idempotency key simultaneously:
  1. Both transactions execute Step 1 (`SELECT`) concurrently.
  2. Both see no existing row.
  3. Both proceed to execute Step 2, creating duplicate side effects.
  4. When the second transaction reaches `actions`, it triggers a `UniqueViolation` and returns HTTP 500, leaving the caller believing the action failed when a side effect was already committed.
- **Verdict:** **UNACCEPTABLE.** Causes immediate schema violations on fresh keys and race-condition data corruption under concurrency.

### Dimension 2: Maintenance Effort & Debuggability
- **Flaws:**
  1. **Broad Exception Swallowing & Secret Leakage:** `except Exception as exc:` catches all errors and reflects `str(exc)` directly into the HTTP 500 response. This risks exposing database credentials, connection parameters, table names, and internal driver stack traces to callers.
  2. **Inverted Dependency Order:** Persisting side effects before the controlling action record violates relational integrity and makes transaction rollback tracing error-prone.
  3. **Lack of Deterministic Connection Cleanup:** Relies on manual commit/rollback without guaranteed resource closure (`finally: connection.close()`), leading to connection leaks under load.
- **Verdict:** **HIGH REWORK COST.** Diagnosing intermittent concurrency failures and database leaks in production would impose severe engineering overhead.

### Dimension 3: Operating-Cost Exposure
- **Downstream Waste & Risk:**
  - Duplicate effects generate unnecessary writes, storage bloat, and database lock contention.
  - *Empirical Note:* We distinguish theoretical concurrency vulnerability from measured benchmarks. In an unconstrained baseline without deduplication, duplicate rate is 100% (100 effects for 100 replays). Under this candidate's check-then-act logic, the duplicate leakage rate is non-deterministic and depends on thread interleaving, network latency, and connection pool sizing.
- **Verdict:** **UNCONTROLLED EXPENSE.** Any window permitting duplicate side effects risks compounding costs in downstream systems.

---

## 4. Human Engineering Decision & Implemented Correction

### Decision: **REJECT Candidate; Implement Atomic `ON CONFLICT` Key Claim**

The human reviewer rejected the candidate and required the following production-grade design:

1. **Single Atomic PostgreSQL Transaction:**
   Enclose all operations within `with connection.transaction():` so that failure at any point guarantees an immediate, clean rollback leaving zero orphan rows.
2. **Atomic Insert / Claim Before Side Effects:**
   Claim the idempotency key first using PostgreSQL's native atomic conflict resolution:
   ```sql
   INSERT INTO actions (idempotency_key, payload_hash, result_json)
   VALUES (%s, %s, '{}'::jsonb)
   ON CONFLICT (idempotency_key) DO NOTHING;
   ```
   If `cur.rowcount == 0`, PostgreSQL's unique index immediately identifies that the key is already claimed, avoiding any check-then-act race window.
3. **Pessimistic Row Lock on Replay:**
   If claimed, the transaction executes:
   ```sql
   SELECT payload_hash, result_json FROM actions WHERE idempotency_key = %s FOR UPDATE;
   ```
   This serializes concurrent replay readers behind any in-flight transaction, ensuring cached results are only read after the initial action successfully commits.
4. **Structured Error Masking & Secret Redaction:**
   Wrap database calls in specific `except psycopg.Error:` handlers that log sanitized messages without credentials and return a documented, generic HTTP 503 (`Action ledger is temporarily unavailable.`), protecting database topology and credentials.
5. **Guaranteed Connection Closure:**
   Connections are closed deterministically in a `finally:` block.

---

## 5. Verification of the Corrected Implementation

The corrected implementation was verified using real PostgreSQL execution:
- **Concurrency Test (`test_concurrent_replays_create_one_effect`):** 10 worker threads submitted concurrent requests with the identical key:
  - **Effects Created:** Exactly **1** effect in PostgreSQL.
  - **HTTP Status:** All 10 requests returned HTTP 200 (1 fresh execution, 9 cached replays). Zero collisions or 500 errors.
- **Fault Atomicity Test (`test_database_failure_atomicity_and_recovery`):** Injected database trigger aborting effect creation rolled back the entire transaction, leaving 0 action and 0 effect rows, allowing seamless retry recovery.