"""Upload validation: size, type allow-list, file signatures and safe filenames."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_IMAGE_PIXELS = 40_000_000
MAX_FILENAME_LENGTH = 120

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".txt": "text/plain",
}
ALLOWED_EXTENSIONS = tuple(MEDIA_TYPES)


class ValidationError(ValueError):
    """Raised when an upload is rejected. The message is safe to show to the user."""


@dataclass(frozen=True)
class ValidatedFile:
    original_name: str
    safe_name: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str
    data: bytes


def safe_filename(name: str) -> str:
    """Return a display/storage-safe version of a user-supplied filename.

    Directory components are dropped, control and shell-special characters are replaced,
    and the length is bounded. Unicode letters (e.g. Bengali) are kept.
    """
    base = Path((name or "").replace("\\", "/")).name
    base = unicodedata.normalize("NFC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")
    base = re.sub(r'[<>:"/\\|?*\x00]', "_", base).strip(" .")
    if not base:
        base = "document"
    stem, suffix = Path(base).stem, Path(base).suffix.lower()
    if len(base) > MAX_FILENAME_LENGTH:
        stem = stem[: MAX_FILENAME_LENGTH - len(suffix)]
    return f"{stem}{suffix}" if stem else f"document{suffix}"


def detect_signature(data: bytes) -> str | None:
    """Return the media type implied by the file's leading bytes, or None if unrecognised."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def validate_upload(name: str, data: bytes, max_bytes: int = MAX_UPLOAD_BYTES) -> ValidatedFile:
    """Validate an uploaded file by extension *and* content signature.

    Raises ValidationError with a user-readable message when the file is rejected.
    """
    safe = safe_filename(name)
    extension = Path(safe).suffix.lower()
    if extension not in MEDIA_TYPES:
        raise ValidationError("Unsupported file type. Upload a PDF, PNG, JPG/JPEG, WEBP or plain-text (.txt) file.")
    if not data:
        raise ValidationError("The file is empty.")
    if len(data) > max_bytes:
        raise ValidationError(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    expected = MEDIA_TYPES[extension]
    if expected == "text/plain":
        if detect_signature(data) is not None or not _looks_like_text(data):
            raise ValidationError("The .txt file is not valid UTF-8 plain text.")
    elif detect_signature(data) != expected:
        raise ValidationError("The file contents do not match its extension. The file may be corrupted or mislabelled.")
    return ValidatedFile(
        original_name=name,
        safe_name=safe,
        extension=extension,
        media_type=expected,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        data=data,
    )
