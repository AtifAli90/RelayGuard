# RelayGuard — Quest Starter Scaffold

RelayGuard is a small, synthetic FastAPI service demonstrating replay-safe handling for one AI-agent tool action. The project is designed to be small enough to understand and verify in a short engineering exercise.

> **Status:** starter scaffold prepared before the timed Quest begins. If you use it for the hiring exercise, disclose what pre-existed and document the changes you personally make during the Quest. Do not claim that this scaffold was created entirely during the timed period.

## The one flow

`POST /v1/actions` receives a `publish_update` action with an `idempotency_key` and `content`. The baseline deliberately writes an effect for every request. The fixed implementation stores the action, payload hash, and synthetic effect atomically in SQLite. Repeating a key with an identical payload returns the stored result; reusing a key with a different payload returns HTTP 409.

No external services are called. This is a local synthetic demonstration only.

## Setup

Requires Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Verify

```bash
python -m pytest -q
python -m scripts.measure
```

`measure.py` compares 100 repeated deliveries to the intentionally defective baseline and the fixed implementation. It reports the actual local values from that run. Execution-time values are local measurements, not service-level performance claims.

## Run locally

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to inspect the schema. The default demo database is written to the operating system temp folder. For isolated runs, set `RELAYGUARD_DB_PATH` to a path you control.

Example request:

```json
{
  "idempotency_key": "update-demo-0001",
  "action_type": "publish_update",
  "content": "Synthetic customer update for the RelayGuard demo."
}
```

## Safety and scope

- The baseline is intentionally defective and must never be used in production.
- The service supports only one synthetic action type.
- It does not connect to LLM providers, email services, payment providers, or production data.
- The SQLite transaction protects the synthetic effect because both the effect and ledger are in the same database transaction. A real external side effect needs a suitable delivery design, commonly a transactional outbox and receiver-side idempotency.
- The starter implementation is not a claim of multi-region, distributed exactly-once processing.

## Files

- `problem.md`: optional context and problem framing.
- `intent.md`: Quest problem selection, alternatives, criteria, non-goals, and evidence plan.
- `directive.md`: working agent instructions plus results/handoff appendix. Update it with final repository links, your real AI session evidence, actual test output, and Loom link before submission.
- `app/baseline.py`: clearly labelled defective baseline.
- `app/main.py`: focused fixed service implementation.
- `tests/test_replay_protection.py`: reproducible functional, validation, conflict, and concurrent replay checks.
- `scripts/measure.py`: repeatable local before/after measurement.
