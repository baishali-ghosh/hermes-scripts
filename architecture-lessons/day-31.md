# 📐 Day 31 — API Versioning
**Module 4: Integration Architecture**

## The Concept
API versioning is the strategy by which you allow a service to evolve its contract without breaking existing consumers. The core rule: **once published, a contract is a promise**. Versioning is how you manage the lifecycle of that promise — when you must break it, how you do so safely, and how long you maintain coexistence. There are three dominant strategies: URI versioning (`/v2/connectors`), header versioning (`Accept: application/vnd.uipath.v2+json`), and query-param versioning (`?api-version=2.0`). Each has different discoverability, cacheability, and client ergonomics tradeoffs. The best strategy is the one your consumers can actually use correctly — and the discipline of **never removing a version until consumers have migrated** is more important than the strategy itself.

## How It Works

```
                        VERSION LIFECYCLE
                        
  PUBLISHED → DEPRECATED → SUNSET → REMOVED
      |             |          |
    Day 0        Add header   Final date
                 warning      (announced
                              3+ months out)

  ┌─────────────────────────────────────────────────────┐
  │               URI Versioning                        │
  │                                                     │
  │  Client ──► /v1/connectors/slack/invoke  ──► v1 handler │
  │  Client ──► /v2/connectors/slack/invoke  ──► v2 handler │
  │                                                     │
  │  Pros: explicit, cacheable, easy to test in browser │
  │  Cons: proliferates routes, tempts to version too early│
  └─────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────┐
  │             Header Versioning                       │
  │                                                     │
  │  GET /connectors/slack/invoke                       │
  │  Accept: application/vnd.uipath.connector.v2+json   │
  │                                                     │
  │  Pros: clean URLs, REST-pure, no route proliferation│
  │  Cons: not cacheable by CDN without Vary header,    │
  │        invisible to humans                          │
  └─────────────────────────────────────────────────────┘

  ADDITIVE CHANGE (non-breaking — no version bump needed):
    + Add optional field to response
    + Add optional request param
    + Add new endpoint
    + Widen enum (add value)

  BREAKING CHANGE (requires new version):
    - Remove or rename field
    - Change field type
    - Make optional field required
    - Narrow enum (remove value)
    - Change error code semantics
```

## Real Scenario — Shield / IS / UiPath

The IS connector invocation API returns a response envelope. In v1:

```json
{ "result": { "data": "...", "status": "success" } }
```

Shield team decides to add structured error details and change `"status"` to `"state"` for consistency with the DAP activity model. That rename **breaks every connector consumer** that pattern-matches on `"status"`.

**Wrong approach:** Edit the existing response shape, ship it, hope consumers notice the changelog.

**Right approach:**
1. Introduce `/v2/connectors/{id}/invoke` with `"state"` field.
2. Keep `/v1/` running, add `Deprecation: true` and `Sunset: 2026-10-01` response headers.
3. Emit a metric on every v1 call — alert when call volume hits zero (or when sunset date approaches with non-zero traffic).
4. Reach out to internal teams hitting v1 and help them migrate.
5. Remove v1 only after sunset date, with confirmed zero traffic.

**Connector SDK versioning** is a second layer: the TypeScript/Python SDK wrapping IS must pin its own version and align with the API version it targets. A major SDK bump = major API bump.

**UiPath CLI pattern:** `withPerfTracking()` and command registration provide a natural extension point — new flags are additive. But if you ever rename a CLI flag, old scripts break. Version discipline applies to CLI contracts too.

## Interview Question

> "Your IS connector invocation API has 200+ internal consumers. You need to change the response envelope shape significantly — it's a breaking change. How do you design and execute the migration? How do you ensure you don't strand any consumer? What signals tell you it's safe to decommission v1?"

*(Expect them to discuss: versioning strategy, deprecation headers, consumer discovery, traffic telemetry, sunset timeline, fallback behavior, and SDK alignment.)*

## Think About It

Which Shield or IS APIs are today's equivalent of a "v1 with no versioning plan" — and what's the real cost if they need to change six months from now?
