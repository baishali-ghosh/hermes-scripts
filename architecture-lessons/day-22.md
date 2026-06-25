---
# 📐 Day 22 — CQRS (Command Query Responsibility Segregation)
**Module 3: Architectural Patterns**

## The Concept
CQRS separates the write side (Commands — mutations with business logic and validation) from the read side (Queries — optimized projections, potentially denormalized). They can use the same database or different ones — the key insight is that the **model** is separate. Commands enforce invariants and emit events; the read model is purpose-built for how consumers query data. This separation lets each side scale, evolve, and be optimized independently without polluting the other.

## How It Works

```
                     WRITE SIDE                     READ SIDE
                  ┌─────────────┐               ┌─────────────────┐
Client ──CMD───▶  │  Command    │               │  Query Handler  │ ◀─── API Read Request
                  │  Handler    │               │                 │
                  │  (validation│               │  (optimized for │
                  │   business  │               │  specific views)│
                  │   logic)    │               └────────┬────────┘
                  └──────┬──────┘                        │
                         │ write                         │ read
                         ▼                               ▼
                  ┌─────────────┐               ┌─────────────────┐
                  │  Write DB   │───event/sync──▶│   Read DB /    │
                  │ (normalized,│               │   Read Model   │
                  │  ACID)      │               │ (denormalized, │
                  └─────────────┘               │  search-ready) │
                                                └─────────────────┘
```

**Sync mechanisms:**
- **Event-driven**: Write side emits domain events → projector updates read model
- **CDC (Change Data Capture)**: Debezium tails the write DB → feeds read store
- **Synchronous dual-write**: Risky (distributed write problem — avoid without careful design)

The read model can be Elasticsearch, Redis, a flat denormalized SQL table, or a materialized view — whatever makes query fast. The write model stays normalized and enforces business rules.

## Real Scenario — Shield / IS / UiPath

**Connector Discovery vs Connector Config:**

Shield's IS layer has two very different access patterns on connector data:

- **Write path** (`POST /connectors`, `PATCH /connectors/{id}/auth`): validation-heavy, version tracking, audit events, credential rotation logic. Normalized schema, low frequency.
- **Read path** (`GET /connectors?search=slack&category=messaging&capability=webhook`): full-text search, faceted filtering, sort by popularity, returns summary projections. High frequency. Called by DAP, by the Studio connector picker, by activity catalog.

If both paths share the same PostgreSQL connector table, you're forced to add search indexes that hurt write performance, or denormalize columns that complicate write validation. CQRS solves this cleanly:

```
                     WRITE SIDE                           READ SIDE
  ┌─────────────────────────────┐           ┌──────────────────────────────┐
  │ ConnectorCommandHandler     │           │ ConnectorQueryHandler        │
  │  - validate schema          │           │  - full-text search          │
  │  - enforce auth policy      │           │  - filter by capability      │
  │  - emit ConnectorUpdated    │           │  - sort, paginate, project   │
  └───────────┬─────────────────┘           └──────────────┬───────────────┘
              │ write                                       │ read
              ▼                                             ▼
  ┌─────────────────────┐    CDC / events    ┌─────────────────────────────┐
  │ PostgreSQL           │ ─────────────────▶│ Elasticsearch / Redis        │
  │ (connectors table,   │                   │ (connector_search_index,     │
  │  normalized, ACID)   │                   │  denormalized, fast lookup)  │
  └─────────────────────┘                   └─────────────────────────────┘
```

ConnectorUpdated event triggers a **projector** that rebuilds the Elasticsearch doc for that connector. DAP's connector picker queries Elasticsearch — zero impact on the write path. A validator that uses schema V2 fields? Write model handles it. The read model only sees what projectors choose to expose.

Result: write path stays clean, read path is as fast as you need it, and neither compromises the other.

## Interview Question

> "The connector search feature is slow because it queries the same database as config writes. You're tasked with fixing it without a full rewrite. How do you design a CQRS split? What drives read model updates, what consistency guarantees can you offer users, and how do you handle a projector falling behind under load?"

**What a strong answer covers:**
- Identify the sync mechanism (CDC vs events vs polling) and its tradeoffs
- What read model technology fits the query shape (Elasticsearch for full-text, Redis for hot lookups)
- Lag: read model is eventually consistent — by how much? How do you surface staleness?
- Projector backpressure: if events queue up, read model drifts — how do you monitor lag and catch up?
- Schema evolution: if write model adds a field, how does it propagate to the read model without a full rebuild?

## Think About It
> Where in IS or Shield today is a single data model being tortured to serve both heavy write logic and complex read queries — and what would the read model look like if you freed it from write-side constraints?
---
