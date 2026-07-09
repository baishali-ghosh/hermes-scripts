---
# 📐 Day 36 — Sharding
**Module 4: Scalability and Performance**

## The Concept
Sharding is horizontal partitioning of a dataset across multiple database nodes, where each node (shard) owns a disjoint subset of the data. No single node holds the full dataset — queries are routed to the correct shard based on a shard key. Sharding solves the problem of write throughput and storage limits that vertical scaling and read replicas can't fix. The shard key choice is the single most consequential decision: it determines whether load is balanced or whether one shard becomes a hot spot.

## How It Works

```
Client Request
     │
     ▼
 Shard Router (hash/range-based routing)
 ┌──────────────────────────────────┐
 │  shardKey = tenant_id % 4        │
 └──────────────────────────────────┘
     │           │           │           │
     ▼           ▼           ▼           ▼
 Shard-0     Shard-1     Shard-2     Shard-3
 tenant 0,4  tenant 1,5  tenant 2,6  tenant 3,7
 [DB Node]   [DB Node]   [DB Node]   [DB Node]

Range sharding:        Hash sharding:
tenant_id 0–999  →  S0    hash(tenant_id) % N → Shard
tenant_id 1000–1999 → S1   Uniform distribution, no range scans
tenant_id 2000+ → S2
```

**Key mechanics:**
- **Shard Router / Proxy** — sits between app and DB; resolves which shard owns the key. (e.g., Vitess for MySQL, mongos for MongoDB)
- **Hash sharding** — uniform distribution, but range queries hit all shards (scatter-gather).
- **Range sharding** — efficient range scans, but risky for monotonically increasing keys (all new writes go to the last shard → hot spot).
- **Directory-based sharding** — a lookup table maps keys to shards; flexible but lookup table is a bottleneck and single point of failure.
- **Resharding** — adding shards requires moving data; usually done via consistent hashing to minimize data movement.

## Real Scenario — Shield / IS / UiPath

**Problem:** IS stores connector execution logs — activity records for every connector invocation across all tenants. At 10,000 executions/minute across a large enterprise fleet, a single Postgres instance buckles on writes, and the `execution_logs` table has 2 billion rows.

**Shard key choice matters here:**

- ❌ `execution_id` (UUID) — hash sharding on this is balanced, but **cross-tenant queries** ("show all executions for tenant X") hit every shard. Scatter-gather for every dashboard load.
- ✅ `tenant_id` — all data for a tenant lands on one shard. Tenant-scoped queries are fast (single shard). Works cleanly because IS is multi-tenant and tenant isolation is already a requirement.
- ⚠️ Watch out: if one tenant is 10× larger (UiPath's own internal tenant), they become a hot shard. Mitigation: sub-shard large tenants by `connector_id` or use virtual shards (e.g., tenant_id gets 4 hash buckets instead of 1).

**Practical design:**

```
Connector Execution Event
         │
         ▼
  IS Processing Layer
         │
         ▼
  Shard Router: shard = fnv32(tenant_id) % NUM_SHARDS
         │
    ┌────┴────┬────────┬────────┐
    ▼         ▼        ▼        ▼
  PG-S0    PG-S1    PG-S2    PG-S3
  (tenants (tenants  ...      ...
   A–G)    H–P)
```

Cross-shard queries (e.g., global audit reports) are handled by an async aggregation pipeline (Kafka → Spark → data warehouse) — not by querying shards directly.

## Interview Question

*"Your IS connector execution log table has hit 2 billion rows and write throughput is maxing out a single Postgres node. You're considering sharding. Walk me through how you choose the shard key, what happens to existing data, how cross-shard queries work, and how you plan for resharding 18 months from now when you double the number of tenants."*

(Expected: address hot spots, scatter-gather cost, migration strategy, consistent hashing, and the tradeoff between query patterns and distribution uniformity.)

## Think About It
If Shield's connector registry (which connectors exist, their config, their enabled state) needed to be sharded — would you shard it at all, or would a different scaling strategy serve you better? What's the right question to ask first?
---
