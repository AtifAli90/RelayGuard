# RelayGuard

> **Replay-safe execution for a synthetic AI-agent tool action.**
> Built with FastAPI, PostgreSQL 16, and Psycopg 3.

---

## 1. Executive Summary

Autonomous AI agents inevitably retry tool calls when encountering transient network timeouts, worker restarts, or orchestration hiccups. Without an atomic idempotency ledger, every replay causes duplicate execution of underlying side effects (duplicate notifications, double billing, or corrupted system state).

**RelayGuard** demonstrates production-aware replay protection for a single synthetic AI-agent action (`POST /v1/actions`, action type: `publish_update`).

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       AI AGENT CALLER                       │
│  POST /v1/actions                                           │
│  { "idempotency_key": "...", "action_type": "...", ... }    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    RELAYGUARD API GATEWAY                   │
│  1. Strict Pydantic validation (unknown fields forbidden)   │
│  2. Compute canonical SHA-256 payload hash                  │
│  3. Single PostgreSQL transaction:                          │
│     • Claim key via INSERT ... ON CONFLICT DO NOTHING       │
│     • If claimed: inspect stored hash under FOR UPDATE      │
│       - Matching: return cached result (replayed: true)     │
│       - Conflict: HTTP 409 Conflict                         │
│     • If new: execute synthetic effect & commit ledger      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     POSTGRESQL STORAGE                      │
│  • actions: idempotency_key (PK), payload_hash, result      │
│  • effects: effect_id (PK), idempotency_key (UNIQUE, FK)    │
└─────────────────────────────────────────────────────────────┘
```

- **Baseline Implementation:** Intentionally defective. Writes a new synthetic effect to `baseline_effects` on every request, completely ignoring the key.
- **Fixed Implementation:** Persists the action record and synthetic effect atomically in PostgreSQL. Returns stored results on exact replay; rejects key reuse with different content with **HTTP 409 Conflict**.

No external network calls, payments, or third-party APIs are contacted. This is a local synthetic demonstration.

---

## 2. Quickstart & Setup

### Prerequisites
- Python 3.11+
- Docker Desktop with Docker Compose (or local PostgreSQL 16+)

### Step 1: Configure Environment Variables

Create your local `.env` file from the provided development template:

**Windows PowerShell:**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

> [!NOTE]
> The default `.env` sets `DATABASE_URL=postgresql://relayguard:relayguard_dev_password@localhost:5434/relayguard`, matching Docker Compose host port **5434** (which avoids collisions with any native PostgreSQL running on port 5432). If you use a native PostgreSQL service on port 5432, update `DATABASE_URL` in `.env` to point to port 5432.

### Step 2: Start PostgreSQL via Docker Compose

```bash
docker compose up -d --wait db
```

The database container runs with an automated healthcheck.

### Step 3: Install Python Dependencies

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

### Step 4: Run Automated Verification Tests

```bash
python -m pytest -v
```

Verifies 10 automated test scenarios against real PostgreSQL:
1. Baseline defect reproduction (10 requests $\rightarrow$ 10 duplicate effects)
2. Exact replay deduplication (10 requests $\rightarrow$ exactly 1 effect, 1 fresh, 9 cached)
3. Payload conflict rejection (HTTP 409 on content mismatch)
4. Strict Pydantic input validation & extra-field rejection (HTTP 422)
5. Concurrency safety under race conditions (10 concurrent worker threads $\rightarrow$ 1 effect)
6. Transactional rollback atomicity (database trigger fault injection and recovery)
7. Operational health check verification (`GET /healthz`)
8. Multi-action repeatability and key isolation
9. Database unavailability error masking (returns HTTP 503 without leaking credentials)
10. Connection URL credential redaction verification

### Step 5: Run Empirical 100-Request Measurement

```bash
python -m scripts.measure
```

Sends 100 identical requests to the defective baseline and 100 to the fixed implementation, reporting effect counts, prevented duplicates (99), and local wall-clock timings.

### Step 6: Run Live Presentation & Demonstration

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
| [`compose.yaml`](compose.yaml) | Docker Compose specification for development PostgreSQL 16 |
| [`.env.example`](.env.example) | Development-only environment template (no secrets committed) |
| [`app/main.py`](app/main.py) | Fixed replay-safe FastAPI service implementation |
| [`app/baseline.py`](app/baseline.py) | Clearly labelled, intentionally defective baseline service |
| [`app/storage.py`](app/storage.py) | Psycopg 3 PostgreSQL schema management & connection handling |
| [`app/config.py`](app/config.py) | Fail-fast environment configuration parser |
| [`tests/test_replay_protection.py`](tests/test_replay_protection.py) | Automated test suite (concurrency, atomicity, conflict, validation) |
| [`scripts/measure.py`](scripts/measure.py) | 100-request before/after measurement tool |
| [`docs/ADR-001-idempotency-storage.md`](docs/ADR-001-idempotency-storage.md) | Architecture Decision Record comparing 4 storage options |
| [`docs/AI_REVIEW_EVIDENCE.md`](docs/AI_REVIEW_EVIDENCE.md) | AI code review analysis evaluating check-then-act vulnerabilities |
| [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) | Full captured test outputs and benchmark evidence |
| [`docs/LOOM_SCRIPT.md`](docs/LOOM_SCRIPT.md) | 5-minute timed video script and shot list |
| [`HANDOFF.md`](HANDOFF.md) | Next-engineer onboarding guide and exercise |
| [`problem.md`](problem.md) | Problem brief and affected user analysis |
| [`intent.md`](intent.md) | Problem selection scoring rubric & non-goals |
| [`directive.md`](directive.md) | Working directive with acceptance criteria and results appendix |
| [`security.md`](security.md) | Security protocols, threat model matrix, and production roadmap |