---
# 📐 Day 34 — Caching Strategies (L1 / L2 / CDN)
**Module 4: Scalability and Performance**

## The Concept
Caching stores computed or fetched data closer to the consumer so repeated requests don't hit slow upstream systems. Caches exist at multiple levels — in-process (L1), distributed (L2), and edge/CDN (L3) — each with different latency, consistency, and capacity tradeoffs. The fundamental tension is **freshness vs speed**: the closer the cache is to the caller, the faster the hit, but the harder it is to invalidate consistently. Choosing the wrong level (or skipping caching entirely) causes avoidable latency spikes and origin overload at scale.

## How It Works

```
                      REQUEST FLOW
 Client / IS Runtime
        │
        ▼
  ┌────────────┐   HIT  ──── return immediately
  │  L1 Cache  │  (in-process, e.g. Node.js Map, Caffeine)
  │  < 1ms     │
  └────────────┘
        │ MISS
        ▼
  ┌────────────┐   HIT  ──── return, populate L1
  │  L2 Cache  │  (distributed, e.g. Redis / Memcached)
  │  ~1-5ms    │
  └────────────┘
        │ MISS
        ▼
  ┌────────────┐   HIT  ──── return, populate L2 + L1
  │  CDN/Edge  │  (static/semi-static assets, API responses)
  │  ~5-50ms   │
  └────────────┘
        │ MISS
        ▼
  ┌────────────┐
  │  Origin DB │  (always slow, always expensive)
  │  ~50-500ms │
  └────────────┘

Key Patterns:
  Cache-Aside (Lazy):   App checks cache → miss → load from DB → write to cache
  Write-Through:        App writes to cache AND DB synchronously
  Write-Behind:         App writes to cache, async flush to DB (risk: data loss on crash)
  Read-Through:         Cache handles DB reads transparently (cache is the interface)

Eviction Policies:
  LRU  — evict least recently used
  LFU  — evict least frequently used
  TTL  — evict after a time-to-live window
```

## Real Scenario — Shield / IS / UiPath

**Connector Config Reads in IS Hot Path**

When an IS workflow fires and needs the config for the Salesforce connector (auth endpoint, base URL, rate limit settings), that config is read on *every* invocation. If it's fetched from the authoritative DB each time:
- At 5,000 req/min across workflows → 5,000 DB reads/min for config that changes maybe once a week.

**The caching stack:**

| Level | What's cached | TTL | Invalidation trigger |
|---|---|---|---|
| **L1** (in-process, per IS pod) | Parsed connector config struct | 60s | Pod restart or local TTL expiry |
| **L2** (Redis cluster, shared) | Raw connector config JSON | 5 min | `config.updated` event → Redis DEL |
| **CDN/Edge** | DAP connector marketplace metadata | 1 hour | Webhook from publish pipeline |

**Critical detail — cache stampede prevention:**
If the L2 TTL expires and 300 concurrent requests all miss simultaneously → 300 DB reads in one second. Fix: **probabilistic early recompute** (refresh cache slightly before TTL) or **single-flight** (lock on the first miss, serve the rest from the in-flight response).

**Auth token caching** is a separate concern: tokens must be invalidated *immediately* on revocation — TTL-based caching of auth tokens is a security bug. Use event-driven invalidation: `token.revoked` → flush from L1 + L2 atomically.

## Interview Question

*"Your IS connector platform serves 100k connector invocations per hour. Each invocation reads connector config and auth settings. The config DB becomes a bottleneck. Design a multi-level caching strategy: what do you cache at each level, how do you handle invalidation, what consistency model do you accept, and how do you prevent cache stampede and security issues with auth data?"*

## Think About It

Which pieces of IS/Shield today are almost certainly NOT cached but should be — and which ones *look* safe to cache but are actually dangerous to?

---
*Day 34 of 50 — Architecture Curriculum for Staff/Principal Engineer readiness*
