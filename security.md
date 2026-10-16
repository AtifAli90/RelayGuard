# security.md — RelayGuard Security Protocols & Threat Model

> **Status:** Active Engineering Protocol
> **Audience:** Security Auditors, Software Engineers, Code Reviewers
> **Engine:** PostgreSQL 16+ / FastAPI / Psycopg 3

---

## 1. Security Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    CLIENT REQUEST                        │
│  POST /v1/actions                                        │
│  { idempotency_key, action_type, content }               │
└───────────────────────────┬──────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│              INPUT VALIDATION LAYER (Pydantic v2)        │
│  • idempotency_key: 8-128 chars, ^[A-Za-z0-9._:-]+$     │
│  • action_type: Literal["publish_update"] only           │
│  • content: 1-1000 chars, whitespace stripped            │
│  • extra fields: STRICTLY FORBIDDEN (extra="forbid")     │
│  → HTTP 422 on any violation (zero DB access)            │
└───────────────────────────┬──────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│           PAYLOAD INTEGRITY PROTOCOL                     │
│  • Deterministic canonical JSON (sorted keys, compact)   │
│  • SHA-256 hash computed over UTF-8 bytes                │
│  • Excludes idempotency key                              │
│  → Used for payload tamper / conflict detection          │
└───────────────────────────┬──────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│     ATOMIC POSTGRESQL TRANSACTION BOUNDARY               │
│  with connection.transaction():                          │
│  1. INSERT ... ON CONFLICT (idempotency_key) DO NOTHING  │
│  2. If claimed: SELECT ... FOR UPDATE (row lock)         │
│     - Hash mismatch: ROLLBACK → HTTP 409 Conflict        │
│     - Hash match: return cached result (replayed: true)  │
│  3. If new: INSERT INTO effects + UPDATE actions.result  │
│  4. Any DB exception: auto-ROLLBACK → HTTP 503           │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Core Security Protocols

### 2.1 Input Validation & Allowlisting Protocol
- **Strict Parameter Whitelisting:** Configured with `ConfigDict(extra="forbid", str_strip_whitespace=True)`. Unrecognized JSON fields cause immediate rejection with HTTP 422 before any database connection is opened.
- **Idempotency Key Constraints:** Length constrained between 8 and 128 characters. Allowed characters strictly restricted to `^[A-Za-z0-9._:-]+$` to prevent null-byte injection, SQL injection attempts, or log injection.
- **Content Limits:** 1 to 1,000 characters; whitespace is stripped to prevent empty or whitespace-only submissions.

### 2.2 Parameterized SQL & Injection Prevention Protocol
- **Zero Dynamic SQL:** All queries in [`app/main.py`](app/main.py), [`app/baseline.py`](app/baseline.py), and [`app/storage.py`](app/storage.py) utilize Psycopg 3 parameterized query binding (`%s`).
- **No String Formatting:** String concatenation, f-strings, and template substitutions are strictly forbidden in SQL execution paths.

### 2.3 Concurrency & Race-Condition Safety Protocol
- **The Anti-Pattern Rejected:** Naive check-then-act (`SELECT` followed by `INSERT`) was formally rejected (see [`docs/AI_REVIEW_EVIDENCE.md`](docs/AI_REVIEW_EVIDENCE.md)).
- **PostgreSQL Atomic Claim:** Keys are claimed via:
  ```sql
  INSERT INTO actions (idempotency_key, payload_hash, result_json)
  VALUES (%s, %s, '{}'::jsonb)
  ON CONFLICT (idempotency_key) DO NOTHING;
  ```
- **Pessimistic Row Locking on Replay:**
  Concurrent replay readers execute `SELECT ... FOR UPDATE`, guaranteeing that any in-flight transaction completes before the stored result is read.

### 2.4 Transactional Rollback & Fault Atomicity Protocol
- **Single Transaction Context:** All state mutations occur within `with connection.transaction():`.
- **Fault Verification:** Verified via automated test `test_database_failure_atomicity_and_recovery`: an injected PostgreSQL trigger raising an internal exception rolls back the entire transaction, leaving zero orphan rows in either `actions` or `effects`.

### 2.5 Structured Error Masking & Secret Redaction Protocol
- **Credential Masking in Errors and Logs:** Database connection URLs are filtered through `mask_database_url` (`app/storage.py`), replacing sensitive passwords with `***` (e.g. `postgresql://user:***@host:port/db`) in all log entries and operational error messages.
- **Error-Handling Boundary for Connection Setup:** In `app/main.py` and `app/baseline.py`, `connect()` is placed inside the `try ... except psycopg.Error:` block. If database connection setup fails (e.g., database service down or network partition), the error is intercepted and transformed into a generic HTTP 503 (`Action ledger is temporarily unavailable.`) without exposing raw driver traces or credentials.
- **No Stack Trace / Schema Leakage:** Internal table names, SQL statements, and database engine internals are never included in API responses.
- **Deterministic Resource Cleanup:** Connections are deterministically closed in `finally` blocks (`if connection is not None and not connection.closed: connection.close()`).
- **Automated Verification:** Verified by regression tests `test_database_unavailability_returns_503_and_masks_secrets` and `test_mask_database_url_helper_redacts_credentials`.

### 2.6 Credential & Environment Protection Protocol
- **No Hardcoded Secrets:** No database passwords or sensitive URLs exist in application code.
- **Git Ignore Safeguard:** `.gitignore` excludes `.env`, `.env.*`, `*.log`, `*.mp4`, test caches, and database dumps.
- **Example Template:** `.env.example` provides development-only placeholders with explicit warnings that they are local defaults.

---

## 3. Threat Model Matrix

| Threat Actor / Vector | Potential Impact | RelayGuard Mitigation | Status |
|---|---|---|---|
| **Replay Flood / Network Retry** | Duplicate actions, repeated side effects | Atomic `ON CONFLICT` deduplication returns cached result | ✅ Mitigated |
| **Payload Tampering / Key Collision** | Executing action B under key from action A | Canonical SHA-256 hash comparison triggers HTTP 409 | ✅ Mitigated |
| **Concurrent Race Exploit** | Parallel identical requests bypass check | PostgreSQL unique constraint + `FOR UPDATE` serializes | ✅ Mitigated |
| **SQL Injection** | Data exfiltration or corruption | 100% parameterized queries via Psycopg 3 | ✅ Mitigated |
| **Payload Bloat / DoS** | Database storage exhaustion | Pydantic strict length bounds (1,000 char max) | ✅ Mitigated |
| **Schema / Error Disclosure** | Information leakage to attacker | Generic HTTP 503 error masking without stack traces | ✅ Mitigated |
| **Credential Leakage in Logs/Errors** | Database password exposed via logs or HTTP | `mask_database_url` redacts passwords; 503 masks details | ✅ Mitigated |
| **Unauthenticated API Access** | Unauthorized tool invocation | ⚠️ No auth layer (intentionally out of demo scope) | ❌ Demo Boundary |
| **External Service Double Delivery** | Duplicate third-party webhook/payment | ⚠️ Out of scope (requires Transactional Outbox) | ❌ Demo Boundary |

---

## 4. Production Security Roadmap

Before deploying RelayGuard to a public or production environment, implement:

- [ ] **Authentication & Authorization:** Require API keys, JWT bearer tokens, or mTLS.
- [ ] **Multi-Tenant Key Scoping:** Scope idempotency keys by tenant: composite primary key `(tenant_id, idempotency_key)` to prevent cross-tenant key hijacking.
- [ ] **Rate Limiting:** Implement token-bucket rate limiting per IP / API key (e.g. via NGINX or FastAPI middleware).
- [ ] **Transactional Outbox:** For any external HTTP side effects, write intent events to an outbox table rather than invoking APIs inline.
- [ ] **Provider-Side Idempotency:** Send `Idempotency-Key` headers to external payment/notification providers.
- [ ] **Key Expiration (TTL):** Implement automated partition pruning or daily background cleanup for records older than 30 days.
- [ ] **TLS Termination:** Enforce HTTPS with HSTS headers.