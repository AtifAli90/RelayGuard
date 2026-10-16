# directive.md — RelayGuard Final Working Directive

> **Status: starter directive, not submission-ready until updated.** This version was drafted before the timed Quest and accompanies a pre-existing starter scaffold. If used, disclose this fact. After accepting the Quest, record the starting commit, personally inspect and change the code, capture the real AI interaction, rerun every check, and replace all submission placeholders with verified links and results. Do not claim pre-existing work was created during the timed window.

## 1. Objective

Make one synthetic AI-agent tool flow easier to trust and change by preventing the same logical action from creating repeated effects when a request is replayed. Demonstrate the baseline, implement a narrowly scoped improvement, review AI-assisted code, measure before/after behavior, and hand the project to another engineer.

## 2. Context

RelayGuard is a small FastAPI service for a single synthetic action, `publish_update`. A caller provides an idempotency key and action payload. The defective baseline creates a new synthetic effect for every request. The fixed demonstration stores an idempotency record and synthetic effect together in a local SQLite transaction, then returns the recorded outcome on exact replay.

No external API, email, payment, LLM provider, production database, or real customer data is used.

## 3. Quality yardstick

Evaluate every proposed implementation against these signals:

1. **User impact / correctness:** number of synthetic effects created per logical action; exact replay behavior; conflicting payload behavior; validation behavior.
2. **Maintainability / rework:** clear transaction boundaries; small, typed request/response flow; explicit status codes; tests that describe intended behavior; no hidden error suppression.
3. **Operating-cost exposure:** count of synthetic effects/tool invocations per repeated request sequence. Local elapsed time is recorded as a secondary signal but must not be treated as a production benchmark.
4. **Concurrency correctness:** simultaneous identical requests must result in one synthetic effect in the demonstrated local SQLite model.
5. **Honest boundaries:** explicitly state that a local database transaction does not guarantee exactly-once behavior for arbitrary external services.

Do not report one metric as a proxy for all quality. A successful HTTP response alone does not prove that an action happened exactly once.

## 4. Scope and boundaries

### In scope

- One endpoint: `POST /v1/actions`.
- One synthetic action type: `publish_update`.
- Input validation for the idempotency key, action type, and content.
- A stable payload hash for detecting key reuse with different content.
- Atomic local ledger/effect creation with SQLite transaction and uniqueness constraints.
- Replay response, payload-conflict response, and reproducible tests.
- One baseline-to-fixed comparison and one code-review example.

### Out of scope

- Real provider calls or production data.
- Real payments, email, publishing, customer communication, or other irreversible side effects.
- General-purpose agent orchestration, authentication, dashboards, queues, retries, or provider integrations.
- Multi-region/distributed consistency or a blanket exactly-once guarantee.
- Unrelated refactoring, new database systems, or changes to unrelated products.

Do not expand scope without recording a decision and why the new work is essential to this single flow.

## 5. Required behavior

- A valid request with a new key creates one action record and one synthetic effect.
- An exact replay with the same key and same canonical payload returns the stored result with `replayed: true` and creates no additional effect.
- Reuse of the same key with a different payload returns HTTP 409 and creates no additional effect.
- Invalid request data returns HTTP 422.
- Ten concurrent exact replays create one synthetic effect in the local SQLite test.
- The baseline remains clearly marked as intentionally defective and is never presented as deployable code.

## 6. AI-agent working instructions

Before editing, inspect `app/main.py`, `app/baseline.py`, `app/storage.py`, and the tests. Summarize the current flow and the defect in no more than five bullets. Do not rewrite the entire project.

When asked to implement or improve a bounded change:

1. State the proposed files to change and why before editing.
2. Preserve the one-endpoint scope and the synthetic-only boundary.
3. Prefer the smallest correct change over a framework or architecture rewrite.
4. Add or update tests that fail for the relevant defect and pass after the change.
5. Do not add new dependencies unless needed; justify each dependency.
6. Do not swallow exceptions. Return explicit, appropriate errors without exposing internal details.
7. Do not implement a check-then-act idempotency pattern that can race. Use a database uniqueness boundary and an atomic transaction for this local synthetic implementation.
8. Do not claim arbitrary external side effects are exactly-once. If proposing a real integration, document the need for an outbox, provider/receiver idempotency, and recovery/reconciliation.
9. Do not introduce unbounded retries, live external calls, credentials, real customer data, or unapproved scope.
10. After editing, show the diff, summarize trade-offs, run relevant tests, and report actual commands and outputs. Never state that a test passed unless it was run.

The human engineer is responsible for reviewing the design, changing or rejecting suggestions, verifying behavior, and accurately reporting results.

## 7. Acceptance criteria

- [ ] The baseline defect is reproduced with the same request repeated ten times.
- [ ] The baseline creates ten effects; the fixed path creates one effect for ten exact replays.
- [ ] A 100-request repeatable measurement is run for baseline and fixed versions.
- [ ] Same key/different payload returns 409.
- [ ] Invalid content returns 422.
- [ ] Concurrent duplicate requests are covered by an automated test.
- [ ] Automated checks pass on the exact final commit.
- [ ] The diff is focused and readable.
- [ ] The actual AI candidate/output that was reviewed or corrected is preserved in the submission record; if no meaningful correction happened, do not fabricate one—perform a real review iteration.
- [ ] An ADR explains at least three alternatives, the decision, and trade-offs.
- [ ] An engineer unfamiliar with the project can reproduce the checks and complete the handoff exercise.
- [ ] The Loom is no longer than five minutes and accurately shows the final revision.
- [ ] Every link opens for a reviewer without asking for extra permissions.

## 8. Verification commands

From the repository root, using Python 3.11+ recommended:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m scripts.measure
```

To inspect/run the API locally:

```bash
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/docs` and submit the example body below. Stop the server after the demonstration. The default app writes a demo database under the system temp directory; use `RELAYGUARD_DB_PATH` when an isolated data path is needed.

Example request:

```json
{
  "idempotency_key": "update-demo-0001",
  "action_type": "publish_update",
  "content": "Synthetic customer update for the RelayGuard demo."
}
```

Repeat the same body to verify the replay response. Change `content` but keep the key to verify HTTP 409.

## 9. Starter scaffold verification evidence — rerun before submission

The starter's current local sandbox run produced:

```text
python -m pytest -q
5 passed in 0.18s
```

The local measurement script produced:

```text
case: baseline-intentionally-defective
requests: 100
http_200_responses: 100
effects_created: 100
elapsed_ms_local: 122.727

case: fixed-idempotency-guard
requests: 100
http_200_responses: 100
effects_created: 1
elapsed_ms_local: 135.053

duplicate_effects_prevented_in_this_run: 99
```

Interpretation: in this single local run, replay protection reduced synthetic effects from 100 to 1 for 100 identical requests. The fixed path was slower in elapsed time in this run (135.053 ms versus 122.727 ms), so no latency improvement is claimed. These figures were measured on the scaffold in the assistant's current sandbox. They are not team-wide or production results. Rerun on the final revision and record the actual environment and output; replace these values if they differ.

## 10. Code-review example and AI contribution — must finalize honestly

### Anti-pattern to scrutinize

The following is a **review illustration**, not a quotation from a logged coding-agent session:

```python
existing = db.get(idempotency_key)
if existing is None:
    effect = publish_update(payload)  # external side effect happens first
    db.save(idempotency_key, effect)
return effect
```

### Review finding

The read, side effect, and save are not one atomic operation. Concurrent requests may both observe the missing key and both execute. If the external side effect succeeds but saving the record fails, a retry can execute it again. A human reviewer should reject this pattern for consequential actions.

### Safer bounded choice in this demo

The local synthetic implementation starts a SQLite write transaction before checking the key, compares a stable payload hash, and commits the action record and synthetic effect together. The schema also has uniqueness constraints. The same key with a different payload returns 409. This safely demonstrates the local case; it is not a blanket guarantee for external providers.

### Actual AI evidence to add before submitting

- AI tool/model actually used: `[fill in]`
- Prompt or task given: `[paste the actual prompt]`
- Short exact excerpt of the generated proposal: `[paste the actual output; do not invent it]`
- What I accepted, changed, or rejected: `[fill in]`
- Technical reason, linked to user impact / maintenance / operating cost: `[fill in]`
- Files and tests changed by me during the Quest: `[fill in]`
- Evidence link or commit: `[fill in]`

If a coding assistant's first proposal is already correct, review a real missing edge case or request an alternative and document the actual decision. Do not manufacture a false AI failure for the recording.

## 11. Architecture Decision Record — ADR-001

**Title:** Protect repeated synthetic tool actions using transactional local idempotency

**Status:** Chosen for the scoped demo; not a production provider-integration decision.

**Context:** A caller can replay a request after an ambiguous response. The baseline ignores the idempotency key and creates another synthetic effect on every delivery.

**Options considered:**

1. **In-memory set/dictionary:** easy to write, but state is lost on restart and is not shared by separate worker processes. Rejected.
2. **Read-then-write without a transaction/constraint:** simple-looking, but the check-and-act sequence can race and duplicate work under concurrent requests. Rejected.
3. **SQLite transaction + unique idempotency key + payload hash:** the key check, stored result, and synthetic effect are protected in one local database transaction; exact replays return the recorded outcome and changed payloads return 409. Selected for this small local demonstration.
4. **Transactional outbox plus provider-side idempotency/consumer deduplication:** more appropriate for real external side effects, but adds queue/worker/provider semantics outside this small Quest's one-flow scope. Deferred, not dismissed for production.

**Trade-offs:**

- SQLite serializes this small local workload and may limit write concurrency at higher scale.
- The demo intentionally makes the effect local and transactional; it does not pretend a database can roll back an external email/payment provider.
- The extra checks increase local code and can add latency; the measured local run was slower for the fixed version, so the demonstrated gain is correctness, not speed.
- Payload mismatch is rejected instead of silently returning an unrelated prior outcome.

**Revisit when:** multiple service instances or external effect providers are introduced; then evaluate provider idempotency semantics, transactional outbox, worker retry policy, reconciliation, and persistent observability.

## 12. Focused diff and change record — fill from final Git history

- Starting commit (pre-existing scaffold): `[insert hash]`
- Final commit: `[insert hash]`
- Changed files during timed Quest: `[list exact files]`
- Diff link: `[insert commit/diff URL]`
- Why this remained focused: `[write 2–3 sentences]`

Do not invent a commit or diff link. Link to the actual repository revision reviewers can open.

## 13. Results and handoff appendix

### Required links — replace placeholders

- Loom video (<= 5 minutes): `[insert accessible Loom URL]`
- Repository: `[insert accessible GitHub/GitLab URL]`
- Focused diff/commit: `[insert real URL]`
- Test run evidence (CI job or captured test output): `[insert real URL or section]`
- Baseline/fixed measurement output: `[insert real URL or section]`
- AI review evidence: `[insert actual prompt/output capture or commit]`
- Optional `problem.md`: available in the same repository.

The repository link must provide reviewer access without needing a separate request. Verify links in a private/incognito browser session if possible.

### Reproduction steps for another engineer

1. Install Python 3.11+ and dependencies with `python -m pip install -r requirements.txt`.
2. Run `python -m pytest -q` and record the exact outcome.
3. Run `python -m scripts.measure`; compare effect counts, not just status codes.
4. Run `uvicorn app.main:app --reload`, open `/docs`, and submit the sample request twice with the same key and payload.
5. Reuse that key with a changed payload and observe HTTP 409.
6. Review `app/main.py`, `app/storage.py`, and ADR-001 before modifying the behavior.
7. Change one behavior, add a test that would fail without the change, then rerun the entire suite and measurement script.

### Handoff exercise

Ask a reviewer to add a new allowed action type without weakening replay safety. They should first describe the payload hash contract, decide whether action type is included in the hash (it is), add validation/tests, and explain how a real external provider would need idempotency support. Do not claim another engineer completed this exercise unless you observe it. If self-demonstrated, state: **“Handoff limitation: demonstrated by the author; no independent reviewer feedback was collected.”**

### Compact review checklist

- [ ] The same key plus same payload creates only one synthetic effect.
- [ ] The same key plus different payload is rejected.
- [ ] Concurrency test covers the check-and-create boundary.
- [ ] No live external calls or secrets are present.
- [ ] No bare `except: pass`, unbounded retries, or hidden failure paths.
- [ ] Error behavior is explicit and documented.
- [ ] Tests pass on the final commit.
- [ ] Metrics are labeled as local, measured, or estimated accurately.
- [ ] Diff is small enough to review in a few minutes.
- [ ] Limitations and production follow-up are explained.

### Final results block — complete at the end of the timed work

- Actual elapsed Quest effort: `[hours/minutes]`
- Final commit/hash: `[hash]`
- Exact test command and result: `[actual output]`
- Actual baseline effect count: `[measured]`
- Actual fixed effect count: `[measured]`
- Actual local timing and environment: `[measured, optional system details]`
- AI used and contribution: `[actual]`
- Correction/rejection decision: `[actual evidence]`
- Remaining limitation: `[actual]`
- Handoff feedback: `[observed feedback OR author-only demonstration]`

## 14. Loom outline — maximum five minutes

Target length: 4 minutes 40 seconds, with time buffer.

- **0:00–0:25 — Problem:** explain replayed AI tool calls and the chosen quality risk.
- **0:25–1:00 — Prioritization:** show `intent.md`, the three candidate problems, and why duplicate effects ranked first.
- **1:00–1:45 — Reproduce baseline:** run the measurement command and show 100 requests creating 100 synthetic effects.
- **1:45–2:40 — Focused change:** show the transaction/unique-key design and the small final diff. Explain why the key's payload hash matters.
- **2:40–3:30 — Verification:** show tests for exact replay, changed payload, invalid content, and concurrent replay; show actual final output.
- **3:30–4:15 — AI and human judgment:** show the real AI proposal and your correction/rejection, explaining the risk and decision.
- **4:15–4:40 — Handoff and limitation:** show reproduction steps, next engineer exercise, and why a real external provider needs additional design.

Record the video after the final code and docs are stable. Use the actual screen, terminal output, and final diff; do not use fabricated dashboard data or scripted results presented as real. Keep secrets and unrelated personal information off screen. Stop before five minutes and verify the Loom link in a logged-out/private browser session.
