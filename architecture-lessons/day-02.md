---
# 📐 Day 2 — Open/Closed Principle
**Module 1: Foundations**

## The Concept
Software entities (classes, modules, services) should be **open for extension** but **closed for modification**.
You add new behavior by adding new code — not by editing existing, working code.
This reduces regression risk: the old code path never changes, so it can't break.
The key enabler is programming to abstractions (interfaces, contracts) rather than concrete implementations.

## How It Works

```
WITHOUT OCP (violation):
──────────────────────────────────────────────────────────
class ConnectorRouter {
  route(connectorType: string) {
    if (connectorType === "slack")    return new SlackConnector()
    if (connectorType === "github")   return new GitHubConnector()
    if (connectorType === "databricks") return new DatabricksConnector()  // ← you TOUCH this file every time
  }
}

WITH OCP (compliant):
──────────────────────────────────────────────────────────
interface IConnector { execute(payload): Promise<Result> }

class SlackConnector    implements IConnector { ... }
class GitHubConnector   implements IConnector { ... }
class DatabricksConnector implements IConnector { ... }  // ← NEW file, nothing existing changes

class ConnectorRegistry {
  private registry = new Map<string, IConnector>()
  register(type: string, connector: IConnector) { this.registry.set(type, connector) }
  resolve(type: string): IConnector { return this.registry.get(type)! }
}

// IS runtime NEVER changes — it calls registry.resolve(type).execute(payload)
```

The **registry + interface** pattern is OCP's most common realization in connector platforms.

## Real Scenario — Shield / IS / UiPath

The Integration Service (IS) connector runtime today routes requests to connectors.
If every new connector (Databricks, Workday, SAP) requires you to edit the core IS routing or
execution logic — adding a case, registering a type inline, tweaking shared dispatch code — that's
an OCP violation.

**The compliant design:**
- IS runtime depends on `IConnectorClient` (interface), never concrete connector classes.
- Each connector is registered at startup via a plugin registry (or DI container).
- Adding Databricks = ship `DatabricksConnectorAdapter` implementing `IConnectorClient`, register it.
- IS runtime: untouched. Zero regression risk on Slack, GitHub, or any existing connector.

**Where this goes wrong in practice:** Feature flags baked into the core dispatch path.
`if (connectorType === "databricks" && featureFlag("databricks-beta"))` — now your core runtime
has knowledge of a specific connector. Violation. The flag should live in the adapter itself, or in
registration logic, not the runtime.

## Interview Question

> "How would you design a connector platform so that adding a new connector requires zero changes
> to the runtime core? Walk me through the abstractions, registration mechanism, and how you'd
> enforce this constraint as the team grows."

*(What they want to hear: interface contract, plugin/registry pattern, DI, boundary enforcement via
linting or architecture tests — e.g. forbid direct imports of concrete connector classes in the
runtime module.)*

## Think About It

In the IS codebase you work in today — is there any file that gets touched every time a new
connector ships? That file is your OCP violation. What abstraction would make it untouchable?
---
