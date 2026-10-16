# memory.md — RelayGuard Project Action Log

> **Purpose:** This document tracks every action, decision, investigation, and change made on the RelayGuard project. It serves as an audit trail for the engineering team and future maintainers.

---

## Project Overview

| Field | Value |
|---|---|
| **Project** | RelayGuard |
| **Type** | FastAPI replay-safe execution gateway for AI-agent tool calls |
| **Language** | Python 3.11+ |
| **Framework** | FastAPI + Pydantic + SQLite |
| **Started** | 2026-10-15 |
| **Status** | Active Development |

---

## Action Log

### 🟢 Session 1 — 2026-10-15 (Initial Analysis & Completion)

#### Action 1: Full Project Analysis
- **Time:** 22:56 PKT
- **What:** Performed complete codebase analysis of all 13 files
- **Files Reviewed:**
  - `app/main.py` — Fixed idempotent endpoint implementation
  - `app/baseline.py` — Intentionally defective baseline (creates duplicate effects)
  - `app/storage.py` — SQLite connection + schema initialization
  - `app/__init__.py` — Package marker
  - `scripts/measure.py` — 100-request before/after measurement
  - `tests/test_replay_protection.py` — 5 test cases (replay, conflict, validation, concurrency)
  - `tests/conftest.py` — pytest fixture for isolated DB
  - `directive.md` — Full working directive with ADR, acceptance criteria, handoff
  - `intent.md` — Problem selection rationale with weighted scoring
  - `problem.md` — Problem brief and impact analysis
  - `README.md` — Setup and usage guide
  - `requirements.txt` — fastapi, uvicorn, pytest, httpx
  - `.gitignore` — Standard Python ignores
- **Finding:** Scaffold is functionally complete. Core idempotency logic works correctly.

#### Action 2: Test Suite Execution
- **Time:** 22:57 PKT
- **Command:** `python -m pytest -q`
- **Result:** ✅ **5 passed** in 0.62s
- **Tests Passing:**
  1. `test_baseline_reproduces_duplicate_effects` — Baseline creates 10 effects for 10 replays
  2. `test_replays_create_only_one_effect_and_return_cached_result` — Fixed creates 1 effect, 9 replayed
  3. `test_reusing_key_with_different_payload_is_rejected` — HTTP 409 on payload conflict
  4. `test_invalid_content_is_rejected` — HTTP 422 on whitespace-only content
  5. `test_concurrent_replays_create_one_effect` — 10 threads, 1 effect

#### Action 3: Measurement Script Execution
- **Time:** 22:57 PKT
- **Command:** `python -m scripts.measure`
- **Result:** ⚠️ Measurement completed but script crashed on cleanup
- **Measurement Output:**
  | Metric | Baseline | Fixed |
  |---|---:|---:|
  | Requests | 100 | 100 |
  | HTTP 200 | 100 | 100 |
  | Effects Created | 100 | 1 |
  | Elapsed (ms) | 802.368 | 252.488 |
- **Bug Found:** `PermissionError: [WinError 32]` — SQLite file handles not released before `TemporaryDirectory` cleanup on Windows

#### Action 4: Git Repository Initialization
- **Time:** 22:58 PKT
- **What:** Initialized git repo (was missing), created initial commit
- **Commit:** `d391290` — "Initial scaffold - RelayGuard starter"
- **Files Committed:** 13 files, 894 insertions

#### Action 5: Bug Fix — Windows PermissionError in measure.py
- **Time:** 22:59 PKT
- **File Changed:** `scripts/measure.py`
- **Problem:** `TemporaryDirectory` context manager fails to delete SQLite files on Windows because connections are still held
- **Fix Applied:**
  - Replaced `TemporaryDirectory` context manager with `tempfile.mkdtemp()` + explicit `shutil.rmtree(ignore_errors=True)`
  - Changed `count_rows()` to use explicit `conn.close()` in `finally` block
  - Added `gc.collect()` before cleanup to release lingering references
- **Verification:** ✅ Script now runs cleanly, exits with code 0 (stderr warning is from starlette deprecation, not our code)

#### Action 6: Re-run Measurement After Fix
- **Time:** 22:59 PKT
- **Result:** ✅ Clean execution
- **Updated Measurement:**
  | Metric | Baseline | Fixed |
  |---|---:|---:|
  | Requests | 100 | 100 |
  | HTTP 200 | 100 | 100 |
  | Effects Created | 100 | 1 |
  | Elapsed (ms) | 667.726 | 176.023 |
- **Interpretation:** 99 duplicate effects prevented. Fixed path was faster in this run (not a generalizable claim).

#### Action 7: Documentation Creation
- **Time:** 22:59 PKT
- **Files Created:**
  - `memory.md` — This action log
  - `security.md` — Security protocol documentation

#### Action 8: Completion Plan Creation
- **Time:** 22:59 PKT
- **What:** Created comprehensive completion plan artifact mapping all acceptance criteria to tasks

---

## Acceptance Criteria Tracker

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Baseline defect reproduced with 10 identical requests | ✅ Done | `test_baseline_reproduces_duplicate_effects` |
| 2 | Baseline: 10 effects; Fixed: 1 effect for 10 replays | ✅ Done | `test_replays_create_only_one_effect_and_return_cached_result` |
| 3 | 100-request measurement for baseline and fixed | ✅ Done | `scripts/measure.py` output |
| 4 | Same key/different payload → 409 | ✅ Done | `test_reusing_key_with_different_payload_is_rejected` |
| 5 | Invalid content → 422 | ✅ Done | `test_invalid_content_is_rejected` |
| 6 | Concurrent duplicates covered by automated test | ✅ Done | `test_concurrent_replays_create_one_effect` |
| 7 | All checks pass on final commit | ✅ Done | `5 passed in 0.62s` |
| 8 | Diff is focused and readable | ✅ Done | Single-file bug fix |
| 9 | AI contribution preserved | 🔲 Pending | Fill in `directive.md` section 10 |
| 10 | ADR with 3+ alternatives | ✅ Done | `directive.md` ADR-001 (4 options) |
| 11 | Reproduction steps for new engineer | ✅ Done | `directive.md` section 13 |
| 12 | Loom video ≤ 5 minutes | 🔲 Pending | Record after finalizing |
| 13 | All links accessible | 🔲 Pending | Push repo + verify links |

---

## Decisions Made

| # | Decision | Rationale | Alternatives Rejected |
|---|---|---|---|
| 1 | SQLite transaction + unique key for idempotency | Atomic local guarantee, simple, correct for demo scope | In-memory dict (lost on restart), check-then-act (race condition), transactional outbox (overscoped) |
| 2 | `BEGIN IMMEDIATE` for write lock | Serializes check-and-create to prevent concurrent duplicates | Default `BEGIN DEFERRED` allows concurrent reads then conflicts |
| 3 | SHA-256 payload hash | Stable, deterministic, collision-resistant for conflict detection | MD5 (weaker), full payload comparison (storage cost) |
| 4 | `tempfile.mkdtemp` over `TemporaryDirectory` | Avoids Windows file-lock cleanup crash | Keeping `TemporaryDirectory` with `ignore_cleanup_errors=True` |

---

## Known Issues

| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | Starlette deprecation warning (httpx → httpx2) | Low | Known — upstream dependency |
| 2 | No git remote configured | Medium | Push to GitHub/GitLab before submission |
| 3 | `directive.md` placeholder sections unfilled | High | Must fill before submission |
| 4 | No `.env.example` or environment documentation | Low | Nice-to-have |

---

## File Change History

| Timestamp | File | Change Type | Description |
|---|---|---|---|
| 2026-10-15 22:59 | `scripts/measure.py` | Bug Fix | Fixed Windows PermissionError on temp file cleanup |
| 2026-10-15 22:59 | `memory.md` | Created | Project action log |
| 2026-10-15 22:59 | `security.md` | Created | Security protocols documentation |
