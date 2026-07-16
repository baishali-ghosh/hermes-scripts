# 📐 Day 43 — Zero Trust Architecture
**Module 5: Security Architecture**

## The Concept
Zero Trust means: **never trust, always verify** — regardless of network location. No principal (user, service, connector) is inherently trusted because it's "inside the network." Every request must be authenticated, authorized, and continuously validated. The three pillars are: strong identity verification on every call, least-privilege access enforced at the data layer (not just perimeter), and continuous telemetry/policy enforcement. Network perimeter security ("castle and moat") is dead — Zero Trust replaced it because perimeters are routinely bypassed via phishing, compromised credentials, or supply chain attacks.

## How It Works

```
TRADITIONAL PERIMETER MODEL
─────────────────────────────────────────────────────────────────
  [ Internet ] ──firewall──> [ Trusted Internal Network ]
                                 ↓
                         "You're in? You're trusted."
                         Any service talks to any service.
─────────────────────────────────────────────────────────────────

ZERO TRUST MODEL
─────────────────────────────────────────────────────────────────
  Every request flows through a Policy Enforcement Point (PEP):

  [Service A] ──request──> [PEP / Sidecar Proxy]
                                  │
                         ┌────────▼────────┐
                         │  Policy Engine  │  ← consults
                         │  (PDP)          │    Identity Provider
                         └────────┬────────┘    Attribute Store
                                  │             Risk/Anomaly Score
                         ALLOW or DENY
                                  │
                                  ▼
                         [Service B / Data]

  Zero Trust Stack:
  ┌─────────────────────────────────────────┐
  │  Identity (Who?)      → mTLS + JWT      │
  │  Device (From where?) → cert, posture   │
  │  Context (Why?)       → time, IP, scope │
  │  Behavior (Normal?)   → anomaly detect  │
  └─────────────────────────────────────────┘
```

Key mechanisms:
- **Service identity**: every microservice has a cryptographic identity (SPIFFE/SPIRE, mTLS cert). Not just a shared secret.
- **Policy as code**: OPA (Open Policy Agent), AWS IAM conditions, or custom policy engines decide access dynamically.
- **Microsegmentation**: services declare exactly which other services can call them, enforced at the sidecar/mesh level (Envoy, Istio).
- **Short-lived credentials**: tokens expire fast (minutes, not days). Forced re-evaluation prevents long-lived compromise windows.
- **Continuous verification**: access decisions happen per-request, not per-session. A session authenticated at T=0 can be denied at T+5m if posture changes.

## Real Scenario — Shield / IS / UiPath

**The problem without Zero Trust:**  
IS runs inside a Kubernetes cluster. Connectors, the auth service, the config store, and the webhook router all share a flat network namespace. A compromised connector pod (e.g., supply-chain attack in a vendor SDK) can freely reach the credentials vault, scrape secrets from the config store, or poison the webhook router. No lateral movement barrier exists.

**Zero Trust applied to the IS/Shield layer:**

1. **Connector-to-IS calls**: Every connector pod gets a SPIFFE SVID (short-lived X.509 cert). IS runtime's Envoy sidecar validates the cert — a connector without a valid SPIFFE identity is rejected before any application-layer code runs.

2. **IS-to-Vault (credentials)**: OPA policy enforces: `connector:slack` can only read `secrets/slack/*`. Even if a Snowflake connector is compromised, it cannot read Slack's OAuth tokens. Vault issues short-lived dynamic secrets (15-min TTL) — stealing one credential is useless after expiry.

3. **Webhook ingestion path**: Incoming webhook from GitHub must present a HMAC signature (identity) AND the calling IP must match GitHub's published CIDR list (context). Both must pass. Neither alone is sufficient.

4. **DAP/admin calls to IS**: Admin tokens scoped to specific operations. A "read connector list" token cannot trigger connector executions. Scope is enforced by the policy engine, not just by API route guards.

5. **Anomaly detection layer**: IS emits per-connector call telemetry. An anomaly (Snowflake connector suddenly calling 10,000 rows at 3am) triggers a policy re-evaluation that can revoke the connector's token mid-session.

**Net effect**: Blast radius of any single compromise is bounded to that connector's specific scope. Lateral movement is structurally prevented.

## Interview Question

> "You're the architect for a multi-tenant connector platform where tenant A's connectors run in the same Kubernetes cluster as tenant B's. A security audit flags that a compromised connector could exfiltrate another tenant's credentials. Design a Zero Trust architecture that prevents lateral movement across tenants — without requiring separate clusters per tenant. What are the tradeoffs of your approach versus hard multi-tenancy (separate clusters)?"

*(Strong answers will cover: namespace isolation + network policies, SPIFFE per-tenant identity namespaces, OPA policies scoped to tenant ID in claims, Vault namespaces or separate mounts, per-tenant short-lived credential rotation, and the honest cost: operational complexity of policy management vs the simplicity of cluster-per-tenant.)*

## Think About It
In the IS connector platform today, if one connector pod were compromised — what is the actual blast radius? Map it out before tomorrow.
