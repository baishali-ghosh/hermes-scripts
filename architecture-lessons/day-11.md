# 📐 Day 11 — Circuit Breaker
**Module 2: Distributed Systems**

## The Concept
The circuit breaker is a stability pattern that prevents cascading failures in distributed systems by detecting repeated failures and stopping further calls to the failing service. It operates as a state machine: **CLOSED** (normal operation), **OPEN** (failures exceed threshold — reject all calls immediately), and **HALF-OPEN** (probe to check if the downstream has recovered). When OPEN, the caller gets a fast error instead of waiting for a timeout — protecting threads, connections, and memory from being held hostage by a broken dependency. The circuit breaker is different from retry: retry is optimistic ("try again"), circuit breaker is defensive ("stop trying until recovery is likely").

## How It Works

```
Normal:                  Failure threshold hit:       Probe after timeout:
                         (e.g., 10 failures/30s)      (1 test request)
  ┌─────────┐               ┌─────────┐               ┌──────────┐
  │ CLOSED  │──failures──►  │  OPEN   │──wait 60s──►  │HALF-OPEN │
  │ (pass)  │               │ (block) │               │ (1 probe)│
  └─────────┘               └─────────┘               └──────────┘
       ▲                                                    │    │
       └──────────── success ─────────────────────────────┘    │
                                                  failure ──────┘
                                                  (→ back to OPEN)

Caller sees:
  CLOSED: real response (or real error)
  OPEN:   immediate CircuitOpenException (no network call made)
  HALF-OPEN: real call; success→CLOSED, failure→OPEN
```

**Key knobs:**
- `failureThreshold` — how many failures before OPEN (absolute count or % of recent calls)
- `windowSize` — rolling time/count window evaluated for failures
- `waitDurationInOpenState` — how long to stay OPEN before probing
- `permittedCallsInHalfOpen` — how many probes allowed before deciding

Libraries: **Resilience4j** (JVM), **Polly** (.NET), **opossum** (Node.js).

## Real Scenario — Shield / IS / UiPath

**Problem:** OpenAI connector in IS returns HTTP 503 ten times in 30 seconds. No circuit breaker.

- IS keeps making HTTP calls → each waits 30s for timeout
- 10 concurrent connector invocations × 30s = 300 thread-seconds held
- Thread pool exhausts → other connectors (Slack, Salesforce, GitHub) queue up → the IS host is now effectively down **because OpenAI is down**

**With Circuit Breaker:**

```
t=0s   → OpenAI 503 #1…#10 in 30s
t=30s  → Circuit OPENS for OpenAI connector
t=30s–90s → All OpenAI connector calls return CircuitOpenException instantly
           (0ms, 0 threads held)
t=90s  → HALF-OPEN: one probe request
t=90s  → OpenAI 200 → circuit CLOSES
t=90s+ → Normal traffic resumes
```

**Where it lives in your stack:**
- Each connector client in IS wraps its HTTP calls with a per-connector circuit breaker
- Circuit state is per-connector, per-target-host — Snowflake tripping doesn't affect Slack
- Combine with **bulkhead** (Day 10): bulkhead limits blast radius of thread exhaustion; circuit breaker limits blast radius in time

**Shield angle:** If a connector's upstream (e.g., SAP) trips, DAP workflows waiting on that connector should receive a `ConnectorUnavailableException` with a retryable hint and estimated recovery time — not a 30-second hang that blocks the RPA bot.

## Interview Question

> "How do you tune circuit breaker thresholds for a connector with high traffic variance — busy during business hours, near-zero at night? What failure modes do you worry about with a poorly tuned circuit breaker?"

**What they're looking for:**
- Time-based rolling windows vs count-based windows (count-based is dangerous at low traffic — 2 failures / 2 requests = 100% failure rate → trips at night even if those 2 were expected transients)
- Minimum request threshold before the breaker can trip (don't open on 1 failure)
- Different thresholds for different error types (5xx vs timeout vs connection refused)
- The "nuisance trip" failure mode: circuit opens during a brief blip, now you have 60s of rejected calls even though the vendor recovered in 5s — discuss waitDuration tuning
- Observability: circuit state changes should emit metrics and alerts; state transitions are operational events

## Think About It
Which connectors in IS are highest-risk for cascading failure if they degrade — and do they currently have any isolation boundary at all?
