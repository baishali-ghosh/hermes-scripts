---
# 📐 Day 5 — DRY, KISS, YAGNI
**Module 1: Foundations**

## The Concept
**DRY (Don't Repeat Yourself):** Every piece of knowledge should have a single, authoritative representation. Duplication means two places to update when logic changes — and they'll drift.
**KISS (Keep It Simple, Stupid):** The simplest solution that solves the actual problem is the best solution. Complexity is a liability, not an asset.
**YAGNI (You Aren't Gonna Need It):** Don't build functionality until you concretely need it. Speculative generality wastes time now and creates dead code that confuses future engineers.
These three are not just coding hygiene — they're architectural discipline. Violations compound across a codebase and eventually become the reason rewrites happen.

## How It Works

**DRY Violation → HOF Fix:**
```
BEFORE (copy-paste in every CLI command):
  const t0 = performance.now();
  // ... do work ...
  telemetry.track({ duration: performance.now() - t0, ...perfProps });

AFTER (one withPerfTracking HOF):
  export function withPerfTracking(fn, perfProps) {
    return async (...args) => {
      const t0 = performance.now();
      const result = await fn(...args);
      telemetry.track({ duration: performance.now() - t0, ...perfProps });
      return result;
    };
  }
  // Every command wraps with it — one change propagates everywhere.
```

**YAGNI Trap Anatomy:**
```
Reality:           You Have:   You Build:
┌─────────────┐   Slack       Generic multi-vendor
│  Slack API  │   connector   abstraction layer +
└─────────────┘               plugin registry +
                               hot-swap interface +
                               vendor negotiation protocol

Cost: 3 weeks. Vendors never added. Abstraction rots.
```

**KISS — The Right Abstraction Moment:**
```
1 vendor  → hardcode it, ship it
2 vendors → wait, feel the pain
3 vendors → NOW abstract — you know the real shape
```

## Real Scenario — Shield / IS / UiPath

**DRY in the CLI:** `withPerfTracking()` is the canonical UiPath CLI example. Every command (`deploy`, `run`, `publish`, `pack`) used to inline `perfProps + Object.assign` boilerplate. When the telemetry schema changed, it had to be updated in 12 places — and 3 were missed. The HOF centralizes it: change once, all commands update. This is DRY working correctly.

**YAGNI in Shield connectors:** When building the first two connectors (Slack, Jira), a well-meaning engineer proposed a "Universal Connector SDK" with automatic retry policies, a plugin registry, hot-swappable auth strategies, and a vendor metadata negotiation layer. That's YAGNI. The right call: build what Slack and Jira actually need. When you add a third connector (GitHub), the patterns become clear and the abstraction earns its existence. Building the SDK for 2 connectors produces over-engineered interfaces that don't fit connector #3 anyway.

**KISS in IS:** When a connector needs to log activity, the simplest path is a direct log write to the activity store. KISS says: do that. Don't build an async event emitter, pluggable log router, and schema registry for the activity log on day one. Add complexity when complexity is genuinely required — not before.

## Interview Question

> "How do you decide when to abstract vs when to duplicate? What signals tell you duplication has become a real problem worth fixing — and what's the risk of abstracting too early?"

**What a strong answer covers:**
- The Rule of Three: duplicate once, abstract on third occurrence when the pattern is confirmed
- Signals: duplication diverges (two copies drift), change requires touching multiple files, tests are copy-pasted
- Risk of early abstraction: wrong interface, wrong seam, abstraction that doesn't fit the third case, over-engineering that becomes legacy tech debt
- DRY is about *knowledge*, not *text* — identical-looking code with different reasons to change should NOT be merged

## Think About It
Where in Shield's connector codebase do you currently have duplicated logic that's already diverged — and what's been the real cost of that drift?
---
