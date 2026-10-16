# RelayGuard — Replay-Safe Execution Gateway for AI-Agent Tool Calls

RelayGuard is a focused, production-aware FastAPI service demonstrating **replay-safe execution for AI-agent tool actions**. Built on **PostgreSQL** using atomic transactions, concurrency-safe uniqueness constraints, and deterministic payload hashing, RelayGuard prevents duplicate side effects when tool invocations are replayed following network drops or agent retry loops.

> **Quest Status:** Initial starter scaffold originated as an illustrative SQLite prototype. During the timed engineering assessment, it was migrated end-to-end to PostgreSQL with Docker Compose, Psycopg 3, atomic concurrency handling, trigger-based fault injection testing, and empirical verification.

---

## 1. The Core Flow

The service exposes `POST /v1/actions` for the synthetic `publish_update` action:

```
┌──────────────────────────────────────────────────────────┐
│                   CALLER / AI AGENT                      │
│  POST /v1/actions                                        │
│  { idempotency_key, action_type, content }               │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│               RELAYGUARD FASTAPI GATEWAY                 │
│  1. Pydantic v2 validation (extra="forbid")              │
│  2. Compute canonical SHA-256 payload hash               │
│  3. Single PostgreSQL transaction:                       │
│     • Claim key via INSERT ... ON CONFLICT DO NOTHING    │
│     • If claimed: inspect stored hash under FOR UPDATE   │
│       - Matching: return cached result (replayed: true)  │
│       - Conflict: HTTP 409 Conflict                      │
│     • If new: execute synthetic effect & commit ledger   │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                 POSTGRESQL STORAGE                       │
│  • actions: idempotency_key (PK), payload_hash, result   │
│  • effects: effect_id (PK), idempotency_key (UNIQUE, FK) │
└──────────────────────────────────────────────────────────┘
```

- **Baseline Implementation:** Intentionally defective. Writes a new synthetic effect to `baseline_effects` on every request, completely ignoring the key.
- **Fixed Implementation:** Persists the action record and synthetic effect atomically in PostgreSQL. Returns stored results on exact replay; rejects key reuse with different content with **HTTP 409 Conflict**.

No external network calls, payments, or third-party APIs are contacted. This is a local synthetic demonstration.

---

## 2. Quickstart & Setup

### Prerequisites
- Python 3.11+
- Docker Desktop with Docker Compose (or local PostgreSQL 16+)

### Step 1: Start PostgreSQL via Docker Compose

```bash
docker compose up -d --wait db
```

The database container runs on port `5434` (mapped to internal `5432` to avoid host conflicts) with a health check.

### Step 2: Install Python Dependencies

**Windows PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Step 3: Run Automated Verification Tests

```bash
python -m pytest -v
```

Verifies 8 automated scenarios against real PostgreSQL, including exact replay, payload conflict, strict Pydantic rejection, 10-thread concurrent replay, and database trigger fault injection.

### Step 4: Run Empirical 100-Request Measurement

```bash
python -m scripts.measure
```

Sends 100 identical requests to the defective baseline and 100 to the fixed implementation, reporting effect counts, prevented duplicates (99), and local wall-clock timings.

### Step 5: Run Live Presentation & Demonstration

To execute a live end-to-end demonstration covering health checks, replay deduplication, conflict rejection, 10-thread parallel race testing, and baseline contrast:

**Windows PowerShell:**
```powershell
.\run_presentation.ps1
```

**Any Platform:**
```bash
python -m scripts.demo_live
```

---

## 3. Running the Local API

```bash
uvicorn app.main:app --reload
```

Open interactive Swagger UI at: `http://127.0.0.1:8000/docs`

### Sample Request:
```bash
curl -X POST http://127.0.0.1:8000/v1/actions \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "update-demo-0001",
    "action_type": "publish_update",
    "content": "Synthetic customer update for the RelayGuard demo."
  }'
```

- **First call:** `HTTP 200` $\rightarrow$ `{"status": "completed", "replayed": false, "effect_id": 1}`
- **Exact repeat:** `HTTP 200` $\rightarrow$ `{"status": "completed", "replayed": true, "effect_id": 1}`
- **Different content with same key:** `HTTP 409 Conflict` $\rightarrow$ `"Idempotency key was already used with a different payload."`

---

## 4. Teardown and Reset

To stop the PostgreSQL container and reset data:
```bash
docker compose down -v
```

---

## 5. Repository Structure

| File / Folder | Purpose |
|---|---|
| [`compose.yaml`](file:///d:/Projects/RelayGuard/compose.yaml) | Docker Compose specification for development PostgreSQL 16 |
| [`.env.example`](file:///d:/Projects/RelayGuard/.env.example) | Development-only environment template (no secrets committed) |
| [`app/main.py`](file:///d:/Projects/RelayGuard/app/main.py) | Fixed replay-safe FastAPI service implementation |
| [`app/baseline.py`](file:///d:/Projects/RelayGuard/app/baseline.py) | Clearly labelled, intentionally defective baseline service |
| [`app/storage.py`](file:///d:/Projects/RelayGuard/app/storage.py) | Psycopg 3 PostgreSQL schema management & connection handling |
| [`app/config.py`](file:///d:/Projects/RelayGuard/app/config.py) | Fail-fast environment configuration parser |
| [`tests/test_replay_protection.py`](file:///d:/Projects/RelayGuard/tests/test_replay_protection.py) | Automated test suite (concurrency, atomicity, conflict, validation) |
| [`scripts/measure.py`](file:///d:/Projects/RelayGuard/scripts/measure.py) | 100-request before/after measurement tool |
| [`docs/ADR-001-idempotency-storage.md`](file:///d:/Projects/RelayGuard/docs/ADR-001-idempotency-storage.md) | Architecture Decision Record comparing 4 storage options |
| [`docs/AI_REVIEW_EVIDENCE.md`](file:///d:/Projects/RelayGuard/docs/AI_REVIEW_EVIDENCE.md) | AI code review analysis evaluating check-then-act vulnerabilities |
| [`docs/TEST_REPORT.md`](file:///d:/Projects/RelayGuard/docs/TEST_REPORT.md) | Full captured test outputs and benchmark evidence |
| [`docs/LOOM_SCRIPT.md`](file:///d:/Projects/RelayGuard/docs/LOOM_SCRIPT.md) | 5-minute timed video script and shot list |
| [`HANDOFF.md`](file:///d:/Projects/RelayGuard/HANDOFF.md) | Next-engineer onboarding guide and exercise |
| [`problem.md`](file:///d:/Projects/RelayGuard/problem.md) | Problem brief and affected user analysis |
| [`intent.md`](file:///d:/Projects/RelayGuard/intent.md) | Problem selection scoring rubric & non-goals |
| [`directive.md`](file:///d:/Projects/RelayGuard/directive.md) | Working directive with acceptance criteria and results appendix |
