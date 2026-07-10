---
# 📐 Day 37 — Load Balancing
**Module 4: Scalability and Performance**

## The Concept
Load balancing distributes incoming requests across a pool of backend instances to prevent any single node from becoming a bottleneck. It operates at different OSI layers (L4 = TCP/UDP, L7 = HTTP/application), and the algorithm used determines fairness, affinity, and efficiency. Beyond traffic distribution, a load balancer is also a health gate — it removes unhealthy instances from rotation automatically. The difference between a good and great load balancer design comes down to session affinity requirements, health-check semantics, and how you handle slow/draining nodes.

## How It Works

```
         Client Requests
               │
        ┌──────▼───────┐
        │  Load Balancer │   ← L4 (TCP) or L7 (HTTP)
        └──────┬───────┘
     ┌─────────┼─────────┐
     ▼         ▼         ▼
 [IS Node 1] [IS Node 2] [IS Node 3]
  healthy     healthy    draining

Algorithms:
  Round Robin       → requests 1,2,3,4... → node1,2,3,1...
  Least Connections → route to node with fewest open connections
  IP Hash           → hash(client_ip) → always same backend (sticky sessions)
  Weighted RR       → assign capacity weights (node3 = 2x CPU → 2x traffic)
  Random w/ 2 picks → pick 2 random nodes, send to less loaded (Netflix)

Health check:
  GET /health → 200 OK within 500ms? → in rotation
                timeout / 5xx?       → removed from pool (passive drain)
```

**Key behaviors:**
- **Connection draining / graceful shutdown**: When a node is removed, the LB stops sending new requests but lets in-flight ones finish (drain window: 30–60s).
- **Slow-start mode**: New instance eases into full traffic (ramp from 0% → 100% over 30s) to avoid cold-cache thundering herd.
- **L7 vs L4**: L7 can route based on URL path, headers, tenant ID. L4 is faster but blind to application content.

## Real Scenario — Shield / IS / UiPath

**Problem:** IS runs 6 nodes behind an L7 load balancer. Each node maintains an in-memory connector client pool. A new deployment is rolled out — 2 nodes are updated, 4 are old.

**Without proper LB config:**
- Requests to updated nodes succeed; requests to old nodes fail with schema mismatch.
- No drain window → in-flight webhook deliveries to old nodes cut off mid-response → connector reports delivery failure.

**Correct design:**
```
Rolling deploy:
  1. LB: mark node-1 as "draining" → stop new requests
  2. Wait drain window (30s) → in-flight webhooks complete
  3. Deploy new version to node-1
  4. LB health check passes → node-1 back in rotation
  5. Repeat for node-2...node-6

For webhook processing specifically:
  - Use L7 LB with connector_id header hash → consistent routing
    (connector state / rate-limit counters live on same node)
  - OR: stateless connectors with shared Redis → any node can handle any connector
    (preferred — L7 round-robin works cleanly)
```

**DAP integration:** When DAP triggers a connector run, the IS gateway receives the HTTP call. L7 LB routes based on `/v1/connectors/{connector_id}/execute` path prefix. Tenant-level routing via `X-Tenant-ID` header allows LB to pin tenants to specific node pools during A/B rollouts — critical for large enterprise tenants who need dedicated capacity.

**Shield connector health:** If a specific connector's upstream API (e.g., Snowflake) is degraded, individual IS nodes handling those requests will show elevated response times. Least-connections algorithm naturally routes *away* from that node (it has more open, slow connections) — giving you implicit isolation without circuit breakers.

## Interview Question

> "IS is deployed across 6 nodes with an L7 load balancer. A new version introduces a breaking schema change in connector response mapping. You cannot take downtime. Walk me through a zero-downtime deployment strategy — specifically, what LB controls do you use, what could go wrong, and how do you roll back if the new version is silently corrupting data?"

*(Think about: drain windows, canary routing by tenant or connector type, passive health check lag vs active probe, rollback triggering on error-rate SLO breach, and what happens to events in-flight during rollback.)*

## Think About It

If your connectors are stateful (in-memory rate-limit counters, cached auth tokens), what does that force you to choose between: L4 sticky sessions, L7 header-hash affinity, or stateless architecture with shared cache — and which has the best failure properties?

---
