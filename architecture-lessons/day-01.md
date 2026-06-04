---
# 📐 Day 1 — Single Responsibility Principle (SRP)
**Module 1: Foundations**

## The Concept
A class, service, or module should have exactly one reason to change — one owner, one job.
"Reason to change" means a specific stakeholder or concern: auth team, rate-limit policy, response schema.
When a module serves two concerns, a change to one bleeds into the other — higher risk, harder testing, no clean ownership.
SRP is not about small code; it's about cohesive responsibility boundaries.

## How It Works

```
❌ SRP Violation — single ShieldConnector class doing everything:

  ShieldConnector
  ├── authenticate()         ← auth team changes this
  ├── applyRateLimit()       ← infra policy changes this
  ├── retryOnFailure()       ← reliability team changes this
  └── mapResponse()          ← schema team changes this
  
  Result: vendor changes auth → you touch rate limit code. Guaranteed bugs.

✅ SRP-compliant — each class has ONE reason to change:

  AuthHandler        → only changes when auth protocol changes
  RateLimiter        → only changes when throttling policy changes
  RetryPolicy        → only changes when reliability SLA changes
  ResponseMapper     → only changes when vendor response schema changes

  ShieldConnector orchestrates, but doesn't own any of these concerns.
```

## Real Scenario — Shield / IS / UiPath

You have a `SlackConnector` class in Shield that:
- Handles OAuth token refresh
- Applies per-tenant rate limiting
- Retries on 429 / 5xx
- Transforms Slack's raw API response into IS's canonical `ConnectorResponse` shape

When Slack deprecates its OAuth v1 flow and you need to switch to v2 — you're deep in the same file that contains retry logic and response transformation. Every diff review is high risk because the boundaries are blurred.

**SRP fix:** Extract `SlackAuthHandler`, `ConnectorRateLimiter`, `HttpRetryPolicy`, `SlackResponseMapper` as separate classes. `SlackConnector` becomes a thin orchestrator. Now the auth swap is a 50-line PR in one file, reviewable in 10 minutes, zero risk to retry or mapping logic.

## Interview Question

> *"Tell me about a time a module became hard to change. What was the underlying design problem, and how would you fix it today?"*

What they're probing: Can you identify that "hard to change" = mixed responsibilities? Can you articulate the cost (risk, test surface, ownership confusion)? Can you propose a clean split that respects actual change drivers — not just "make it smaller"?

Strong answer structure: describe the real impact (a bug introduced during an unrelated change, a painful review, a broken test suite), name the violated principle precisely, then describe the refactor in terms of who now owns what and how the boundaries map to real teams.

## Think About It

Pick one class or service you own on the Shield team — who are the two (or more) different stakeholders whose changes would force you to touch the same file?

---
*Curriculum: Staff/Principal Engineer & Solutions Architect Prep — Baishali Ghosh, Shield Team, UiPath*
