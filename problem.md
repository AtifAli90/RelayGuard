# Problem Brief — RelayGuard

> Status: planning scaffold prepared before the timed Quest. This document is optional supporting context, not one of the three required submission items. If used, disclose what existed before acceptance and what is changed during the timed work.

## Problem

An AI agent or an orchestration layer may retry a tool call when a response is delayed, lost, or ambiguous. If the service cannot recognize a replay of the same logical action, it may perform the action more than once. In a customer-update workflow, this can publish duplicate updates; in other domains, the same pattern could create duplicate tickets, reminders, reports, or orders.

## Affected user and impact

- End user: receives duplicate or confusing output, reducing trust in the automation.
- Support/operator: must explain or manually undo repeated actions.
- Engineering team: must debug whether a request was processed when the response failed.
- System owner: may incur repeated downstream calls or usage costs.

These are plausible impacts of the failure mode; this synthetic exercise does not claim that a real user or customer was interviewed or affected.

## Evidence to collect

1. Reproduce the deliberately defective baseline with ten requests containing the same idempotency key and payload.
2. Count synthetic effects in SQLite, not just HTTP responses.
3. Run the same sequence against the fixed implementation.
4. Run automated checks for repeated requests, same key with a different payload, invalid input, and concurrent replay.
5. Run the measurement script and preserve its raw output. Report elapsed time as local and environment-specific.

## Baseline evidence in the prepared scaffold

The initial sandbox run used `python -m pytest -q` and reported **5 passed**. The measurement script sent 100 repeated requests per case:

| Measure | Deliberately defective baseline | Replay-safe implementation |
|---|---:|---:|
| Requests attempted | 100 | 100 |
| HTTP 200 responses | 100 | 100 |
| Synthetic effects created | 100 | 1 |
| Local elapsed time | 122.727 ms | 135.053 ms |

In that single local run, the corrected implementation prevented 99 repeated synthetic effects. It was about 10.0% slower in elapsed time in this run; this is not a production performance benchmark, and the project does not claim a latency improvement. The intended benefit measured here is duplicate-effect prevention, not lower request latency.

## Scope boundary

The exercise includes one synthetic action: `publish_update`. It uses FastAPI, Pydantic validation, SQLite, and pytest. No external AI provider, email service, payment provider, or live customer data is used.

The fixed implementation stores the idempotency record and synthetic effect in the same SQLite transaction. This is suitable for demonstrating the local pattern only. A production integration with an external side effect needs separate analysis, usually including a transactional outbox, stable provider-side idempotency keys, retries with bounded behavior, and reconciliation.

## Not claimed

- No customer interviews or user feedback were collected.
- No production, multi-region, high-throughput, or load-testing claims are made.
- No claim is made that this guarantees exactly-once delivery to arbitrary external systems.
- Local measurements are not generalizable to other machines or deployment conditions.
