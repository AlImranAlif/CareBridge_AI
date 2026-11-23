"""Builders for synthetic test documents. No real patient data is used anywhere in the tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from carebridge.extraction import ocr_status

LATIN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
BENGALI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
]


def find_font(candidates: list[str]) -> str | None:
    return next((p for p in candidates if Path(p).exists()), None)


def ocr_ready(language: str = "eng") -> bool:
    status = ocr_status()
    return status.available and language in status.languages


def text_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def text_image(lines: list[str], font_path: str | None = None, size: int = 34, fmt: str = "PNG") -> bytes:
    font = ImageFont.truetype(font_path or find_font(LATIN_FONT_CANDIDATES), size)
    height = 60 + len(lines) * int(size * 1.8)
    image = Image.new("RGB", (1400, height), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((40, 30 + i * int(size * 1.8)), line, fill="black", font=font)
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def scanned_pdf(image_pages: list[bytes]) -> bytes:
    """A PDF whose pages contain only images (no text layer), like a scanner produces."""
    doc = pymupdf.open()
    for png in image_pages:
        with Image.open(BytesIO(png)) as im:
            width, height = im.size
        page = doc.new_page(width=width * 0.6, height=height * 0.6)
        page.insert_image(page.rect, stream=png)
    data = doc.tobytes()
    doc.close()
    return data
