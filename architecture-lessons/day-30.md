# 📐 Day 30 — Webhook Reliability
**Module 4: Integration Architecture**

## The Concept
Webhooks are inherently unreliable: the sender fires and forgets, the receiver can be down, crash mid-process, or acknowledge without actually processing. A reliable webhook system treats every inbound event as a durable message — not a transient HTTP call — and separates receipt from processing. The core guarantees to design for are: at-least-once delivery, ordered or idempotent processing, and dead-letter recovery. Without deliberate design, dropped events, silent duplicates, and phantom failures are guaranteed at scale.

## How It Works

```
Vendor (GitHub, Slack, SAP)
         |
         | POST /webhook  (fire and forget)
         v
  ┌─────────────────────┐
  │  Ingestion Layer    │  ← Acknowledge FAST (200 OK < 3s or vendor retries)
  │  (lightweight HTTP) │    Write to durable queue BEFORE processing
  └────────┬────────────┘
           │ enqueue(raw_payload, idempotency_key)
           v
  ┌─────────────────────┐
  │   Durable Queue     │  ← SQS / Kafka / RabbitMQ
  │  (at-least-once)    │    Message retained until ACK'd
  └────────┬────────────┘
           │ consume
           v
  ┌─────────────────────┐
  │  Processing Worker  │  ← Idempotent handler (check seen key before work)
  │  (connector trigger)│    ACK only after successful processing
  └────────┬────────────┘
           │ on failure
           v
  ┌─────────────────────┐
  │  Retry + DLQ        │  ← Exponential backoff, max attempts
  │  (dead letter queue)│    Alerts on DLQ depth
  └─────────────────────┘
```

**Key invariant:** Acknowledge receipt ≠ acknowledge processing. These must be decoupled.

**Delivery states to model explicitly:**
- `RECEIVED` — ingested into queue
- `PROCESSING` — worker picked up
- `PROCESSED` — handler succeeded, ACK sent
- `FAILED` — moved to DLQ after max retries
- `SKIPPED` — duplicate detected via idempotency key

## Real Scenario — Shield / IS / UiPath

In the IS webhook pipeline, a GitHub connector receives `push` events to trigger automation workflows. The naive implementation: GitHub POSTs → IS handler processes synchronously → triggers workflow → returns 200. Problem: if the workflow engine is slow (cold start, high load), GitHub's 10-second timeout fires, GitHub sees a timeout, marks delivery failed, and retries. Now you have a duplicate trigger. If the handler crashes mid-processing, the event is lost entirely.

**Reliable design for IS:**

1. **Ingestion service** receives the POST, writes `{event_id, raw_payload, source: "github", received_at}` to SQS immediately, returns `200 OK` in < 500ms. No processing happens here.
2. **Worker** consumes from SQS, checks Redis/DB for `event_id` (idempotency guard), triggers workflow, marks `event_id` as processed.
3. Worker ACKs the SQS message only after successful trigger.
4. On failure: SQS visibility timeout expires, message becomes visible again → retry. After N retries → DLQ.
5. Ops alert on DLQ depth > 0 for > 5 minutes.

**Ordering:** GitHub events for a single repo must be processed in order (push before push-derived PR). Use SQS FIFO with `repo_id` as the MessageGroupId to serialize per repo without blocking other repos.

**Signature validation:** GitHub sends `X-Hub-Signature-256`. Validate HMAC in the ingestion layer BEFORE queuing. Reject invalid signatures with `401` — never queue unauthenticated events.

## Interview Question

> *You own the IS webhook pipeline. During a Snowflake maintenance window, Snowflake fires a burst of 50,000 queued events the moment it comes back online. Your worker fleet processes ~2,000 events/minute. Design the system so this burst doesn't: (a) overwhelm the workers, (b) cause timeouts that trigger Snowflake to retry and double the load, (c) result in out-of-order processing for tenant-sensitive workflows. What are the key mechanisms, and what's the tradeoff you'd make on latency vs ordering guarantees?*

## Think About It
Where in the IS webhook pipeline today is the boundary between "receipt" and "processing" — and is it explicit in code, or implicit in whoever wrote the handler?
