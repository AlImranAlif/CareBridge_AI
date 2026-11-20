# CareBridge AI — MVP

A local demonstration prototype for organizing patient-provided medical documents into a simple timeline and source-linked summary.

## Important safety notice

This is a competition prototype, not a medical device or clinical decision-support system. It does not diagnose, prescribe, or recommend treatment. Use synthetic or de-identified records only. Do not deploy this demo with real patient data: it lacks production authentication, encryption-at-rest, cloud access controls, and clinical validation.

## Features

- Upload text-based PDF and image documents
- Extract text from PDFs; optional OCR for scanned PDFs and images
- Heuristic document classification
- Conservative candidate extraction for a few common lab fields
- Patient timeline
- Source-text previews and downloadable summary
- Local SQLite database and local file storage
- Synthetic demo records

## Next.js + FastAPI MVP

The Bangla-first web workspace uses `apps/api` for upload, extraction, history, source context, and candidate review. Its local demo database and files are created in `.carebridge-mvp/` at the repository root; the original `data/carebridge.db` and `data/uploads` remain separate and are not imported.

Install the API package from `apps/api` with `python -m pip install -e ".[dev]"`. Start it from that directory with `python -m uvicorn app.main:app --reload --port 8000`. In another terminal, run `npm run dev` from `apps/web` (install dependencies with `npm ci` if needed). Open http://localhost:3000. The API URL defaults to `http://localhost:8000/api/v1`; override it with `NEXT_PUBLIC_API_BASE_URL` in the web environment if needed.

Accepted uploads: PDF, PNG, JPEG, and WEBP; maximum 10 MB and 100 PDF pages. PDF text layers use PyMuPDF. Scanned PDFs and images use local Tesseract OCR with `ben` and `eng` language packs. OCR is optional for text PDFs; without OCR, scanned files return a safe error. The API never sends documents to an external AI service. Candidate matching is a small English-language heuristic for a few laboratory labels; all matches need user review.

This demo has no authentication or patient isolation. A public deployment is suitable only for a controlled demonstration using synthetic data. Do not upload real patient records or claim secure medical record storage. It is not a clinical decision-support system.

## Public demo deployment (Vercel + Render)

The monorepo web project is `apps/web`; the FastAPI service is `apps/api`. Deploy the API with the repository's `render.yaml` Blueprint. It uses `apps/api/Dockerfile` to install the API's Python dependencies and Tesseract English/Bengali OCR packages. The Blueprint uses Render's Free web service plan and sets `DATA_DIR` to `/tmp/carebridge-data`, where the API stores its document SQLite database and uploaded files. This is temporary instance storage: files and document records can disappear on restart, redeploy, or instance replacement. This configuration adds no persistent disk, paid database, or other paid Render resource and is intended for a synthetic-data demo.

In Render, create a Blueprint from this repository and select the `feature/full-stack-foundation` branch. When prompted for `CORS_ORIGINS`, enter the exact Vercel production origin, including `https://` and no trailing slash. No database URL or application secret is required by this SQLite demo API. In Vercel, import the same repository and set Root Directory to `apps/web`; use the Next.js framework defaults. Add `NEXT_PUBLIC_API_BASE_URL` with the Render service URL plus `/api/v1`, for example `https://your-service.onrender.com/api/v1`, to Production and Preview. Redeploy after setting it. For Preview deployments, add their exact origins as a comma-separated list to Render's `CORS_ORIGINS` if they must call the API.

The frontend's API URL is baked into the Next.js build. Set Vercel's `NEXT_PUBLIC_API_BASE_URL` to `https://<your-render-service>.onrender.com/api/v1` (as shown in `apps/web/production.env.example`); if the Render URL changes, update the Vercel variable and redeploy. Uploads and SQLite are temporary demo storage and may be lost on restart or redeploy. Authentication and patient isolation are not implemented. Use synthetic data only. No database migrations are needed or run by this deployment.

`apps/api/.env.example` and `apps/web/production.env.example` show variable names and formats. They contain placeholders only; do not commit real `.env` files or secrets.

## Requirements

- Python 3.10+
- Windows, macOS, or Linux
- For scanned images/PDFs: Tesseract OCR installed separately, with English and Bengali language data if Bengali OCR is needed.

## Run on Windows (PowerShell)

```powershell
cd carebridge_ai_mvp
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If PowerShell blocks activation, run this once in the current terminal:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Run on macOS/Linux

```bash
cd carebridge_ai_mvp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

The browser will open at the local Streamlit address, usually http://localhost:8501.

## Demo

1. Open the **Health timeline** tab.
2. Click **Load synthetic demo records**.
3. Review the timeline and generated summary.
4. Open **Add records** to upload a synthetic PDF or image.

## Current limitations

- Extraction is heuristic, not clinically validated.
- Date recognition supports a limited numeric format.
- The summary is templated and extractive, not generated by an LLM.
- Bengali OCR depends on local Tesseract language-pack installation.
- No real user accounts, role-based access, encryption, consent token, or external hospital integration yet.

## Recommended team split

- Frontend/product: improve Streamlit UI or migrate to Next.js.
- AI/ML: OCR benchmarking, document classification, structured extraction, evaluation.
- Backend/integration: authentication, database schema, secure storage, audit trail and sharing.

## Suggested evaluation

Create a synthetic test set with manually labeled document type, dates, and target fields. Report:
- document classification accuracy
- field-level precision/recall
- date extraction accuracy
- processing success rate
- factual support rate for generated summaries

Do not claim target metrics as achieved until measured.
