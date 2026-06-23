---
# 📐 Day 20 — Pub/Sub vs Message Queue
**Module 3: Architectural Patterns**

## The Concept
A **Message Queue** delivers each message to exactly one consumer — messages are distributed across workers to spread load. A **Pub/Sub system** delivers every message to all subscribed consumers simultaneously — one publication fans out to N independent subscribers. Choosing the wrong one means either dropped events (single consumer when you needed broadcast) or duplicated work (broadcast when you needed exactly-one processing). The choice isn't about the broker (Kafka or RabbitMQ can do both) — it's about the delivery semantic your use case requires.

## How It Works

**Message Queue — work distribution (one consumer wins):**

```
Producer  -->  [ Queue ]  -->  Worker A  (processes msg 1)
                           -->  Worker B  (processes msg 2)
                           -->  Worker C  (processes msg 3)
```
Each message is "claimed" by one worker. Worker B never sees msg 1.

**Pub/Sub — fan-out (all subscribers get a copy):**

```
Producer  -->  [ Topic ]  -->  Subscription: Audit      --> Audit Service
                           -->  Subscription: Billing    --> Billing Service
                           -->  Subscription: Analytics  --> Analytics Service
```
All three receive the same message independently. Audit failure doesn't block Billing.

**In Kafka terms:**
- Queue behavior = all workers in the **same consumer group** (partitions shared among them)
- Pub/Sub behavior = each service in its **own consumer group** (each group gets full copy)

## Real Scenario — Shield / IS / UiPath

**Scenario 1 — Queue (correct choice):**
IS receives 10,000 inbound webhook events per minute from vendors. You have 8 worker pods processing these events and invoking automation workflows. Use a queue: each webhook is processed **exactly once** by one worker. If you used Pub/Sub here, all 8 workers would each process every event — you'd invoke every automation 8 times.

**Scenario 2 — Pub/Sub (correct choice):**
Every connector activity event (invocation succeeded/failed) needs to reach: the **Audit trail**, the **Billing metering** service, and the real-time **Analytics dashboard**. Use Pub/Sub: one event publication fans out. Audit service going down doesn't block Billing from receiving its copy. Adding a new consumer (e.g., SLA alerting service) = add a new subscription — **zero changes to the producer or queue consumers.**

**Scenario 3 — The trap (mixing both):**
Your existing webhook pipeline is a Queue (correct). Product now asks: "We want a real-time analytics dashboard that sees all events." Wrong answer: add analytics as a consumer to the existing queue — it would steal ~12% of messages from the real workers. Right answer: add a Pub/Sub topic upstream, fan out to (a) existing queue for workers, and (b) analytics subscription directly.

```
Vendor Webhook
      |
      v
  [WebhookReceived Topic]   <-- Pub/Sub fan-out point
      |                 \
      v                  v
  [Processing Queue]   [Analytics Subscription]
  (worker pool)        (dashboard / stream processor)
```

## Interview Question

*"IS processes connector webhooks via a message queue today. Product asks for a real-time analytics dashboard that needs to see all events without impacting existing webhook processing. How do you add this capability? Walk me through the architecture change, the delivery guarantees you'd provide, and what you'd do if the analytics service falls behind."*

Probe areas: fan-out topology, backpressure on slow consumers, dead letter queues, ordering guarantees across branches, at-least-once vs exactly-once tradeoffs when analytics state is derived.

## Think About It
In the IS connector activity pipeline today — which events need queue semantics, which need Pub/Sub semantics, and is there a single event stream that actually needs **both** applied at different stages?
---
