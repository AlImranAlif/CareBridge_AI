"""Read-side helpers: turn stored rows into display records, and sort, filter and search them."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .classification import TYPE_CONFIRMATION_WARNING, UNKNOWN
from .storage import LEGACY_MISSING_DATE


def _load_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


@dataclass
class DocumentRecord:
    id: str
    patient_name: str
    filename: str
    doc_type: str
    doc_date: str | None
    date_status: str
    created_at: str
    sha256: str
    text: str
    extraction_method: str
    classification_confidence: str
    type_confirmed: bool
    status: str
    lab_results: list[dict] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    media_type: str = ""
    storage_name: str | None = None

    @property
    def needs_type_confirmation(self) -> bool:
        return not self.type_confirmed and (self.classification_confidence == "low" or self.doc_type == UNKNOWN)

    @property
    def medications(self) -> list[dict]:
        return self.details.get("medications") or []

    @property
    def display_date(self) -> str:
        if not self.doc_date:
            return "Date unknown"
        return f"{self.doc_date} (uncertain)" if self.date_status == "uncertain" else self.doc_date


def to_record(row) -> DocumentRecord:
    """Build a DocumentRecord from a sqlite row, tolerating rows written by the original prototype."""
    keys = set(row.keys())

    def get(name, default=None):
        return row[name] if name in keys and row[name] is not None else default

    doc_date = get("doc_date")
    if doc_date == LEGACY_MISSING_DATE:
        doc_date = None
    date_status = get("date_status") or ("found" if doc_date else "missing")
    labs = _load_json(get("extracted_json"), [])
    for lab in labs:
        lab.setdefault("reference_range", "")
        lab.setdefault("page", None)
        lab.setdefault("uncertain", "")
        lab.setdefault("source_excerpt", "")
    return DocumentRecord(
        id=row["id"],
        patient_name=get("patient_name", ""),
        filename=get("filename", ""),
        doc_type=get("doc_type", UNKNOWN),
        doc_date=doc_date,
        date_status=date_status,
        created_at=get("created_at", ""),
        sha256=get("sha256", ""),
        text=get("extracted_text", ""),
        extraction_method=get("extraction_method", "Not recorded"),
        classification_confidence=get("classification_confidence", "not recorded"),
        type_confirmed=bool(get("type_confirmed", 0)),
        status=get("status", "processed"),
        lab_results=labs,
        pages=_load_json(get("pages_json"), []),
        details=_load_json(get("details_json"), {}),
        warnings=[
            w for w in _load_json(get("warnings_json"), [])
            if not (get("type_confirmed") and w == TYPE_CONFIRMATION_WARNING)
        ],
        media_type=get("media_type", ""),
        storage_name=get("storage_name"),
    )


def sort_timeline(records: list[DocumentRecord]) -> list[DocumentRecord]:
    """Oldest dated record first; records without a date go last, ordered by upload time."""
    dated = sorted((r for r in records if r.doc_date), key=lambda r: (r.doc_date, r.created_at))
    undated = sorted((r for r in records if not r.doc_date), key=lambda r: r.created_at)
    return dated + undated


def filter_records(records: list[DocumentRecord], doc_types: list[str] | None = None, query: str = "") -> list[DocumentRecord]:
    """Keep records whose type is selected and whose filename or extracted text contains the query."""
    query = (query or "").strip().casefold()
    result = []
    for record in records:
        if doc_types and record.doc_type not in doc_types:
            continue
        if query and query not in record.filename.casefold() and query not in (record.text or "").casefold():
            continue
        result.append(record)
    return result
