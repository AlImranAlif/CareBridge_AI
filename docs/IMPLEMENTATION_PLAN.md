# Implementation plan

Status of the phases from the improvement brief. Each phase keeps the Streamlit + SQLite stack
and must leave the app runnable with all tests passing.

## Phase 0 — Audit — done
See [AUDIT.md](AUDIT.md).

## Phase 1 — Stabilise the existing workflow — done in this branch

| Area | Change |
| --- | --- |
| Structure | Logic moved from `app.py` into the `carebridge/` package (UI-free, testable). |
| Upload validation | Size limit, extension allow-list, magic-byte check, UTF-8 check, safe filenames, SHA-256 duplicate detection per profile, multi-file upload. `.txt` support added. |
| PDF / OCR | Per-page text with page numbers; OCR only for pages with no usable text; EXIF rotation; page and pixel limits; encrypted/corrupt files handled; language data detected instead of assumed. |
| Classification | Weighted, word-boundary rules in `CATEGORY_RULES`; new types (imaging, consultation, diagnostic, Unknown); confidence and "please confirm" prompt; user can change the type. |
| Extraction | More date formats incl. Bengali digits; birth dates ignored; discharge/report dates preferred over admission/collection dates; lab ranges; medicines as written; doctor, facility, patient; page + source line for every value; conflicts flagged, never overwritten. |
| Storage | Additive, versioned migration with automatic backup; transactional save; file removed if DB insert fails; delete record / delete profile. |
| UI | Dashboard, upload progress and per-file results, timeline search/filter/needs-review, page-level source view, original download, structured summary with references, Data & privacy tab. |
| Tests | 73 unit tests + synthetic evaluation script. |

## Phase 2 — Review workflow (next)
* Let users edit/confirm individual extracted values (store original + corrected value and who/when).
* Show the source page image next to each value (PDF page render).
* Per-document "reviewed" status in the timeline.

## Phase 3 — Better extraction
* Expand test-name dictionary and unit normalisation (mg/dL ↔ mmol/L shown, not converted silently).
* Table-aware PDF extraction for multi-column lab reports.
* Image pre-processing (deskew, thresholding) measured against the evaluation set before adoption.
* Grow the evaluation set with harder synthetic scans (skew, noise, handwriting-like fonts).

## Phase 4 — Optional LLM explanations
Only if needed, behind a configuration flag, with: grounded prompts containing only stored source
text, mandatory citations, refusal of diagnosis/treatment questions, and checks that every claim
maps to a source line. Off by default; the rule-based summary remains.

## Phase 5 — Privacy hardening (before any real data)
Authentication, per-user isolation, encryption at rest, audit log, retention settings. Until then
the app must be used with synthetic or de-identified records only.

## Relationship to `feature/full-stack-foundation`
That branch contains a separate Next.js + FastAPI implementation. Merging the two, or porting the
`carebridge/` package into the FastAPI backend, is a separate decision and is not part of these phases.
