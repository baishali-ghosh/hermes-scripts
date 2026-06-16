---
# 📐 Day 13 — Distributed Consensus / Raft
**Module 2: Distributed Systems**

## The Concept
Distributed systems need a way for multiple nodes to agree on a single value or leader — even when nodes crash or messages are delayed. Raft is the most widely understood consensus algorithm: a single leader is elected by majority vote, all writes go through the leader, and the leader replicates entries to a quorum (majority) of followers before committing. Raft trades availability for consistency — during a leader election, the cluster temporarily stops making progress. No quorum = no writes. The power of Raft is that it makes consensus explainable: one leader at a time, ever-increasing term numbers, and strict majority acknowledgment.

## How It Works

```
Nodes: N1 (Leader), N2 (Follower), N3 (Follower)    N=3, Quorum=2

NORMAL OPERATION:
  Client ──WRITE──► N1 (Leader)
                       │
               Append to local log
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
        N2 (ack)               N3 (ack)
          └────────────┬────────────┘
                  Quorum reached (2/3)
                       │
                  N1 commits
                  N1 replies OK to client

LEADER FAILURE:
  N1 goes down
  N2 and N3 don't receive heartbeat (within election timeout)
  N2 increments term → sends RequestVote to N3
  N3 votes YES → N2 becomes new leader (term+1)
  Cluster resumes — but during election window, writes are rejected

SPLIT BRAIN PREVENTION:
  Term numbers are monotonically increasing.
  Any node receiving a message from a higher term
  immediately demotes itself to follower.
  You can NEVER have two simultaneous leaders in the same term.
```

**Key numbers to internalize:**
- Quorum = (N/2) + 1
- N=3 → tolerate 1 failure
- N=5 → tolerate 2 failures
- Election timeout: typically 150–300ms; tunable

## Real Scenario — Shield / IS / UiPath

**Webhook Queue Leader Election in IS**

The IS cluster runs multiple nodes. To avoid duplicate webhook processing, only ONE node should be the "active processor" at a time — the leader drains the queue while followers standby.

This is leader election built on Raft (via etcd or a similar primitive):

```
IS Node A (Leader) ──────── processes WebhookReceived events
IS Node B (Follower) ──────── standby, watches etcd lease
IS Node C (Follower) ──────── standby, watches etcd lease

Node A crashes mid-processing:
  etcd lease expires (TTL, e.g. 10s)
  B and C race to acquire the lease
  B wins → becomes new leader → resumes queue processing

In-flight events from Node A:
  Not yet committed to queue (at-least-once delivery handles replay)
  OR already in queue but unacknowledged → reprocessed by B (idempotency needed!)
```

**Where you see Raft in your stack:**
- `etcd` (Kubernetes' backing store) uses Raft — this is why etcd quorum loss = cluster freeze
- `Consul` leader election for service registration
- Any distributed lock your IS infra uses (Redlock, ZooKeeper)

**Why this matters for the Shield team:**
When your IS cluster restarts or a pod is evicted, there's an election window (seconds) where no leader exists. During that window: incoming webhooks queue up, connector config reads may stall on write-path operations. Knowing this tells you to size your election timeout conservatively, monitor for frequent re-elections (sign of instability), and design webhook processing to be idempotent so the new leader can safely reprocess events the old leader partially handled.

## Interview Question

*"Your IS cluster uses leader election for webhook processing. The leader goes down mid-flight — it had dequeued 40 webhook events but only acknowledged 15 to the broker. A new leader is elected. What happens to those 40 events? What guarantees does your system need to handle this correctly, and what happens if you don't have them?"*

**Strong answer covers:**
- At-least-once delivery: the 25 unacknowledged events get redelivered to the new leader
- Idempotency at the consumer (connector handler) is mandatory — without it, those 25 events cause duplicate side effects (duplicate Slack messages, duplicate DB writes, double-charged actions)
- Election timeout sizing: too short → frequent elections under transient network blips; too long → longer unavailability window when a real failure occurs
- Monitoring: track election frequency as a health signal; >1 election/hour = investigate
- The 15 already-acknowledged events: those are safe, the broker will NOT redeliver them

## Think About It

> When the IS leader goes down and the new leader reprocesses events — what is the minimum state the connector handler must be stateless about to guarantee safety?
---
