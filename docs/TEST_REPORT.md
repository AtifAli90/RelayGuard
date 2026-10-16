# RelayGuard Test & Verification Report

> **Generated:** 2026-10-15
> **Environment:** Windows 11 (AMD64), Python 3.14.3, PostgreSQL 18.3 & PostgreSQL 16 (Docker Compose)
> **Test Framework:** pytest 9.0.3, TestClient (Starlette/HTTPX)

---

## 1. Automated Test Suite Results

Command executed:
```bash
python -m pytest -v
```

### Full Console Output:
```text
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

============================== warnings summary ===============================
C:\Users\HMAT Technologies\AppData\Roaming\Python\Python314\site-packages\fastapi\testclient.py:1
  C:\Users\HMAT Technologies\AppData\Roaming\Python\Python314\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 8 passed, 1 warning in 4.93s =========================
```

---

## 2. Test Coverage Matrix

| Test Function | Target Behavior | Database Assertion | Result |
|---|---|---|---|
| `test_baseline_reproduces_duplicate_effects` | Defective baseline creates duplicate effects | `SELECT COUNT(*) FROM baseline_effects` == 10 | **PASSED** |
| `test_exact_replays_create_one_effect_and_return_cached_result` | 10 exact replays return cached outcome | `SELECT COUNT(*) FROM effects` == 1 | **PASSED** |
| `test_reusing_key_with_different_payload_is_rejected` | Same key with different payload returns 409 | `SELECT COUNT(*) FROM effects` == 1 | **PASSED** |
| `test_invalid_requests_are_rejected_and_create_no_effects` | Input validation (action, key regex, content, extra fields) -> 422 | `SELECT COUNT(*) FROM effects` == 0 | **PASSED** |
| `test_concurrent_replays_create_one_effect` | 10 parallel threads executing identical requests | `SELECT COUNT(*) FROM effects` == 1 (0 race errors) | **PASSED** |
| `test_database_failure_atomicity_and_recovery` | PostgreSQL trigger fault injection & atomic rollback | `SELECT COUNT(*) FROM actions/effects` == 0 during fault | **PASSED** |
| `test_healthz_endpoint` | Operational health check | Connectivity probe (`SELECT 1`) -> 200 | **PASSED** |
| `test_repeatability_with_multiple_actions` | Clean multi-key isolation and repeat execution | Exactly 5 actions and 5 effects | **PASSED** |

---

## 3. Before/After 100-Request Measurement Results

Command executed:
```bash
python -m scripts.measure
```

### Measured Output:
```text
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
NOTE: Elapsed wall-clock times are local, environment-specific figures,
NOT a production benchmark. The primary correctness metric is duplicate
effect prevention (1 effect per logical action).
========================================================================
```

### Analysis of Empirical Results:
1. **Correctness Win:** In the baseline, 100 requests generated 100 synthetic effects in PostgreSQL. In the fixed version, 100 requests generated **1 synthetic effect** (99 duplicates prevented).
2. **Timing Note:** The fixed version took 6138 ms (61.38 ms/req) vs 5526 ms (55.26 ms/req) for the baseline. The additional transaction synchronization, canonical payload hash computation, and index checks add approximately 6 ms of overhead per request. No performance or latency gain is claimed; the demonstrated benefit is 100% correctness and atomic deduplication.
