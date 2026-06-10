---
# 📐 Day 7 — Consistency Models
**Module 2: Distributed Systems**

## The Concept
In a distributed system, multiple replicas hold copies of data. Consistency models define the rules for what a reader is guaranteed to see after a write. The spectrum runs from strongest to weakest: **Linearizability → Sequential Consistency → Causal Consistency → Eventual Consistency**. Stronger models feel like a single system but cost you latency and availability. Weaker models give you speed but can serve stale data. Choosing the right model per data type — not one-size-fits-all — is what separates good distributed system design from fragile one.

## How It Works

```
STRONGEST                                              WEAKEST
─────────────────────────────────────────────────────────────▶
  Linearizability    Sequential     Causal      Eventual
  (real-time order)  (global order) (cause→effect) (converge eventually)
  
  - Reads reflect    - All nodes    - Causally   - All replicas
    latest write       agree on       related      eventually agree
    immediately        operation      writes are   but any given
  - Highest latency   order          seen in       read may be stale
                    - Slower         order
                      than causal
```

**How each works under the hood:**

| Model            | How it achieves it                                       | Latency     |
|------------------|----------------------------------------------------------|-------------|
| Linearizability  | Single-leader or consensus (Raft/Paxos) on every op     | Highest     |
| Sequential       | Global total ordering, not necessarily wall-clock       | High        |
| Causal           | Track causality (vector clocks), enforce causal order   | Medium      |
| Eventual         | Anti-entropy / gossip; no ordering guarantees           | Lowest      |

## Real Scenario — Shield / IS / UiPath

**Two distinct data types, two different consistency needs:**

**1. Connector execution logs (IS activity history)**  
These are append-only, immutable event records. If you read from replica 2 right after writing to replica 1 and see 3-second-old data, no harm done. The dashboard shows "last 24h of runs" — a slightly stale page is fine. → **Eventual consistency** is the right call. Use it. Get the throughput and low latency.

**2. Auth token revocation (security-critical)**  
A customer revokes a compromised OAuth token. IS has 3 replicas behind a load balancer. If replica 2 still serves the old valid-token state 500ms later, that window is a security hole. The token must be invalid on ALL nodes before the revocation API returns 200. → **Linearizable consistency** required. Pay the latency cost. This is a security invariant, not a performance question.

**The mistake teams make:**  
Applying strong consistency everywhere because "correctness matters." That turns your entire system into a CP bottleneck. The right design is: *know which data has which consistency requirement and model them separately*.

```
IS Architecture — Consistency tiering

  [Token Revocation Store]       [Activity Log Store]
  ┌────────────────────┐         ┌───────────────────┐
  │  Leader (Raft)     │         │  Node A           │
  │  Replica 1         │         │  Node B (async)   │
  │  Replica 2 (sync)  │         │  Node C (async)   │
  └────────────────────┘         └───────────────────┘
  Linearizable — all reads        Eventual — fast writes,
  go through leader or            reads may lag by seconds
  quorum-confirmed reads           → fine for dashboards
```

## Interview Question

> "Your system stores connector execution history across 3 replicas. A user queries from replica 2 right after writing to replica 1. Sometimes they see missing results. What consistency model does the current system implement? What model should it implement, and what's the cost of upgrading it?"

*What a Staff/Principal answer includes:*  
- Identifying current behavior as eventual consistency  
- Questioning whether this is actually a problem or just perceived (are these audit/billing reads, or just dashboard?)  
- Explaining options: read-your-writes consistency (user always hits same replica), monotonic reads, or full linearizability  
- Calling out the cost: stronger consistency = higher write latency, lower throughput, potential availability loss on node failure  
- Proposing a tiered approach: not all data needs the same model

## Think About It
> For each of the top 5 data types in Shield/IS (auth tokens, connector configs, webhook events, activity logs, feature flags) — which consistency model does your system *actually* provide today, and which one should it provide?
---
