# 📐 Day 41 — OAuth2 / OIDC

**Module 4: Security Architecture**

## The Concept

OAuth2 is an *authorization* framework — it lets a user (or service) delegate access to resources without sharing credentials. The caller gets a scoped, time-limited access token, not a password. OpenID Connect (OIDC) layers *authentication* on top of OAuth2: the identity provider (IdP) also issues an ID token (a signed JWT) that proves *who* the caller is. These two protocols together are the foundation of every modern SSO, API gateway, and service-to-service auth flow.

Key artifacts:
- **Access Token** — proves "you are authorized to do X" (consumed by resource servers / APIs).
- **ID Token** — proves "you are user Y" (consumed by clients / UIs).
- **Refresh Token** — opaque credential used to obtain new access tokens without re-authentication.

## How It Works

### Authorization Code Flow (human-facing, most secure)

```
Browser / App                    IdP (e.g. UiPath Identity)        Resource Server (IS API)
     |                                   |                                  |
     |-- GET /authorize?                 |                                  |
     |   response_type=code &           |                                  |
     |   client_id=... &                |                                  |
     |   scope=openid connector:read -->|                                  |
     |                                   |--- login prompt → user logs in  |
     |<-- 302 redirect with ?code=XYZ --|                                  |
     |                                   |                                  |
     |-- POST /token                     |                                  |
     |   code=XYZ, client_secret ----->  |                                  |
     |<-- { access_token, id_token,      |                                  |
     |      refresh_token } -------------|                                  |
     |                                   |                                  |
     |-- GET /connectors                 |                                  |
     |   Authorization: Bearer <at> ----|---------------->                 |
     |                                   |       validate JWT sig + expiry  |
     |<-- 200 data ----------------------------<-----|                      |
```

### Client Credentials Flow (service-to-service — no human)

```
Shield Service                  IdP                            IS API
     |                           |                               |
     |-- POST /token             |                               |
     |   client_id + secret ---> |                               |
     |<-- { access_token } ------|                               |
     |                           |                               |
     |-- POST /connector/invoke  |                               |
     |   Authorization: Bearer --|---------------------------->  |
     |                           |       validate JWT            |
     |<-- 200 result ---------------------------------<----------|
```

### Token Anatomy (JWT Access Token)

```
Header.Payload.Signature

Payload (decoded):
{
  "sub":   "service:shield-worker-1",
  "aud":   "is-api",
  "iss":   "https://identity.uipath.com",
  "iat":   1752000000,
  "exp":   1752003600,      ← 1 hour TTL
  "scope": "connector:invoke connector:read"
}
```

The resource server (IS API) validates: correct `iss`, `aud`, signature (via JWKS endpoint), not expired. **No database lookup needed** — the JWT is self-contained.

### Token Refresh Cycle

```
Access Token expires (exp)
  └─> Client presents Refresh Token to /token endpoint
        └─> IdP issues new Access Token (+ optionally new Refresh Token)
              └─> Old Refresh Token is revoked (rotation)
```

Refresh tokens are long-lived but opaque — they must be stored securely (not in localStorage, never in logs).

## Real Scenario — Shield / IS / UiPath

**Scenario: Shield connector calling a vendor API on behalf of a UiPath tenant**

1. **Human auth (UI session):** Tenant admin connects Salesforce via Shield. UI does Authorization Code Flow with PKCE (no client secret on frontend). UiPath Identity issues tokens; Shield stores the refresh token in Vault (not in the DB).

2. **Runtime auth (service-to-service):** When Shield worker needs to invoke the Salesforce connector, it uses **Client Credentials Flow** against UiPath Identity to get an IS-scoped access token. It then calls IS API with that bearer token.

3. **Token caching:** Access tokens are short-lived (15 min–1 hr). Shield caches them in memory (not disk) and refreshes ~60s before expiry. Without this, every connector invocation triggers a round-trip to the IdP — adding latency and hammering the token endpoint.

4. **Scope enforcement:** IS API checks `scope: connector:invoke` in the JWT before processing. A Shield read-only service that only has `connector:read` gets a 403 on write operations — no custom auth logic needed in IS, the scope in the token handles it.

5. **OIDC for Admin UI:** The Shield admin console uses OIDC — it gets an ID Token to display "Welcome, Baishali" and knows which tenant/org the user belongs to (claims: `tenant_id`, `org_id`). The access token goes to the API; the ID token stays in the UI.

**What goes wrong if you skip this correctly:**
- Connector stores vendor API key in env vars → rotated key = redeploy.
- IS accepts tokens from any issuer → token forgery attack.
- Refresh token in `localStorage` → XSS steals it, attacker has long-lived credential.
- Access token TTL set to 24h for "convenience" → compromised token valid for a day.

## Interview Question

> *"You're designing the auth flow for a multi-tenant connector platform. Each tenant connects to different external systems using credentials they own. A connector invocation at runtime must use the correct tenant's credentials. Walk me through the end-to-end token and credential flow — from tenant onboarding to a live API call. Where does each token type live, who validates what, and how do you handle token expiry under high concurrency without hammering the IdP?"*

(Examines: OAuth2 flows, token storage security, caching strategy, race condition on concurrent refresh, multi-tenancy isolation, Vault integration.)

## Think About It

In the Shield connector runtime, which services should use Client Credentials vs Authorization Code flow — and is there any case where a connector runtime worker should hold a user-context access token rather than a service identity token?
