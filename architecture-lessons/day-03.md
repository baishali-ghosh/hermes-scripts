# 📐 Day 3 — Liskov Substitution + Interface Segregation
**Module 1: Foundations**

## The Concept

**LSP (Liskov Substitution Principle):** If `S` is a subtype of `T`, you must be able to replace any `T` with an `S` without breaking the program. Subtypes must honor the *behavioral contract* of the base type — not just the method signatures. Violations usually look like `if (connector instanceof SAPConnector) { skip(); }` buried in runtime logic.

**ISP (Interface Segregation Principle):** Clients should not be forced to depend on methods they don't use. One fat interface is worse than several focused ones. If a class must implement methods it can't support (throws `NotImplementedException`), the interface needs splitting.

The two principles are cousins: LSP protects substitutability *vertically* (base ↔ subtype), ISP protects cohesion *horizontally* (interface ↔ implementor).

---

## How It Works

**ISP Violation — Fat Connector Interface:**

```
IConnector (fat)
├── fetchData()          ← ✅ all connectors
├── pushData()           ← ✅ most connectors
├── triggerWebhook()     ← ❌ SAP OData can't do this
├── subscribeToStream()  ← ❌ REST connectors can't do this
└── deleteRecord()       ← ❌ some read-only connectors
```

SAP OData connector forced to implement `triggerWebhook()` → throws at runtime. **ISP violation.**

**ISP Fix — Segregated Interfaces:**

```
IConnector (base)
├── fetchData()
└── getMetadata()

IWebhookCapable (mixin)
└── triggerWebhook()

IStreamCapable (mixin)
└── subscribeToStream()

IWriteCapable (mixin)
├── pushData()
└── deleteRecord()

SlackConnector    implements IConnector + IWebhookCapable + IWriteCapable
SAPODataConnector implements IConnector                   (read-only, no webhook)
KafkaConnector    implements IConnector + IStreamCapable
```

IS runtime checks capability via interface query, not instanceof:

```typescript
if (connector instanceof IWebhookCapable) {
  connector.triggerWebhook(payload);
} else {
  throw new UnsupportedCapabilityError("Webhook not supported");
}
```

**LSP Example — Correct Behavioral Contract:**

```
IConnector.fetchData() contract:
  - Returns ConnectorResponse (never null)
  - Throws ConnectorAuthError on auth failure
  - Throws ConnectorTimeoutError after 30s

SlackConnector.fetchData() ✅ — honors the contract
LegacyConnector.fetchData() ❌ — returns null on empty, 
                                  throws raw HttpException instead of ConnectorAuthError
                                  → IS runtime breaks when treating it as IConnector
```

---

## Real Scenario — Shield / IS / UiPath

**The problem Shield likely has (or had):**

Every IS connector is wired through a single `IConnector` interface that was designed for REST-based, bidirectional connectors. Then came:

- **SAP OData**: read-only, no webhooks
- **Kafka / Streaming connectors**: event-stream oriented, no request/response fetch
- **CLI-invoked connectors**: no persistent connection, no push

If the base interface mandates `triggerWebhook()` and `pushData()`, three connector families have dead method stubs littered throughout the codebase. That's ISP violation territory.

**The LSP angle on Shield**: Connector adapters in IS inherit from or implement `BaseConnectorClient`. If the DAP activity catalog queries `connector.getSupportedTriggers()` and SAP returns an empty list but the contract says "at least one trigger," any code that iterates `triggers[0]` crashes. LSP violation — SAP is not truly substitutable.

**Fix in your world:**
1. Break `IConnector` into `IReadableConnector`, `IWritableConnector`, `IWebhookConnector`, `IStreamConnector`.
2. Capability registry maps connectorId → set of supported interfaces.
3. IS runtime capability-checks before dispatch, not via instanceof branching.
4. Every connector implementation's behavioral contract is documented (and ideally tested via a shared contract test suite).

---

## Interview Question

> *"You're designing the base connector interface for a platform that must support REST, webhook, streaming, and CLI-invoked connectors. A new connector type only supports read operations and has no webhook capability. How do you model this without violating ISP or LSP? Walk me through your interface hierarchy, and explain how the IS runtime dispatches calls safely."*

**What strong answers cover:**
- Splits interfaces by capability, not by connector type
- Uses composition over inheritance ("implements multiple focused interfaces")
- Runtime capability discovery without instanceof chains
- Contract tests that verify every connector implementation honors behavioral expectations (error types, return nullability, timeout behavior)
- Trade-off awareness: more interfaces = more indirection; how do you keep it navigable?

---

## Think About It

> Do any of Shield's current connectors silently no-op or return stub data for methods they don't actually support — and how would you even know?
