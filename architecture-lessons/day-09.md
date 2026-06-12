---
# 📐 Day 9 — Fail Fast vs Fail Safe
**Module 2: Distributed Systems**

## The Concept
Two opposing failure philosophies — and both are correct, in different contexts.

**Fail Fast**: Detect failure immediately and surface it loudly. Return an error, throw an exception, stop processing. No silent degradation.

**Fail Safe**: When something goes wrong, return a safe default, degrade gracefully, or continue with reduced functionality. Availability wins over correctness.

The key insight: the right choice depends entirely on whether a safe default exists and whether operating in a degraded state causes more harm than stopping.

## How It Works

```
         [External Dependency Unavailable]
                        |
              +---------+---------+
              |                   |
         Is there a           No safe default /
         safe default?        critical operation?
              |                   |
             YES                  NO
              |                   |
         FAIL SAFE            FAIL FAST
         Return default       Throw/Error
         Log warning          Alert + Surface
         Degrade gracefully   Stop processing
              |                   |
    User sees reduced       User sees clear error
    functionality           Operator sees alert
    (might not notice)      (noisy, actionable)
```

**Pattern applied to dependencies:**

| Dependency               | Strategy   | Why                                                        |
|--------------------------|------------|------------------------------------------------------------|
| Feature flag service     | Fail Safe  | Assume features enabled; outage ≠ broken product           |
| Auth token issuer        | Fail Fast  | Can't safely proceed without valid identity                |
| Audit log sink           | Fail Safe  | Log locally, drain later; don't block the user action      |
| Credentials vault        | Fail Fast  | No credentials = don't attempt connector call              |
| Activity log service     | Fail Safe  | Eventual write is fine; connector call can still succeed   |

## Real Scenario — Shield / IS / UiPath

**Fail Safe — Feature Flags in IS:**
IS reads connector capability flags (e.g., `connector.ai_enabled`) from a flag service at startup. If that service is unreachable during a rolling deploy:
- Fail Safe: treat all flags as `true` (features enabled). Users experience no disruption. Flag service comes back, flags normalize.
- Wrong choice (Fail Fast here): IS refuses to start → entire connector layer is down because of a non-critical dependency.

**Fail Fast — Connector Auth Token Refresh:**
A connector's OAuth access token has expired. IS calls the token refresh endpoint — network timeout, no response.
- Fail Fast: surface `AUTH_REFRESH_FAILED`, stop the connector invocation, return error to caller. Do NOT proceed with an expired token that will just get a 401 three seconds later.
- Wrong choice (Fail Safe here): retry the connector call with the stale token → guaranteed downstream 401 cascade, harder to debug, potentially triggers vendor-side rate limits or lockouts.

**The real trap:** Developers default to Fail Safe because it feels "user friendly." But silent failures create invisible data corruption, security gaps, and debugging nightmares. Fail Fast is not unfriendly — it's honest.

## Interview Question

> *"A connector's auth token refresh service is unreachable. Do you fail fast or fail safe? What factors drive your decision? Now generalize — how do you establish a policy across IS so engineers make consistent choices for each dependency type?"*

Think about: safe default existence, security implications, blast radius of degradation, observability (silent vs loud), SLA requirements of the calling path.

## Think About It
Look at the IS dependencies you own — for each one, do you know explicitly whether it's fail-fast or fail-safe, and is that decision documented and tested?
