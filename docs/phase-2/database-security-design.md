# Phase 2.2 — Database Identity and Security Design

**Status:** final design draft for human review; not approved for implementation or production.
**Scope:** identity mapping, patient membership, audit metadata, account and patient lifecycle, and PostgreSQL row-level security (RLS) for the Next.js/FastAPI stack.
**Identity provider:** ZITADEL Cloud remains a provisional candidate only; see [identity-provider-evaluation.md](identity-provider-evaluation.md).

This document records design decisions and implementation requirements. It does not authorize schema changes, database objects, role/grant changes, or application changes. PostgreSQL 18 is a planning target, not a verified deployment fact.

## 1. Design decisions and boundaries

- Use stable internal UUIDs for CareBridge users and patients. Keep external authentication keys in a separate exact `(issuer, subject)` mapping. Email is not an identity key, authorization input, or automatic account-linking mechanism.
- Represent patient access through explicit memberships. In the initial release, only `self` membership is usable. Caregiver and representative roles are reserved schema concepts; they grant no access until separate authority, scope, consent, expiry, revocation, recovery, and audit rules are approved. There is no clinician/doctor role in this phase.
- FastAPI validates bearer access tokens, resolves the verified external identity, checks account status, and derives the internal user UUID. It binds that UUID as transaction-local `app.user_id` for protected database work. The browser never supplies the trusted internal identity.
- Application authorization remains required. RLS is a second boundary against query mistakes. A custom PostgreSQL GUC is not cryptographic proof of authentication: a compromised API process or arbitrary SQL execution with its database credential can set it. RLS and the GUC alone do not contain that threat.
- Ordinary runtime SQL cannot mutate memberships or freely create identity, user, and patient rows. It may execute only individually approved, narrowly scoped database operations for exact identity resolution, atomic bootstrap, and later separately reviewed identity or membership workflows.
- No protected table, RLS policy, function, trigger, role, grant, or migration is to be created until this draft is approved and the unresolved decisions in §10 are addressed.

## 2. Conceptual data model

The following is a design model, not executable migration SQL. UUIDs should be generated inside the approved bootstrap operation (or by a database generator it invokes), never accepted as caller-selected bootstrap targets. Use `timestamptz` in UTC and server-side timestamps. Status and role values should have database checks.

### `users`

`id UUID PRIMARY KEY`; `status` in `active`, `deactivated`, `deletion_pending`, `deleted`; created/updated/deactivated/deletion-requested/deleted timestamps. The internal ID is immutable. Do not store email here as a key. Any future contact data needs a separately protected, purpose-limited design.

### `external_identities`

`id UUID PRIMARY KEY`; `user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`; exact canonical `issuer`; exact case-sensitive `subject`; `linked_at`, `last_authenticated_at`, and nullable `unlinked_at`. Enforce a database uniqueness constraint on `(issuer, subject)` across both current and historical rows. Resolution returns a mapping only when it is linked and its account is active. An unlinked subject is not silently reusable for another account; recovery/relinking is a separate reviewed workflow. Never normalize or lowercase `subject`.

### `patients`

`id UUID PRIMARY KEY`; `created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT`; minimal optional user-chosen `display_label`; status in `active`, `archived`, `deletion_pending`, `deleted`; lifecycle timestamps. There is no `owner_user_id`: membership expresses access. `created_by_user_id` records provenance; it is not an ownership grant and does not imply transfer rights.

### `patient_memberships`

`id UUID PRIMARY KEY`; `patient_id` and `user_id` non-null restrictive foreign keys; role in `self`, `caregiver`, `representative`; status in `active`, `revoked`, `expired`; nullable `granted_by_user_id`; grant/revocation/expiry timestamps; optional controlled nonclinical reason code. Enforce at most one active row per `(patient_id, user_id)` and at most one active `self` row per patient with database uniqueness constraints/indexes. Preserve revoked rows according to the eventual retention policy. These constraints ensure *at most* one active self membership; bootstrap and its transaction guarantee the initial self membership exists at creation.

Membership role does not establish caregiver status, legal representative authority, or consent. Initial access policy accepts only `role = 'self'`. No ordinary runtime `INSERT`, `UPDATE`, or `DELETE` privilege is granted on this table.

### `audit_events`

Append-only event records should include an allowlisted event type, outcome, source, occurrence time, optional actor and patient references, opaque resource/request IDs, controlled reason code, and strictly allowlisted/size-limited metadata. Do not store credentials, tokens, authorization codes, session cookies, clinical values, uploaded content, or free-form request data. Actor and patient references may be nullable so history can survive approved erasure; do not cascade user or patient deletion into audit history. Audit events are not a second clinical record and are not tamper-proof against privileged database compromise.

## 3. Authentication, identity resolution, and bootstrap

These are separate trust steps. The database does not validate OIDC tokens.

### 3.1 OIDC validation by the application

FastAPI must validate each API **access token** before using any identity claim. Verify the signature with keys from the configured, trusted issuer JWKS; pin the allowed signing algorithm(s); require the exact configured issuer and CareBridge API audience; validate `exp` and `nbf`; and require a valid, known `kid` that selects a trusted JWKS key. Unknown `kid` may trigger a bounded JWKS refresh; if the key remains unknown or trust cannot be established, fail closed. Also validate any required token type, scopes, or authorization claims for the chosen provider/token profile. Never accept an ID token as the API bearer credential.

For the browser login flow, bind and validate OAuth `state` at the callback as a CSRF/callback correlation defense. Use Authorization Code with PKCE. Validate OIDC `nonce` in the ID-token flow that issued it (normally the web login callback). Do not demand an OIDC nonce claim in an API access token unless the selected protocol explicitly puts it there and requires its validation. Keep ID tokens and access tokens distinct: the ID token describes an authentication event to its client; the access token authorizes calls to its intended resource server.

### 3.2 Exact database identity resolution

After successful access-token validation, FastAPI takes the validated exact `(iss, sub)` pair. A restricted database operation may look up only that exact pair and return either “no mapping” or the mapped internal user UUID and account status. It must not accept email, partial matches, wildcards, lists, or a caller-selected internal UUID, and it must expose no identity listing or table-read capability. A matching but unlinked identity is not an active mapping. The API rejects inactive/deletion-pending accounts even when their token is otherwise valid. Rate-limit and audit attempts at the API boundary without logging the raw subject or token.

The operation is an exact lookup, not cryptographic proof to PostgreSQL that the caller validated a token. Its trusted caller is the API process. A transaction-local marker or custom GUC can reduce accidental misuse but is settable by that same database credential and must not be represented as a cryptographic boundary. A compromised API or arbitrary SQL under its credential can probe exact values; prevent table enumeration through privileges, keep the operation narrow, rate-limit, monitor, and include this in the threat model. If RLS would otherwise hide the pre-login rows, implement resolution as one fixed `SECURITY DEFINER` lookup operation: its separate `NOLOGIN` owner receives only the minimum `SELECT` rights on identity and user status data and the narrowly justified `BYPASSRLS` capability. It owns no tables, has no DDL rights, cannot be assumed by runtime, and exposes no operation beyond exact pair resolution. Revoke `PUBLIC` execution and grant only the fixed operation to runtime. Do not reuse the membership-predicate or bootstrap owner.

### 3.3 Atomic first-login bootstrap

If exact resolution reports no mapping, FastAPI may invoke one approved bootstrap operation with only the exact validated `issuer` and `subject`. The database operation generates the internal user UUID, patient UUID, external-identity row ID, and membership ID itself; the caller cannot choose any of these IDs or a role, status, owner, or grant target. It performs one atomic unit:

1. Create one active user.
2. Create the exact external identity mapping to that user.
3. Create one minimal patient row with `created_by_user_id` set to that user.
4. Create exactly one active `self` membership for that user and patient.

The database enforces permanent uniqueness for `(issuer, subject)`, plus the active membership uniqueness invariants in §2. The function/operation should serialize bootstrap attempts for the same exact pair (for example, a transaction-scoped advisory lock derived from the pair) and then re-check the mapping while holding that lock. This prevents the common concurrent first-login race: the first call creates the complete set, and a waiting call observes the existing mapping and returns a conflict/already-provisioned outcome without creating another patient. The unique constraint remains authoritative if another writer or an unexpected race bypasses the serialization path.

On a uniqueness conflict or any failure, the bootstrap statement must fail atomically so none of its user, identity, patient, or membership inserts persist. The caller rolls back the transaction, then performs restricted exact resolution in a fresh transaction. If the identity now resolves, continue with that UUID/status; if not, return a generic retryable failure and do not loop indefinitely. If the identity key exists historically but is unlinked, do not create another account or reassign it automatically; return a non-enumerating conflict requiring the separately approved recovery/linking process. A network timeout has an unknown outcome: retry by exact resolution first, and only call bootstrap again if no mapping exists.

Grant the runtime credential `EXECUTE` only on this fixed bootstrap operation. It receives no direct writes to `users`, `external_identities`, `patients`, or `patient_memberships` for this workflow. Revoke `PUBLIC` execution; fix and review the operation owner, safe `search_path`, schema-qualified references, allowed inputs, and effective grants. If implemented as `SECURITY DEFINER`, use a separate dedicated `NOLOGIN` owner with only the minimum exact-pair `SELECT` and fixed insert privileges required for this workflow. If RLS would otherwise block those operations, this isolated owner needs `BYPASSRLS`; it must not own protected tables, have schema/DDL rights or unrelated privileges, or be assumable by runtime. Do not reuse the identity-resolution or RLS membership predicate owner. The database operation cannot independently authenticate the OIDC token; the API remains its trust boundary.

Identity linking/unlinking and account merging are not part of bootstrap. Linking requires an authenticated target account, fresh proof of control over the added identity, recent reauthentication, CSRF protections where browser initiated, and audit. Never link or merge accounts because email or display name matches.

## 4. Membership authorization model

“Own” means a patient for which the user has an active membership. It does not arise from creating a row.

| Capability | `self` | `caregiver` | `representative` |
|---|---|---|---|
| Read patient profile or records | Yes, subject to product scope | Disabled; future explicit scope | Disabled; future explicit scope and authority evidence |
| Add/correct patient-provided records | Yes, subject to product scope | Disabled | Disabled |
| Manage own login identities | Own user only | Own user only | Own user only |
| Grant/revoke memberships | No | No | No |
| Access audit history | Own security events only if separately approved | No by default | No by default |
| Clinician/doctor access | Not in this phase | Not in this phase | Not in this phase |

Enabling any non-self role requires a separate design for evidence, consent, scope, expiry, revocation, notification, disputes, recovery, and abuse monitoring. Membership alone must not claim legal authority.

## 5. RLS and transaction identity context

Enable and force RLS on `users`, `external_identities`, `patients`, `patient_memberships`, audit rows as appropriate, and every patient-scoped table and partition introduced later. Use command-specific policies, default deny, both `USING` and `WITH CHECK` for writes, column grants/projections where row visibility is insufficient, and explicit patient filters in service queries. Review the effective OR-composition of all policies. Referential integrity checks can reveal limited existence information; return generic errors where enumeration is a concern.

For an authenticated request, FastAPI opens one transaction, resolves the validated external identity as described above, and sets `app.user_id` with a parameterized `set_config('app.user_id', :internal_user_id, true)` before any protected query. The value is the canonical internal UUID from exact resolution, never a browser body/header/query value or raw provider subject. The `true` makes the value transaction-local; commit/rollback ends it. Do not use session-level `SET` or set identity before authentication. Health checks without protected-table access need no user context.

Use one explicit transaction per protected unit of work. Bind the context once at its outer boundary; nested service functions share that transaction and cannot switch identities. On errors, roll back before returning the connection. Background work opens its own transaction and establishes an intentional service context; it never inherits a web request session. Keep SQLAlchemy rollback-on-return enabled, while relying on transaction-local context and transaction completion as the security property.

### 5.1 Policy scope

- **`patients`:** reads and ordinary updates require an active authorized membership and an eligible patient status. Insert is available only through the approved bootstrap operation. Runtime cannot delete; archival/purge is a controlled lifecycle operation.
- **`patient_memberships`:** a user may read only their own membership rows if needed. Runtime has no direct mutation privileges. Future access changes require a separate fixed authorization operation with actor, target, allowed transition, scope, and audit checks. The membership policy must not query `patients` or call a path that recurses back to the patient policy.
- **`users` and `external_identities`:** runtime access is minimized to own-row projections and narrow fixed operations. Identity resolution and linking do not grant broad table reads or writes.
- **`audit_events`:** runtime may insert only constrained events with actor bound to context, except a separate approved system/anonymous path. No runtime update/delete. Reads are deny-by-default or through a narrowly scoped, audited user-filtered service operation.
- **Other patient-scoped tables:** require their own RLS policies, grants, and tests before use. RLS is row-level, not column-level. Review views, functions, triggers, jobs, partition parents/children, and maintenance paths explicitly.

### 5.2 Non-recursive membership predicate

The patient policy calls only this conceptual helper:

```sql
app_private.has_active_patient_membership(patient_id_text)
```

The helper accepts only the patient ID as text. It obtains the actor UUID internally from transaction-local `app.user_id`; strictly validates the patient identifier and actor UUID using safe parsing that catches invalid UUID input; and returns false for missing, empty, malformed, or null context/argument. It verifies that the actor exists as an active user and has a matching membership with `status = 'active'`, `role = 'self'` for the initial release, and no expiry or an expiry later than transaction time. It returns only a boolean and uses no dynamic SQL. It does not read the `patients` table.

The patient RLS policy separately checks the patient's own status directly, in addition to calling this helper for membership authorization. Membership policies must not query `patients`; scope their rows only to the validated transaction actor. Thus the patient policy checks its own row status and calls the predicate, the predicate reads only the required `users` and `patient_memberships` rows, and neither table's policy calls back to `patients`. This avoids recursive RLS evaluation.

Use a dedicated `NOLOGIN` function-owner role, distinct from runtime, table/schema owner, migration role, bootstrap-operation owner, and retention worker. Because PostgreSQL RLS applies under a `SECURITY DEFINER` function owner's identity, this isolated owner needs `BYPASSRLS` to read the required protected rows without re-entering their policies. That capability is privileged: give it no login credential, no runtime role-membership/`SET ROLE` path, no table ownership, no schema/DDL rights, no unrelated data privileges, and ownership of only this reviewed predicate. Grant only the necessary `SELECT` rights on the two required tables. If the platform cannot safely isolate this role, do not weaken runtime privileges; design and review a different non-recursive architecture.

Set a fixed safe `search_path` (prefer `pg_catalog`) and schema-qualify every referenced relation and function. Revoke `EXECUTE` from `PUBLIC`; grant execution only to the runtime role as needed for policy evaluation. The helper does not grant table privileges or expose row contents. Runtime cannot assume its owner or choose another actor. Review owner, effective grants, function settings, error behavior, and all policy paths before implementation.

### 5.3 GUC spoofing boundary

The custom GUC is not intrinsically authenticated. Any caller able to issue arbitrary SQL using the runtime credential can generally set `app.user_id` to another UUID. Validate tokens in FastAPI; derive context only from resolved internal IDs; use bound parameters and no dynamic SQL; prohibit user-supplied SQL; minimize injection surfaces and runtime privileges; monitor authorization failures. A compromised API process/database credential is outside what RLS or this GUC can contain. Stronger database identity binding would require a separate design.

## 6. Database roles and privilege boundaries

Role names below are conceptual; create none until implementation approval.

| Role | Design boundary |
|---|---|
| Schema/table owner | `NOLOGIN`; owns protected schema objects. Not used by API or routine jobs. `FORCE ROW LEVEL SECURITY` applies to protected tables for ordinary owner access, but does not constrain superusers or `BYPASSRLS`. |
| Migration role | Separate deployment-only credential with only controlled migration/ownership authority. Not available to the application. Review every migration and its effective role switching. |
| Runtime application role | `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, no `CREATEROLE`, `CREATEDB`, schema `CREATE`, protected-table ownership, or membership that permits assuming a privileged role. Only required schema `USAGE`, column/table privileges, and allowlisted function execution. No direct membership writes; no arbitrary identity/bootstrap writes; no `TRUNCATE`, DDL, or unnecessary `REFERENCES`. |
| Identity-resolution owner | If exact resolution uses `SECURITY DEFINER`, separate `NOLOGIN` owner with only the minimum `SELECT` rights on identity and user-status rows and narrowly justified `BYPASSRLS`; no table ownership, DDL, login, unrelated data privileges, or runtime `SET ROLE` route. Owns only the reviewed exact-pair lookup operation. |
| Membership predicate owner | Dedicated `NOLOGIN`, `BYPASSRLS` as narrowly justified in §5.2; no table ownership, DDL, login, or runtime `SET ROLE` route; only required read privileges and the reviewed helper function. |
| Bootstrap operation owner | If `SECURITY DEFINER` is used, a separate `NOLOGIN` owner with only the minimum exact-pair lookup and fixed atomic insert rights; narrowly isolated `BYPASSRLS` if required by protected tables. No table ownership, schema DDL, unrelated data access, or runtime `SET ROLE` route. It is distinct from the identity-resolution and predicate owners. |
| Audit reader / retention worker | Optional isolated, audited roles. Audit reads and lifecycle deletion are narrowly scoped. Any cross-patient elevated path must be an explicit reviewed operation; no broad routine runtime bypass. |

Revoke default `PUBLIC` schema/table/function rights where relevant. Review effective privileges and role memberships, not only direct grants. Use TLS and protected secret injection/rotation. No application connection may use a superuser, table owner, `BYPASSRLS`, or a role able to assume one.

## 7. Account, membership, patient, and audit lifecycle

These operations are distinct and must not be collapsed into “delete account.” Retention durations, legal holds, and legal duties remain unresolved pending qualified legal review and product decisions.

- **Account deactivation:** change user status to `deactivated`, deny new requests even for valid tokens, revoke local sessions, and make memberships ineffective. This does not delete patient records, identity history, or audit events.
- **Identity unlinking/deletion:** after reauthentication and a viable alternative sign-in or completed deletion workflow, mark an identity unlinked through a fixed audited operation. Do not silently reassign its `(issuer, subject)` key. Provider-side session revocation does not automatically unlink the local mapping. Retain or purge identity history only under the approved retention policy.
- **Membership revocation:** set status/revocation time in one audited, authorized operation. Later transactions lose access; define in-flight transaction semantics and recheck authorization for long-running jobs. Revocation does not delete the patient record.
- **Patient record retention/deletion:** deactivating or deleting a login does not automatically delete a patient record. Never transfer access or ownership implicitly to a caregiver or another member. If no authorized membership remains, the patient record becomes inaccessible to ordinary users and requires a separately approved, audited retention workflow. Archive/purge must cover relational rows, documents, derived text, summaries, indexes, queues, caches, and object-store versions after applicable holds and retention periods.
- **Restrictive FKs and provenance:** `ON DELETE RESTRICT` on `created_by_user_id` and membership/identity relationships intentionally prevents careless physical user deletion while dependent records remain. Preserve a minimal user tombstone/provenance row while required; it records historical creation, not continuing access. If qualified review permits eventual erasure, an explicit workflow must first address dependents and provenance without silently rewriting historical attribution.
- **Audit events:** retain independently from account login state. Preserve accurate historical attribution; where erasure is approved, null direct actor references or use a separately approved minimal pseudonymous tombstone rather than rewriting events as another person's actions. Audit detail must be minimized and access controlled.
- **Backups:** document backup expiry and ensure restored snapshots reapply deletion tombstones and queued purges before normal access resumes. Do not promise immediate removal from immutable backups; publish actual expiry behavior after it is defined.

Retention periods, legal hold rules, what patient records must be kept, whether/when identity history may be erased, and backup expiry are unresolved and require qualified legal review before implementation or launch.

## 8. Audit event requirements

Capture meaningful authentication outcomes, authorization denials, patient/resource access, membership changes, account/identity changes, and administrative actions using allowlisted fields: actor/target opaque IDs where appropriate, event type, outcome, timestamp, source, request correlation ID, and controlled reason code. Do not capture tokens, passwords, authorization codes, cookies, request bodies, clinical values, uploaded contents, or raw subject values. Avoid free-form metadata and query-string logging. Define access, event-class retention, purge/pseudonymization, legal hold, backup, and integrity-protected export requirements before launch. IdP event delivery needs its own authenticity, replay, ordering, failure-monitoring, and retention design.

## 9. Required verification plan (implementation phase)

Use a disposable database populated only with synthetic identities, UUIDs, and labels. Execute security tests as the actual non-owner runtime role with only intended grants; owner/superuser tests do not validate RLS. Tests are requirements for a later implementation phase and have not been run as part of this design review.

1. Cross-patient isolation: users A and B can access only their respective self membership patient; cross-read/write attempts fail or return no rows. Test every patient-scoped table and API IDOR path.
2. Context fail-closed: missing, empty, malformed, null, and invalid `app.user_id` contexts deny reads/writes; a forged browser user ID does not alter the verified principal.
3. Membership lifecycle: deactivated user, revoked membership, expired membership, non-self role, and archived/deletion-pending patient are denied. Test expiration boundaries using database transaction time.
4. Pool isolation: force reuse of a small pool; after commit, rollback, cancellation, and exception, identity A is absent in a context-free transaction and cannot leak into B's transaction.
5. Atomic bootstrap: same exact `(issuer, subject)` in concurrent first-login requests yields at most one user, mapping, patient, and active self membership. A waiting/retried request resolves the existing mapping. Same email with different subjects remains separate. Historical unlinked mapping cannot be reassigned.
6. Bootstrap rollback: inject failure at each insert step and a uniqueness conflict; verify no partial/orphan user, identity, patient, or membership remains. Timeout retry resolves first and never creates duplicates.
7. Exact identity resolution: only the exact pair is queried; no email, wildcard, prefix, list, or enumeration API is available. Check generic not-provisioned response and API rate limiting/audit behavior.
8. Privileges and ownership: inspect effective grants, role memberships, `rolsuper`, `rolbypassrls`, object ownership, `FORCE ROW LEVEL SECURITY`, function configuration, `PUBLIC` execution, and schema rights. Runtime cannot mutate memberships directly, create arbitrary objects, bypass RLS, `SET ROLE` to privileged owners, replace functions, or read unfiltered protected rows.
9. Run helper tests as actual runtime role: helper accepts only patient ID; actor comes from GUC; active user, `self` active unexpired membership passes; missing/malformed context, inactive user, other patient, revoked/expired membership, and non-self role fail; policies do not recurse.
10. Audit: runtime cannot update/delete events or read other users' events; metadata allowlist is enforced and logs contain no credentials or clinical values.
11. Lifecycle: test deactivation, unlinking, membership revocation, retained patient with no active member, approved purge, pseudonymization, backup restore/tombstone replay, and object-store cleanup.

## 10. Unresolved decisions before implementation

1. Qualified legal review of Bangladesh requirements, international transfers, patient-record retention/deletion, identity/audit retention, legal holds, pseudonymization, and backup expiry.
2. Provider selection and contractual due diligence; ZITADEL Cloud remains provisional. Verify actual data categories/regions, subprocessors, terms, pricing, event retention/export, and revocation behavior. See provider evaluation.
3. Evidence and authorization workflow for any caregiver/representative access; disabled in this phase.
4. Patient archive, deletion, orphan-record support, and future access-regrant policy, without implicit ownership transfer.
5. Audit visibility, access approvals, event-class retention, purge/export, and break-glass administration.
6. Threat-model decision on whether the GUC/runtime-credential trust boundary needs a stronger database identity binding design.
7. Actual PostgreSQL version, extension availability, managed-service support for isolated `BYPASSRLS` function owner, TLS, backups, and migration process.
8. Account recovery/contact needs and how verified contact data would be stored separately from identity keys.

## 11. Approval gate

This is a final design draft for human review only. It is not production-approved and is not authorization to implement. No application code, configuration, migration, database object, role, grant, existing data, or legacy asset may be changed under this document alone. Resolve the open items, review the exact SQL and API behavior, and obtain explicit implementation approval before proceeding.
