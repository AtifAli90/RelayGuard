# RelayGuard — Engineering Handoff & Maintenance Guide

> **Audience:** Incoming Reliability Engineers, Software Engineers, and Code Reviewers
> **Status:** Production-Aware Demonstration Handoff

---

## 1. Quick Reproduction Steps

From a clean clone on Python 3.11+:

### Windows PowerShell:
```powershell
# 1. Create local .env configuration from example template
Copy-Item .env.example .env

# 2. Start PostgreSQL via Docker Compose
docker compose up -d --wait db

# 3. Setup virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# 4. Run automated tests (10 passing scenarios)
python -m pytest -v

# 5. Run reproducible 100-request before/after measurement
python -m scripts.measure

# 6. Run local API server
uvicorn app.main:app --reload
```

### macOS / Linux:
```bash
# 1. Create local .env configuration from example template
cp .env.example .env

# 2. Start PostgreSQL via Docker Compose
docker compose up -d --wait db

# 3. Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 4. Run automated tests (10 passing scenarios)
python -m pytest -v

# 5. Run reproducible 100-request before/after measurement
python -m scripts.measure

# 6. Run local API server
uvicorn app.main:app --reload
```

> [!NOTE]
> **Database Port Configuration:** Docker Compose binds PostgreSQL to host port `5434` (`postgresql://relayguard:relayguard_dev_password@localhost:5434/relayguard`) to prevent conflicts with native PostgreSQL services running on port 5432. If connecting directly to a native PostgreSQL installation on port 5432, adjust `DATABASE_URL` in `.env` accordingly.

---

## 2. Interactive Verification via Swagger UI

1. Open `http://127.0.0.1:8000/docs` in your browser.
2. Submit `POST /v1/actions` with the sample payload:
   ```json
   {
     "idempotency_key": "handoff-test-0001",
     "action_type": "publish_update",
     "content": "Initial synthetic action for handoff test."
   }
   ```
   - **Response:** HTTP 200, `"replayed": false`, `"effect_id": 1`.
3. Submit the **exact same request** a second time:
   - **Response:** HTTP 200, `"replayed": true`, `"effect_id": 1` (cached outcome returned, no new effect).
4. Change `"content"` to `"Modified content under same key."` and submit again:
   - **Response:** HTTP 409 Conflict (`"Idempotency key was already used with a different payload."`).
5. Change `"idempotency_key"` to `"short"` (< 8 characters):
   - **Response:** HTTP 422 Unprocessable Entity (strict Pydantic validation).

---

## 3. The Next Engineer Exercise: Adding a Second Action Type

To verify that you can extend RelayGuard safely without weakening replay guarantees, complete this exercise:

### Goal:
Add support for a second synthetic action type: `"archive_record"`.

### Step-by-Step Instructions:

1. **Inspect the Payload Hash Contract in [`app/main.py`](app/main.py):**
   ```python
   canonical = json.dumps(
       {"action_type": request.action_type, "content": request.content},
       sort_keys=True,
       separators=(",", ":"),
       ensure_ascii=False,
   )
   ```
   *Question to answer:* Is `action_type` included in the hash?
   *Answer:* Yes. Changing `action_type` for an existing key must trigger an HTTP 409 Conflict.
2. **Update Request Validation:**
   In `ActionRequest`, expand the allowed literal:
   ```python
   action_type: Literal["publish_update", "archive_record"]
   ```
3. **Add Automated Test in [`tests/test_replay_protection.py`](tests/test_replay_protection.py):**
   ```python
   def test_archive_record_action_replay(fixed_client, db_url):
       action = {
           "idempotency_key": "archive-key-0001",
           "action_type": "archive_record",
           "content": "Archive record synthetic payload.",
       }
       res1 = fixed_client.post("/v1/actions", json=action)
       res2 = fixed_client.post("/v1/actions", json=action)
       assert res1.status_code == 200 and res1.json()["replayed"] is False
       assert res2.status_code == 200 and res2.json()["replayed"] is True
   ```
4. **Run `python -m pytest -v`** and verify all tests pass.

---

## 4. Honest Production Boundaries

> [!IMPORTANT]
> The atomicity demonstrated here is valid because **both the idempotency ledger and synthetic effect live in the same PostgreSQL database**.

If you migrate RelayGuard to invoke real third-party external services (such as Stripe payments, Twilio SMS, or SendGrid emails), **a database transaction cannot roll back an external HTTP request**.

To take this service to enterprise production, you MUST implement:

1. **Transactional Outbox Pattern:**
   - Instead of making external HTTP calls directly in the request handler, write an `outbox` event into PostgreSQL within the same transaction as the idempotency record.
   - An asynchronous background daemon (or worker pool) reads uncommitted outbox rows and delivers them with exponential backoff.
2. **Provider-Side Idempotency Keys:**
   - Transmit a deterministic idempotency key (e.g. `Idempotency-Key: <key>`) in headers to external providers that support it.
3. **Consumer-Side Deduplication & Reconciliation:**
   - Downstream webhook listeners and receivers must track processed event IDs.
   - A reconciliation job runs periodically to audit discrepancies between internal intent and external provider state.
4. **Key Expiration & TTL Pruning:**
   - Implement partition pruning or daily background cleanup for idempotency records older than 30–90 days to prevent unbounded database growth.

---

## 5. Reviewer Quality Checklist

When reviewing pull requests in RelayGuard, check each item:

- [ ] Does the change preserve the single atomic transaction boundary (`with connection.transaction():`)?
- [ ] Is all SQL strictly parameterized (no string interpolation or f-strings)?
- [ ] Does the change avoid vulnerable check-then-act (`SELECT` then `INSERT`) patterns?
- [ ] Are Pydantic models configured with `extra="forbid"` and strict bounds?
- [ ] Are database errors securely mapped to HTTP 503 without leaking credentials or stack traces?
- [ ] Are connections closed deterministically in `finally` blocks?
- [ ] Do automated tests assert database state (`_get_count`) in addition to HTTP status codes?
- [ ] Has `measure.py` been executed to verify no duplicate effects are introduced?