---
# 📐 Day 35 — DB Indexing
**Module 4: Scalability and Performance**

## The Concept
An index is a data structure (usually a B-tree or hash) maintained alongside a table that maps column values to row locations — trading write overhead and storage for dramatically faster reads. Without the right indexes, every query does a full table scan regardless of how beefy your hardware is. Over-indexing kills write throughput and bloats storage. The art is choosing indexes that serve your actual read patterns without punishing your write path.

Four key types to understand:
- **B-tree** — ordered, supports range queries and equality (`WHERE ts > X AND ts < Y`)
- **Hash** — O(1) equality only, no ranges
- **Composite** — multi-column, column order in the index matches your query's WHERE/ORDER clauses
- **Partial** — index only a subset of rows (`WHERE status = 'active'`), dramatically smaller footprint

## How It Works

```
Table: connector_activity (tenant_id, connector_id, status, created_at, payload)

Full Table Scan (no index):
  Query: WHERE tenant_id = 'abc' AND created_at > '2026-07-01'
  DB reads EVERY page → 10M rows scanned → 800ms

B-tree Index on (tenant_id, created_at):
  Query hits index → narrows to ~500 rows → follows row pointers → 3ms

Why column order matters in composite index:
  Index: (tenant_id, created_at)
    ✅ WHERE tenant_id = X                  — uses index (leftmost prefix)
    ✅ WHERE tenant_id = X AND created_at > Y — uses full index
    ❌ WHERE created_at > Y                  — skips index (no leftmost prefix)

EXPLAIN output you want to see:
  type: ref or range   ← good
  type: ALL            ← full table scan, red flag
  rows: 500            ← vs 10,000,000 without index
```

**Write cost:** Every INSERT/UPDATE/DELETE must update all covering indexes. 12 indexes on a high-write table = 12x write amplification.

## Real Scenario — Shield / IS / UiPath

The `connector_activity` table in IS stores every execution event. Common queries:

1. **Shield dashboard:** "Show me all failed runs for tenant X in the last 7 days"
   → Needs composite index on `(tenant_id, status, created_at)`

2. **Connector detail page:** "All executions for connector Y in tenant X"
   → Composite index on `(tenant_id, connector_id, created_at DESC)`

3. **Health monitoring:** "All pending executions older than 10 minutes across all tenants"
   → Partial index: `CREATE INDEX ON connector_activity (created_at) WHERE status = 'PENDING'`
   → Skips all COMPLETED rows (99% of the table), tiny index, fast scan

**The trap Baishali has likely seen:** A query that worked fine in staging (100K rows) crawls in production (50M rows) because it relied on a sequential scan. EXPLAIN in prod finally shows `type: ALL`. Adding the right composite index after the fact is a common production fire that an upfront indexing strategy prevents.

**Cardinality matters:** `status` has 3 values (LOW cardinality). An index on `status` alone is nearly useless — the DB might ignore it and scan anyway. Always lead with high-cardinality columns like `tenant_id` or `connector_id`.

## Interview Question

> "Your team reports that the IS connector activity dashboard is loading slowly — P95 at 4 seconds. You run EXPLAIN and see `type: ALL` on a 50M row table. The current index is on `(status)` alone. Walk me through your diagnosis, the indexing strategy you'd implement, and the risks of applying it to a live production table."

*What they're probing: EXPLAIN analysis, composite index design, cardinality reasoning, online vs offline index build risk, migration safety (CONCURRENTLY in Postgres), and read/write tradeoff awareness.*

## Think About It
What queries hit the connector activity or config tables most frequently in IS — and do you know if they have indexes designed for those exact patterns, or did indexes get added reactively after slowdowns appeared in production?
