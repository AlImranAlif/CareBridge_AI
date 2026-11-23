"""The document-processing pipeline.

    validate -> extract text (OCR if needed) -> clean -> classify -> extract fields
    -> validate fields -> build a storage record

Each stage is a separate function in its own module; this module only wires them together.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from .classification import ClassificationResult, classify
from .extraction import ExtractionError, ExtractionResult, PageText, extract_text
from .fields import ExtractedDetails, extract_details
from .text_cleaning import clean_text
from .validation import ValidatedFile, validate_upload


@dataclass
class ProcessedDocument:
    file: ValidatedFile
    extraction: ExtractionResult
    pages: list[PageText]
    classification: ClassificationResult
    details: ExtractedDetails
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    def to_record(self, patient_name: str) -> dict:
        """Row values for DocumentStore.save_document."""
        doc_id = str(uuid.uuid4())
        return {
            "id": doc_id,
            "patient_name": patient_name,
            "filename": self.file.safe_name,
            "doc_type": self.classification.label,
            "doc_date": self.details.document_date.value,
            "extracted_text": self.text,
            "extracted_json": json.dumps([asdict(r) for r in self.details.lab_results], ensure_ascii=False),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "sha256": self.file.sha256,
            "media_type": self.file.media_type,
            "size_bytes": self.file.size_bytes,
            "storage_name": f"{doc_id}{self.file.extension}",
            "extraction_method": self.extraction.method,
            "classification_confidence": self.classification.confidence,
            "type_confirmed": 0,
            "date_status": self.details.document_date.status,
            "status": "needs_review" if self.warnings or self.classification.needs_confirmation else "processed",
            "pages_json": json.dumps([asdict(p) for p in self.pages], ensure_ascii=False),
            "details_json": json.dumps(self.details.details_dict(), ensure_ascii=False),
            "warnings_json": json.dumps(self.warnings, ensure_ascii=False),
        }


def clean_pages(pages: list[PageText]) -> list[PageText]:
    return [PageText(p.page, clean_text(p.text), p.method) for p in pages]


def validate_details(details: ExtractedDetails, patient_name: str | None = None) -> list[str]:
    """Check extracted fields for problems and mark conflicts. Returns user-facing warnings.

    Nothing is corrected or removed: conflicting or suspicious items are flagged as uncertain.
    """
    warnings: list[str] = []
    doc_date = details.document_date
    if doc_date.value and date.fromisoformat(doc_date.value) > date.today():
        doc_date.status = "uncertain"
        doc_date.reason = "; ".join(filter(None, [doc_date.reason, "date is in the future"]))
    if doc_date.status == "missing":
        warnings.append("No document date was found. The record is listed at the end of the timeline.")
    elif doc_date.status == "uncertain":
        warnings.append(f"Document date is uncertain: {doc_date.reason}.")

    by_test: dict[str, list] = defaultdict(list)
    for result in details.lab_results:
        by_test[result.field].append(result)
    for name, results in by_test.items():
        if len({(r.value, r.unit.lower()) for r in results}) > 1:
            for r in results:
                r.uncertain = "; ".join(filter(None, [r.uncertain, "different values for this test in the same document"]))
            warnings.append(f"{name}: different values were found in the same document. Check the source.")

    found_name = details.patient_name_in_document
    if patient_name and found_name and found_name.value.casefold() != patient_name.strip().casefold():
        warnings.append(
            f'The document names the patient as "{found_name.value}", which differs from the selected profile.'
        )
    return warnings


def process_document(filename: str, data: bytes, patient_name: str | None = None) -> ProcessedDocument:
    """Run every pipeline stage. Raises ValidationError or ExtractionError with user-safe messages."""
    validated = validate_upload(filename, data)
    extraction = extract_text(validated.data, validated.extension)
    pages = clean_pages(extraction.pages)
    text = "\n\n".join(p.text for p in pages if p.text)
    if not text.strip():
        hint = " ".join(extraction.warnings) or "Try a clearer scan or a text-based PDF."
        raise ExtractionError(f"No readable text was found. {hint}")
    classification = classify(text, validated.safe_name)
    details = extract_details(pages)
    warnings = list(extraction.warnings) + validate_details(details, patient_name)
    if classification.needs_confirmation:
        warnings.append("The document type could not be identified confidently. Please confirm it.")
    return ProcessedDocument(validated, extraction, pages, classification, details, warnings)
