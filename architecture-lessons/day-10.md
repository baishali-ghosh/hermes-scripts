---
# 📐 Day 10 — Bulkhead Pattern
**Module 2: Distributed Systems**

## The Concept
The Bulkhead pattern is named after ship compartments that prevent a single breach from sinking the whole vessel. In software, it means **partitioning resources** (thread pools, connection pools, semaphores) so that a failure or slowdown in one component cannot exhaust the resources required by others. Without bulkheads, one misbehaving dependency can cascade into a full system outage. The pattern trades resource efficiency (dedicated pools sit idle) for fault isolation (failures stay contained).

## How It Works

Without bulkheads — shared thread pool:
```
IS Runtime
└── Shared Thread Pool (50 threads)
      ├── Snowflake connector → 50 slow queries → POOL EXHAUSTED
      ├── Slack connector     → starved, requests queued
      ├── OpenAI connector    → starved, requests queued
      └── GitHub connector    → starved, requests queued
                                        ↓
                             All connectors fail together
```

With bulkheads — isolated thread pools:
```
IS Runtime
├── Snowflake Pool (10 threads) → 10 slow queries → Snowflake ONLY degrades
├── Slack Pool    (10 threads) → still serving requests ✅
├── OpenAI Pool   (10 threads) → still serving requests ✅
└── GitHub Pool   (10 threads) → still serving requests ✅
```

Key parameters to tune:
- **Pool size** — max concurrent calls per connector
- **Queue depth** — how many requests wait before rejecting
- **Timeout** — how long a thread can be held before it's released
- **Rejection policy** — fail-fast with error vs queue with timeout

## Real Scenario — Shield / IS / UiPath

**The problem Baishali's team faces:**  
The IS layer routes requests to ~50 connectors. All share the same underlying HTTP client thread pool. Snowflake is running complex queries that take 8–12 seconds each. During a Snowflake outage, 50 concurrent requests all block for 12 seconds — every thread is occupied. Now a Slack message send (which takes 80ms normally) also queues. The entire IS layer grinds to a halt because one slow connector ate the shared pool.

**The fix:**  
Each connector gets its own bounded `ExecutorService` / Resilience4j `Bulkhead`. When the Snowflake pool fills:
- New Snowflake requests → `BulkheadFullException` → fail-fast back to caller
- Slack, OpenAI, GitHub → completely unaffected, their pools are untouched

```
ConnectorExecutor
├── SnowflakeExecutor    { maxConcurrent: 10, maxWait: 500ms }
├── SlackExecutor        { maxConcurrent: 20, maxWait: 200ms }
├── OpenAIExecutor       { maxConcurrent: 15, maxWait: 300ms }
└── DefaultExecutor      { maxConcurrent: 5,  maxWait: 200ms }  ← new/unknown connectors
```

In Shield specifically: DAP telemetry pipelines and connector activity logging should be in separate bulkheads from the live connector execution path. A spike in telemetry writes must never throttle active automation runs.

## Interview Question

> "You notice that when one external API becomes slow, all connector calls in IS degrade — even for unrelated connectors. Walk me through how you'd diagnose this, design a fix using the bulkhead pattern, and decide on pool sizes for 50 connectors. What operational metrics would you expose to know if your bulkheads are correctly tuned?"

**What they're looking for:**  
Diagnosis (shared resource identification → thread dump / metrics), design (per-connector isolation strategy), sizing rationale (traffic profiling, SLA requirements, not just "equal split"), and observability (pool utilization, rejection rate, wait time per connector).

## Think About It
Which current IS components share a resource that, if exhausted, would silently degrade the entire system — and what's the smallest change that would isolate them?
---
