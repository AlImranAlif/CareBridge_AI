# Phase 0 — Repository audit

Audit of `main` at commit `6759f44` (before the Phase 1 changes in this branch).

## 1. What is in the repository

| Path | Content |
| --- | --- |
| `app.py` | 232-line Streamlit app: UI, text extraction, OCR, classification, regex extraction, SQLite access and summary in one file. |
| `requirements.txt` | `streamlit`, `pymupdf`, `Pillow`, `pytesseract` (lower bounds only). |
| `.streamlit/config.toml` | Teal theme. |
| `data/.gitkeep` | Runtime data folder (DB + uploads), git-ignored. |
| `README.md` | Describes the **Next.js + FastAPI** app on the `feature/full-stack-foundation` branch (live Render demo, `apps/api`, `apps/web`). Those folders do not exist on `main`, so the README did not match the code on `main`. |

There were no tests, no docs folder and no sample files on `main`.

## 2. How the original app worked

```text
st.file_uploader  ->  extract_text()  ->  classify()  ->  extract_fields()  ->  INSERT INTO documents
   (pdf/png/jpg/webp)   PyMuPDF text,      keyword          4 regexes           + file saved as
                        else OCR all       substring        (Hb, glucose,       data/uploads/<uuid>
                        pages eng+ben      match            creatinine, WBC)
```

* **Upload**: one file at a time; the Streamlit `type=` filter was the only check (extension-based).
* **PDF**: all page text joined; if the *whole* document had no text, *every* page was OCR'd. Page numbers were lost.
* **Images**: OCR with `eng+ben` (fails if Bengali data is not installed).
* **Classification**: first matching keyword list wins (Prescription → Lab → Discharge → Other). No confidence.
* **Date**: first `20YY-MM-DD` / `20YY/MM/DD` in the text; otherwise the literal string `"Date not identified"` was stored in `doc_date`.
* **Storage**: one SQLite table `documents(id, patient_name, filename, doc_type, doc_date, extracted_text, extracted_json, created_at, sha256)`; parameterised queries; file saved under the document id with no extension.
* **Timeline**: per-patient expander list sorted by `doc_date`, with candidate values table, 1,800-char text preview and a delete button.
* **Summary**: plain list of documents and candidate values with filenames; downloadable `.txt`. Labelled "AI-assisted" but no AI is used.
* **Demo data**: three synthetic `.txt` records inserted directly into the DB (bypassing the pipeline).

## 3. What worked

* Text-layer PDF extraction, image OCR when Tesseract is installed, SQLite persistence with parameterised SQL, SHA-256 per file, per-record delete (row + file), clear medical disclaimers, synthetic demo records.

## 4. Problems found (prioritised)

| # | Severity | Problem |
| --- | --- | --- |
| 1 | High | **No content validation.** Files were trusted by extension; no size limit; corrupted PDFs/images raised unhandled exceptions (stack trace in the UI). |
| 2 | High | **No duplicate detection** although the SHA-256 was computed and stored. |
| 3 | High | **Untestable structure**: all logic ran at import time inside the Streamlit script, so nothing could be unit-tested. No tests existed. |
| 4 | High | `json.loads` on stored data in the timeline/summary had no error handling (one bad row would break the page). |
| 5 | Medium | **Date extraction** only handled `YYYY-MM-DD`/`YYYY/MM/DD`; common `DD/MM/YYYY` and `12 Jan 2026` formats were ignored; a date of birth could be chosen as the document date. A sentinel string was stored in the date column. |
| 6 | Medium | **Classification** used substring matching: `"rx"` matched inside words such as "proxy"; any mention of "glucose" made a prescription a lab report if no prescription keyword appeared first; no Unknown fallback, imaging/consultation/diagnostic types missing. |
| 7 | Medium | **Lab regexes** matched anywhere in the text (e.g. `hb` followed by any number later on the line), had no reference ranges, no page numbers and no uncertainty marking. Medicines, doctor and facility were not extracted. |
| 8 | Medium | **OCR fallback was all-or-nothing** (mixed PDFs with some scanned pages lost those pages) and hard-coded `eng+ben`, which raises if `ben` data is missing. |
| 9 | Medium | No DB error handling; file written after the insert (crash in between leaves orphans); no schema versioning. |
| 10 | Low | Timeline had no search/filter; original file could not be downloaded; summary had no section structure, no uncertainty list and called itself "AI-assisted". |
| 11 | Low | README described a different codebase (see §1). |

## 5. Dependency review

All four dependencies are mainstream and appropriate. `pymupdf` now prefers `import pymupdf` over the deprecated `fitz` name (both are supported by the new code). No new runtime dependency was added in Phase 1; `pytest` is a dev-only dependency.

## 6. Security / privacy review

* No authentication (documented; none added — a fake login would be worse than none).
* Data stored unencrypted in `data/` (git-ignored; correct).
* No external network calls; no API keys.
* Filenames were displayed but never used as storage paths (good); now also sanitised.
* Missing: upload size cap, content-signature checks, decompression-bomb limits, PDF page limit, password-protected PDF handling — all added in Phase 1.

## 7. Testing status before this work

No automated tests, no evaluation data.
