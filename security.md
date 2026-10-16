# security.md — RelayGuard Security Protocols

> **Purpose:** This document defines all security protocols, design patterns, and boundary constraints followed in the RelayGuard project. It serves as a reference for code reviews, audits, and onboarding.

---

## 1. Security Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    CLIENT REQUEST                        │
│  POST /v1/actions                                        │
│  { idempotency_key, action_type, content }               │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              INPUT VALIDATION LAYER                      │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Pydantic v2 strict validation:                     │ │
│  │ • idempotency_key: 8-128 chars, [A-Za-z0-9._:-]   │ │
│  │ • action_type: literal "publish_update" only        │ │
│  │ • content: 1-1000 chars, strip whitespace           │ │
│  │ • extra fields: FORBIDDEN (extra="forbid")         │ │
│  │ → HTTP 422 on any violation                        │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│           PAYLOAD INTEGRITY CHECK                        │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ SHA-256 hash of canonical JSON payload              │ │
│  │ • Deterministic: sorted keys, compact separators    │ │
│  │ • UTF-8 encoded before hashing                     │ │
│  │ → Used for payload conflict detection               │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│        TRANSACTIONAL IDEMPOTENCY GUARD                   │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ BEGIN IMMEDIATE (write lock acquired first)         │ │
│  │ • Check for existing key → replay or conflict       │ │
│  │ • Same payload → return stored result (replayed)    │ │
│  │ • Different payload → HTTP 409 CONFLICT             │ │
│  │ • New key → INSERT action + effect atomically       │ │
│  │ COMMIT (or ROLLBACK on error)                       │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              RESPONSE (no internal details exposed)      │
│  • 200: action completed or replayed                     │
│  • 409: payload conflict                                 │
│  • 422: validation error                                 │
│  • 503: storage temporarily unavailable                  │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Security Protocols

### 2.1 Input Validation Protocol

**Goal:** Reject all malformed, malicious, or out-of-scope inputs at the API boundary.

| Field | Constraint | Rationale |
|---|---|---|
| `idempotency_key` | 8–128 chars, regex `^[A-Za-z0-9._:-]+$` | Prevents SQL injection, path traversal, null bytes, and overly short/long keys |
| `action_type` | Literal `"publish_update"` only | Allowlist — no arbitrary action execution |
| `content` | 1–1000 chars, whitespace stripped | Prevents empty submissions and DoS via oversized payloads |
| Extra fields | **Forbidden** (`extra="forbid"`) | Rejects unexpected data injection |

**Implementation:** Pydantic `BaseModel` with `ConfigDict(extra="forbid", str_strip_whitespace=True)` in [`app/main.py`](file:///d:/Projects/RelayGuard/app/main.py#L18-L25).

**Behavior:**
- Invalid input → **HTTP 422** with Pydantic validation error detail
- No internal stack traces or file paths exposed in error responses

---

### 2.2 Idempotency & Replay Protection Protocol

**Goal:** Ensure each logical action executes exactly once in the local SQLite scope, regardless of how many times the request is replayed.

**Mechanism:**
1. Client provides an `idempotency_key` with each request
2. Server computes a **SHA-256 hash** of the canonical payload (`action_type` + `content`)
3. Before any mutation, a **`BEGIN IMMEDIATE`** transaction acquires the write lock
4. Within the transaction:
   - If key exists with **same hash** → return stored result with `replayed: true` (no new effect)
   - If key exists with **different hash** → rollback, return **HTTP 409**
   - If key is new → INSERT action record + synthetic effect atomically, COMMIT

**Database Constraints:**
- `actions.idempotency_key` — **PRIMARY KEY** (unique by definition)
- `effects.idempotency_key` — **UNIQUE** constraint (one effect per key)
- `effects.idempotency_key` → `actions.idempotency_key` — **FOREIGN KEY**

**Implementation:** [`app/main.py`](file:///d:/Projects/RelayGuard/app/main.py#L61-L114), [`app/storage.py`](file:///d:/Projects/RelayGuard/app/storage.py#L20-L43)

---

### 2.3 Concurrency Safety Protocol

**Goal:** Prevent race conditions where concurrent identical requests both pass the "key not found" check and both create effects.

**Mechanism:**
- **`BEGIN IMMEDIATE`** acquires an exclusive write lock on the SQLite database *before* reading
- This serializes all concurrent write transactions at the database level
- The anti-pattern of "read → check → write" (check-then-act) is explicitly rejected

**Why not `BEGIN DEFERRED`:**
- Deferred transactions allow concurrent reads, then conflict at write time
- Two threads could both read "key not found" and both attempt to insert
- `BEGIN IMMEDIATE` ensures only one thread can enter the check-and-create block

**Tested by:** [`test_concurrent_replays_create_one_effect`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py#L65-L79) — 10 concurrent threads, verified 1 effect created.

---

### 2.4 Payload Integrity Protocol

**Goal:** Detect when a client reuses an idempotency key with a different payload (accidental or malicious key collision).

**Mechanism:**
1. Canonical JSON is constructed with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
2. SHA-256 hash of the UTF-8 encoded canonical string
3. Hash stored alongside the action record in `actions.payload_hash`
4. On replay, computed hash is compared against stored hash
5. Mismatch → **HTTP 409 Conflict**

**Why SHA-256:**
- Deterministic — same input always produces the same hash
- Collision-resistant — effectively impossible to craft two different payloads with the same hash
- Compact — 64-character hex string stored per record

**Implementation:** [`_stable_payload_hash()`](file:///d:/Projects/RelayGuard/app/main.py#L28-L35)

---

### 2.5 Error Handling Protocol

**Goal:** Return explicit, appropriate errors without exposing internal implementation details.

| Scenario | Status Code | Detail Exposed | Internal Details |
|---|---|---|---|
| Invalid input | 422 | Pydantic field errors | ❌ No stack traces |
| Payload conflict | 409 | "Idempotency key was already used with a different payload." | ❌ No hash values exposed |
| Database error | 503 | "Action ledger is temporarily unavailable." | ❌ No SQLite error messages |
| Successful action | 200 | Action result | ❌ No database internals |

**Rules Enforced:**
- ❌ **No bare `except: pass`** — all exceptions are either re-raised or converted to specific HTTP errors
- ❌ **No exception swallowing** — `sqlite3.Error` is caught, rolled back, and surfaced as 503
- ❌ **No internal path/schema leaks** — error messages are human-readable, not debug dumps
- ✅ **HTTPException re-raised cleanly** — the `except HTTPException: raise` pattern prevents 409 errors from being caught by the generic sqlite3.Error handler

**Implementation:** [`app/main.py`](file:///d:/Projects/RelayGuard/app/main.py#L108-L114)

---

### 2.6 Data Boundary Protocol

**Goal:** Ensure no real user data, credentials, or external systems are involved.

| Boundary | Enforcement |
|---|---|
| No real customer data | All content is synthetic strings (e.g., "Synthetic customer update for the RelayGuard demo.") |
| No credentials/secrets | No API keys, tokens, passwords, or .env files in the codebase |
| No external API calls | No HTTP client, no outbound network requests, no provider integrations |
| No authentication | Service is unauthenticated (demo-only scope) |
| No real side effects | "Effects" are SQLite rows, not emails, payments, or notifications |
| Isolated test databases | Each test uses `tmp_path` for a fresh, disposable SQLite database |

---

### 2.7 Database Security Protocol

**Goal:** Protect the SQLite database from corruption, unauthorized access, and data integrity issues.

| Measure | Implementation |
|---|---|
| **WAL mode** | `PRAGMA journal_mode = WAL` — crash-safe journaling |
| **Foreign keys enforced** | `PRAGMA foreign_keys = ON` — referential integrity on every connection |
| **Connection timeout** | `timeout=10.0` — prevents indefinite blocking |
| **Manual transaction control** | `isolation_level=None` — explicit `BEGIN`/`COMMIT`/`ROLLBACK` |
| **Connection cleanup** | Explicit `connection.close()` in `finally` blocks |
| **Configurable path** | `RELAYGUARD_DB_PATH` env var, defaults to temp directory |
| **Parent directory creation** | `path.parent.mkdir(parents=True, exist_ok=True)` — safe initialization |

**Implementation:** [`app/storage.py`](file:///d:/Projects/RelayGuard/app/storage.py)

---

### 2.8 Dependency Security Protocol

**Goal:** Minimize attack surface from third-party packages.

| Dependency | Version Constraint | Purpose | Risk Mitigation |
|---|---|---|---|
| `fastapi` | `>=0.115, <1.0` | Web framework | Pinned to minor range, well-maintained |
| `uvicorn[standard]` | `>=0.30, <1.0` | ASGI server | Production-grade, pinned |
| `pytest` | `>=8.0, <10.0` | Test framework | Dev-only dependency |
| `httpx` | `>=0.27, <1.0` | Test HTTP client | Dev-only dependency |

**Rules:**
- ✅ Version ranges with upper bounds (no `>=X` without `<Y`)
- ✅ No unnecessary dependencies — stdlib `sqlite3`, `hashlib`, `json` used where possible
- ❌ No dependency added without justification in the directive

---

## 3. Known Security Limitations

> [!WARNING]
> These limitations are intentional and documented — they reflect the demo scope, not oversights.

### 3.1 No Authentication or Authorization
The API has no auth layer. Any client can call `POST /v1/actions`. This is acceptable for a local demo but would require JWT/OAuth/API key authentication in production.

### 3.2 No Rate Limiting
No request rate limiting is implemented. A malicious client could exhaust the SQLite write lock or fill the database. Production would need rate limiting (e.g., via a reverse proxy or middleware).

### 3.3 No TLS/HTTPS
The development server uses plain HTTP. Production deployment requires TLS termination (typically at the load balancer or reverse proxy level).

### 3.4 Local-Only Idempotency Guarantee
The idempotency guarantee applies only within the local SQLite transaction boundary. **It does NOT guarantee:**
- Exactly-once delivery to external services (email, payment, notification)
- Cross-instance deduplication in a distributed deployment
- Recovery from partial failures where an external side effect succeeded but the local commit failed

**Production would require:**
- A **transactional outbox** pattern to atomically record the intent and deliver asynchronously
- **Provider-side idempotency keys** (e.g., Stripe's `Idempotency-Key` header)
- **Consumer-side deduplication** at the receiving service
- **Reconciliation** processes to detect and resolve drift

### 3.5 SQLite Scalability
SQLite serializes writes and is not suitable for high-concurrency production workloads. The demo uses it because it's zero-configuration and demonstrates the transaction pattern clearly. Production would use PostgreSQL or similar with `SERIALIZABLE` or `SELECT ... FOR UPDATE` patterns.

### 3.6 No Audit Logging
Actions have `created_at` timestamps but no audit trail (who, from where, request metadata). Production would log request provenance for security forensics.

---

## 4. Threat Model Summary

| Threat | Mitigation | Residual Risk |
|---|---|---|
| **Replay attack** (duplicate actions) | Idempotency key + transactional dedup | ✅ Mitigated for local scope |
| **Payload tampering** (key reuse with different content) | SHA-256 hash comparison → 409 | ✅ Mitigated |
| **SQL injection** | Parameterized queries (`?` placeholders) throughout | ✅ Mitigated |
| **Input overflow** | Pydantic max_length constraints | ✅ Mitigated |
| **Unexpected field injection** | `extra="forbid"` rejects unknown fields | ✅ Mitigated |
| **Race condition** (concurrent duplicates) | `BEGIN IMMEDIATE` serializes writes | ✅ Mitigated for SQLite |
| **Error information leak** | Generic error messages, no stack traces | ✅ Mitigated |
| **Denial of Service** | ⚠️ No rate limiting | ❌ Not mitigated (demo scope) |
| **Unauthorized access** | ⚠️ No authentication | ❌ Not mitigated (demo scope) |
| **Man-in-the-middle** | ⚠️ No TLS | ❌ Not mitigated (demo scope) |
| **External side-effect duplication** | ⚠️ Out of scope for this demo | ❌ Documented limitation |

---

## 5. Security Testing Coverage

| Test | What It Validates | File |
|---|---|---|
| `test_baseline_reproduces_duplicate_effects` | Confirms the defect exists without the guard | [`tests/test_replay_protection.py`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py#L29-L35) |
| `test_replays_create_only_one_effect_and_return_cached_result` | Replay protection works for sequential requests | [`tests/test_replay_protection.py`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py#L38-L48) |
| `test_reusing_key_with_different_payload_is_rejected` | Payload conflict detection → 409 | [`tests/test_replay_protection.py`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py#L51-L56) |
| `test_invalid_content_is_rejected` | Input validation → 422 | [`tests/test_replay_protection.py`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py#L59-L62) |
| `test_concurrent_replays_create_one_effect` | Concurrency safety under 10 threads | [`tests/test_replay_protection.py`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py#L65-L79) |

---

## 6. Production Security Checklist

If moving RelayGuard beyond demo scope, implement these security measures:

- [ ] Add authentication (API keys, JWT, OAuth2)
- [ ] Add authorization (role-based access control)
- [ ] Enable TLS/HTTPS (via reverse proxy or framework config)
- [ ] Add rate limiting (per-client, per-endpoint)
- [ ] Replace SQLite with PostgreSQL (or similar RDBMS)
- [ ] Implement transactional outbox for external side effects
- [ ] Add audit logging (request source, user, timestamp, outcome)
- [ ] Add request tracing (correlation IDs, OpenTelemetry)
- [ ] Set up dependency scanning (e.g., pip-audit, Snyk)
- [ ] Add CORS policy (restrict allowed origins)
- [ ] Implement graceful shutdown and health checks
- [ ] Add input sanitization for any rendered output
- [ ] Set up secret management (e.g., HashiCorp Vault, cloud KMS)
- [ ] Configure security headers (HSTS, X-Content-Type-Options, etc.)
