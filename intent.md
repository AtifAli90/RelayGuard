# intent.md — Why RelayGuard, and Why This Problem?

> **Quest Status & Pre-Existing Work Disclosure:**
> The original project scaffold existed prior to the timed Quest as an illustrative single-file SQLite prototype. During the timed engineering assessment, the architecture was elevated to a production-aware demonstration using **PostgreSQL**, **Docker Compose (`compose.yaml`)**, **Psycopg 3**, atomic concurrency handling (`INSERT ... ON CONFLICT DO NOTHING`), database-level failure atomicity with trigger fault injection, and empirical before/after measurements. Pre-existing scaffold work is disclosed; all PostgreSQL code, tests, ADRs, reviews, and measurements reported below were executed during this session.

---

## 1. Decision Summary

I selected one high-impact reliability vulnerability: **duplicate synthetic tool side effects when an AI-agent tool invocation is replayed following an ambiguous, timed-out, or lost response**.

RelayGuard is a focused execution gateway for a synthetic agent tool action, `publish_update`. The engineering mission is to make replayed tool calls safe: execute the logical action once, record its outcome atomically, return that stored result on exact replay (`replayed: true`), and reject key reuse with modified payload parameters (HTTP 409 Conflict).

This problem ranked first because duplicate action execution directly degrades end-user trust, generates compounding operational cleanup costs, and allows for an empirical, verifiable before-and-after demonstration under real database concurrency.

---

## 2. Three Candidate Problems Evaluated

Scores represent initial engineering judgments and reliability risk evaluations, not fabricated customer interviews. Each dimension is scored from 1 (low risk/urgency) to 5 (critical risk/urgency). The weighted priority formula is:

$$\text{Priority Score} = (\text{User Impact} \times 0.50) + (\text{Maintenance / Rework} \times 0.30) + (\text{Operating-Cost Exposure} \times 0.20)$$

| Candidate Reliability Problem | User Impact (50%) | Maintenance / Rework (30%) | Operating-Cost Exposure (20%) | Weighted Priority | Decision |
|---|---:|---:|---:|---:|---|
| **A. Duplicate side effects when a tool call is replayed** | **5** | **4** | **4** | **4.5 / 5.0** | **CHOSEN** |
| B. N+1 query pattern in an agent entity list endpoint | 3 | 4 | 5 | 3.8 / 5.0 | Defer |
| C. Missing validation on structured agent tool output | 4 | 3 | 2 | 3.3 / 5.0 | Defer |

### Why Problem A Was Chosen:
1. **User Impact (Weight: 50%):** Replaying an action that is not idempotent creates duplicate external consequences—duplicate customer updates, repeated billing charges, redundant notification blasts, or duplicate support tickets. This is the single fastest way an autonomous agent destroys operator trust.
2. **Maintenance / Rework (Weight: 30%):** Recovering from duplicate actions requires tedious manual database surgery, reconciling external vendor states, and writing complex compensating operations.
3. **Operating-Cost Exposure (Weight: 20%):** Unchecked agent retry loops multiply database write operations and downstream API costs.
4. **Empirical Verifiability:** The failure mode is deterministically reproducible: effect count in PostgreSQL provides an incontrovertible metric beyond simple HTTP 200 response codes.

### Why Problems B & C Were Deferred:
- **N+1 Query Pattern:** An important performance optimization, but less distinctive to the autonomous agent reliability challenge; fixing it primarily tunes read latency rather than preventing irreversible side effects.
- **Missing Validation:** Standard Pydantic schema validation is routine; while critical, solving it alone does not address transactional atomicity, concurrency races, or state deduplication.

---

## 3. User Persona and Failure Scenario

- **Persona:** A software engineer integrating an autonomous AI agent into operational workflows.
- **Scenario:** The agent decides to publish a customer update (`publish_update`). The agent's HTTP client submits the request to the gateway. The server begins execution, but network latency causes the agent's HTTP client to time out before receiving the acknowledgment.
- **The Failure:** Believing the request failed, the agent retries the call with the same idempotency key.
  - In the **baseline**, the service executes a second synthetic effect, writing another duplicate entry.
  - In the **fixed RelayGuard gateway**, the service detects the key claim in PostgreSQL, verifies the canonical SHA-256 payload hash, returns the original completed result with `replayed: true`, and creates zero additional effects.

---

## 4. Empirical Baseline vs. Fixed Evidence (PostgreSQL)

Measurements were executed on the final revision using `python -m scripts.measure` against PostgreSQL 18:

| Metric | Defective Baseline | Replay-Safe Gateway |
|---|---:|---:|
| Database Engine | PostgreSQL 18.3 | PostgreSQL 18.3 |
| Requests Attempted | 100 | 100 |
| Successful HTTP 200 Responses | 100 | 100 |
| **Synthetic Effects Created** | **100** | **1** |
| Local Elapsed Time | 5,526.834 ms | 6,138.108 ms |
| Average Latency / Request | 55.268 ms | 61.381 ms |
| **Duplicate Effects Prevented** | — | **99** |

### Integrity Note on Latency:
The fixed path required ~6 ms of additional overhead per request due to SHA-256 payload hashing, transaction synchronization, and uniqueness index lookups. **We do not claim a speed improvement.** The verified value is 100% correctness (1 effect per logical action).

---

## 5. Engineering Approach & Architecture

1. **One Endpoint Flow:** `POST /v1/actions` strictly constrained to `publish_update`.
2. **Strict Validation:** Pydantic v2 rejects unknown fields (`extra="forbid"`), enforces key regex `^[A-Za-z0-9._:-]+$`, length bounds (8–128), and content limits (1–1000 chars).
3. **Deterministic Payload Hashing:** SHA-256 hash of canonical UTF-8 JSON (`sort_keys=True`, compact separators). Excludes the idempotency key itself.
4. **PostgreSQL Concurrency-Safe Claim:** Uses `INSERT INTO actions ... ON CONFLICT (idempotency_key) DO NOTHING` paired with `FOR UPDATE` row locking. Eliminates check-then-act race conditions.
5. **Atomic Effect & Ledger Commit:** Action record and synthetic effect commit in a single PostgreSQL transaction (`with connection.transaction():`). If any step fails, neither row remains committed.
6. **Trigger-Based Fault Testing:** Automated verification installs a PostgreSQL trigger simulating internal effect failure; verifies complete rollback and subsequent retry recovery.
7. **Explicit Error Masking:** Database exceptions roll back and return a clean HTTP 503 without leaking stack traces or database connection strings.

---

## 6. Acceptance Criteria

- [x] Baseline defect reproduced: 10 identical requests produce 10 effects.
- [x] Fixed implementation verified: 10 exact replays produce 1 effect (1 fresh, 9 replayed).
- [x] 100-request reproducible measurement executed against PostgreSQL.
- [x] Key reuse with modified payload returns HTTP 409 Conflict.
- [x] Malformed requests and extra fields return HTTP 422.
- [x] Concurrency safety: 10 simultaneous threads produce exactly 1 effect.
- [x] Failure atomicity: database-level fault injection verifies total rollback.
- [x] Automated tests pass on final revision (`8 passed in 4.93s`).
- [x] Focused diff with zero unrelated refactors or dependency bloat.
- [x] ADR-001 evaluates 4 alternatives with clear trade-offs.
- [x] Real AI review candidate analyzed against the 3 quality dimensions.
- [x] Engineering handoff guide (`HANDOFF.md`) complete with next-engineer exercise.
- [ ] Loom video recorded by candidate ($\le$ 5 minutes).

---

## 7. Explicit Non-Goals & Boundaries

- **No Real Third-Party Providers:** No real emails, payments, SMS, or live LLM provider calls.
- **No Blanket External Exactly-Once Guarantee:** A local PostgreSQL transaction guarantees atomicity only for state stored within the same database. For external HTTP calls, production requires a Transactional Outbox and receiver-side idempotency.
- **No Unrelated Microservices or Tools:** No Redis, Kafka, Celery, or frontend dashboards.
