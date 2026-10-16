# Problem Brief — RelayGuard

> **Status:** Supporting context document for the RelayGuard Quest. Accompanying pre-existing starter notes are documented honestly; all PostgreSQL architecture, Docker Compose setup, and empirical metrics below were measured and verified during this engineering session.

---

## 1. Problem Statement

Autonomous AI agents and LLM orchestration layers frequently retry tool calls when an HTTP response is lost, delayed, or interrupted by network jitter. If an execution gateway cannot deterministically recognize an exact replay of a previously completed logical action, it executes the action multiple times. In a customer-update flow (`publish_update`), this publishes duplicate notifications; in transactional domains, this failure mode duplicates ticket creation, billing charges, inventory holds, or external notifications, degrading user trust in automated systems.

---

## 2. Affected User and Operational Impact

- **End User:** Receives duplicate messages or records, causing confusion and degrading confidence in the automation.
- **Support & Operations:** Must manually audit, explain, or perform compensating operations to roll back duplicate effects.
- **Engineering Team:** Spends valuable triage time debugging whether unacknowledged requests actually completed upstream.
- **System Owner:** Incurs repeated downstream database writes, compute consumption, and third-party vendor charges.

*Note: These represent plausible operational risks of this failure mode; this synthetic exercise does not claim real users or customers were interviewed.*

---

## 3. Empirical Verification Evidence (PostgreSQL)

The automated test suite (`python -m pytest -v`) confirms **10 passed** scenarios on PostgreSQL (full log in [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md)). The reproducible measurement script (`python -m scripts.measure`, Measurement ID `d644137c`) evaluated 100 repeated deliveries per implementation against PostgreSQL:

| Measure | Intentionally Defective Baseline | Replay-Safe Implementation |
|---|---:|---:|
| Measurement ID | `measure-base-d644137c` | `measure-fixed-d644137c` |
| Database Engine | PostgreSQL 18.3 / PostgreSQL 16 (Docker) | PostgreSQL 18.3 / PostgreSQL 16 (Docker) |
| Requests Attempted | 100 | 100 |
| HTTP 200 Responses | 100 | 100 |
| Synthetic Effects Created | **100** | **1** |
| Local Elapsed Time | 4,057.922 ms | 4,183.196 ms |
| Average ms / request | 40.579 ms | 41.832 ms |
| **Duplicate Effects Prevented** | — | **99** |

### Interpretation:
In this PostgreSQL run, the replay-safe implementation prevented **99 duplicate synthetic effects**. The fixed version required ~1.25 ms of additional overhead per request due to payload canonicalization, transaction synchronization, and uniqueness index lookups. Elapsed wall-clock times are local, environment-specific figures, not a production benchmark. **No latency improvement is claimed.** The primary success metric is duplicate effect prevention (1 effect per logical action).

---

## 4. Scope Boundaries & Explicit Non-Goals

- **In Scope:**
  - One endpoint (`POST /v1/actions`) and one synthetic action type (`publish_update`).
  - Strict Pydantic v2 validation and deterministic SHA-256 payload canonicalization.
  - Concurrency-safe atomic key claim and synthetic effect creation in a single PostgreSQL transaction.
  - Database-side fault injection and recovery testing via PostgreSQL triggers.
  - Full local execution via Docker Compose and native Python on Windows/macOS/Linux.
- **Out of Scope (Explicit Non-Goals):**
  - No real third-party external providers (no Stripe, Twilio, SendGrid, or live LLMs).
  - No claims of arbitrary distributed exactly-once execution across disparate network services.
  - No authentication, multi-tenancy, rate limiting, or web dashboard UI.

---

## 5. What Is Not Claimed

- No claims are made that a local database transaction guarantees exactly-once delivery to external webhooks or APIs.
- Local execution times are environment-specific and do not represent production performance benchmarks.
- No user interviews or live production incidents are fabricated.
