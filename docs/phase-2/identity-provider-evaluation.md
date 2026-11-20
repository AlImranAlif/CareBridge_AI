# CareBridge AI — Phase 2, Step 1: Identity Provider Evaluation

**Status:** comparative design draft; no provider is approved for implementation or production.
**Provisional recommendation:** continue evaluating ZITADEL Cloud as the leading candidate, subject to technical validation, procurement, contract, residency, and qualified legal review.
**Scope:** identity-provider selection and trust boundaries for the Next.js/FastAPI architecture. This document does not authorize application, database, configuration, deployment, or legacy-data changes.

Provider features, plans, prices, regions, contracts, and documentation can change. This draft intentionally makes no verified claim that any provider offers Bangladesh data residency, satisfies applicable law, or is production-suitable for CareBridge. Revalidate all provider-specific statements against current documentation and contract terms before a decision.

## 1. Decision summary

ZITADEL Cloud is a **provisional design recommendation only** for continued evaluation because the prior desk review found its standards-based OIDC model and documented web/API integration direction compatible with CareBridge's target architecture. This is not a procurement decision, production approval, or finding of legal compliance. Whether its current service, contract, operational controls, and data locations meet CareBridge's requirements remains unverified.

Keep the identity provider limited to authentication credentials, authentication factors, sessions, and minimal account/security attributes. CareBridge remains authoritative for internal user UUIDs, exact external identity mappings, patient records, memberships, authorization, and audit policy. Do not send clinical records, documents, extracted text, diagnoses, medications, or other clinical content to an identity provider.

Auth0, Supabase Auth, Clerk, and self-hosted Keycloak remain comparison candidates. Supabase, Keycloak, and self-hosted ZITADEL may be reconsidered if verified regional or operational requirements favor them. No provider automatically enforces CareBridge patient authorization or PostgreSQL RLS.

## 2. Selection criteria

Evaluate providers against the following requirements using current product documentation, a technical proof of concept after approval, and contractual evidence:

| Area | CareBridge requirement |
|---|---|
| Protocol | OIDC/OAuth flow appropriate for a web client and a separate API resource server; exact issuer and audience configuration. |
| API token verification | Asymmetric signing where available, published trusted JWKS, documented rotation behavior, stable key identifiers, and a supported fail-closed verification pattern. |
| Web integration | Authorization Code flow with PKCE, server-side callback/session handling, state/CSRF protections, and no secrets in browser bundles. |
| Factors and recovery | Required MFA/passkey options, enrollment and recovery controls, administrator protections, and usable audit signals; verify exact tier and configuration. |
| Session control | Understand refresh/access-token lifetimes and what revocation does to already-issued self-contained access tokens. Decide whether sensitive operations need an online session/revocation check. |
| Audit | Required event types, export/API access, integrity, availability, and retention. Provider events complement but do not replace CareBridge authorization logs. |
| Data and contract | Data categories, processing locations, backups, telemetry, subprocessors, support access, contract/DPA, breach terms, deletion behavior, and transfer terms established in writing. |
| Cost and operations | Current price units and plan gates, support, non-auth platform costs, availability, operational staffing, backup/upgrade burden, and migration effort. |
| Portability | Ability to retain internal UUIDs and exact `(issuer, subject)` mappings independently of provider-specific user identifiers and claims. |

## 3. Candidate comparison (questions, not verified endorsements)

The table summarizes evaluation dimensions to investigate. It is not a current feature, price, region, security certification, or legal-compliance statement. Confirm details directly with providers and applicable contracts.

| Candidate | Potential fit to validate | Material questions and trade-offs |
|---|---|---|
| **ZITADEL Cloud** | Standards-oriented OIDC; prior desk review identified provider documentation relevant to FastAPI/JWKS and Next.js integration. | Confirm the exact current regions and which data categories each covers; contract, subprocessors, event retention/export, session revocation semantics, support access, plan limits, and total price. Confirm required MFA/recovery controls and API audience configuration. |
| **Auth0** | Mature OIDC ecosystem and established web/API integration materials. | Confirm relevant plan gates, pricing units, tenant/data-region options, logs/export retention, session controls, API audience behavior, support terms, and contract requirements. |
| **Supabase Auth** | May fit teams considering a broader Supabase platform and its web integration tooling. | Assess platform coupling and whether identity data shares project infrastructure; verify project/auth data placement, subprocessors, plan limits, audit retention, token profile, key rotation, and whether the selected architecture can keep clinical data appropriately separated. |
| **Clerk** | May reduce Next.js UI/session integration effort. | Verify the intended role as OIDC provider/resource-server issuer for this architecture, API audience/token template, session token semantics, MFA/recovery features and plan, regional choices, event retention, and export. |
| **Keycloak (self-hosted)** | Greater control over deployment and configuration if operated by CareBridge. | No provider-hosted residency conclusion follows from self-hosting. CareBridge would own hosting, patching, HA, backups, key rotation, monitoring, recovery, incident response, and administrative security. Estimate staffing and hosting evidence before comparing total cost. |
| **ZITADEL (self-hosted)** | Potential alternative if its software and operating model meet requirements and CareBridge needs direct hosting control. | Validate software capabilities, support model, hosting location, patching/availability responsibilities, backups, telemetry, and total operating cost. Cloud service terms do not establish self-hosted behavior. |

Do not compare a SaaS fee with self-hosted software cost alone. Include infrastructure, staffing, support, backup, monitoring, recovery, security response, and any required contractual features.

## 4. Authentication responsibilities and flow

The detailed database behavior is specified in [database-security-design.md](database-security-design.md). The intended boundary is:

1. **Browser login:** Next.js initiates the OIDC Authorization Code flow with PKCE. Bind OAuth `state` to the initiating browser session and validate it at the callback for callback/CSRF protection. Validate OIDC `nonce` in the ID-token flow where it was issued and is required. Keep confidential credentials server-side; use appropriately secured session cookies.
2. **ID token:** Validate the ID token for the web client as required by the selected OIDC flow, including signature, issuer, intended client audience, time claims, and nonce. An ID token is not a bearer credential for the CareBridge API.
3. **API access token:** FastAPI independently validates every access token presented to it: signature using trusted issuer JWKS; pinned allowed algorithm; exact configured issuer; CareBridge API audience; expiration and not-before; and a recognized `kid` matched to a trusted key. It may refresh JWKS on an unknown `kid` using bounded logic. If the key or token cannot be validated, fail closed. Validate any required scopes/claims for the selected provider and token profile. Do not require an OIDC nonce in the access token unless the selected protocol provides and requires it.
4. **Identity resolution:** Only after API-token validation, FastAPI sends the exact validated `(issuer, subject)` to the restricted database lookup. The lookup returns the internal UUID and account status for that exact mapping, or no mapping. Email is never used for matching. Inactive accounts are denied.
5. **First login:** A no-mapping result may invoke the atomic fixed bootstrap operation in the database design. The operation internally generates user, patient, and membership identifiers and creates the user, external identity, patient, and initial active `self` membership together. Concurrent attempts converge on the exact unique identity; conflict/retry behavior is to resolve the exact identity again, never to create partial accounts or merge by email.
6. **Database authorization:** Once the internal user is resolved, FastAPI binds that UUID to transaction-local `app.user_id` for protected work. The value is never taken from a browser-supplied identifier. Application authorization remains necessary; RLS is additional enforcement.

### Trust limitation

The database does not validate the OIDC signature or prove that the API validated a token. The custom transaction-local GUC is not cryptographic proof: a caller able to execute arbitrary SQL with the runtime database credential can generally set it to another UUID. Exact-only lookup operations and limited SQL privileges reduce accidental exposure, but a compromised API process/database credential remains a threat. RLS or the GUC alone does not eliminate it. Stronger identity-to-database binding would require a separate design.

## 5. Data location, contract, and legal review

No residency conclusion is made here, including for Bangladesh, neighboring countries, backups, logs, telemetry, support access, or subprocessors. A provider's advertised region, if any, is not by itself evidence of where all relevant data is processed or stored and does not establish legal compliance.

Before provider approval, obtain current written answers and review them with qualified counsel on:

- What categories of identity, credential, session, log, support, backup, telemetry, and diagnostic data are stored or processed, and in which jurisdictions.
- All subprocessors and onward transfers; region selection scope and exceptions; government-access process; deletion and backup expiry behavior.
- Contract/DPA availability, roles and responsibilities, security incident notification, service availability/support commitments, audit rights, and applicable security terms.
- Applicable Bangladesh requirements and any international-transfer, consent/legal-basis, data-subject-rights, retention, breach, and health-data obligations.
- Whether the proposed minimal identity attributes and authentication events are appropriate, and how provider and CareBridge retention schedules interact.

These questions remain unresolved. Do not describe any candidate as Bangladesh-resident, legally compliant, or suitable for real patient data until evidence and qualified review support that conclusion.

## 6. Pricing and operational due diligence

Pricing, included user units, plan names, MFA/passkey availability, log retention, export, support, and regional features change. No prices or plan entitlements are asserted in this draft. Before procurement, record a dated quote or pricing-calculator result for expected active and returning users, environments, authentication factors, email/SMS, log export, support, and any platform/database charges. Clarify cancellation, data export, migration assistance, and deletion costs.

For any managed provider, evaluate outage behavior for login, refresh, JWKS retrieval, and session revocation. Define safe public-key cache bounds and what happens when trust cannot be refreshed. Offline JWT validation cannot instantly learn about revocation; select access-token lifetime and determine whether sensitive operations need an online session/version/revocation check.

For a self-hosted option, include operational ownership for updates, vulnerability response, high availability, key management, backups/restore drills, monitoring, protected administrator access, recovery abuse, and incident response. Self-hosting changes operational responsibility and possible placement; it does not create compliance by itself.

## 7. Recommendation and next decision gate

**Provisional recommendation: continue ZITADEL Cloud evaluation.** Its standards-oriented model appears directionally compatible with the intended architecture in the prior desk review. That is a candidate ranking for further diligence only. This draft does not verify current ZITADEL Cloud regions, contractual terms, subprocessors, pricing, legal suitability, or production fitness.

Keep Supabase Auth, Auth0, Clerk, and self-hosted Keycloak/ZITADEL as alternatives until the criteria in §2 are evidenced. Choose only after current technical documentation, a bounded integration proof of concept, pricing/contract review, residency/data-flow evidence, and qualified legal review. A provider decision does not authorize implementation; the database security design, token profile, recovery/linking policy, retention decisions, and role/grant design also require approval.

## 8. Reference starting points

These links are research entry points, not assertions that the linked material was revalidated for this draft. Recheck current documentation and contractual terms at decision time.

### ZITADEL

- [OIDC endpoints, JWKS, and rotation](https://zitadel.com/docs/apis/openidoauth/endpoints)
- [FastAPI integration example](https://zitadel.com/docs/sdk-examples/fastapi)
- [Hosted login and MFA](https://zitadel.com/docs/guides/integrate/login/hosted-login)
- [Passkeys and MFA configuration](https://zitadel.com/docs/guides/manage/console/default-settings)
- [Audit events / Event API](https://zitadel.com/docs/guides/integrate/external-audit-log)
- [Pricing](https://zitadel.com/pricing)
- [Cloud regions](https://zitadel.com/zitadel-cloud)
- [Cloud service description](https://zitadel.com/docs/legal/service-description/cloud-service-description)

### Other candidates

- [Auth0 pricing](https://auth0.com/pricing) · [Next.js quickstart](https://auth0.com/docs/quickstart/webapp/nextjs) · [FastAPI/JWT guide](https://auth0.com/docs/quickstart/backend/python) · [data residency](https://auth0.com/docs/get-started/architecture-scenarios/data-residency)
- [Supabase pricing](https://supabase.com/pricing) · [signing keys/JWKS](https://supabase.com/docs/guides/auth/signing-keys) · [Next.js server-side auth](https://supabase.com/docs/guides/auth/server-side/nextjs) · [regions](https://supabase.com/docs/guides/platform/regions) · [residency and transfers](https://supabase.com/legal/privacy-resources/data-residency-and-transfers-faq)
- [Clerk pricing](https://clerk.com/pricing) · [manual JWT verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification) · [Next.js quickstart](https://clerk.com/docs/quickstarts/nextjs) · [security and residency](https://clerk.com/security)
- [Keycloak OIDC endpoints](https://www.keycloak.org/securing-apps/oidc-layers) · [server administration](https://www.keycloak.org/docs/latest/server_admin/index.html) · [project](https://www.keycloak.org/)

### Repository context

- [Architecture blueprint](../../ARCHITECTURE_BLUEPRINT.md)
- [Current README](../../README.md)
- [Phase 1 documentation note](../README.md)

---

**Approval gate:** this is a comparative design draft for human review. No identity provider is approved for production. Resolve technical, pricing, contract, data-location, and legal questions, and obtain explicit approval before implementation.
