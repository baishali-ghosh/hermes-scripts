# 📐 Day 45 — RBAC vs ABAC
**Module 6: Security Architecture**

## The Concept
**RBAC (Role-Based Access Control):** Permissions are assigned to roles; users are assigned to roles. Access is determined by: *does this role have permission X?* Simple, fast, and easy to audit — but coarse-grained. Adding edge cases bloats the role graph.

**ABAC (Attribute-Based Access Control):** Access is determined by evaluating a policy over *attributes* — of the subject (user), resource, environment, and action. Fine-grained and contextual, but significantly more complex to implement, audit, and debug.

Neither is universally better. RBAC wins for simpler domains with stable permission structures. ABAC wins when access decisions depend on runtime context — tenant, region, data sensitivity, time of day, resource ownership.

## How It Works

**RBAC Model:**
```
User → Role(s) → Permission(s) → Resource
       --------
       e.g. Shield_Admin → [read:connectors, write:connectors, delete:connectors]
       e.g. Shield_Viewer → [read:connectors]
```

Decision: `allowed = user.roles.any(r => r.permissions.includes(required_permission))`

**ABAC Model:**
```
Policy Engine evaluates:
  Subject attrs:   { userId, tenantId, department, clearanceLevel }
  Resource attrs:  { ownerId, tenantId, sensitivity, region }
  Environment:     { time, ip, requestOrigin }
  Action:          { type: "write" }

Policy:  "allow write IF subject.tenantId == resource.tenantId
          AND subject.clearanceLevel >= resource.sensitivity
          AND environment.ip IN subject.allowedRegions"
```

Decision engine: OPA (Open Policy Agent), Cedar (AWS), Casbin.

**Comparison:**
```
┌─────────────────────┬──────────────────┬──────────────────────┐
│ Dimension           │ RBAC             │ ABAC                 │
├─────────────────────┼──────────────────┼──────────────────────┤
│ Granularity         │ Coarse           │ Fine (context-aware) │
│ Performance         │ Fast (cache)     │ Slower (policy eval) │
│ Auditability        │ Simple           │ Complex              │
│ Flexibility         │ Low              │ High                 │
│ Operational cost    │ Low              │ High                 │
│ Role explosion risk │ HIGH             │ N/A                  │
│ Policy drift risk   │ N/A              │ HIGH                 │
└─────────────────────┴──────────────────┴──────────────────────┘
```

## Real Scenario — Shield / IS / UiPath

**The problem RBAC hits in Shield:** You have `Shield_Admin` and `Shield_Viewer`. Simple. But then product says:
- Connector A is owned by Tenant X — only Tenant X users can delete it
- Connector B has PII data — only users with `data_steward` attribute can read logs
- A service account should only be able to invoke connectors between 9am–5pm UTC

You can't model this with roles. You'd end up with: `TenantX_Shield_Admin_PII_BusinessHours` — **role explosion**. That's your signal to move to ABAC.

**Hybrid design in IS:**
1. **RBAC for coarse access:** `Shield_Admin`, `Shield_Viewer`, `IS_Developer` control UI access and API surface
2. **ABAC for fine-grained resource decisions:** When a request hits the connector execution layer, OPA (or Cedar) evaluates:
   ```
   subject.tenantId == connector.tenantId
   AND action.type in subject.allowedActions
   AND connector.sensitivity <= subject.clearanceLevel
   ```
3. The connector config store tags every resource with `{ tenantId, sensitivity, ownerId, region }`.
4. Every auth token carries user attributes (from OIDC claims or an attribute store).

**UiPath CLI angle:** The CLI's `--profile` system is RBAC-flavored (profile = role). But when Shield invokes connectors on behalf of different tenants, the decision *which* connector a given JWT can access is pure ABAC — it evaluates tenant isolation as a policy rule.

**DAP angle:** DAP controls which apps show which features to which users. Feature visibility per tenant + user tier = ABAC. "Show this UI element if `user.plan == enterprise` AND `tenant.region == EU` AND `feature.enabled == true`" — three attributes, one policy.

## Interview Question

> "You're designing the authorization model for a multi-tenant connector platform. Tenant A has 200 connectors, some marked sensitive. Tenant B users must never access Tenant A's resources. Some Tenant A power users can read connector logs but not delete them. Certain automated service accounts should only operate during business hours. Walk me through how you model this. Would you use RBAC, ABAC, or a hybrid? Where would you store policies, how would you enforce them at runtime, and how would you make the system auditable when a permission denial occurs?"

Good follow-up probes:
- What happens to performance if every connector API call requires a policy eval?
- How do you cache ABAC decisions safely without making them stale?
- If a policy is wrong, how do you detect it before it causes an incident?

## Think About It

Where in Shield/IS today are you doing RBAC that secretly needs ABAC — and what runtime attributes are you *not* using that would unlock the right access decisions?
