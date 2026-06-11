---
# 📐 Day 8 — PACELC

**Module 2: Distributed Systems**

## The Concept

PACELC extends CAP beyond the "partition" edge case to cover normal operations too. The model states: **if there is a Partition (P), choose between Availability (A) or Consistency (C); Else (E) — when the system is running normally — choose between Latency (L) or Consistency (C)**. CAP tells you what breaks under failure; PACELC tells you what you sacrifice every single day in normal operation. Most production systems are EL/AP — they trade consistency for low latency even when there's no failure. Understanding this helps you defend design choices to stakeholders who ask "why don't you just read from the source of truth every time?"

## How It Works

```
          PARTITION OCCURS?
               /     \
             YES       NO (Else)
             /           \
    Choose A or C     Choose L or C
        /   \              /    \
      AP     CP          EL      EC
   (stay    (block    (read     (read
  available  on       cache,   source-
  + stale)  split)   fast)     of-truth,
                              slower)
```

**Common real-world picks:**

| System        | Partition choice | Normal ops choice |
|---------------|-----------------|-------------------|
| Cassandra     | AP               | EL                |
| ZooKeeper     | CP               | EC                |
| DynamoDB      | AP               | EL (default)      |
| etcd          | CP               | EC                |
| Redis (async) | AP               | EL                |

The EL vs EC trade is often *more impactful* than PA vs PC because partitions are rare; normal ops happen millions of times a day.

## Real Scenario — Shield / IS / UiPath

**Connector config reads in the IS hot path.**

When IS runtime executes a connector step (say, a Slack connector sending a message), it needs the connector's config: base URL, auth type, rate limit settings, etc. Two options:

```
Option A — EC (Every read hits authoritative DB)
  IS Runtime → PostgreSQL config store → returns config
  Latency: +40–80ms per connector step
  Consistency: Always fresh

Option B — EL (Reads from local in-memory cache, refreshed every 60s)
  IS Runtime → local cache hit → returns config
  Latency: ~0ms overhead
  Consistency: Up to 60s stale
```

IS chose **EL/AP** — config reads go to a local cache. Normal connector config changes (updating an auth token, changing rate limits) take up to 60 seconds to propagate. This is explicitly accepted. Under a partition (IS node can't reach config store), it stays available using cached config — AP.

**Where EC matters:** Credential *revocation*. If a customer revokes a connector's OAuth token, IS should not use it for 60 more seconds. That specific read bypasses cache — it's EC because the cost of inconsistency (security breach, API call with revoked creds) outweighs the latency hit.

**Design rule:** Default EL for non-security config. Opt into EC selectively for security-sensitive reads.

## Interview Question

> "A PM asks why IS doesn't read connector config directly from the authoritative database on every request — it would guarantee freshness. How do you explain the tradeoff? And where would you *not* use a cache, and why?"

*(Expect: articulation of PACELC, quantification of latency cost at scale, identification of which data classes need EC, and how to implement selective cache bypass for revocation/security events.)*

## Think About It

Which specific fields in the IS connector config model are truly EC-required, and which are safe as EL — and what's the cost of getting that boundary wrong in each direction?
