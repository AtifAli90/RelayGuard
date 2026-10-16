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
- [x] Health probe (`GET /healthz`) verified connected and returns HTTP 200.
- [x] Unavailable database returns HTTP 503 without leaking credentials or connection strings.
- [x] Connection URL credential-masking helper verified by automated test.
- [x] Automated test suite passes cleanly against PostgreSQL — **10 passed** (full output in [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md)).
- [x] Focused diff containing only justified changes and clean architecture.
- [x] ADR-001 compares 4 storage alternatives with trade-offs.
- [x] Reconstructed AI review archetype analyzed against the 3 quality dimensions.
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

## 9. Empirical Verification Evidence

Full console output for every command is preserved in [docs/TEST_REPORT.md](docs/TEST_REPORT.md). A concise summary is reproduced here.

### Automated Test Suite (10 tests, all passing):

```text
python -m pytest -v
...
10 passed, 1 warning in 18.27s
```

Tests cover: baseline defect reproduction, exact replay deduplication, payload conflict (HTTP 409), input validation (HTTP 422), 10-thread concurrency safety, database fault-injection atomicity, health probe, multi-key repeatability, database-unavailability HTTP 503, and credential-masking verification.

### 100-Request PostgreSQL Measurement (Measurement ID `d644137c`):

> **Note:** Elapsed wall-clock times are local, environment-specific figures. They are not a production benchmark. The primary correctness metric is effect count.

| Metric | Defective Baseline | Fixed RelayGuard |
|---|---:|---:|
| Requests attempted | 100 | 100 |
| HTTP 200 responses | 100 | 100 |
| **Effects created in PostgreSQL** | **100** | **1** |
| Elapsed (ms, local) | 4,057.922 | 4,183.196 |
| Avg ms/request (local) | 40.579 | 41.832 |

**Duplicate effects prevented: 99.**
The fixed path required marginally more time (~1.25 ms/request) for atomic key-claim overhead. No latency improvement is claimed.

---

## 10. AI Code Review & Human Engineering Judgment

During this session, a reconstructed AI proposal archetype illustrating a naive check-then-act query pattern (`SELECT ... if not found INSERT ...`) was evaluated and **rejected**:

- **Candidate Defects:**
  1. *Immediate Foreign-Key Failure:* In RelayGuard's schema (`app/storage.py`), `effects.idempotency_key` carries a foreign key referencing `actions.idempotency_key`. The candidate inserts into `effects` before `actions`. On every fresh key, PostgreSQL raises `ForeignKeyViolation`. The exception handler catches this, rolls back the transaction, and returns HTTP 500 (`detail=str(exc)`). No rows are committed; every fresh action fails.
  2. *Transactional Rollback & Concurrency Failure:* Because both inserts share a transaction and `connection.rollback()` runs on exception, and because `effects.idempotency_key` has a `UNIQUE` constraint, the candidate does not leave multiple committed database effects. However, instead of safely returning a cached HTTP 200 response (`replayed: true`), concurrent replays crash with HTTP 500. Furthermore, if non-database external side effects (e.g. emails, webhooks) were executed prior to commit, they could not be rolled back.
  3. *Security & Resource Leakage:* Raw driver exception strings are returned directly to callers (`detail=str(exc)`), leaking database structure and credentials, and connections are not deterministically closed in a `finally` block.
- **Human Technical Decision:** Replaced with PostgreSQL atomic key claim:
  `INSERT INTO actions ... ON CONFLICT (idempotency_key) DO NOTHING` paired with `FOR UPDATE` row locking. Exception handling strictly maps `psycopg.Error` to a clean HTTP 503 without leaking database internals, and connection cleanup is guaranteed in a `finally` block.
- **Evidence Documentation & Provenance:** Full analysis across User Impact, Maintenance, and Operating Cost, explicit provenance disclosure, and instructions for genuine session transcripts are documented in [`docs/AI_REVIEW_EVIDENCE.md`](docs/AI_REVIEW_EVIDENCE.md).

---

## 11. Architecture Decision Record (ADR-001)

A complete architectural record evaluating 4 storage strategies is published at [`docs/ADR-001-idempotency-storage.md`](docs/ADR-001-idempotency-storage.md):
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
  - `tests/conftest.py` & `tests/test_replay_protection.py`: 10 comprehensive PostgreSQL integration and security tests.
  - `scripts/measure.py`: 100-request benchmark tool.
  - Supporting documentation: `HANDOFF.md`, `problem.md`, `intent.md`, `memory.md`, `security.md`, `docs/ADR-001-idempotency-storage.md`, `docs/AI_REVIEW_EVIDENCE.md`, `docs/TEST_REPORT.md`, `docs/LOOM_SCRIPT.md`.

---

## 13. Results and Handoff Appendix

### Required Submission Links (Candidate Action Items)
- **Loom Video ($\le$ 5 minutes):** `[PENDING — Candidate to record using docs/LOOM_SCRIPT.md and insert URL]`
- **Repository URL:** https://github.com/AtifAli90/RelayGuard
- **Focused Diff / Commit Link:** https://github.com/AtifAli90/RelayGuard/commits/main
- **Test Run Evidence:** Captured in [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md).
- **Measurement Output:** Captured in Section 9 above.
- **AI Review Evidence:** Captured in [`docs/AI_REVIEW_EVIDENCE.md`](docs/AI_REVIEW_EVIDENCE.md).

### Next-Engineer Exercise
The next engineer is invited to extend RelayGuard by adding support for a second action type (`archive_record`) while adhering to the payload hash contract. Full instructions and checklist are provided in [`HANDOFF.md`](HANDOFF.md).

### Final Results Summary
- **Elapsed Engineering Effort:** ~45 minutes (timed Quest implementation).
- **Automated Test Result:** 10 passed, 1 warning.
- **Baseline Effects Created:** 100 effects for 100 requests.
- **Fixed Effects Created:** 1 effect for 100 requests (99 duplicates prevented).
- **Remaining Limitations:** Unauthenticated API (demo scope); local PostgreSQL transaction only (external providers require Transactional Outbox).