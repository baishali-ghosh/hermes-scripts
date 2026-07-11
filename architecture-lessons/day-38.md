---
# 📐 Day 38 — Async Processing

**Module 4: Scalability and Performance**

## The Concept

Async processing decouples the act of **accepting work** from **doing the work**. Instead of blocking the caller while you execute a potentially slow operation, you acknowledge immediately and process in the background. This dramatically improves throughput, resilience under load spikes, and perceived responsiveness. The fundamental contract shifts: the caller gets a job ID or a 202 Accepted, not an instant result. It requires deliberate design around status polling, callbacks, or event emission to close the loop.

## How It Works

```
Synchronous (blocks caller):
  Client ──POST /run──► API ──(wait 8s)──► Connector ──► Vendor API
           ◄─────────────────────────── result (8s later)

Async (non-blocking):
  Client ──POST /run──► API ──enqueue──► Queue ──► Worker ──► Vendor API
           ◄── 202 {jobId: "xyz"}               └─► result stored

  Client ──GET /jobs/xyz/status──► API ──► DB
          ◄── {status: "completed", result: {...}}

OR via callback/webhook:
  Worker finishes ──► POST /webhooks/client-callback ──► Client
```

Key components:
- **Producer**: API layer enqueues the job and returns immediately
- **Queue / Broker**: Kafka, RabbitMQ, SQS, Redis Streams — buffers work
- **Worker pool**: Consumes from queue, executes, persists result
- **Result store**: DB / cache keyed by jobId for polling, OR webhook callback
- **Dead letter queue (DLQ)**: Failed messages after N retries land here for investigation

Patterns:
- **Fire-and-forget** (no result needed): audit logs, analytics events
- **Request-reply async**: poll for status or receive callback — connector runs
- **Streaming**: results flow back incrementally as they're produced

## Real Scenario — Shield / IS / UiPath

**Problem**: Shield connectors calling LLM APIs (OpenAI, Azure OpenAI) can take 5–30 seconds per request. Connecting this to a synchronous HTTP path means:
- Held threads for 30s per request
- Load spike during peak DAP automation runs → 500 threads held → OOM → cascade
- Caller frameworks time out at 10s, missing 30s completions

**Async redesign for Shield AI connector**:

```
DAP Automation ──POST /connectors/openai/run──► IS API Layer
                        ◄── 202 { jobId: "conn-run-a1b2c3" }

IS API Layer ──enqueue(ConnectorRunJob)──► Redis Queue (or Kafka topic)

Worker Pool (N workers, isolated thread pool):
  ├── Worker 1 ──► OpenAI API (30s) ──► store result in Redis (TTL 10m)
  ├── Worker 2 ──► OpenAI API (12s) ──► store result
  └── Worker 3 ──► OpenAI API (5s)  ──► store result

DAP Automation ──GET /jobs/conn-run-a1b2c3──► IS API ──► Redis
                    ◄── { status: "completed", output: {...} }
```

Additional IS patterns you'd use:
- **Connector activity events** (WebhookReceived) go async into Kafka — log consumer, audit consumer, and billing consumer each process independently at their own pace
- **Bulk connector provisioning** (provisioning 100 connectors on tenant onboarding) — async job per connector, fan-out, aggregate status
- **Rate-limited vendor APIs** — async queue with a rate-limited worker prevents 429s upstream from Snowflake or Salesforce when IS spikes

**Backpressure signal**: When the queue depth exceeds threshold, IS API returns 429 with `Retry-After` instead of blindly enqueuing more — protecting workers from being overwhelmed.

## Interview Question

> "You're migrating a synchronous connector execution endpoint (POST /run) that handles 200 req/s peak to an async model. Walk me through the full design: how does the client discover completion, how do you handle partial failures mid-job, how do you prevent the result store from becoming a hot spot, and what happens to in-flight jobs during a worker deployment rollout?"

## Think About It

Which connector calls in IS today are synchronous but should be async — and what's the risk of making that change for callers who currently expect a synchronous response?
