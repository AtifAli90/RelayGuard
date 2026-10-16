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
| **Updated** | 2026-10-15 |
| **Status** | Production-Aware Demonstration Complete |

---

## Action Log

### 🟢 Session 1 — 2026-10-15 (Initial Scaffold Analysis & Bug Fixes)
- Audited pre-existing SQLite starter files and identified Windows file-lock PermissionErrors in `measure.py`.
- Fixed connection leaks, added initial test cases, created `security.md` and `memory.md`.

---

### 🟢 Session 2 — 2026-10-15 (PostgreSQL Transition, Docker Compose & Fault Atomicity)

#### Action 1: Environment & Infrastructure Audit
- **Time:** 23:15 PKT
- **What:** Verified Docker Desktop and local PostgreSQL services.
- **Findings:**
  - Docker Desktop available with Docker Compose v5.5.1.
  - PostgreSQL 18 running locally on port 5432.
  - Compose service configured to expose port 5434:5432 to avoid host port collisions.

#### Action 2: PostgreSQL Infrastructure Provisioning
- **Time:** 23:19 PKT
- **Files Created / Modified:**
  - `compose.yaml` — PostgreSQL 16 container with health check and named volume `relayguard_postgres_data`.
  - `.env.example` — Safe development-only defaults; documented ports.
  - `.gitignore` — Ignore `.env`, `.env.*`, `*.sqlite3*`, `*.log`, `*.mp4`, test caches.
  - `requirements.txt` — Added `psycopg[binary]>=3.2.0,<4.0`.

#### Action 3: Database & Storage Layer Migration
- **Time:** 23:20 PKT
- **Files Created / Modified:**
  - `app/config.py` — Added `get_database_url()` with fail-fast validation and local `.env` parser.
  - `app/storage.py` — Rewritten for PostgreSQL using Psycopg 3 (`dict_row`). Deterministic schema initialization creating `actions`, `effects`, and `baseline_effects`.
  - `app/main.py` — Concurrency-safe atomic transaction using `INSERT ... ON CONFLICT DO NOTHING` + row-level locking (`FOR UPDATE`) for replays. Structured error handling mapping `psycopg.Error` to HTTP 503.
  - `app/baseline.py` — Intentionally defective baseline writing to `baseline_effects` in PostgreSQL.

#### Action 4: Comprehensive Test Suite & Fault Injection
- **Time:** 23:22 PKT
- **File:** `tests/test_replay_protection.py`, `tests/conftest.py`
- **What:** Built 8 PostgreSQL integration tests:
  1. Baseline defect reproduction (10 requests -> 10 effects).
  2. Exact replay (10 requests -> 1 effect, 1 fresh, 9 replayed).
  3. Payload conflict detection (same key, different content -> HTTP 409).
  4. Validation & extra-field rejection (HTTP 422).
  5. Concurrency safety (10 threads in parallel via ThreadPoolExecutor -> 1 effect, 0 race errors).
  6. **Failure atomicity with DB trigger fault injection**: injected PostgreSQL trigger `fail_effect_insert()` raising an exception, verified total transaction rollback (`_get_count` == 0), dropped trigger, and verified retry succeeds cleanly.
  7. Operational health check (`GET /healthz` -> 200).
  8. Multi-action repeatability and test isolation.
- **Command:** `python -m pytest -v`
- **Result:** ✅ **8 passed, 1 warning in 4.93s**

#### Action 5: 100-Request PostgreSQL Measurement
- **Time:** 23:23 PKT
- **File:** `scripts/measure.py`
- **What:** Updated measurement script to test 100 repeated deliveries against PostgreSQL using unique run IDs.
- **Result:**
  | Metric | Defective Baseline | Replay-Safe Implementation |
  |---|---:|---:|
  | Database Engine | PostgreSQL 18.3 | PostgreSQL 18.3 |
  | Requests Attempted | 100 | 100 |
  | HTTP 200 Responses | 100 | 100 |
  | **Effects Created** | **100** | **1** |
  | Elapsed Wall-Clock | 5,526.834 ms | 6,138.108 ms |
  | **Duplicate Effects Prevented** | — | **99** |

#### Action 6: Engineering Artifacts & Review Documentation
- **Time:** 23:24 – 23:29 PKT
- **Files Created:**
  - `docs/ADR-001-idempotency-storage.md` — Complete ADR evaluating 4 storage options.
  - `docs/AI_REVIEW_EVIDENCE.md` — Real AI candidate check-then-act code review across the 3 quality dimensions.
  - `docs/TEST_REPORT.md` — Full test output and measurement evidence.
  - `docs/LOOM_SCRIPT.md` — Timed 5-minute video storyboard and shot list.
  - `HANDOFF.md` — Reproduction steps, next-engineer exercise, and production outbox guidance.
  - Updated `README.md`, `problem.md`, `intent.md`, `directive.md`, `security.md`.

---

## Decisions Made

| # | Decision | Rationale | Alternatives Rejected |
|---|---|---|---|
| 1 | Transition to PostgreSQL via Psycopg 3 | Production-standard relational database with enterprise row locking and concurrency | In-memory dict, SQLite (limited concurrency/types) |
| 2 | Atomic `INSERT ... ON CONFLICT DO NOTHING` + `FOR UPDATE` | Prevents check-then-act race conditions; serializes concurrent key claims safely | Naive `SELECT` then `INSERT` (catastrophic race condition) |
| 3 | Single Transaction Boundary | Guarantees synthetic effect and action record commit together or rollback together | Separate commits, check-after-commit |
| 4 | Trigger-Based Fault Injection | Tests real database engine transaction rollback under unhandled exceptions | Mocking the database driver (does not prove engine atomicity) |
| 5 | Docker Compose for Dev Environment | Zero-friction local startup with health check and isolated volumes | Requiring manual PostgreSQL installation |

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
| 8 | Automated checks pass on final commit | ✅ PASSED | `8 passed in 4.93s` |
| 9 | Focused diff with zero unrelated refactors | ✅ PASSED | Strictly 1 flow, verified files only |
| 10 | ADR evaluates 4 alternatives with trade-offs | ✅ PASSED | `docs/ADR-001-idempotency-storage.md` |
| 11 | AI code review candidate analyzed & rejected | ✅ PASSED | `docs/AI_REVIEW_EVIDENCE.md` |
| 12 | Engineering handoff guide complete | ✅ PASSED | `HANDOFF.md` |
| 13 | Loom video recorded ($\le$ 5 min) | 🔲 CANDIDATE ACTION | Script in `docs/LOOM_SCRIPT.md` |
| 14 | External repository links verified | 🔲 CANDIDATE ACTION | Push to GitHub & verify |
