"""SQLite metadata storage and local file storage for uploaded documents.

All SQL is parameterised. Schema changes are applied as additive migrations tracked with
``PRAGMA user_version``; existing rows are never dropped, and the database file is copied
to a timestamped backup before a migration touches it.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("carebridge.storage")

SCHEMA_VERSION = 2

# Original prototype table (schema version 0/1). Kept verbatim so existing databases still load.
_BASE_TABLE = """CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, patient_name TEXT, filename TEXT, doc_type TEXT,
    doc_date TEXT, extracted_text TEXT, extracted_json TEXT,
    created_at TEXT, sha256 TEXT
)"""

# Columns added in schema version 2. All are nullable or defaulted so old rows remain valid.
_V2_COLUMNS = [
    ("media_type", "TEXT"),
    ("size_bytes", "INTEGER"),
    ("storage_name", "TEXT"),
    ("extraction_method", "TEXT"),
    ("classification_confidence", "TEXT"),
    ("type_confirmed", "INTEGER NOT NULL DEFAULT 0"),
    ("date_status", "TEXT"),
    ("status", "TEXT NOT NULL DEFAULT 'processed'"),
    ("pages_json", "TEXT"),
    ("details_json", "TEXT"),
    ("warnings_json", "TEXT"),
]

LEGACY_MISSING_DATE = "Date not identified"


class StorageError(Exception):
    """Raised for database or file-system failures. The message is safe to show to the user."""


class DocumentStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "carebridge.db"
        self.uploads_dir = self.data_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.last_backup: Path | None = None
        self._initialise()

    # ------------------------------------------------------------------ setup

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error as exc:
            logger.error("db_connect_failed error_type=%s", type(exc).__name__)
            raise StorageError("The local database could not be opened.") from None
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            logger.error("db_operation_failed error_type=%s", type(exc).__name__)
            raise StorageError("A database operation failed. No changes were saved.") from None
        finally:
            conn.close()

    def _initialise(self) -> None:
        existed = self.db_path.exists() and self.db_path.stat().st_size > 0
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            has_rows = existed and conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='documents'"
            ).fetchone()[0] and conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        if has_rows:
            self.last_backup = self._backup(version)
        with self.connect() as conn:
            conn.execute(_BASE_TABLE)
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
            for name, decl in _V2_COLUMNS:
                if name not in existing:
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {decl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_patient ON documents(patient_name)")
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _backup(self, from_version: int) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.db_path.with_name(f"carebridge.v{from_version}-backup-{stamp}.db")
        shutil.copy2(self.db_path, target)
        logger.info("db_backup_created schema_from=%s", from_version)
        return target

    # ------------------------------------------------------------------ files

    def file_path(self, row: sqlite3.Row | dict) -> Path:
        """Location of the stored original. Legacy rows used the bare document id as the name."""
        name = row["storage_name"] if "storage_name" in row.keys() and row["storage_name"] else row["id"]
        path = (self.uploads_dir / Path(name).name).resolve()
        if self.uploads_dir.resolve() not in path.parents:
            raise StorageError("Invalid stored file path.")
        return path

    def read_file(self, row: sqlite3.Row | dict) -> bytes | None:
        path = self.file_path(row)
        return path.read_bytes() if path.exists() else None

    # ------------------------------------------------------------------ queries

    def find_duplicate(self, sha256: str, patient_name: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE sha256=? AND patient_name=? LIMIT 1", (sha256, patient_name)
            ).fetchone()

    def list_documents(self, patient_name: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if patient_name is None:
                return conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
            return conn.execute(
                "SELECT * FROM documents WHERE patient_name=? ORDER BY created_at DESC", (patient_name,)
            ).fetchall()

    def list_patients(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT DISTINCT patient_name FROM documents ORDER BY patient_name").fetchall()
        return [r["patient_name"] for r in rows if r["patient_name"]]

    def get_document(self, doc_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()

    # ------------------------------------------------------------------ writes

    def save_document(self, record: dict, data: bytes) -> None:
        """Write the original file, then the metadata row. Removes the file if the insert fails."""
        path = self.uploads_dir / record["storage_name"]
        try:
            path.write_bytes(data)
        except OSError as exc:
            logger.error("file_write_failed document_id=%s error_type=%s", record["id"], type(exc).__name__)
            raise StorageError("The uploaded file could not be saved to disk.") from None
        columns = [
            "id", "patient_name", "filename", "doc_type", "doc_date", "extracted_text", "extracted_json",
            "created_at", "sha256", "media_type", "size_bytes", "storage_name", "extraction_method",
            "classification_confidence", "type_confirmed", "date_status", "status", "pages_json",
            "details_json", "warnings_json",
        ]
        values = [record.get(c) for c in columns]
        for key in ("extracted_json", "pages_json", "details_json", "warnings_json"):
            idx = columns.index(key)
            if not isinstance(values[idx], str):
                values[idx] = json.dumps(values[idx] if values[idx] is not None else [], ensure_ascii=False)
        try:
            with self.connect() as conn:
                conn.execute(
                    f"INSERT INTO documents ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})", values
                )
        except StorageError:
            path.unlink(missing_ok=True)
            raise

    def update_document_type(self, doc_id: str, doc_type: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET doc_type=?, type_confirmed=1 WHERE id=?", (doc_type, doc_id))

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document's row and its stored file. Returns False if it did not exist."""
        row = self.get_document(doc_id)
        if row is None:
            return False
        path = self.file_path(row)
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.error("file_delete_failed document_id=%s error_type=%s", doc_id, type(exc).__name__)
            raise StorageError("The record was deleted but its file could not be removed from disk.") from None
        return True

    def delete_patient_documents(self, patient_name: str) -> int:
        rows = self.list_documents(patient_name)
        for row in rows:
            self.delete_document(row["id"])
        return len(rows)
