import pytest

from carebridge.extraction import ExtractionError
from carebridge.pipeline import process_document
from carebridge.validation import ValidationError
from tests.helpers import ocr_ready, scanned_pdf, text_image, text_pdf


def test_text_pdf_end_to_end():
    data = text_pdf(["LABORATORY REPORT\nReport Date: 2026-01-12\nHemoglobin: 13.5 g/dL 12-16"])
    processed = process_document("report.pdf", data, "Demo Patient")
    record = processed.to_record("Demo Patient")
    assert record["doc_type"] == "Laboratory report"
    assert record["doc_date"] == "2026-01-12"
    assert record["extraction_method"] == "PDF text layer"
    assert record["storage_name"].endswith(".pdf")
    assert processed.details.lab_results[0].reference_range == "12-16"


def test_invalid_upload_stops_pipeline():
    with pytest.raises(ValidationError):
        process_document("x.pdf", b"not a pdf")


def test_empty_document_reports_no_text():
    with pytest.raises(ExtractionError, match="No readable text"):
        process_document("blank.txt", b"   \n  ")


def test_conflicting_values_are_flagged_not_overwritten():
    processed = process_document("lab.txt", b"Lab report\nHemoglobin 13.5 g/dL\nHemoglobin 11.0 g/dL")
    values = [r.value for r in processed.details.lab_results]
    assert values == ["13.5", "11.0"]
    assert all("different values" in r.uncertain for r in processed.details.lab_results)
    assert any("Hemoglobin" in w for w in processed.warnings)


def test_patient_name_mismatch_warns():
    processed = process_document("lab.txt", b"Lab report\nPatient: Someone Else\nDate: 2026-01-01", "Demo Patient")
    assert any("Someone Else" in w for w in processed.warnings)


def test_unknown_type_requests_confirmation():
    processed = process_document("note.txt", b"A synthetic note with nothing recognisable.")
    assert processed.classification.label == "Unknown"
    assert processed.to_record("P")["status"] == "needs_review"


@pytest.mark.skipif(not ocr_ready("eng"), reason="Tesseract with English data is not installed")
def test_scanned_pdf_end_to_end():
    page = text_image(["PRESCRIPTION", "Date: 08/03/2026", "Tab. Napa 500 mg 1+0+1"])
    processed = process_document("scan.pdf", scanned_pdf([page]))
    assert processed.extraction.method == "OCR"
    assert processed.classification.label == "Prescription"
    assert processed.details.document_date.value == "2026-03-08"
