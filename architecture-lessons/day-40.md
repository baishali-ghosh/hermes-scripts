# 📐 Day 40 — Performance Observability: Metrics, Distributed Tracing, and Profiling
**Module 4: Scalability and Performance**

## The Concept

Performance observability is the ability to understand *why* a system is slow, not just *that* it is slow.
It rests on three pillars: **Metrics** (aggregated numbers over time — latency percentiles, throughput, error rates), **Distributed Tracing** (end-to-end request journeys across services, tagged with span timing), and **Profiling** (CPU/memory/I/O hot spots at the code level).
Using only one pillar leads to blind spots — metrics tell you *what* is degraded, traces tell you *where*, and profiles tell you *why* at the code level.
For Staff/Principal engineers the real skill is correlating all three to give a root cause in under 30 minutes, not 3 days.

---

## How It Works

### Pillar 1 — Metrics

```
IS runtime emits metrics (via Prometheus/OTel) every scrape interval:

  connector_call_duration_seconds{connector="snowflake", status="200"} histogram
  connector_call_errors_total{connector="snowflake", error="timeout"}  counter
  connector_pool_active_connections{connector="snowflake"}             gauge

Dashboards (Grafana) → P50 / P95 / P99 latency charts, error rate alerts
```

**Key insight:** Always instrument P99, not just averages. A connector averaging 120 ms but with a P99 of 4 s means 1 in 100 requests is terrible — average hides it.

---

### Pillar 2 — Distributed Tracing

```
Incoming Webhook ──► IS Gateway
       │  trace_id = abc123, span = root (0 ms)
       ▼
  Auth Middleware ── span: auth (12 ms)
       │
       ▼
  Connector Dispatch ── span: dispatch (2 ms)
       │
       ├──► Snowflake Connector ── span: vendor_call (3,800 ms) ◄── PROBLEM HERE
       │
       └──► Activity Logger ── span: log (5 ms)

Total latency = 3,819 ms  |  Root cause visible in ONE trace waterfall
```

Trace propagation uses W3C `traceparent` header across service boundaries. Every async step (message queue, webhook, cron) must re-attach the trace context or you lose the chain.

---

### Pillar 3 — Profiling

Continuous profiling (Pyroscope, Parca, or Go's pprof) samples the call stack every N ms:

```
snowflake_connector.go — 61% CPU
  └─ executeQuery()
       └─ json.Unmarshal()  ◄── hot: deserializing 2 MB payload into map[string]interface{}
                                 Fix: unmarshal into typed struct, 4× faster
```

Profiling is triggered when: P99 is high but trace spans look normal (cost is inside one call, not network wait).

---

## Real Scenario — Shield / IS / UiPath

**Scenario:** The DAP team reports that connector invocations from the UiPath CLI are "randomly slow" — sometimes 200 ms, sometimes 8 s. Metrics show P95 = 350 ms but P99 = 7.8 s. No obvious errors.

**Step 1 — Metrics:** You see `connector_pool_active_connections{connector="salesforce"}` is near the pool max (49/50) during spikes. Suspected: connection saturation.

**Step 2 — Traces:** You pull a P99 trace. The span waterfall shows 7.4 s spent *waiting before* the Salesforce vendor call starts — the span is queued at the pool wait stage, not in network time. This proves it's not Salesforce's latency; it's your connection pool blocking.

**Step 3 — Profile (optional here):** Confirms no CPU hot spot — this is purely I/O blocking on pool acquire.

**Fix:** Increase pool size (Day 39 lesson), add pool-wait timeout to fail fast instead of queuing, add a dedicated metric `connector_pool_wait_duration_seconds` to alert early next time.

**Instrumentation rule for Shield connectors:**
- Every outbound vendor call: trace span + error count + duration histogram
- Every pool acquire: wait duration gauge
- Every webhook ingress: trace context extracted from vendor header (or synthesized if absent)

---

## Interview Question

> "Your SRE team says connector P99 latency spiked from 300 ms to 6 s starting at 14:32. You have metrics, traces, and profiles available. Walk me through exactly how you diagnose the root cause — what do you look at, in what order, and what would each tool tell you that the others can't?"

**What a strong answer covers:**
- Start with metrics to *scope* the blast radius (which connectors? which error types? is it CPU, I/O, or latency?)
- Drill into traces for a P99 sample to *locate* the slow span (network? queue wait? downstream service?)
- Use profiling only if the trace shows cost inside a single process (not waiting on external)
- Explain that metrics alone can't tell you *where*, traces alone can't tell you *why at code level*, profiles alone can't tell you *which requests* are affected

---

## Think About It

Pick one connector in IS — if its P99 spiked 10× right now, what is the first metric you'd look at, the first trace span you'd filter for, and do you have those instruments in place today?
