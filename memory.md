# memory.md — RelayGuard Project Action Log & Decision Audit

> **Purpose:** This document tracks every action, decision, investigation, and change made on the RelayGuard project. It serves as an audit trail for the engineering team and future maintainers.

---

## Project Overview

| Field | Value |
|---|---|
| **Project** | RelayGuard |
| **Type** | FastAPI replay-safe execution gateway for AI-agent tool calls |
| **Language** | Python 3.11+ |
| **Database** | PostgreSQL 16+ via Psycopg 3 & Docker Compose |
| **Framework** | FastAPI + Pydantic v2 |
| **Updated** | 2026-10-16 |
| **Status** | Production-Aware Demonstration Complete |

---

## Action Log

### 🟢 Session 1 — 2026-10-15 (Initial Scaffold Analysis & Bug Fixes)
- Audited pre-existing SQLite starter files and identified Windows file-lock PermissionErrors in `measure.py`.
- Fixed connection leaks, added initial test cases, created `security.md` and `memory.md`.

---

### 🟢 Session 2 — 2026-10-15 (PostgreSQL Transition, Docker Compose & Fault Atomicity)

#### Action 1: Environment & Infrastructure Audit
- Verified Docker Desktop and local PostgreSQL services.
- Docker Compose configured to expose port 5434:5432 to avoid host port collisions.

#### Action 2: PostgreSQL Infrastructure Provisioning
- Files created: `compose.yaml`, `.env.example`, `requirements.txt` (`psycopg[binary]>=3.2.0,<4.0`).

#### Action 3: Database & Storage Layer Migration
- `app/config.py` — `get_database_url()` with fail-fast validation.
- `app/storage.py` — Psycopg 3 schema initialization.
- `app/main.py` — Atomic `ON CONFLICT DO NOTHING` + row-level locking (`FOR UPDATE`).
- `app/baseline.py` — Intentionally defective baseline writing to `baseline_effects`.

#### Action 4: Comprehensive Test Suite & Fault Injection
- Built 8 PostgreSQL integration tests (baseline reproduction, exact replay, 409 conflict, 422 validation, 10-thread concurrency, trigger fault injection atomicity, health check, repeatability).

#### Action 5: 100-Request PostgreSQL Measurement
- Executed `scripts/measure.py`: 100 baseline effects vs 1 fixed effect (99 duplicate effects prevented).

#### Action 6: Engineering Artifacts & Review Documentation
- Created ADR-001, AI review evidence, test report, Loom script, handoff guide.

---

### 🟢 Session 3 — 2026-10-16 (Final Quest Readiness Audit & Hardening)

#### Action 7: AI Review Evidence Provenance & Technical Audit (Task 1)
- Audited `docs/AI_REVIEW_EVIDENCE.md` against `app/storage.py` schema.
- Identified that the candidate inserted into `effects` before `actions`, which immediately violates PostgreSQL's foreign key constraint (`ForeignKeyViolation`) on fresh keys.
- Clarified provenance: explicitly documented that the proposal is a reconstructed review archetype representing the check-then-act anti-pattern, rather than an unedited raw session export.
- Removed unsupported empirical percentages; clearly distinguished theoretical concurrency race windows from measured benchmarks.

#### Action 8: Database Error Normalization & Secret Redaction (Task 2)
- Added `mask_database_url()` in `app/storage.py` to redact credentials (`user:***@host:port/db`) in error messages and logs.
- Moved `connect()` inside `try ... except psycopg.Error:` boundary in `app/main.py` and `app/baseline.py`.
- Handled database connection failures cleanly by returning HTTP 503 (`Action ledger is temporarily unavailable.`) without leaking database credentials, URLs, or internal driver stack traces.
- Guaranteed deterministic connection cleanup in `finally:` blocks.
- Added 2 new automated regression tests (`test_database_unavailability_returns_503_and_masks_secrets` and `test_mask_database_url_helper_redacts_credentials`). Test suite now passes 10/10.

#### Action 9: Environment Configuration Realignment (Task 3)
- Realigned default `DATABASE_URL` in `.env.example` to match Docker Compose host port `5434`.
- Added clear documentation in `README.md` and `HANDOFF.md` for copying `.env.example` to `.env` (`Copy-Item` / `cp`) and distinguishing Docker port 5434 from native PostgreSQL port 5432.

#### Action 10: Relative Repository Links & Scoring Calculation Fix (Task 4)
- Replaced all absolute `file:///` URLs across all markdown files with clean relative repository links.
- Corrected Candidate B's weighted priority score in `intent.md` and `docs/LOOM_SCRIPT.md`: `(3 * 0.50) + (4 * 0.30) + (5 * 0.20) = 3.7 / 5.0` (corrected from 3.8).

#### Action 11: Verification Execution (Task 5)
- Ran `python -m pytest -v`: 10 passed, 0 failed.
- Ran `python -m scripts.measure`: 100 baseline vs 1 fixed effect (99 prevented).
- Ran `python -m scripts.demo_live`: 7 phases passed.
- Ran `git diff --check`: 0 whitespace issues, exit code 0.

---

## Decisions Made

| # | Decision | Rationale | Alternatives Rejected |
|---|---|---|---|
| 1 | Transition to PostgreSQL via Psycopg 3 | Production-standard relational database with enterprise row locking and concurrency | In-memory dict, SQLite (limited concurrency/types) |
| 2 | Atomic `INSERT ... ON CONFLICT DO NOTHING` + `FOR UPDATE` | Prevents check-then-act race conditions; serializes concurrent key claims safely | Naive `SELECT` then `INSERT` (catastrophic race condition) |
| 3 | Single Transaction Boundary | Guarantees synthetic effect and action record commit together or rollback together | Separate commits, check-after-commit |
| 4 | Trigger-Based Fault Injection | Tests real database engine transaction rollback under unhandled exceptions | Mocking the database driver (does not prove engine atomicity) |
| 5 | Docker Compose for Dev Environment | Zero-friction local startup with health check and isolated volumes | Requiring manual PostgreSQL installation |
| 6 | Redact Connection Credentials via `mask_database_url` | Prevents database passwords from leaking into logs, exception objects, or HTTP responses | Exposing raw connection strings in error traces |
| 7 | Intercept Connection Failure inside HTTP 503 Boundary | Guarantees documented HTTP 503 response when database is unreachable | Unhandled 500 Internal Server Error |

---

## Acceptance Criteria Tracker

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Baseline defect reproduced (10 identical requests) | ✅ PASSED | `test_baseline_reproduces_duplicate_effects` |
| 2 | Exact replay creates 1 effect (10 replays) | ✅ PASSED | `test_exact_replays_create_one_effect_and_return_cached_result` |
| 3 | 100-request measurement executed on PostgreSQL | ✅ PASSED | `scripts/measure.py` (99 prevented) |
| 4 | Key reuse with different payload returns 409 | ✅ PASSED | `test_reusing_key_with_different_payload_is_rejected` |
| 5 | Invalid content & extra fields return 422 | ✅ PASSED | `test_invalid_requests_are_rejected_and_create_no_effects` |
| 6 | Concurrent replay covered by automated test | ✅ PASSED | `test_concurrent_replays_create_one_effect` (10 threads) |
| 7 | Failure atomicity verified with DB fault injection | ✅ PASSED | `test_database_failure_atomicity_and_recovery` |
| 8 | Database unavailability error masking & secret redaction | ✅ PASSED | `test_database_unavailability_returns_503_and_masks_secrets` |
| 9 | Connection URL credential masking helper | ✅ PASSED | `test_mask_database_url_helper_redacts_credentials` |
| 10 | Automated checks pass on final commit | ✅ PASSED | `10 passed in 18.27s` |
| 11 | Focused diff with zero unrelated refactors | ✅ PASSED | Strictly 1 flow, verified files only |
| 12 | ADR evaluates 4 alternatives with trade-offs | ✅ PASSED | `docs/ADR-001-idempotency-storage.md` |
| 13 | AI code review candidate analyzed & rejected | ✅ PASSED | `docs/AI_REVIEW_EVIDENCE.md` |
| 14 | Engineering handoff guide complete | ✅ PASSED | `HANDOFF.md` |
| 15 | Loom video recorded ($\le$ 5 min) | 🔲 CANDIDATE ACTION | Script in `docs/LOOM_SCRIPT.md` |
| 16 | External repository linked | ✅ PASSED | https://github.com/AtifAli90/RelayGuard |
