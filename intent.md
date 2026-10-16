# intent.md — Why RelayGuard, and Why This Problem?

> **Preparation-status disclosure:** This is a planning draft and the attached repository is a starter scaffold prepared before the Quest timer starts. It includes a runnable illustrative implementation and local measurements. If I use it for the timed Quest, I will identify this pre-existing work and separately record the code, tests, reviews, and decisions I make after accepting. I will not represent the starter as work created entirely during the timed window.

## 1. Decision summary

I chose one focused problem: **duplicate synthetic tool effects when an AI-agent action is replayed after an ambiguous or failed response**.

The project, RelayGuard, is a small FastAPI execution gateway for one synthetic action, `publish_update`. The intended change is to make repeated requests with the same idempotency key safe: execute the logical action once, store its result, return that result on exact replay, and reject reuse of the same key for a different payload.

This problem ranked first because it has a direct and explainable user impact, can be reproduced in a small codebase, and permits a repeatable before/after measure. It also creates a natural opportunity to review AI-generated code for transaction boundaries, concurrency, and honest limits.

## 2. Three candidate problems compared

Scores are initial engineering judgments, not observed customer research. Each criterion is scored from 1 (low) to 5 (high), where a higher number means greater reason to prioritize the problem. The weighted score is `User impact × 0.50 + Maintenance/rework × 0.30 + Operating-cost exposure × 0.20`.

| Candidate quality problem | User impact (50%) | Maintenance/rework (30%) | Operating-cost exposure (20%) | Weighted priority | Decision |
|---|---:|---:|---:|---:|---|
| A. Duplicate side effects when a tool call is replayed | 5 | 4 | 4 | **4.5 / 5.0** | **Choose** |
| B. N+1 query pattern in a list endpoint | 3 | 4 | 5 | 3.8 / 5.0 | Defer |
| C. Missing validation on structured agent output | 4 | 3 | 2 | 3.3 / 5.0 | Defer |

### Why A wins

- **User impact:** the same logical action may be visible or consequential more than once.
- **Maintenance/rework:** engineers must diagnose ambiguous outcomes and may need compensating operations.
- **Operating cost:** repeated tool invocations can repeat work or downstream usage.
- **Evidence quality:** the baseline can be reproduced deterministically with synthetic inputs; effect count is more meaningful than a successful HTTP status alone.

### Why the other options are not selected

- **N+1 query:** valuable and measurable, but it is less directly tied to the AI-agent reliability angle and would require a separate endpoint/data model.
- **Missing validation:** important, but basic schema validation is comparatively routine and less distinctive for this short assessment.

Only option A is implemented in this exercise. The others are explicitly out of scope.

## 3. User and scenario

The hypothetical user is an engineer integrating an AI agent with an action-taking tool. The agent sends a request to publish a synthetic customer update. The action succeeds, but the response may be lost or delayed, so the caller retries with the same idempotency key. Without replay protection, the baseline repeats the synthetic effect.

This is a designed scenario, not a claim that an actual customer was interviewed or that a production system suffered this incident.

## 4. Baseline evidence and intended value

In the prepared local sandbox run:

- `python -m pytest -q`: **5 passed**.
- `python -m scripts.measure`: 100 repeated requests created 100 synthetic effects in the deliberately defective baseline and 1 in the replay-safe implementation.
- In the same run, elapsed time was 122.727 ms for the baseline and 135.053 ms for the fixed path. These environment-specific times show no speed improvement; in fact the fixed path was slower in this run. I will not claim a latency win.

The directly supported result is that the implementation prevents repeated synthetic effects for exact request replays in this local test. The desired operational value is a safer logical-action boundary, not a promise of globally exactly-once execution.

Before submission, I will rerun the checks on the actual submission revision, preserve full output, and replace these figures if the results differ.

## 5. Proposed engineering approach

1. Keep one API flow: `POST /v1/actions` for the synthetic `publish_update` action.
2. Validate fields, allowed action type, content length, and idempotency-key format.
3. Hash the canonical action payload so reuse of the same key with different content is not silently accepted.
4. Use a transaction and a database uniqueness constraint so concurrent replay requests cannot create multiple synthetic effects in this SQLite demonstration.
5. Return the recorded result with `replayed: true` for exact replays; return HTTP 409 when a key is reused with a different payload.
6. Add tests for baseline reproduction, exact replay, payload conflict, invalid content, and concurrent replay.
7. Inspect an AI-generated candidate before accepting it. In particular, scrutinize check-then-act code, unbounded retries, broad exception suppression, and claims that a database transaction makes arbitrary external side effects exactly-once.

## 6. Success criteria

- The deliberate baseline reproduces the duplicate-effect defect.
- Ten sequential identical submissions create ten baseline effects and one fixed effect.
- One hundred repeated submissions create 100 baseline effects and one fixed effect in the measurement run.
- Reusing a key with a different payload returns 409 and creates no second effect.
- Invalid content returns 422.
- Ten concurrent exact replays result in one effect in the local concurrent test.
- The automated tests pass on the final revision.
- `directive.md` contains exact reproduction steps, actual test output, the reviewed AI candidate and correction, decision trade-offs, a readable diff link, a handoff, and the Loom link.

These are acceptance criteria; I will report only outcomes I actually observe on the final revision.

## 7. Non-goals

- No live LLM or tool-provider integration.
- No real notification, payment, purchase, email, or publishing action.
- No multi-region or distributed exactly-once guarantee.
- No comprehensive agent platform, dashboard, authentication system, queue, or general policy engine.
- No benchmark claim about production latency or throughput.
- No unverified claims about user interviews, customer impact, savings, revenue, or adoption.
- No unrelated refactor or technology migration.

## 8. What pre-existed and what I will do during the Quest

The current starter already contains a baseline module, a reference fixed implementation, five tests, a local measurement script, and draft documentation. That is pre-existing preparation and must be disclosed if used.

During the timed Quest, I will:

- create a separate Quest branch and record the starting commit;
- independently inspect and explain the implementation before changing it;
- use an AI coding assistant for a bounded change or review, save the actual relevant prompt/output, and personally decide what to accept or reject;
- make and explain at least one substantive, reviewable change or test improvement;
- rerun tests and measurements on the final revision;
- update `directive.md` with the real diff, final results, actual AI contribution/correction, and any limitations;
- record actual effort and the exact Loom/repository links.

I will not backdate instructions or represent work completed before the timer as work completed during it.
