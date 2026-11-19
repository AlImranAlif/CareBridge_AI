# CareBridge AI — Target Architecture and Implementation Blueprint

**Status:** proposal for review; implementation has not started.  
**Scope:** architecture for a patient-owned personal health record (PHR) built with Next.js, FastAPI, PostgreSQL, SQLAlchemy, Alembic, and modular document intelligence services.

## 1. Executive proposal

Build a modular monolith first: one versioned FastAPI application, one Next.js application, one PostgreSQL database, and a separate background worker for document processing. Keep document blobs in private object storage, not PostgreSQL. Use an external OpenID Connect identity provider or a maintained authentication library, enforce patient ownership in every API query, and add PostgreSQL row-level security (RLS) as defense in depth. Documents and extracted facts remain the source of truth; AI output is a reviewable, provenance-linked convenience layer and must not diagnose or recommend treatment.

This is a target design, not a claim that the prototype is production-ready, legally compliant, clinically validated, or suitable for real patient data. Hosting jurisdiction, applicable privacy law, identity provider, retention policy, and operational owner must be decided before deployment with real records.

## 2. Existing application assessment (read-only inspection)

Inspected `app.py`, `README.md`, `requirements.txt`, and the SQLite database metadata. No patient names, extracted text, or upload names were printed or used as test data.

| Area | Current state | Reusable capability / gap |
|---|---|---|
| UI | Single Streamlit app with Add records, Health timeline, Privacy/project notes | Product flow and copy can guide Next.js screens; UI is not an API/client separation |
| Persistence | SQLite `documents` table; 7 rows; 9 columns: `id`, `patient_name`, `filename`, `doc_type`, `doc_date`, `extracted_text`, `extracted_json`, `created_at`, `sha256` | Data concepts and hashes inform the new model; patient name is not an identity/authorization key |
| Source files | 7 files under `data/uploads` | Preserve in place. Names/extensions were not inspected in output; contents were not opened |
| PDF/OCR | PyMuPDF text extraction; if no text layer, optional Tesseract with English/Bengali; Pillow image loading | Extraction behavior and language support can be wrapped behind replaceable adapters; add page-level provenance, limits, failure states, and evaluation |
| Classification | Keyword rules return Prescription, Laboratory report, Discharge summary, or Other | Reuse as versioned baseline classifier with confidence and human correction |
| Lab fields | Regex candidates for Hemoglobin, Glucose, Creatinine, and WBC with units and nearby excerpt | Reuse as candidate extraction rules; add normalized units, page/offset evidence, confidence, review status; never infer clinical meaning |
| Timeline | Sorts documents by extracted date, then unknown dates last | Reuse date-first interaction; distinguish document date, upload time, and date certainty |
| Summary | Deterministic template over uploaded record labels and candidate values; downloadable text | Reuse source-first constraints; add explicit citations, generation version, review lifecycle, and stale invalidation |
| Safety | README explicitly calls this a demonstration; no production authentication, encryption-at-rest, cloud access controls, consent, or clinical validation | Keep warnings; security and governance are release gates, not UI-only disclaimers |

SQLite integrity check passed. The seven database records and seven source files were not modified, migrated, or opened. Existing demo fixtures in code are synthetic and are not a substitute for a labeled evaluation corpus.

### Reuse strategy

Extract the current `classify`, `extract_text`, and `extract_fields` behavior into service interfaces, preserving the current behavior as a baseline adapter and adding unit fixtures made exclusively from authored synthetic documents. Do not import `app.py` from production services because it couples UI, filesystem, database initialization, processing, and persistence. Keep current SQLite and uploads as a separately preserved legacy set. A future import is an opt-in, offline, dry-run-first job with a manifest, row/file counts, checksums, validation report, duplicate policy, and explicit approval; it copies rather than moves and never changes the old SQLite database or source files.

## 3. Target architecture

```text
Browser
  └─ Next.js App Router (TypeScript, Tailwind; server-rendered pages + small client widgets)
       └─ server-only data access layer / BFF (session cookie; minimal DTOs)
            └─ FastAPI REST API (/api/v1; Pydantic schemas; generated OpenAPI)
                 ├─ AuthZ + application services
                 ├─ SQLAlchemy 2.x ─ PostgreSQL (Alembic migrations; tenant/patient RLS)
                 ├─ private object storage (quarantine / clean document objects)
                 └─ job queue ─ processing worker
                                ├─ file validation / malware scan
                                ├─ PDF text extraction / OCR adapters
                                ├─ classification and field candidate extraction
                                └─ grounded summary generation
```

Keep domain logic independent of HTTP, SQLAlchemy, OCR libraries, and any LLM provider. Start with a modular monolith and one worker process; split services only when measured load, team boundaries, or independent deployment needs justify it. Use managed secrets, TLS between services, encrypted database/storage volumes, encrypted backups, centralized metrics, and redacted structured logs. Never log document bytes, extracted text, tokens, or health values.

### Suggested repository structure

```text
carebridge/
├─ apps/
│  ├─ api/
│  │  ├─ app/main.py                 # FastAPI construction, middleware, routers
│  │  ├─ app/api/v1/{router.py,auth.py,patients.py,documents.py,timeline.py,summaries.py,jobs.py}
│  │  ├─ app/core/{config.py,security.py,logging.py,errors.py}
│  │  ├─ app/db/{base.py,session.py,models/}
│  │  ├─ app/schemas/                 # Request/response DTOs
│  │  ├─ app/services/                # Use cases and authorization-aware orchestration
│  │  ├─ app/repositories/             # Persistence interfaces/adapters
│  │  ├─ app/storage/                  # Object-store adapter, quarantine and lifecycle
│  │  ├─ app/processing/               # Pipeline contracts, task dispatch/status
│  │  └─ alembic/{env.py,versions/}
│  ├─ worker/
│  │  ├─ app/worker.py
│  │  └─ app/tasks/{validate.py,extract.py,classify.py,summarize.py}
│  └─ web/
│     ├─ app/(auth)/{login,register}/
│     ├─ app/(patient)/{dashboard,documents,timeline,summary,settings}/
│     ├─ app/api/                     # Narrow BFF routes only when useful
│     ├─ components/{shell,documents,timeline,forms}/
│     ├─ lib/{server-api,auth,dto,validation}/
│     └─ styles/
├─ packages/contracts/                # Generated OpenAPI client/types; no secrets
├─ tests/{unit,api,integration,security,e2e,fixtures/synthetic}/
├─ infra/{local,deploy,observability}/
├─ docs/{architecture,security,runbooks,decisions}/
└─ pyproject.toml / package.json / lockfiles
```

## 4. Database design and relationships

Use UUID primary keys, UTC timestamps (`timestamptz`), explicit foreign keys, unique constraints, and indexed ownership/date columns. Use SQLAlchemy 2.x typed mappings and Alembic for every schema change. No database field should conflate authentication identity with patient display name.

| Entity | Important fields and purpose |
|---|---|
| `users` | `id`, normalized unique login/email or external `issuer` + `subject`, status, created/updated timestamps. Store no plaintext password. If local credentials are chosen, use a maintained password hashing library and account recovery controls. |
| `patients` | `id`, `owner_user_id -> users.id`, optional display label, locale/time zone, timestamps. MVP invariant: one owner per patient. |
| `documents` | `id`, `patient_id`, opaque `storage_key`, original filename as untrusted display metadata, detected media type, byte size, SHA-256, status, document type + confidence, document date + precision/source, uploaded/created timestamps, retention/deletion state. |
| `document_versions` | `id`, `document_id`, immutable object key/hash, version number, created by/time, replacement reason. Preserve original content; corrections create a version. |
| `processing_runs` | `id`, `document_version_id`, pipeline/version, status, started/finished times, safe error code, retry count, model/provider configuration reference (no secret), idempotency key. |
| `document_pages` | `id`, `document_version_id`, page number, extracted text, extraction method, language, OCR confidence/quality metrics, page dimensions. Access is patient-scoped. |
| `extracted_facts` | `id`, `patient_id`, `document_version_id`, page, fact type/code, raw label/value/unit, normalized value/unit if safe, confidence, text offsets or excerpt, status (`candidate`, `confirmed`, `rejected`), reviewer/time. Store candidate observations; do not derive a diagnosis. |
| `summaries` | `id`, `patient_id`, status, content/structured blocks, generated time, generator/prompt version, input watermark/hash, reviewed time and reviewer. Rebuild or mark stale after source changes. |
| `summary_citations` | `summary_id`, `document_version_id`, optional `extracted_fact_id`, page, character offsets/snippet hash. Every factual statement should map to one or more citations. |
| `sessions` / `refresh_tokens` | Hashed opaque token identifier, `user_id`, issue/expiry/revocation times, device metadata minimized. Only needed if session lifecycle is application-managed. |
| `audit_events` | Actor, patient scope, action, resource type/id, outcome, timestamp, request/correlation ID, minimal metadata. Append-only permissions; never include clinical content. |
| `share_grants` (later phase) | Patient, recipient/scope, expiration, revocation, consent record and purpose. No sharing enabled until consent and access model are reviewed. |

Relationships: `users 1—N patients`; `patients 1—N documents`, `extracted_facts`, `summaries`, `audit_events`; `documents 1—N document_versions`; `document_versions 1—N processing_runs` and `document_pages`; `document_versions 1—N extracted_facts`; `summaries 1—N summary_citations`; citations reference immutable document versions and optionally a fact. Keep file bytes out of the relational database.

**Legacy mapping:** `patient_name` maps only to a patient display label after an owner is explicitly established; `filename` to original display metadata; `doc_type` to a proposed classification; `doc_date` to a nullable date plus precision/source; `extracted_text` to page text only if page mapping can be reconstructed (otherwise one legacy text block); `extracted_json` to candidate facts with review state `candidate`; `created_at` to upload timestamp; `sha256` to integrity hash; `id` can be retained as an external legacy ID or mapped to a new UUID with a manifest. No auto-assignment to a real account.

## 5. Authentication, authorization, privacy

- Prefer a maintained OIDC identity provider using Authorization Code + PKCE; verify issuer, audience, signature, nonce/state, expiry, and account status. Do not build custom OAuth. If local login is required, use a maintained auth library, modern password hashing, verified recovery, rate limits, MFA option, and breached-password controls.
- Keep browser session credentials in `Secure`, `HttpOnly`, appropriately `SameSite` cookies; avoid browser local storage. Rotate/revoke sessions; short-lived access credentials and opaque, hashed, revocable refresh/session records if using refresh tokens. Apply CSRF protection to cookie-authenticated mutations.
- Enforce authorization at every FastAPI service/repository operation: derive owner from authenticated principal, scope every patient/document/fact/summary query by `owner_user_id`, and return indistinguishable not-found responses for inaccessible IDs. Never trust a patient ID supplied by the client without an ownership check. The UI is not an authorization boundary.
- Add PostgreSQL RLS to patient-owned tables as defense in depth. Use a non-owner runtime database role without `BYPASSRLS`; bind the authenticated owner ID transaction-locally; define `USING` and `WITH CHECK` policies in Alembic; test both allowed and denied reads/writes. RLS does not replace service checks, and table owners/superusers may bypass it.
- Minimize patient data; encrypt transit and storage/backups with managed keys and rotation; separate keys from data; keep secrets out of source and frontend bundles. Set no-store/private cache headers for PHI pages/API responses and disable shared caching of patient-specific output.
- Audit authentication, document access/download/deletion, sharing/consent, fact edits, summary generation/review, and administrative access. Restrict audit readers; establish retention/deletion and incident response before launch.
- No broad staff/admin access in initial scope. Support access, correction, export, deletion, and account closure workflows according to applicable policy/law. Legal review must determine the applicable jurisdiction, controller/processor/covered-entity/business-associate roles, breach duties, and retention obligations.

## 6. Document upload and processing workflow

1. **Authorize and reserve:** authenticated owner requests an upload; API checks patient ownership, allowed formats, declared size, quota, and idempotency. Return upload intent and a short-lived scoped upload destination or accept a streamed `UploadFile`. Use generated object keys; never use the supplied filename as a path.
2. **Quarantine:** write to private quarantine storage with encryption; enforce reverse-proxy and application limits, rate/quota limits, and CSRF protections. Validate extension allowlist, file signature/content, actual size, parser safety, and malware scan. Reject encrypted, malformed, oversized, or unsupported files with a safe reason.
3. **Finalize:** calculate SHA-256 while streaming; persist document/version and an outbox/job record in one database transaction. Move/copy to clean storage only after validation. Never expose public object URLs; authorized download uses an application stream or very short-lived signed URL after a fresh access check.
4. **Queue:** worker claims idempotent job and sets `processing`; retries are bounded; safe errors and timestamps are persisted; dead-letter/manual retry path is observable. API returns `202 Accepted` and job status rather than waiting for OCR.
5. **Extract:** PDF text layer first, OCR only for image/scanned pages; images get size/pixel limits. Run parsers in resource-limited isolated workers. Record per-page method, language, text, OCR metrics, and text coordinates/offsets. Preserve original source and extraction versions.
6. **Classify and extract fields:** apply current rules as a baseline, return confidence and evidence, accept `unknown`; extract only supported candidate observations with units and exact page/offset evidence. Date parser stores uncertain/missing date as null plus reason, never a fake sentinel date.
7. **Review and timeline:** present original document alongside candidate facts; user can confirm/correct/reject candidates. Preserve who changed what and prior value. Failed/low-quality processing remains visible and retryable.
8. **Retention and deletion:** deletion is an audited workflow that revokes access immediately, removes object versions and derived content per retention policy, and records a minimal tombstone. Backups expire under a documented schedule; deletion semantics are communicated accurately.

OWASP file handling guidance supports extension allowlisting, content validation instead of trusting the supplied MIME header, generated filenames, size limits, authenticated upload, storage outside the web root, and malware/sandbox scanning. These are requirements for the planned implementation, not evidence that the current prototype has those controls.

## 7. OCR and document intelligence pipeline

Define contracts: `FileValidator`, `TextExtractor`, `OCRProvider`, `DocumentClassifier`, `FactExtractor`, `SummaryGenerator`, `ObjectStore`, `JobQueue`. Each adapter returns typed results and safe diagnostic codes. Preserve the current PyMuPDF/Tesseract/regex implementation behind interfaces first, then improve independently.

`received → quarantined → validated → queued → extracting → classifying → extracting_facts → needs_review → ready` with terminal `rejected`/`failed`; transitions are persisted and idempotent. Reprocessing creates a new run/version and does not silently overwrite reviewed data. Record pipeline name/version, OCR engine and language-pack version, model identifier/configuration (not credentials), timestamps, and outputs needed for provenance.

OCR quality work: language selection per document/page (English/Bengali), orientation/deskew/image normalization with original preservation, page-level confidence, low-confidence flag, timeout/page-count/pixel caps, and a manual review path. Compare text-layer and OCR output only on synthetic or properly authorized/de-identified evaluation material. Track classification precision/recall by class, field precision/recall and unit accuracy, date accuracy, OCR page quality, processing success/failure, latency, duplicate detection, and confidence calibration. Thresholds are release decisions set before measuring; do not claim targets until measured.

## 8. Source-grounded medical summaries

Begin with deterministic templates over confirmed facts and document metadata. If an LLM is introduced later, treat extracted document text as untrusted input (including embedded instructions), prohibit tool execution, allowlist the fields it can use, and require structured output validated against a schema. The model may only select or paraphrase facts in a supplied evidence bundle; it cannot add medical knowledge, infer a diagnosis, or recommend treatment.

Each displayed assertion has citation IDs that resolve to document version, page, and exact source excerpt/offset, plus optional confirmed fact ID. Validate that every assertion has at least one citation and that cited values/date/unit match source facts. If evidence is missing or contradictory, state that records differ or omit the assertion. Label summary as generated, show generation time and source freshness, offer source navigation, and allow user feedback/review. Store generator/prompt version and input watermark; mark stale when a source changes. Avoid sending health data to third-party model providers unless data use, retention, location, contractual terms, and consent are approved. Keep summary generation asynchronous and auditable.

## 9. Patient health timeline and frontend structure

Next.js App Router with TypeScript, Tailwind, accessible component primitives, server components for initial reads, and client components only for interactions (filters, upload progress, review controls). A server-only data access layer calls FastAPI and emits minimal DTOs; never pass ORM rows or full extracted text to broad client component props. All route handlers/server actions validate input and repeat authorization checks. Avoid patient-data cache reuse across users.

Screens: sign-in/recovery; patient home with recent records and processing state; upload with requirements/progress; document list and detail (source viewer, extracted facts, review); chronological timeline; summary with clickable source citations; privacy/security settings and export/delete controls. UI should distinguish document date from upload date, show unknown/approximate dates honestly, allow type/date filters, and surface processing/review status. Responsive, keyboard operable, accessible labels/focus/error announcements, plain language, and consistent empty/error states.

## 10. API and representative schemas

Base path `/api/v1`; JSON UTF-8, UUID identifiers, UTC RFC 3339 times, consistent `{code, message, request_id}` errors, pagination with opaque cursor, idempotency key on create/finalize operations, and generated OpenAPI. Use explicit response models and never return storage keys, secret/session fields, or unreviewed extracted text unless the caller is authorized and the view requires it. Production API docs are access-controlled or disabled; the development schema remains generated and versioned.

| Method / path | Purpose | Typical response |
|---|---|---|
| `GET /health/live`, `GET /health/ready` | Liveness/readiness; no PHI | `200 {status}` |
| `GET /api/v1/me` | Current principal and minimal profile | `MeResponse` |
| `GET /api/v1/patients` | Owned patient profiles | cursor page |
| `POST /api/v1/patients` | Create patient profile | `201 PatientResponse` |
| `GET /api/v1/patients/{patient_id}` | Owned patient profile | `PatientResponse` |
| `POST /api/v1/patients/{patient_id}/documents` | Reserve/stream upload; ownership + quota check | `202 UploadAccepted` |
| `POST /api/v1/documents/{document_id}/complete` | Finalize direct upload and enqueue processing | `202 JobResponse` |
| `GET /api/v1/patients/{patient_id}/documents` | Filtered/paginated documents | `DocumentPage` |
| `GET /api/v1/documents/{document_id}` | Metadata, processing status, authorized detail | `DocumentDetail` |
| `GET /api/v1/documents/{document_id}/content` | Authorized download/stream | file response |
| `DELETE /api/v1/documents/{document_id}` | Request deletion workflow | `202 DeletionResponse` |
| `GET /api/v1/jobs/{job_id}` | Processing status and safe error | `JobResponse` |
| `GET /api/v1/patients/{patient_id}/timeline` | Chronological events with cursor/date/type filters | `TimelinePage` |
| `GET /api/v1/patients/{patient_id}/facts` | Candidate/confirmed facts | `FactPage` |
| `PATCH /api/v1/facts/{fact_id}` | Confirm/correct/reject with audit | `FactResponse` |
| `POST /api/v1/patients/{patient_id}/summaries` | Generate/rebuild source-grounded summary | `202 JobResponse` |
| `GET /api/v1/patients/{patient_id}/summaries/{summary_id}` | Summary blocks and citation references | `SummaryResponse` |
| `POST /api/v1/summaries/{summary_id}/review` | Record review/feedback (not medical sign-off) | `SummaryResponse` |

Authentication/session endpoints are delegated to OIDC provider or maintained auth integration; callback, logout, and CSRF behavior must be specified with the chosen provider before implementation. No share-grant endpoints in MVP.

### Example DTO shapes

```json
{
  "patient_id": "uuid",
  "filename": "blood-test.pdf",
  "media_type": "application/pdf",
  "size_bytes": 345678,
  "sha256": "hex-digest",
  "document_type": null,
  "document_date": null,
  "idempotency_key": "client-generated-opaque-value"
}
```

```json
{
  "id": "uuid",
  "status": "needs_review",
  "document_type": {"value": "laboratory_report", "confidence": 0.91},
  "document_date": {"value": "2026-01-12", "precision": "day", "source": "page_text"},
  "facts": [{
    "id": "uuid", "label": "Hemoglobin", "raw_value": "13.5", "raw_unit": "g/dL",
    "status": "candidate", "confidence": 0.88,
    "evidence": {"page": 1, "start": 42, "end": 64, "excerpt": "Hemoglobin: 13.5 g/dL"}
  }]
}
```

```json
{
  "id": "uuid", "status": "ready", "generated_at": "2026-11-20T00:00:00Z",
  "stale": false,
  "blocks": [{"text": "A document dated 2026-01-12 lists hemoglobin as 13.5 g/dL.",
    "citations": [{"document_id": "uuid", "version_id": "uuid", "page": 1,
      "fact_id": "uuid", "excerpt": "Hemoglobin: 13.5 g/dL"}]}],
  "notice": "Generated from uploaded records; verify details in the cited source documents."
}
```

## 11. Automated testing and validation requirements

All fixtures must be authored synthetic documents. Do not use real patient data in tests, demos, logs, bug reports, or CI artifacts.

- **Unit:** date parsing/uncertainty, MIME/signature/size checks, hash streaming, rule classification, each field regex and offsets, unit parsing, state transitions, summary citation validator, DTO redaction.
- **API integration:** PostgreSQL migrations up/down in disposable database; repository ownership filters; upload quarantine/finalize; worker idempotency/retry; deletion and stale-summary lifecycle; pagination.
- **Authorization/security:** cross-patient IDOR/BOLA tests for every route and object; RLS policy tests using runtime non-owner role; unauthenticated/expired session, CSRF, rate limits, MIME spoofing, path traversal, oversized/decompression-bomb PDFs, malware fixture, SQL injection, unsafe HTML/PDF preview, no-store headers, secret/PHI log scans.
- **Pipeline fixtures:** synthetic text PDFs, scanned PDFs, English and Bengali authored examples, rotated/low-quality image, malformed/empty/encrypted PDFs, unsupported file, duplicate hash. Assert safe failure and resource limits.
- **Summary evaluation:** each factual block cites a source; citation resolves to exact source version; no unsupported value/date/unit; contradictions surfaced; prompt-injection strings in fixture documents cannot change system policy; output schema validated; summaries become stale after source edits.
- **Frontend:** component/accessibility checks, keyboard navigation, upload errors/progress, source citation navigation, unauthorized states, no patient data in shared cache. End-to-end tests use synthetic accounts and isolated environments.
- **Operational gates:** dependency/security scanning, secret scanning, backup restore exercise, migration rehearsal, audit log integrity/retention, observability alert tests, incident/deletion runbooks, and manual privacy/security review. Define pass thresholds before running evaluation; never advertise unmeasured accuracy.

## 12. Phased implementation roadmap

| Phase | Work and exit gate |
|---|---|
| 0 — Decisions and threat model | Confirm user/tenant model, jurisdiction, hosting, identity provider, supported formats/languages, retention/deletion, model/data-processing constraints, availability and budget. Produce threat model, data inventory, access matrix, and acceptance criteria. No real records. |
| 1 — Foundation | Create repo structure, pinned dependencies, local compose/dev services, configuration/secrets pattern, CI, logging redaction, FastAPI skeleton/OpenAPI, Next.js shell and accessible design system. Gate: no secrets/PHI in client bundle/logs; reproducible local setup. |
| 2 — Identity and data boundary | Implement maintained OIDC/session flow; users/patients schema; SQLAlchemy and Alembic; owner-scoped services; RLS and audit events. Gate: cross-owner tests fail closed across every endpoint. |
| 3 — Secure document lifecycle | Private object storage, quarantine, upload limits/validation/scan, checksums, async queue, job status, authorized download/deletion. Gate: malicious/oversized inputs rejected and originals remain immutable. |
| 4 — OCR and review | Port PDF/Tesseract/regex/classification behind service interfaces; page provenance; candidate review UI; synthetic multilingual corpus and baseline metrics. Gate: known extraction quality, safe failures, user corrections audited. |
| 5 — Timeline and grounded summaries | Timeline filtering/date uncertainty; deterministic cited summaries; stale invalidation; review/feedback and export. Gate: automated citation completeness/support checks pass; no diagnostic or treatment language. |
| 6 — Legacy import rehearsal (separate approval) | Build an offline dry-run importer for a copy of SQLite and copied source files only; produce checksums, mapping exceptions, duplicate report, and reconciliation counts. Gate: zero writes to original paths, exact count/hash reconciliation, explicit owner mapping and human approval before any import. |
| 7 — Hardening and release readiness | Penetration/security review, ASVS-based verification, restore/deletion drills, operational runbooks, privacy/legal review, accessibility, load tests, incident response, backup/key rotation. Gate: documented owner sign-off and deployment approval. |

## 13. Research notes: documented capability vs. recommendation

Anara research consulted official documentation/standards. The linked documents describe capabilities or security requirements; the architecture choices below are recommendations inferred for this product, not mandates made by those sources.

| Topic | Documented | Recommendation/inference |
|---|---|---|
| FastAPI | Supports multipart `UploadFile`/`File`/`Form`, and generates OpenAPI from routes/models. | Use async upload jobs, strict upstream/application size caps, and restrict production docs endpoints. [FastAPI file docs](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/) · [FastAPI features](https://fastapi.tiangolo.com/features/) |
| Next.js | Security guide recommends a server-only DAL, authorization near data access, and minimal DTOs; Server Actions are public entry points requiring validation/authz. | Keep PHI access in a server-only BFF/DAL and ensure patient-specific cache isolation. [Next.js data security](https://nextjs.org/docs/app/guides/data-security) · [Next.js authentication](https://nextjs.org/docs/app/guides/authentication) |
| PostgreSQL | RLS can default-deny with no policy; table owners and privileged roles can bypass it; policies govern rows. | Use owner-scoped checks plus RLS with a non-owner runtime role, not RLS alone. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) |
| Upload security | OWASP recommends allowlisted formats, signature/content validation, generated names, size limits, authenticated access, separate storage, and scanning. | Quarantine then validate/scan before parsing; store privately under opaque keys. [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) |
| Security verification | OWASP ASVS 5.0 covers authentication, sessions, access control, data protection, files/resources, and APIs; API Security Top 10 includes object-level authorization risk. | Turn relevant ASVS controls into release gates and test every ID-addressed endpoint for cross-patient access. [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) · [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) |
| Healthcare controls | NIST SP 800-66 Rev. 2 is an informational resource for implementing the HIPAA Security Rule; applicability is a legal/organizational determination. | Use it as a security control reference only after jurisdiction and operating role are reviewed. [NIST SP 800-66 Rev. 2](https://csrc.nist.gov/pubs/sp/800/66/r2/final) |
| Provenance | FHIR R5 Provenance records agents, activities, and entities involved in creating/revising resources. | Adopt provenance-like fields for extraction and summary lineage; full FHIR adoption is optional. [FHIR R5 Provenance](https://hl7.org/fhir/R5/provenance.html) |

**Version note:** Anara reported FastAPI request-body/form-parser limits in releases 0.164.0/0.165.0 on 2026-11-18 and a Python support change. Verify current package compatibility and pin versions during Phase 1; do not rely on a specific feature until the selected version is confirmed. SQLAlchemy 2.x and Alembic are proposed; their current official docs should be rechecked at implementation time.

## 14. Approval boundary

This blueprint is ready for review. No existing file, SQLite record, or uploaded source file was altered; no migration, application replacement, or real-patient-data testing occurred. Implementation should begin only after review/approval of this architecture and resolution of the Phase 0 decisions.
