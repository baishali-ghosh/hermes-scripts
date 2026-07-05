---
# 📐 Day 32 — Rate Limiting
**Module 4: Integration Architecture**

## The Concept
Rate limiting controls how many requests a client can make to a system in a given time window. It protects backend services from overload, enforces fair usage across tenants, and lets you offer tiered SLAs. There are three distinct flavors: **inbound** (protect your service from callers), **outbound** (respect vendor API limits when you're the caller), and **distributed** (coordinate rate limit state across multiple nodes or replicas). Getting all three right is a Staff-level concern — most engineers only think about one.

## How It Works

**Classic algorithms:**

```
Token Bucket                     Leaky Bucket
─────────────────────            ─────────────────────
Tokens refill at fixed rate      Requests drain at fixed rate
Bursts allowed (up to capacity)  Smooths out bursts
  [Bucket: 10 tokens]              [Queue → drain 1/s]
  Each request = 1 token           Overflow = dropped
  No tokens → 429                  No burst absorption

Fixed Window                     Sliding Window Log
─────────────────────            ─────────────────────
Count resets every N seconds     Keep timestamps of each request
Boundary problem: burst          Accurate, memory-heavy
  [0s───50req──60s│0s───50req]    [dequeue old → count remaining]
  100 req in 2s across boundary
```

**Distributed rate limiting (multiple IS nodes):**

```
  Node A ──┐
  Node B ──┼──► Redis (atomic INCR + TTL) ──► allow / 429
  Node C ──┘

Each node checks shared counter — no per-node drift.
Cost: one Redis round-trip per request on hot path.
Optimization: local token bucket (approximate) + Redis sync every N ms.
```

## Real Scenario — Shield / IS / UiPath

IS sits between UiPath automation workflows and vendor APIs (OpenAI, Salesforce, ServiceNow). Two rate limiting concerns collide here:

**1. Outbound — respecting vendor limits:**  
OpenAI limits to 500 req/min per API key. A customer's automation blasts 800 webhook-triggered calls in a burst. Without outbound rate limiting in the IS connector layer, you get HTTP 429s from OpenAI, your retry logic kicks in, and now you have 800 retrying requests with jitter — but jitter only helps if the base rate is already under the limit. The fix: **per-connector, per-tenant rate limiter** in the IS executor. Each connector defines its limit in config; the IS layer queues/throttles before dispatching.

```
Automation Workflow
       │ 800 req burst
       ▼
  IS Connector Layer
  ┌─────────────────────────────┐
  │  OpenAI adapter             │
  │  RateLimiter(500 req/min)   │
  │  └─ Token bucket per tenant │
  └────────┬────────────────────┘
           │ ≤500/min (smoothed)
           ▼
       OpenAI API  ← no 429s
```

**2. Inbound — protecting IS from abusive tenants:**  
In a multi-tenant IS deployment, Tenant A's runaway automation shouldn't degrade Tenant B's response times. Enforce per-tenant quotas at the API gateway or IS ingress. Use Redis-backed sliding window so quota is accurate across all IS replicas.

**3. Coordinating the two:**  
When IS itself gets rate-limited by a vendor AND by its own inbound limiter, the error you surface to the caller matters. Distinguish: `TENANT_QUOTA_EXCEEDED` (caller's fault, don't retry) vs `VENDOR_RATE_LIMITED` (transient, retry with backoff). Collapsing these into a generic 429 confuses downstream error-handling logic.

## Interview Question

*"You're building the outbound rate limiting layer for IS connectors. Vendors have per-API-key limits. Tenants share API keys in some tiers and have dedicated keys in premium tiers. How do you design a rate limiter that handles both models, works across 10 IS replicas, and doesn't become a bottleneck in the hot path? Walk through the data structures, coordination mechanism, and failure behavior if Redis is unreachable."*

## Think About It

If Redis goes down and your distributed rate limiter can no longer enforce limits — do you fail open (allow all traffic, risk vendor throttle) or fail closed (reject all, guarantee downtime)? What does each choice cost you, and can the answer differ per connector tier?
