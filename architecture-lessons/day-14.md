---
# 📐 Day 14 — Logical Clocks and Vector Clocks
**Module 2: Distributed Systems**

## The Concept
Wall clocks across distributed machines are unreliable — NTP drift, leap seconds, and clock skew mean two events timestamped at "the same millisecond" on different nodes have no meaningful ordering guarantee. Lamport timestamps solve this by using a monotonically increasing counter: each event increments the counter, and when a message is received, the receiver sets its counter to `max(local, received) + 1`. This gives you causal ordering but can't distinguish *concurrent* events from *causally related* ones. Vector clocks extend this by maintaining one counter *per node*, enabling you to definitively detect whether event A caused B, B caused A, or they were fully concurrent — which is critical when you need to detect and resolve conflicting writes.

## How It Works

**Lamport Clock (causality tracking):**
```
Node A: [1]  ──send──>  Node B receives, sets clock = max(1,0)+1 = [2]
Node A: [2]             Node B: [3]  (next event)
```

**Vector Clock (conflict detection):**
```
         Node A      Node B      Node C
Start:   [0,0,0]    [0,0,0]    [0,0,0]
A writes: [1,0,0]
A→B msg: B receives → [1,1,0]
C writes: [0,0,1]   ← CONCURRENT with A's write (no causal link)
B writes: [1,2,0]   ← CAUSED BY A (A's counter present in B's clock)
```

**Detecting conflicts:**
- If `clock_A ≤ clock_B` component-wise → A happened-before B (no conflict)
- If neither dominates the other → concurrent writes → **conflict** → need merge strategy

## Real Scenario — Shield / IS / UiPath

Two IS nodes receive a config update for the Salesforce connector at "the same time" (wall clock: same millisecond):
- **Node 1** updates `auth.clientSecret` → its vector clock: `[1,0]`
- **Node 2** updates `rateLimitRpm: 500→600` → its vector clock: `[0,1]`

Wall clock ordering tells you nothing useful here. But vector clocks reveal these are **concurrent writes** — neither node knew about the other's change. Your system now has a clear signal: *this is a conflict that needs resolution*, not just an ordering question.

Options for resolution:
1. **Last-write-wins** (LWW) — simplest, but dangerous for connector secrets
2. **Merge** — apply both field-level changes (works if fields are independent)
3. **Escalate** — surface conflict to admin for manual resolution

Without logical clocks, Node 2's write silently overwrites Node 1's `clientSecret` change — customers start getting auth failures with no audit trail of what happened.

This is also why IS connector execution logs need **logical sequence IDs** rather than wall-clock timestamps when ordering across nodes. A log entry with `seqId: 4201` from Node A and `seqId: 4202` from Node B tells you causal order. Two entries at `2026-06-18T10:32:00.001Z` tell you nothing.

```
IS Node 1               IS Node 2
    │                       │
    ├─ seqId=100 (write)    │
    │─────────────────────>─│  (sync)
    │                       ├─ seqId=101 (read after sync)
    │                       │   ✅ Causal order preserved
    │
    │                   IS Node 3 (partitioned)
    ├─ seqId=100 (write)    │
    │   X ─────────────────>│  (partition — never arrives)
    │                       ├─ seqId=100' (concurrent write!)
    │                       │   ⚠️ Vector clock detects CONFLICT
```

## Interview Question

*"Two IS nodes simultaneously update connector config — one changes the auth secret, the other changes the rate limit. Your config store uses last-write-wins based on wall-clock timestamps. A customer's connector starts failing silently. Walk me through what happened, why wall-clock ordering failed you, and how you'd redesign the conflict detection and resolution strategy. What tradeoffs does your redesign introduce?"*

## Think About It

In the IS connector config store today — do you know what happens when two engineers update the same connector's config simultaneously? Is there a conflict detection mechanism, or does one write silently lose?
---
