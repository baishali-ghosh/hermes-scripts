---
# 📐 Day 12 — Retry, Exponential Backoff, Jitter
**Module 2: Distributed Systems**

## The Concept
When a network call fails transiently, retrying immediately risks hammering a struggling service and making things worse. Exponential backoff doubles the wait between each retry attempt, giving the downstream system time to recover. Jitter adds randomness to the wait time to prevent synchronized retry storms — the "thundering herd" problem. Together these three techniques form the standard, production-grade retry primitive in distributed systems.

## How It Works

```
Attempt 1 → FAIL
Wait: base_delay * 2^0 + random_jitter     → e.g. 1s + 0.3s = 1.3s
Attempt 2 → FAIL
Wait: base_delay * 2^1 + random_jitter     → e.g. 2s + 0.7s = 2.7s
Attempt 3 → FAIL
Wait: base_delay * 2^2 + random_jitter     → e.g. 4s + 0.2s = 4.2s
Attempt 4 → SUCCESS (or abort after max_retries)
```

**Without jitter (thundering herd):**
```
t=0   → 50 clients fail simultaneously
t=4s  → 50 clients retry simultaneously   ← you DDoS yourself
t=8s  → 50 clients retry simultaneously   ← and again
```

**With full jitter (spread load):**
```
t=0      → 50 clients fail simultaneously
t=1s-5s  → retries spread across window   ← vendor recovers normally
```

**Key parameters:**
- `base_delay`: starting wait (e.g. 500ms)
- `max_delay`: cap the backoff ceiling (e.g. 30s)
- `max_retries`: don't retry forever (e.g. 5)
- `jitter_range`: randomness window (e.g. 0–1s, or full jitter: 0–computed_backoff)
- `retryable_codes`: 429, 503, 504 → retry. 400, 401, 403 → do NOT retry.

## Real Scenario — Shield / IS / UiPath

**Scenario: IS pod restart triggers webhook delivery storm**

IS is processing 500 pending webhook deliveries. An IS pod restarts (rolling deploy or OOM kill). On startup, all 500 webhook delivery tasks re-initialize and hit the vendor APIs at `t+4s` (fixed backoff, no jitter). You just sent a 500-request burst to Snowflake, OpenAI, and Slack simultaneously — likely triggering their rate limits, causing a second wave of failures.

**The fix in IS connector retry logic:**

```typescript
function retryDelay(attempt: number, base = 500, maxDelay = 30_000): number {
  const exponential = base * Math.pow(2, attempt);
  const capped = Math.min(exponential, maxDelay);
  // Full jitter: random between 0 and capped
  return Math.random() * capped;
}

async function callWithRetry(fn: () => Promise<Response>, maxAttempts = 5) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fn();
      if (res.status === 429 || res.status >= 500) throw new RetryableError(res.status);
      return res;
    } catch (err) {
      if (i === maxAttempts - 1 || !isRetryable(err)) throw err;
      await sleep(retryDelay(i));
    }
  }
}
```

**Extra:** If the vendor returns a `Retry-After` header (common on 429), always honor it — override your computed backoff. Slack, SendGrid, OpenAI all do this.

**Also relevant — UiPath CLI:** The `withPerfTracking()` HOF pattern from Day 5 is composable here. You can build a `withRetry()` HOF that wraps any command execution, keeping retry logic separate from business logic (SRP + DRY).

## Interview Question

*"You're implementing retry logic for connector API calls. The vendor rate limits at 100 req/s. During normal operation, IS has 50 active connectors each making ~3 calls/s. An IS restart causes all connectors to retry simultaneously. How do you design the retry strategy so a mass restart doesn't trigger rate limiting, and how do you validate your approach before going to production?"*

**What a strong answer covers:**
- Full jitter vs decorrelated jitter (decorrelated is mathematically more spread)
- Per-connector retry budgets vs global retry concurrency limiter
- Respect `Retry-After` from vendor
- Load testing with simulated mass restart
- Circuit breaker as a companion (Day 11) — don't retry when circuit is OPEN

## Think About It

Where in the IS or Shield webhook pipeline today are retries done with a **fixed delay** — and what would happen if 100 pods restarted simultaneously at the same time?
---
