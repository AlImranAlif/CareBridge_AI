from __future__ import annotations

import builtins
from io import BytesIO

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.v1 import documents
from app.core.config import Settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    settings = Settings(data_dir=str(tmp_path / "demo-storage"), max_upload_bytes=10_485_760)
    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    with TestClient(app) as test_client:
        yield test_client


def synthetic_lab_pdf() -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text(
        (72, 72),
        "LAB REPORT\nDate: 2026-11-18\nHemoglobin: 13.5 g/dL\nGlucose: 92 mg/dL",
    )
    content = pdf.tobytes()
    pdf.close()
    return content


def synthetic_scanned_pdf() -> bytes:
    pdf = fitz.open()
    pdf.new_page()
    content = pdf.tobytes()
    pdf.close()
    return content


def test_document_upload_extracts_text_and_returns_source_context(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("synthetic-lab.pdf", synthetic_lab_pdf(), "application/pdf")},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["doc_type"] == "Laboratory report"
    assert document["doc_date"] == "2026-11-18"
    assert document["extraction_method"] == "PDF text layer"
    assert "Hemoglobin: 13.5 g/dL" in document["source_text"]
    fact = next(item for item in document["facts"] if item["field"] == "Hemoglobin")
    assert fact["value"] == "13.5"
    assert fact["page"] == 1
    assert "Hemoglobin: 13.5 g/dL" in fact["excerpt"]
    assert fact["review_status"] == "needs_review"


def test_invalid_file_type_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"synthetic content", "text/plain")},
    )
    assert response.status_code == 400


def test_oversized_upload_is_rejected(client: TestClient, monkeypatch) -> None:
    settings = Settings(data_dir="unused", max_upload_bytes=64)
    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("large.pdf", b"%PDF-" + (b"x" * 100), "application/pdf")},
    )
    assert response.status_code == 413


def test_document_listing_and_detail_retrieval(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("synthetic-lab.pdf", synthetic_lab_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    listing = client.get("/api/v1/documents")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [document_id]
    assert "source_text" not in listing.json()[0]

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == document_id
    assert "Glucose: 92 mg/dL" in detail.json()["source_text"]


def test_image_upload_reports_missing_ocr_dependency(
    client: TestClient, monkeypatch
) -> None:
    image_bytes = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(image_bytes, format="PNG")
    original_import = builtins.__import__

    def import_without_ocr(name, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("synthetic missing optional dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_ocr)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("synthetic-scan.png", image_bytes.getvalue(), "image/png")},
    )
    assert response.status_code == 503
    assert "OCR is unavailable" in response.json()["message"]


def test_scanned_pdf_reports_missing_ocr_dependency(
    client: TestClient, monkeypatch
) -> None:
    original_import = builtins.__import__

    def import_without_ocr(name, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("synthetic missing optional dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_ocr)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("synthetic-scan.pdf", synthetic_scanned_pdf(), "application/pdf")},
    )
    assert response.status_code == 503
    assert "Scanned PDF OCR is unavailable" in response.json()["message"]
