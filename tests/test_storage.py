import json
import sqlite3

import pytest

from carebridge.pipeline import process_document
from carebridge.records import to_record
from carebridge.storage import SCHEMA_VERSION, DocumentStore, StorageError

LAB_TEXT = b"LABORATORY REPORT\nDate: 2026-01-12\nHemoglobin: 13.5 g/dL"


def save(store, name="lab.txt", data=LAB_TEXT, patient="Demo Patient"):
    record = process_document(name, data, patient).to_record(patient)
    store.save_document(record, data)
    return record


def test_save_list_get_and_file_roundtrip(tmp_path):
    store = DocumentStore(tmp_path)
    record = save(store)
    rows = store.list_documents("Demo Patient")
    assert len(rows) == 1
    loaded = to_record(rows[0])
    assert loaded.doc_type == "Laboratory report"
    assert loaded.doc_date == "2026-01-12"
    assert loaded.lab_results[0]["value"] == "13.5"
    assert store.read_file(rows[0]) == LAB_TEXT
    assert store.get_document(record["id"])["filename"] == "lab.txt"


def test_duplicate_detection_is_per_patient(tmp_path):
    store = DocumentStore(tmp_path)
    record = save(store)
    assert store.find_duplicate(record["sha256"], "Demo Patient") is not None
    assert store.find_duplicate(record["sha256"], "Someone Else") is None


def test_delete_removes_row_and_file(tmp_path):
    store = DocumentStore(tmp_path)
    record = save(store)
    path = store.uploads_dir / record["storage_name"]
    assert path.exists()
    assert store.delete_document(record["id"]) is True
    assert not path.exists()
    assert store.get_document(record["id"]) is None
    assert store.delete_document(record["id"]) is False


def test_delete_patient_documents(tmp_path):
    store = DocumentStore(tmp_path)
    save(store, "a.txt")
    save(store, "b.txt", LAB_TEXT + b"\nGlucose 90 mg/dL")
    save(store, "c.txt", patient="Other")
    assert store.delete_patient_documents("Demo Patient") == 2
    assert store.list_patients() == ["Other"]


def test_failed_insert_removes_written_file(tmp_path):
    store = DocumentStore(tmp_path)
    record = save(store)
    with pytest.raises(StorageError):
        store.save_document(dict(record, storage_name="second.txt"), LAB_TEXT)  # duplicate primary key
    assert not (store.uploads_dir / "second.txt").exists()


def test_update_document_type_marks_confirmed(tmp_path):
    store = DocumentStore(tmp_path)
    record = save(store)
    store.update_document_type(record["id"], "Prescription")
    loaded = to_record(store.get_document(record["id"]))
    assert loaded.doc_type == "Prescription" and loaded.type_confirmed


def test_migrates_legacy_database_without_losing_rows(tmp_path):
    legacy = tmp_path / "carebridge.db"
    conn = sqlite3.connect(legacy)
    conn.execute(
        """CREATE TABLE documents (id TEXT PRIMARY KEY, patient_name TEXT, filename TEXT, doc_type TEXT,
        doc_date TEXT, extracted_text TEXT, extracted_json TEXT, created_at TEXT, sha256 TEXT)"""
    )
    fields = [{"field": "Hemoglobin", "value": "13.5", "unit": "g/dL", "source_excerpt": "Hemoglobin: 13.5"}]
    conn.execute(
        "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
        ("legacy-1", "Demo Patient", "old.pdf", "Laboratory report", "Date not identified", "text", json.dumps(fields), "2026-01-01T00:00:00", "ab" * 32),
    )
    conn.commit()
    conn.close()
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "legacy-1").write_bytes(b"legacy bytes")

    store = DocumentStore(tmp_path)
    assert store.last_backup is not None and store.last_backup.exists()
    with store.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    row = store.get_document("legacy-1")
    record = to_record(row)
    assert record.doc_date is None and record.date_status == "missing"
    assert record.lab_results[0]["reference_range"] == ""
    assert store.read_file(row) == b"legacy bytes"
    assert store.delete_document("legacy-1")
    assert not (tmp_path / "uploads" / "legacy-1").exists()

    # Opening again must not create another backup or change anything.
    assert DocumentStore(tmp_path).last_backup is None
