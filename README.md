# CareBridge AI

CareBridge AI helps patients organise and understand their medical documents. Upload prescriptions,
lab reports, discharge summaries or scans; the app extracts the text (with OCR for scans),
suggests a document type, pulls out dates, lab values and medicines with their source page, and
builds a timeline and a source-referenced summary.

> **Demonstration only.** Not a medical device and not an electronic health record. It does not
> diagnose, prescribe or give treatment advice. Use **synthetic or de-identified records only.**

This branch (`main`) is the **Streamlit** app. A separate Next.js + FastAPI implementation lives on
the [`feature/full-stack-foundation`](https://github.com/AlImranAlif/CareBridge_AI/tree/feature/full-stack-foundation)
branch (live demo: [carebridge-web-p5qg.onrender.com](https://carebridge-web-p5qg.onrender.com/)).

## Features

* **Upload** PDF, PNG, JPG/JPEG, WEBP and TXT (max 10 MB). Files are checked by content, not just
  extension; duplicates are detected; corrupt or password-protected files get a clear message.
* **Text extraction** from the PDF text layer page by page; Tesseract OCR (English, plus Bengali if
  installed) only for pages or images without text.
* **Document type** suggestion with a confidence level (lab report, prescription, discharge
  summary, imaging report, consultation, diagnostic report, other, unknown). Low confidence asks
  you to confirm.
* **Extracted details**: document date, lab test / value / unit / reference range, medicine lines
  as written, doctor, facility, patient name. Each value shows its page and source line. Missing
  values stay missing; uncertain ones are marked.
* **Timeline** in date order (unknown dates last), filter by type, full-text search, needs-review
  filter, page source view, original file download, delete.
* **Summary** built only from stored records, with references like `[D2, p.1]` and a list of
  missing or uncertain information.
* **Data & privacy** tab: where files are stored, delete all records for a profile.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-ben   # optional, for scans
.venv/bin/streamlit run app.py
```

Click **Load synthetic demo records** on the dashboard to try it without your own files.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CAREBRIDGE_DATA_DIR` | `./data` | Where the SQLite DB and uploaded files are stored. |
| `CAREBRIDGE_OCR_LANG` | `eng+ben` if available, else `eng` | Tesseract language string. |

Existing `data/carebridge.db` files from the earlier version are upgraded automatically; a backup
copy is written next to the database first.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate.py     # synthetic accuracy check
```

See [docs/TESTING.md](docs/TESTING.md).

## Project layout

```text
app.py                 Streamlit UI
carebridge/            validation, extraction, classification, fields, pipeline,
                       storage, records, summary, demo data
tests/                 unit tests; tests/eval/dataset.json synthetic evaluation set
scripts/evaluate.py    evaluation script
docs/                  AUDIT.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, TESTING.md
```

## Data handling and limitations

* Everything is stored locally in `data/` (git-ignored). No external AI or network service is called.
* There is **no login, no encryption at rest and no access control**. Anyone with access to the
  machine or the app URL can see the records.
* Extraction is rule-based and will miss or misread values, especially on photos and handwriting.
  Always check values against the original document.
* The summary is extractive: it repeats what the documents say and never interprets results.

## Roadmap

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).
