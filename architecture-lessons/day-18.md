---
# 📐 Day 18 — Microservices vs Monolith
**Module 3: Architectural Patterns**

## The Concept
A **monolith** packages all functionality into a single deployable unit — one build, one deploy, one process. **Microservices** split that into independently deployable units, each owning its own domain, data store, and lifecycle. The choice isn't ideological — it's driven by team topology, deployment independence needs, failure isolation requirements, and the cost of operational overhead you're willing to absorb. A poorly-run microservices system is strictly worse than a well-run monolith. Conway's Law is real: your architecture will mirror your org chart.

## How It Works

```
MONOLITH
┌─────────────────────────────────────────────────────┐
│  IS Runtime                                         │
│  ┌──────────┐ ┌────────────┐ ┌────────────────────┐ │
│  │ Connector│ │  Webhook   │ │  Activity Catalog  │ │
│  │ Registry │ │  Ingestion │ │  + Audit           │ │
│  └──────────┘ └────────────┘ └────────────────────┘ │
│  ┌──────────┐ ┌────────────┐                         │
│  │   Auth   │ │  Rate Lim  │  One deploy, shared DB  │
│  └──────────┘ └────────────┘                         │
└─────────────────────────────────────────────────────┘

MICROSERVICES
┌────────────┐    ┌────────────┐    ┌────────────────┐
│ Connector  │    │  Webhook   │    │    Activity    │
│  Registry  │◄──►│  Ingestion │◄──►│    Catalog     │
│  Service   │    │  Service   │    │    Service     │
│  [own DB]  │    │  [own DB]  │    │    [own DB]    │
└────────────┘    └────────────┘    └────────────────┘
       │                 │                   │
       └──────────── message bus ────────────┘
              (each service deploys independently)
```

**Key dimensions to evaluate:**
| Factor | Monolith | Microservices |
|---|---|---|
| Deployment | One unit | Independent per service |
| Failure blast radius | Whole app | Isolated service |
| Latency (internal calls) | In-process, fast | Network hop, slower |
| Operational overhead | Low | High (k8s, meshes, tracing) |
| Team independence | Low | High |
| Testing | Easier | Harder (contract testing needed) |

## Real Scenario — Shield / IS / UiPath

**The "split everything" trap:** Imagine someone proposes: each of Shield's 50+ connectors becomes its own microservice — its own pod, health check, Helm chart, deployment pipeline, and on-call rotation. That's 50+ services with network overhead for every execution, 50 service meshes to debug, and every IS feature change requiring 50 coordinated deployments. The operational cost exceeds any benefit because connectors don't need independent scaling — they share the same execution model.

**Valid splits that exist today:**
- **IS runtime** vs **connector registry** — different scaling profiles (connector registry is read-heavy and slow-changing; runtime is high-throughput), different change rates, different failure domains. That boundary is worth the seam.
- **Webhook ingestion** vs **connector execution** — ingestion must scale horizontally for burst traffic; execution can be bounded per customer tier. Separate services make sense.
- **Auth/credential vault** vs everything else — security boundary alone justifies the split. You want exactly one service that can decrypt secrets, not every service touching them.

**The monolith-first rule for new domains:** When Shield adds a new integration category (e.g., AI model connectors), start in the monolith. Extract when you've seen the actual seams and scaling pressure. Premature extraction creates the wrong boundaries and you're stuck with them.

## Interview Question

*"A PM proposes splitting each connector into its own microservice. What questions do you ask before agreeing? What hidden costs would you surface?"*

**What the interviewer is probing:**
- Do you understand the operational overhead of microservices isn't free?
- Can you distinguish between "independent deployability" (the real benefit) and "just smaller code" (not a benefit)?
- Do you know Conway's Law — does the team structure actually map to the proposed service boundaries?
- Can you identify what's gained vs what's lost (distributed tracing, contract testing, service mesh, on-call burden, cross-service transactions)?

Strong answer covers: deployment independence needs, failure isolation reality, team ownership, whether connectors have genuinely different scaling requirements, the cost of distributed calls vs in-process, and whether you can afford the operational maturity needed.

## Think About It

Which boundary in the IS/Shield system has caused the most pain when it *wasn't* separated — and what would the correct seam have been?
