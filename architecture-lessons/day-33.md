---
# 📐 Day 33 — Schema Contracts
**Module 3: Integration Architecture**

## The Concept
A schema contract is a formal, versioned agreement between a producer and consumer about the shape of data exchanged — fields, types, required vs optional, evolution rules. It is not just documentation; it is a machine-enforceable boundary. Without schema contracts, every payload change is a silent breaking change discovered at runtime. A strong schema contract allows producers and consumers to evolve independently within defined compatibility rules: backward-compatible (new optional fields), forward-compatible (ignoring unknown fields), and full compatibility (both).

## How It Works

```
Producer                   Schema Registry               Consumer
   │                             │                           │
   │  1. Register schema v2      │                           │
   │ ──────────────────────────► │                           │
   │                             │  2. Compatibility check   │
   │                             │    (vs v1) — PASS         │
   │  3. Serialize with v2       │                           │
   │  schema ID embedded ──────► queue/topic ──────────────► │
   │                             │                           │
   │                             │  4. Consumer fetches v2   │
   │                             │ ◄──────────────────────── │
   │                             │  schema → deserialize     │
```

**Key concepts:**
- **Backward compatibility**: Consumer on v1 can read producer's v2 data (new fields are optional)
- **Forward compatibility**: Consumer on v2 can read producer's v1 data (unknown fields ignored)
- **Full compatibility**: Both directions — enables independent deploys
- **Breaking changes**: Removing required fields, renaming fields, changing types — must bump major version

**Schema formats:**
- **JSON Schema / OpenAPI** — HTTP APIs, webhook payloads
- **Avro / Protobuf** — high-throughput event streams (Kafka)
- **GraphQL schema** — query-based APIs
- **AsyncAPI** — event-driven/async API documentation + contracts

## Real Scenario — Shield / IS / UiPath

**The Problem:** Shield connector sends a `WebhookReceived` event to IS. IS activity log consumer, billing consumer, and DAP consumer all decode it. The Shield team adds a new required field `connectorVersion` to the payload — without telling anyone.

Result: billing consumer crashes at 2am. Activity log consumer silently drops events. DAP shows no data for the tenant. Three teams debugging one undisclosed field addition.

**The Fix — Schema Contract on the Webhook Payload:**

```
webhook_payload/
  v1.0.0.avsc   ← original schema, registered in Confluent Schema Registry
  v1.1.0.avsc   ← added optional field "connectorVersion" (backward compatible ✅)
  v2.0.0.avsc   ← renamed "tenantId" → "orgId" (BREAKING — requires migration plan ❌)
```

**Enforcement layers:**
1. **At publish time:** Producer SDK validates payload against registered schema before emitting
2. **At consume time:** Consumer SDK fetches schema by ID embedded in message header, fails early on schema mismatch
3. **At CI time:** Schema compatibility check runs in PR pipeline — breaking change = build fails

**For IS connector webhook ingestion specifically:**
- Each connector vendor defines an inbound webhook schema (OpenAPI spec)
- IS adapter layer validates incoming payloads against it — invalid shape = 400 immediately, not a silent bad record downstream
- Schema Registry tracks connector payload versions so IS can deserialize events from old connector deployments still running v1 alongside new v2 deployments

**For IS outbound connector calls:**
- Contract tests (Pact) verify that IS's expectation of the vendor API response shape matches what the vendor actually returns
- Run in CI — catches vendor API drift before it hits production

## Interview Question

*"You're building a multi-tenant connector platform where 50 connectors each emit events to a shared Kafka topic. Each connector has a slightly different payload shape. How do you design the schema strategy so new connectors can be added, existing connector payloads can evolve, and no single connector's schema change can silently break consumers? What are the tradeoffs between a shared schema vs per-connector schemas vs a schema envelope pattern?"*

## Think About It
Which connector in Shield's current pipeline most likely has an undocumented, unversioned implicit schema — and what would it take to make it explicit and machine-enforceable?
---
