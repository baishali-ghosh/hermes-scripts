---
# 📐 Day 42 — Mutual TLS (mTLS)
**Module 5: Security Architecture**

## The Concept
Standard TLS is one-way: the client verifies the server's certificate, but the server does not verify the client. Mutual TLS (mTLS) adds the second handshake — the client presents its own certificate, the server validates it against a trusted CA. Only clients with a valid, trusted cert can establish the connection at all. This makes mTLS an authentication layer baked into the transport, not the application. Compromise of a service = that service's cert is revoked; all other services are automatically excluded from trusting it.

## How It Works

```
  Client (IS Runtime)               Server (Connector Endpoint / Sidecar)
       |                                          |
       |------ ClientHello ---------------------->|
       |<----- ServerHello + Server Cert ---------|
       | (client verifies server cert against CA) |
       |------ Client Cert + ClientKeyExchange -->|
       | (server verifies client cert against CA) |
       |------ Finished (encrypted) ------------>|
       |<----- Finished (encrypted) -------------|
       |         [Mutual trust established]       |
       |====== Application Data (encrypted) ====>|

  CA (Certificate Authority) — the single trust anchor
  Both certs signed by same CA (or CA chain).
  Revocation: CRL or OCSP — server checks cert not revoked.
```

**Key components:**
- **CA**: issues + signs certs for all services (internal PKI via Vault, cert-manager, or AWS ACM PCA)
- **Client cert**: identity of the calling service (e.g., `is-runtime.shield.internal`)
- **Server cert**: identity of the called service (e.g., `snowflake-connector.shield.internal`)
- **Revocation**: CRL (certificate revocation list) or OCSP for real-time cert invalidation

## Real Scenario — Shield / IS / UiPath

IS runtime calls out to connector sidecars or vendor proxy services inside the UiPath service mesh. With plain API keys, a compromised IS pod can forge requests to any connector. With mTLS:

- Each IS pod gets a cert issued by internal CA: `is-runtime-<podid>.shield.internal`
- Each connector sidecar has its cert: `snowflake-connector.shield.internal`
- Istio (or Linkerd) handles the mTLS handshake transparently at the sidecar layer — application code doesn't change
- A compromised Snowflake connector **cannot** impersonate the IS runtime to call Slack connector — different cert, different SPIFFE/SVID identity

**Zero-trust upgrade path for Shield:**
```
Today:  IS → [Bearer token in header] → Connector
Better: IS → [mTLS at transport] + [Bearer token at app layer] → Connector
```
Two layers: transport identity (who is the calling service?) + application identity (who is the end user?). They're orthogonal. mTLS solves service-to-service impersonation; JWT solves user-level authorization.

**Certificate rotation** is the operational challenge. Certs expire (typically 24h–90 days in a service mesh). Vault's PKI secrets engine + cert-manager in Kubernetes handle automated rotation. If rotation fails and certs expire, mTLS connections break silently — suddenly "all connectors are down" with no clear error. Monitor cert expiry as a first-class SLI.

## Interview Question

*"You're hardening the IS connector platform. A security review recommends mTLS for all service-to-service calls. The team pushes back: 'We already have OAuth2 tokens, that's enough.' How do you evaluate their claim? When does mTLS add real security value on top of bearer tokens, and when is it operational overhead without proportional benefit? What would a threat model reveal?"*

## Think About It
If a connector sidecar's private key is leaked, what's your recovery path — and how fast can you revoke + rotate without dropping live connector traffic?
---
