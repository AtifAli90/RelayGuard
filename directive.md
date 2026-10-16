# directive.md — RelayGuard Final Working Directive

> **Quest Status & Pre-Existing Work Disclosure:**
> This directive reflects the finalized, production-aware PostgreSQL implementation of RelayGuard. The pre-existing scaffold originated as an illustrative SQLite proof-of-concept. During the timed Quest window, the service was transitioned end-to-end to PostgreSQL using Docker Compose (`compose.yaml`), Psycopg 3, atomic key claims (`INSERT ... ON CONFLICT DO NOTHING`), database-level failure atomicity via trigger fault injection, and automated concurrent verification. Pre-existing starter notes are disclosed honestly; all PostgreSQL code, tests, ADRs, reviews, and measurements reported below were executed during this session.

---

## 1. Objective

Make one synthetic AI-agent tool flow (`publish_update`) dependable, auditable, and replay-safe by preventing repeated executions of the same logical action. Demonstrate the defective baseline, implement an atomic PostgreSQL idempotency guard, review AI-assisted proposals with rigorous engineering judgment, measure empirical before/after behavior, and provide a clean handoff to another engineer.

---

## 2. Technical Context

RelayGuard is a focused FastAPI execution gateway for a single synthetic action, `publish_update`. Callers submit an `idempotency_key`, `action_type`, and `content`.

- **Defective Baseline:** Creates a new synthetic effect row in PostgreSQL on every delivery, ignoring duplicate keys.
- **Fixed Implementation:** Persists the action record and synthetic effect atomically within a single PostgreSQL transaction (`with connection.transaction():`). If replayed with identical payload content, it returns the cached outcome with `replayed: true`. If replayed with different content, it returns HTTP 409 Conflict. If any internal database step fails, the entire transaction rolls back cleanly.

No live third-party network APIs, emails, payment gateways, or customer data are touched. This is a local synthetic demonstration.

---

## 3. Quality Yardstick

Every proposal and change is evaluated against these four non-negotiable signals:

1. **User Impact / Correctness:** Number of synthetic effects created per logical action; exact replay idempotency; conflicting payload detection; strict Pydantic input validation.
2. **Maintainability / Debuggability:** Clear transaction boundaries; typed request models; explicit HTTP status codes; comprehensive integration tests asserting database state; zero exception swallowing.
3. **Operating-Cost Exposure:** Count of synthetic effects and redundant database writes prevented per repeated request sequence.
4. **Concurrency Correctness:** Simultaneous identical requests under parallel threads must serialize safely and yield exactly one synthetic effect in PostgreSQL without race conditions.
5. **Honest Architectural Boundaries:** A local PostgreSQL transaction guarantees atomicity only for internal database state; it does not provide distributed exactly-once delivery across external third-party network APIs.

---

## 4. Scope and Boundaries

### In Scope
- Single endpoint: `POST /v1/actions`.
- Single synthetic action type: `publish_update`.
- Operational health probe: `GET /healthz`.
- Input validation: Pydantic v2 rejecting extra fields (`extra="forbid"`), regex on keys, length constraints.
- Stable canonical payload hash: deterministic SHA-256 (excludes key).
- Concurrency-safe atomic key claim in PostgreSQL via `INSERT ... ON CONFLICT DO NOTHING` and `FOR UPDATE` locking.
- Database trigger fault injection verifying transactional rollback atomicity.
- Reproducible 100-request before/after measurement script.
- Local execution via Docker Compose (`compose.yaml`) and native Python.

### Out of Scope (Explicit Non-Goals)
- No real third-party provider calls (no Stripe, Twilio, SendGrid, or live LLMs).
- No arbitrary distributed exactly-once claims across external networks.
- No general-purpose agent orchestration, UI dashboards, authentication, or Redis queues.

---

## 5. Required Behavior & Contract

| Scenario | HTTP Status | Response Contract | Database Effect Count |
|---|---|---|---|
| Valid fresh request | 200 OK | `status: "completed"`, `replayed: false`, `effect_id: N` | Exactly 1 effect created |
| Exact replay (same key & payload) | 200 OK | `status: "completed"`, `replayed: true`, `effect_id: N` | 0 new effects created |
| Payload conflict (same key, diff content) | 409 Conflict | `"detail": "Idempotency key was already used with a different payload."` | 0 new effects created |
| Invalid content or extra fields | 422 Unprocessable | Pydantic validation error detail | 0 effects created |
| Database transaction failure | 503 Unavailable | `"detail": "Action ledger is temporarily unavailable."` | 0 effects created (rollback) |
| Concurrent exact replays (10 threads) | 200 OK | 1 fresh (`replayed: false`), 9 replays (`replayed: true`) | Exactly 1 effect created |

---

## 6. AI-Agent Working Instructions & Rules

1. **Inspect before editing:** Read configuration, storage, main app, and existing tests before modifying code.
2. **Preserve scope:** Keep strictly to the single flow (`publish_update`) and local synthetic boundaries.
3. **Reject check-then-act anti-patterns:** Never accept application-level `SELECT` then `INSERT` logic that races under concurrency; mandate database-enforced atomicity.
4. **Zero exception swallowing:** Never use bare `except: pass`. Map internal database driver exceptions to clean, secure HTTP 503 errors without leaking SQL statements or credentials.
5. **Document honest limits:** Clearly state the distinction between local PostgreSQL atomicity and external outbox/reconciliation requirements.
6. **Report only verified data:** Never claim a test or measurement passed unless it was actually executed and the console output captured.

---

## 7. Acceptance Criteria Checklist

- [x] Baseline defect reproduced: 10 identical requests produce 10 baseline effects in PostgreSQL.
- [x] Fixed implementation verified: 10 exact replays produce 1 effect (1 fresh, 9 replayed).
- [x] 100-request repeatable measurement executed against PostgreSQL (99 duplicates prevented).
- [x] Key reuse with modified payload returns HTTP 409 Conflict.
- [x] Invalid content and unexpected fields return HTTP 422 Unprocessable Entity.
- [x] Concurrency test verifies 10 simultaneous threads yield exactly 1 effect in PostgreSQL.
- [x] Database-level fault injection verifies transactional rollback atomicity.
- [x] Automated test suite passes cleanly against PostgreSQL (`8 passed in 4.93s`).
- [x] Focused diff containing only justified changes and clean architecture.
- [x] ADR-001 compares 4 storage alternatives with trade-offs.
- [x] Real AI review candidate analyzed against the 3 quality dimensions.
- [x] Engineering handoff guide (`HANDOFF.md`) complete with next-engineer exercise.
- [ ] Loom video recorded by candidate ($\le$ 5 minutes; script in `docs/LOOM_SCRIPT.md`).
- [ ] All repository and external links tested in incognito window.

---

## 8. Verification Commands

From the repository root (Python 3.11+):

```bash
# 1. Start PostgreSQL container
docker compose up -d --wait db

# 2. Run automated test suite
python -m pytest -v

# 3. Run empirical 100-request before/after measurement
python -m scripts.measure

# 4. Start local development server
uvicorn app.main:app --reload
```

---

## 9. Empirical Verification Evidence (Captured Outputs)

### Automated Test Suite:
```text
python -m pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: D:\Projects\RelayGuard
plugins: anyio-4.13.0, langsmith-0.9.2
collecting ... collected 8 items

tests/test_replay_protection.py::test_baseline_reproduces_duplicate_effects PASSED [ 12%]
tests/test_replay_protection.py::test_exact_replays_create_one_effect_and_return_cached_result PASSED [ 25%]
tests/test_replay_protection.py::test_reusing_key_with_different_payload_is_rejected PASSED [ 37%]
tests/test_replay_protection.py::test_invalid_requests_are_rejected_and_create_no_effects PASSED [ 50%]
tests/test_replay_protection.py::test_concurrent_replays_create_one_effect PASSED [ 62%]
tests/test_replay_protection.py::test_database_failure_atomicity_and_recovery PASSED [ 75%]
tests/test_replay_protection.py::test_healthz_endpoint PASSED            [ 87%]
tests/test_replay_protection.py::test_repeatability_with_multiple_actions PASSED [100%]

======================== 8 passed, 1 warning in 4.93s =========================
```

### 100-Request PostgreSQL Measurement:
```text
python -m scripts.measure
========================================================================
                RELAYGUARD POSTGRESQL LOCAL MEASUREMENT
========================================================================
Environment context:
  OS:              Windows 11 (AMD64)
  Python:          3.14.3
  Database engine: PostgreSQL (PostgreSQL 18.3 on x86_64-windows)
  Measurement ID:  1b644a01
------------------------------------------------------------------------
Case: baseline-intentionally-defective
  Idempotency Key:     measure-base-1b644a01
  Requests Attempted:  100
  HTTP 200 Responses:  100
  Effects Created:     100
  Elapsed Time (ms):   5526.834
  Avg ms/request:      55.268
------------------------------------------------------------------------
Case: fixed-idempotency-guard
  Idempotency Key:     measure-fixed-1b644a01
  Requests Attempted:  100
  HTTP 200 Responses:  100
  Effects Created:     1
  Elapsed Time (ms):   6138.108
  Avg ms/request:      61.381
------------------------------------------------------------------------
Duplicate effects prevented in this run: 99
========================================================================
```

---

## 10. AI Code Review & Human Engineering Judgment

During this session, an AI proposal suggesting a naive check-then-act query pattern (`SELECT ... if not found INSERT ...`) was reviewed and **rejected**:

- **Candidate Defect:** `SELECT` followed by `INSERT` creates a fatal concurrency window where concurrent agent retries both observe "key not found" and execute duplicate effects. Furthermore, raw database exceptions were exposed directly to API callers (`detail=str(exc)`).
- **Human Technical Decision:** Replaced with PostgreSQL atomic key claim:
  `INSERT INTO actions ... ON CONFLICT (idempotency_key) DO NOTHING` paired with `FOR UPDATE` row locking. Exception handling strictly maps `psycopg.Error` to a clean HTTP 503 without leaking database internals.
- **Evidence Documentation:** Full analysis against User Impact, Maintenance, and Operating Cost is captured in [`docs/AI_REVIEW_EVIDENCE.md`](file:///d:/Projects/RelayGuard/docs/AI_REVIEW_EVIDENCE.md).

---

## 11. Architecture Decision Record (ADR-001)

A complete architectural record evaluating 4 storage strategies is published at [`docs/ADR-001-idempotency-storage.md`](file:///d:/Projects/RelayGuard/docs/ADR-001-idempotency-storage.md):
1. In-memory deduplication (Rejected: lost on restart/unshared across workers).
2. Naive check-then-act pattern (Rejected: race conditions under concurrency).
3. PostgreSQL uniqueness + single atomic transaction (Chosen for local synthetic gateway).
4. Transactional Outbox + Provider Idempotency (Deferred to production roadmap for external network calls).

---

## 12. Focused Diff and Change Record

- **Scope Maintained:** One endpoint, one synthetic action type, PostgreSQL storage and verification.
- **Files Modified / Added:**
  - `compose.yaml`: Docker Compose specification for PostgreSQL 16.
  - `.env.example`: Safe local defaults.
  - `requirements.txt`: Added `psycopg[binary]`.
  - `app/config.py`: Fail-fast environment URL parsing.
  - `app/storage.py`: Psycopg 3 schema initialization and connection management.
  - `app/main.py`: Atomic PostgreSQL replay-safe gateway.
  - `app/baseline.py`: PostgreSQL defective baseline.
  - `tests/conftest.py` & `tests/test_replay_protection.py`: 8 comprehensive PostgreSQL integration tests.
  - `scripts/measure.py`: 100-request benchmark tool.
  - Supporting documentation: `HANDOFF.md`, `problem.md`, `intent.md`, `memory.md`, `security.md`, `docs/ADR-001-idempotency-storage.md`, `docs/AI_REVIEW_EVIDENCE.md`, `docs/TEST_REPORT.md`, `docs/LOOM_SCRIPT.md`.

---

## 13. Results and Handoff Appendix

### Required Submission Links (Candidate Action Items)
- **Loom Video ($\le$ 5 minutes):** `[PENDING — Candidate to record using docs/LOOM_SCRIPT.md and insert URL]`
- **Repository URL:** https://github.com/AtifAli90/RelayGuard
- **Focused Diff / Commit Link:** https://github.com/AtifAli90/RelayGuard/commits/main
- **Test Run Evidence:** Captured in [`docs/TEST_REPORT.md`](file:///d:/Projects/RelayGuard/docs/TEST_REPORT.md).
- **Measurement Output:** Captured in Section 9 above.
- **AI Review Evidence:** Captured in [`docs/AI_REVIEW_EVIDENCE.md`](file:///d:/Projects/RelayGuard/docs/AI_REVIEW_EVIDENCE.md).

### Next-Engineer Exercise
The next engineer is invited to extend RelayGuard by adding support for a second action type (`archive_record`) while adhering to the payload hash contract. Full instructions and checklist are provided in [`HANDOFF.md`](file:///d:/Projects/RelayGuard/HANDOFF.md).

### Final Results Summary
- **Elapsed Engineering Effort:** ~45 minutes (timed Quest implementation).
- **Automated Test Result:** 8 passed, 1 warning in 4.93s.
- **Baseline Effects Created:** 100 effects for 100 requests.
- **Fixed Effects Created:** 1 effect for 100 requests (99 duplicates prevented).
- **Remaining Limitations:** Unauthenticated API (demo scope); local PostgreSQL transaction only (external providers require Transactional Outbox).
