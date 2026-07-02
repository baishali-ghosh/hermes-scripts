---
# 📐 Day 29 — Backpressure
**Module 4: Integration Architecture**

## The Concept
Backpressure is a flow-control mechanism where a slow downstream consumer signals an upstream producer to slow down — rather than silently falling behind and eventually crashing. Without it, fast producers overwhelm slow consumers: buffers fill, memory blows up, or events are simply dropped. The fix isn't "add more queue" — it's propagating load signals upstream so producers self-throttle. Backpressure is what separates a resilient integration pipeline from a ticking time bomb.

## How It Works

```
Fast Producer                    Slow Consumer
    │                                 │
    │  ────── events ──────►  [Queue] │
    │                         ↑ FULL  │
    │  ◄───── slow down! ─────────────│
    │  (backpressure signal)          │
    │                                 │
    │ now produces at consumer rate   │
```

Three strategies:

1. **Drop** — Shed the load. Acceptable only if events are low-value (metrics, heartbeats). Never for transactions.
2. **Buffer + Block** — Accept up to N, block the producer when full. Producer stalls instead of overwriting.
3. **Rate signal** — Consumer exposes credit/quota; producer only sends what's authorized. gRPC flow control works this way.

Reactive Streams (RxJava/Project Reactor) standardize this with `request(n)` — consumer pulls at its own pace.

## Real Scenario — Shield / IS / UiPath

The webhook ingestion path in IS: SAP fires 5,000 events/sec during a batch job. Your webhook receiver writes each event to a queue for downstream connector processing. But the connector pool for SAP (configured for 20 concurrent calls) processes at ~200 events/sec.

**Without backpressure:** Queue depth grows without bound. Within minutes memory pressure builds, queue consumer lag spikes, and IS starts OOM-crashing — taking down *all* connectors, not just SAP.

**With backpressure design:**
- Receiver maintains a bounded in-memory queue (e.g., 10,000 capacity).
- When queue hits 80% full → receiver returns HTTP `429 Too Many Requests` to the vendor webhook push.
- Well-behaved vendors (SAP, Salesforce) back off and retry with exponential backoff.
- For vendors that don't respect 429, you add a drop policy at 100% with a counter/alert.

On the internal side, between IS components:
- Use bounded queues + blocking publishers (Reactor's `onBackpressureBuffer(maxSize, DROP_OLDEST)` or `onBackpressureError()`).
- Expose queue depth as a metric — make backpressure *visible*; never let it be silent data loss.

## Interview Question

*"Your IS webhook ingestion pipeline is processing 500 events/sec normally, but a single misbehaving vendor suddenly bursts to 8,000 events/sec. Walk me through how you'd detect this, what happens to your current architecture, and how you'd redesign the ingestion layer with explicit backpressure. Where does load shedding become acceptable, and where is it never acceptable?"*

## Think About It
In your current webhook pipeline, if a consumer falls behind right now — where does the overflow actually go, and do you have visibility into it before it becomes an incident?
---
