---
# 📐 Day 19 — Event-Driven Architecture
**Module 3: Architectural Patterns**

## The Concept
In Event-Driven Architecture (EDA), components communicate by publishing and consuming events — not by calling each other directly. A producer emits an event describing *something that happened* (e.g., `WebhookReceived`, `ConnectorFailed`) and moves on. It has zero knowledge of who consumes that event or how many consumers exist. This decoupling enables independent scaling, replayability, and fan-out to multiple consumers without the producer changing. The tradeoff: you gain loose coupling and resilience, but you lose the simplicity of synchronous request/response — debugging, ordering, and exactly-once delivery all become harder to reason about.

## How It Works

```
Vendor → HTTP POST → [Webhook Ingestion Service]
                              |
                              | emits: WebhookReceived {connectorId, payload, ts}
                              ↓
                        [Event Broker]
                       (Kafka / RabbitMQ / SQS+SNS)
                              |
              ┌───────────────┼────────────────┐
              ↓               ↓                ↓
      [Logger Service]  [Connector Activity  [Audit Trail
                          Trigger Service]    Service]
```

- Each consumer group processes independently
- If the Audit Trail consumer crashes → it re-reads from its last committed offset
- Logger going slow → doesn't block the Connector Activity trigger
- Add a new consumer (e.g., billing)? → zero changes to producer or other consumers

Key EDA primitives:
- **Event**: immutable, past-tense fact (`WebhookReceived`, not `ProcessWebhook`)
- **Topic/Queue**: channel where events land
- **Consumer Group**: set of workers competing to process messages from a topic
- **Offset / Checkpoint**: where a consumer is in the event stream

## Real Scenario — Shield / IS / UiPath

**Webhook Ingestion Pipeline at IS:**

Today, when a vendor (e.g., GitHub) fires a webhook — a push event, a PR opened — IS receives it via the ingestion endpoint. If that handler also synchronously triggers the connector activity, logs it, and writes to the audit trail, you have a fragile coupled pipeline. One slow downstream (audit DB is backed up) blocks the whole chain.

Redesign with EDA:
1. **Ingestion Service** validates the webhook signature, emits `WebhookReceived` to Kafka topic `connector.events`, returns `200 OK` immediately.
2. **Connector Activity Consumer** reads from that topic → triggers IS automation logic.
3. **Audit Trail Consumer** reads from the same topic (different consumer group) → writes to audit DB.
4. **Metrics Consumer** reads and updates real-time dashboard.

Now the vendor gets a fast `200 OK`. Each downstream service fails and recovers independently. If IS is being deployed, the Kafka topic holds events — nothing is lost.

**The ordering challenge:** GitHub sends `push` then `pull_request.closed` in sequence. If two partitions handle them, ordering isn't guaranteed. For connectors where event order matters (state machine transitions), you must partition by `connectorId` or `repoId` so related events always go to the same partition and are processed in order.

**The exactly-once problem:** Kafka guarantees at-least-once delivery by default. Your connector activity trigger must be idempotent — processing the same `WebhookReceived` event twice should not create duplicate automation runs. Use the event's idempotency key (e.g., `X-GitHub-Delivery` header) to deduplicate before acting.

## Interview Question

*"You're redesigning the connector webhook pipeline to be event-driven. What guarantees does your system need around ordering and exactly-once delivery? Walk me through the end-to-end design, and what happens when the Connector Activity Consumer crashes mid-processing — how do you prevent double-execution or missed execution?"*

Expected tradeoffs to hit:
- At-least-once (Kafka default) vs exactly-once (requires idempotent consumers OR Kafka transactions — more complexity)
- Per-partition ordering vs global ordering (global = one partition = no horizontal scale)
- Consumer checkpointing: commit offset *after* successful processing, not before (at-least-once) — this is a deliberate choice
- Compensating for duplicate events via an idempotency table (connectorId + deliveryId seen-set in Redis/DB)

## Think About It

When a webhook consumer crashes and restarts, it re-reads from its last committed offset — what does your connector activity trigger need to be true about itself to make that safe?
