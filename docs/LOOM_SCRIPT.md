# RelayGuard — Loom Presentation Script & Shot List (Max 5 Minutes)

> **Target Duration:** 4 minutes 45 seconds (15-second buffer)
> **Presenter:** Candidate / Lead Engineer
> **Format:** Screen share + webcam bubble in bottom corner

---

## Shot List & Narration Plan

### 0:00 – 0:25: Problem Statement & RelayGuard Mission
- **On Screen:** `problem.md` or IDE with `app/main.py`
- **Narration:**
  > "Hi, I'm presenting RelayGuard. When AI agents execute tool actions like publishing updates or creating records, network drops or LLM retry loops often resubmit the exact same request. Without replay protection, each retry duplicates side effects—spamming users, duplicating orders, or wasting resources. RelayGuard is an execution gateway for a synthetic `publish_update` action that guarantees exact replays produce exactly one effect."

### 0:25 – 0:55: Problem Prioritization (Why This Problem?)
- **On Screen:** `intent.md` (Table 1: Candidate Quality Problems)
- **Narration:**
  > "In `intent.md`, we evaluated three candidate reliability issues using a weighted rubric across User Impact, Maintenance, and Operating Cost.
  > While N+1 queries and input validation scored 3.7 and 3.3, duplicate agent side effects scored 4.5 out of 5.0.
  > Duplicating consequential tool effects directly damages user trust and incurs compounding operational cleanup costs. That's why we focused our efforts here."

### 0:55 – 1:25: Baseline Reproduction & Empirical Measurement
- **On Screen:** Terminal running `python -m scripts.measure`
- **Narration:**
  > "Let's reproduce the defect live. Our measurement script sends 100 identical requests to both our defective baseline and our fixed implementation against PostgreSQL.
  > Notice the result: The baseline created 100 separate synthetic effects in the database—one for every single delivery.
  > The fixed implementation created exactly 1 effect, preventing 99 duplicate side effects. Wall-clock times vary by environment; the primary metric is effect count, not speed."

### 1:25 – 2:10: Architecture & Focused Diff
- **On Screen:** `git diff` or `app/main.py` showing `execute_action`
- **Narration:**
  > "Here is our implementation. Rather than a naive check-then-act pattern that races under load, we use PostgreSQL's atomic concurrency primitives inside a single transaction.
  > We execute `INSERT INTO actions ... ON CONFLICT (idempotency_key) DO NOTHING`.
  > If the key was already claimed, we lock the row with `FOR UPDATE` and compare a canonical SHA-256 payload hash. If matching, we return the cached response with `replayed: true`. If the payload changed, we reject with HTTP 409 Conflict.
  > If the key is new, the action ledger and synthetic effect are committed in the same database transaction."

### 2:10 – 3:15: Verification Suite (Concurrency & Fault Atomicity)
- **On Screen:** Terminal running `python -m pytest -v`
- **Narration:**
  > "Let's run our test suite: `python -m pytest -v`. All 10 tests pass against real PostgreSQL.
  > Two critical tests to highlight:
  > First, `test_concurrent_replays_create_one_effect`: 10 parallel threads hit the API simultaneously with the same key. Exactly 1 effect is created, with 0 race condition errors.
  > Second, `test_database_failure_atomicity_and_recovery`: We inject a PostgreSQL trigger that forces an exception on effect insertion. The entire transaction rolls back cleanly—leaving neither action nor effect rows in the database. When the fault is cleared, the retry succeeds cleanly."

### 3:15 – 4:10: AI Code Review & Human Correction
- **On Screen:** `docs/AI_REVIEW_EVIDENCE.md`
- **Narration:**
  > "During this project, we evaluated a reconstructed AI proposal archetype shown here in `docs/AI_REVIEW_EVIDENCE.md`.
  > The archetype attempts a naive `SELECT` check followed by an `INSERT`.
  > As lead engineer, I rejected that candidate across all three quality dimensions:
  > In User Impact: the code inserts into `effects` before `actions`, immediately triggering a foreign-key violation on every new request, breaking the service on all fresh keys. Even if the ordering were reversed, check-then-act creates a race condition.
  > In Maintenance: it caught broad exceptions, leaked raw database error strings to callers, and failed to guarantee connection cleanup.
  > In Operating Cost: broken requests and race conditions risk operational overhead.
  > I replaced it with PostgreSQL's atomic `ON CONFLICT` pattern, `FOR UPDATE` locking, and strict exception masking."

### 4:10 – 4:45: Handoff & Production Boundaries
- **On Screen:** `HANDOFF.md` or `directive.md` (Handoff section)
- **Narration:**
  > "For handoff, any engineer can spin up the environment with `docker compose up -d --wait db` and verify with `pytest`.
  > As an exercise, the next engineer is invited to add a new action type without weakening the payload contract.
  > Crucially, our honest boundary: this local transaction guarantees atomicity for synthetic internal database effects. For arbitrary external side effects like Stripe or SendGrid, production requires a Transactional Outbox and receiver-side idempotency."

### 4:45 – 5:00: Concise Close
- **On Screen:** Camera on presenter
- **Narration:**
  > "RelayGuard demonstrates focused engineering rigor: verifiable PostgreSQL tests, atomic concurrency, empirical before-and-after proof, and honest boundaries. Thank you."

---

## Presenter Instructions
1. Practice with a stopwatch to stay strictly under 4:45.
2. Record using Loom (Chrome extension or desktop client).
3. Confirm audio is clear and 1080p resolution is selected.
4. Copy the public Loom URL, paste it into `directive.md` under Section 13, and verify the link opens in an incognito window.