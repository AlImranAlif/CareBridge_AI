# Testing

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
# OCR tests also need Tesseract (+ Bengali data for the Bengali test):
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-ben fonts-noto-core
```

## Unit tests

```bash
.venv/bin/python -m pytest -q
```

70 tests. All test documents are generated in the test itself (PDFs with PyMuPDF, images with
Pillow); no real records are used. OCR tests are skipped automatically if Tesseract (or the
Bengali language pack) is not installed.

| File | Covers |
| --- | --- |
| `test_validation.py` | Allowed types, extension/content mismatch, oversize, empty, binary disguised as text, filename sanitising, signature detection. |
| `test_extraction.py` | Text PDFs with page numbers, scanned PDF → OCR, mixed PDF (OCR only the empty page), corrupt/encrypted PDF, blank PDF warning, plain text, corrupt image, image OCR, Bengali OCR. |
| `test_classification.py` | Each document type, `Unknown` fallback, confidence levels, `rx` not matched inside words, filename only a weak signal. |
| `test_fields.py` | Date formats, ambiguous day/month marked, invalid dates ignored, Bengali digits, birth-date exclusion, discharge/report date preferred over admission/collection date, missing date stays missing, lab values with units, ranges and pages, missing values not invented, medicines copied as written, doctor/facility/patient. |
| `test_storage.py` | Persistence and file round-trip, per-profile duplicate detection, delete (row + file), delete profile, file removed when insert fails, type confirmation, legacy-schema migration with backup. |
| `test_records_summary.py` | Timeline order (undated last), filter/search, summary sections and `[D#, p.#]` references, every summarised value present in its cited source, empty summary. |
| `test_pipeline.py` | Text and scanned PDF end to end, invalid upload and empty document stop with a message, conflicting values flagged, patient-name mismatch warning, unknown type requests confirmation. |

## Synthetic evaluation

```bash
.venv/bin/python scripts/evaluate.py          # --json out.json writes per-document results
```

`tests/eval/dataset.json` holds 14 synthetic documents (text PDF, plain text, scanned PDF, photo,
Bengali scan; lab, prescription, discharge, imaging, consultation, diagnostic, unknown) with
expected type, date, lab values and medicines. The script builds each file, runs the real
pipeline and compares.

Latest result (this branch, Tesseract 5 with `eng+ben`):

| Metric | Value |
| --- | --- |
| Processing success | 14 / 14 |
| Classification accuracy | 1.00 |
| Document-date accuracy | 1.00 (was 0.93 before the discharge-date fix) |
| Lab field precision / recall | 1.00 / 1.00 |
| Medicine name precision / recall | 1.00 / 1.00 |
| Mean OCR character similarity | 0.99 |
| Summary claims with source support | 21 / 21 |

**Limits of these numbers.** The dataset is small and was written by the same author as the
rules, so it measures regressions, not real-world accuracy. Clean synthetic scans are much easier
than real phone photos. Do not quote these figures as clinical or production performance.

## Manual smoke test

```bash
.venv/bin/streamlit run app.py
```

1. Dashboard → **Load synthetic demo records**; 4 records, one marked "date unknown".
2. Upload a text PDF, an image and a `.txt`; upload the same file again → duplicate notice.
3. Upload a `.pdf` renamed from a `.png` → rejected with a clear message.
4. Timeline: filter by type, search a test name, open page source, download original, delete a record.
5. Summary: references like `[D1, p.1]` match the timeline numbering.
