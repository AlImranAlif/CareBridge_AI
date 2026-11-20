"""Local, reviewable document workflow for the CareBridge demonstration MVP."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("carebridge.documents")
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MIME_BY_EXT = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _paths() -> tuple[Path, Path]:
    configured = Path(get_settings().data_dir)
    root = configured if configured.is_absolute() else Path(__file__).resolve().parents[5] / configured
    root.mkdir(parents=True, exist_ok=True)
    blobs = root / "uploads"
    blobs.mkdir(exist_ok=True)
    return root / "documents.sqlite3", blobs


def _connect() -> sqlite3.Connection:
    database, _ = _paths()
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY, filename TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
      sha256 TEXT NOT NULL, doc_type TEXT NOT NULL, doc_date TEXT, extraction_method TEXT NOT NULL,
      status TEXT NOT NULL, source_text TEXT NOT NULL, facts_json TEXT NOT NULL,
      uploaded_at TEXT NOT NULL, storage_name TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _extract(raw: bytes, suffix: str) -> tuple[list[dict], str]:
    pages: list[dict] = []
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError:
            raise HTTPException(503, "PDF extraction is unavailable on this server.") from None
        try:
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                if pdf.page_count > 100:
                    raise HTTPException(400, "PDF exceeds the 100 page limit.")
                pages = [{"page": n, "text": page.get_text("text").strip()} for n, page in enumerate(pdf, 1)]
                method = "PDF text layer"
                if not any(p["text"] for p in pages):
                    try:
                        import pytesseract
                        from PIL import Image
                        from io import BytesIO
                    except ImportError:
                        raise HTTPException(
                            503,
                            "Scanned PDF OCR is unavailable. Install Tesseract and its Bengali/English language data.",
                        ) from None
                    try:
                        pages = []
                        for n, page in enumerate(pdf, 1):
                            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                            text = pytesseract.image_to_string(Image.open(BytesIO(pix.tobytes("png"))), lang="ben+eng")
                            pages.append({"page": n, "text": text.strip()})
                        method = "OCR (Bengali + English)"
                    except Exception:
                        raise HTTPException(
                            503,
                            "Scanned PDF OCR failed. Check Tesseract and its Bengali/English language data.",
                        ) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, "The PDF could not be read. Please upload a valid PDF.") from None
    else:
        try:
            import pytesseract
            from PIL import Image, ImageOps
            from io import BytesIO
            with Image.open(BytesIO(raw)) as image:
                if image.width * image.height > 40_000_000:
                    raise HTTPException(400, "Image dimensions exceed the supported limit.")
                image = ImageOps.exif_transpose(image).convert("RGB")
                text = pytesseract.image_to_string(image, lang="ben+eng").strip()
            pages = [{"page": 1, "text": text}]
            method = "OCR (Bengali + English)"
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Image OCR is unavailable. Install Tesseract with Bengali and English language data.") from None
    return pages, method


def _classify(text: str, filename: str) -> str:
    s = f"{text} {filename}".lower()
    if any(x in s for x in ("prescription", "dosage", "প্রেসক্রিপশন", "চিকিৎসাপত্র")):
        return "Prescription"
    if any(x in s for x in ("laboratory", "lab report", "hemoglobin", "glucose", "creatinine", "পরীক্ষার ফল")):
        return "Laboratory report"
    if any(x in s for x in ("discharge", "admission", "hospital course", "ছাড়পত্র")):
        return "Discharge summary"
    return "Medical document"


def _facts(pages: list[dict]) -> list[dict]:
    patterns = [
        ("Hemoglobin", r"(?i)\b(?:hemoglobin|haemoglobin|hb)\b\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(g/dl|gm/dl)?"),
        ("Glucose", r"(?i)\b(?:blood glucose|glucose|fbs|rbs)\b\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl|mmol/l)?"),
        ("Creatinine", r"(?i)\bcreatinine\b\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?"),
        ("WBC", r"(?i)\b(?:wbc|white blood cell(?: count)?)\b\s*[:\-]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:/cumm|cells/ul)?"),
    ]
    found = []
    for page in pages:
        source = page["text"]
        for label, pattern in patterns:
            for match in re.finditer(pattern, source):
                found.append({"id": str(uuid4()), "field": label, "value": match.group(1), "unit": (match.group(2) or ""), "page": page["page"], "excerpt": source[max(0, match.start()-55):min(len(source), match.end()+55)].replace("\n", " "), "review_status": "needs_review"})
    return found


def _as_document(row: sqlite3.Row, include_text: bool = False) -> dict:
    result = {key: row[key] for key in row.keys() if key not in {"source_text", "facts_json", "storage_name"}}
    result["facts"] = json.loads(row["facts_json"])
    if include_text:
        result["source_text"] = row["source_text"]
    return result


@router.post("/upload", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict:
    filename = Path((file.filename or "document").replace("\\", "/")).name[:180]
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "Choose a PDF, PNG, JPG, or WEBP document.")
    settings = get_settings()
    pieces, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(413, "File exceeds the 10 MB upload limit.")
        pieces.append(chunk)
    raw = b"".join(pieces)
    signature_ok = (suffix == ".pdf" and raw.startswith(b"%PDF-")) or (suffix == ".png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or (suffix in {".jpg", ".jpeg"} and raw.startswith(b"\xff\xd8\xff")) or (suffix == ".webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
    if not signature_ok:
        raise HTTPException(400, "The file contents do not match the selected document type.")
    pages, method = _extract(raw, suffix)
    text = "\n\n".join(p["text"] for p in pages if p["text"])
    if not text.strip(): raise HTTPException(422, "No readable text was found. Try a clearer scan or another document.")
    facts = _facts(pages)
    match = re.search(r"\b(20\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))\b", text)
    doc_date = None
    if match:
        try: doc_date = date.fromisoformat(match.group(1).replace("/", "-")).isoformat()
        except ValueError: pass
    doc_id = str(uuid4())
    storage_name = f"{doc_id}{suffix}"
    uploaded_at = datetime.now(timezone.utc).isoformat()
    _, blobs = _paths()
    try:
        (blobs / storage_name).write_bytes(raw)
        with _connect() as conn:
            conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (doc_id, filename, MIME_BY_EXT[suffix], size, hashlib.sha256(raw).hexdigest(), _classify(text, filename), doc_date, method, "needs_review", text, json.dumps(facts, ensure_ascii=False), uploaded_at, storage_name))
            row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    except Exception as exc:
        (blobs / storage_name).unlink(missing_ok=True)
        logger.error("document_upload_persistence_failed document_id=%s error_type=%s", doc_id, type(exc).__name__)
        raise HTTPException(500, "The document could not be saved.") from None
    return _as_document(row, include_text=True)


@router.get("")
def list_documents() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY CASE WHEN doc_date IS NULL THEN 1 ELSE 0 END, doc_date DESC, uploaded_at DESC"
        ).fetchall()
    return [_as_document(row) for row in rows]


@router.get("/{document_id}")
def get_document(document_id: str) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found.")
    return _as_document(row, include_text=True)


class ReviewRequest(BaseModel):
    status: str


@router.patch("/{document_id}/facts/{fact_id}")
def review_fact(document_id: str, fact_id: str, request: ReviewRequest) -> dict:
    if request.status not in {"confirmed", "rejected"}:
        raise HTTPException(400, "Review status must be confirmed or rejected.")
    with _connect() as conn:
        row = conn.execute("SELECT facts_json FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Document not found.")
        facts = json.loads(row["facts_json"])
        target = next((fact for fact in facts if fact["id"] == fact_id), None)
        if target is None:
            raise HTTPException(404, "Extracted item not found.")
        target["review_status"] = request.status
        conn.execute("UPDATE documents SET facts_json=? WHERE id=?", (json.dumps(facts, ensure_ascii=False), document_id))
    return target
