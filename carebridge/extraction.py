"""Text extraction from PDFs, images and plain-text files, with OCR fallback.

Each page keeps its page number and the method used, so extracted fields can point
back to the page they came from.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO

from .validation import MAX_IMAGE_PIXELS, MAX_PDF_PAGES

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF releases only ship the "fitz" name
    try:
        import fitz
    except ImportError:
        fitz = None
try:
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None
try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

logger = logging.getLogger("carebridge.extraction")

# A page with fewer meaningful characters than this is treated as scanned and sent to OCR.
MIN_PAGE_TEXT_CHARS = 25
OCR_RENDER_ZOOM = 2.0

METHOD_TEXT_LAYER = "PDF text layer"
METHOD_OCR = "OCR"
METHOD_PLAIN_TEXT = "Plain text"
METHOD_NONE = "No text"


class ExtractionError(Exception):
    """Raised when no text can be extracted. The message is safe to show to the user."""


@dataclass
class PageText:
    page: int
    text: str
    method: str


@dataclass
class ExtractionResult:
    pages: list[PageText]
    warnings: list[str] = field(default_factory=list)
    ocr_language: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def method(self) -> str:
        methods = sorted({p.method for p in self.pages if p.text.strip()})
        if not methods:
            return METHOD_NONE
        return " + ".join(methods)


@dataclass(frozen=True)
class OcrStatus:
    available: bool
    languages: tuple[str, ...]
    message: str


@lru_cache(maxsize=1)
def ocr_status() -> OcrStatus:
    """Report whether the Tesseract engine and language data are usable on this machine."""
    if pytesseract is None or Image is None:
        return OcrStatus(False, (), "pytesseract or Pillow is not installed.")
    try:
        pytesseract.get_tesseract_version()
        languages = tuple(sorted(set(pytesseract.get_languages(config="")) - {"osd"}))
    except Exception:
        return OcrStatus(False, (), "Tesseract OCR is not installed or not on PATH.")
    if "eng" not in languages:
        return OcrStatus(False, languages, "Tesseract is installed but English language data (eng) is missing.")
    return OcrStatus(True, languages, "Tesseract OCR is available.")


def ocr_language() -> str:
    """Language string passed to Tesseract.

    Uses CAREBRIDGE_OCR_LANG when set; otherwise English plus Bengali when the Bengali
    data (ben) is installed, else English only.
    """
    configured = os.environ.get("CAREBRIDGE_OCR_LANG", "").strip()
    if configured:
        return configured
    return "eng+ben" if "ben" in ocr_status().languages else "eng"


def _ocr_image(image) -> str:
    return pytesseract.image_to_string(image, lang=ocr_language())


def _meaningful_chars(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def extract_pdf(data: bytes, use_ocr: bool = True) -> ExtractionResult:
    """Extract text page by page; OCR only pages whose text layer is (nearly) empty."""
    if fitz is None:
        raise ExtractionError("PDF support is unavailable. Install the packages in requirements.txt.")
    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise ExtractionError("The PDF could not be opened. It may be corrupted.") from None
    with pdf:
        if pdf.needs_pass:
            raise ExtractionError("The PDF is password-protected. Remove the password and upload it again.")
        if pdf.page_count == 0:
            raise ExtractionError("The PDF has no pages.")
        if pdf.page_count > MAX_PDF_PAGES:
            raise ExtractionError(f"The PDF has more than {MAX_PDF_PAGES} pages.")
        status = ocr_status() if use_ocr else OcrStatus(False, (), "OCR disabled.")
        result = ExtractionResult(pages=[])
        skipped_pages: list[int] = []
        for number, page in enumerate(pdf, start=1):
            try:
                text = page.get_text("text")
            except Exception:
                text = ""
                result.warnings.append(f"Page {number}: the text layer could not be read.")
            if _meaningful_chars(text) >= MIN_PAGE_TEXT_CHARS:
                result.pages.append(PageText(number, text, METHOD_TEXT_LAYER))
                continue
            if not status.available:
                result.pages.append(PageText(number, text, METHOD_TEXT_LAYER))
                skipped_pages.append(number)
                continue
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(OCR_RENDER_ZOOM, OCR_RENDER_ZOOM), alpha=False)
                with Image.open(BytesIO(pix.tobytes("png"))) as image:
                    ocr_text = _ocr_image(image)
                result.ocr_language = ocr_language()
                best = ocr_text if _meaningful_chars(ocr_text) > _meaningful_chars(text) else text
                result.pages.append(PageText(number, best, METHOD_OCR if best is ocr_text else METHOD_TEXT_LAYER))
            except Exception as exc:
                logger.warning("ocr_failed page=%s error_type=%s", number, type(exc).__name__)
                result.pages.append(PageText(number, text, METHOD_TEXT_LAYER))
                result.warnings.append(f"Page {number}: OCR failed.")
        if skipped_pages:
            pages = ", ".join(map(str, skipped_pages))
            result.warnings.append(
                f"Page(s) {pages} look scanned but OCR is unavailable ({status.message}). Text from these pages may be missing."
            )
    return result


def extract_image(data: bytes) -> ExtractionResult:
    """OCR a PNG/JPEG/WEBP image."""
    if Image is None:
        raise ExtractionError("Image support is unavailable. Install the packages in requirements.txt.")
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ExtractionError("The image dimensions are too large.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError("The image could not be opened. It may be corrupted.") from None
    status = ocr_status()
    if not status.available:
        raise ExtractionError(f"Images need OCR, but OCR is unavailable: {status.message}")
    try:
        text = _ocr_image(image)
    except Exception as exc:
        logger.warning("ocr_failed page=1 error_type=%s", type(exc).__name__)
        raise ExtractionError("OCR failed for this image.") from None
    return ExtractionResult(pages=[PageText(1, text, METHOD_OCR)], ocr_language=ocr_language())


def extract_plain_text(data: bytes) -> ExtractionResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractionError("The text file is not valid UTF-8.") from None
    return ExtractionResult(pages=[PageText(1, text, METHOD_PLAIN_TEXT)])


def extract_text(data: bytes, extension: str) -> ExtractionResult:
    """Dispatch to the right extractor for a validated file extension."""
    extension = extension.lower()
    if extension == ".pdf":
        return extract_pdf(data)
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        return extract_image(data)
    if extension == ".txt":
        return extract_plain_text(data)
    raise ExtractionError("Unsupported file type.")
