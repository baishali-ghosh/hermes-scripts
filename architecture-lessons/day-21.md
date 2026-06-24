---
# 📐 Day 21 — Hexagonal Architecture (Ports & Adapters)
**Module 3: Architectural Patterns**

## The Concept
Hexagonal Architecture (coined by Alistair Cockburn) places the core business logic at the center — the **hexagon** — and surrounds it with **ports** (interfaces the core defines) and **adapters** (implementations that satisfy those interfaces). The core never imports or depends on infrastructure — it doesn't know whether it's talking to Slack, a test double, or a gRPC stream. All external systems are plugged in via adapters. This is what makes the core independently testable, and infrastructure choices swappable.

## How It Works

```
                  ┌──────────────────────────────────────┐
  Inbound         │              HEXAGON                 │         Outbound
  (driving)       │        (IS Core / Domain)            │         (driven)
                  │                                      │
  HTTP webhook ──►│── Port: IWebhookReceiver             │
  gRPC event ────►│    (inbound port)                    │
                  │                                      │
                  │         Business Logic               │── Port: IConnectorClient ──► SlackAdapter
                  │         (orchestrate, validate,      │                           ──► GitHubAdapter
                  │          route, emit)                │── Port: IEventPublisher ───► KafkaAdapter
                  │                                      │                           ──► InMemoryAdapter (test)
                  └──────────────────────────────────────┘

  Adapter (left side) translates HTTP → domain call.
  Adapter (right side) translates domain call → external API call.
  The hexagon never knows which adapter is wired in.
```

Key rule: **dependency arrows always point inward**. Adapters depend on ports. The hexagon depends on nothing outside itself.

## Real Scenario — Shield / IS / UiPath

In the IS connector layer, the hexagon is the connector execution engine — it validates config, applies rate limiting rules, handles retries policy. The **outbound ports** are:
- `IConnectorClient` — defines `execute(request): ConnectorResponse`
- `ICredentialStore` — defines `getSecret(key): string`
- `IActivityLogger` — defines `log(event: ConnectorEvent): void`

The **adapters** are:
- `SlackConnectorAdapter implements IConnectorClient` — calls Slack REST API
- `AzureKeyVaultAdapter implements ICredentialStore` — calls Azure KV
- `KafkaActivityLoggerAdapter implements IActivityLogger` — pushes to Kafka topic

At test time you wire in `InMemoryConnectorClientAdapter`, `MockCredentialStore`, `InMemoryLogger` — and the entire execution engine is testable without a single real HTTP call. At deploy time you wire in the real adapters via DI container. **Switching from Azure KV to HashiCorp Vault = write one new adapter. Zero hexagon changes.**

The DAP integration (Digital Adoption Platform) is also an adapter concern — how DAP consumes IS webhook events is an inbound adapter decision, not a core change.

## Interview Question

> "How would you structure the IS codebase so that switching from REST to gRPC for connector communication requires changing only one file per connector?"

*(Strong answer: REST and gRPC are both infrastructure concerns — they belong in outbound adapters. The hexagon calls `IConnectorClient.execute()`. Today `SlackRestAdapter` handles REST. Add `SlackGrpcAdapter` without touching the hexagon. The switch is a DI wiring change. Bonus points: discuss how inbound also follows the same pattern — the HTTP controller and gRPC server both call the same hexagon port.)*

## Think About It

> Pick one class in your IS codebase that directly imports a vendor SDK or HTTP client — could you move that import behind a port today without changing any business logic?
---
