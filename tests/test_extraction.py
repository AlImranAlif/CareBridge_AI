import pytest

from carebridge.extraction import (
    METHOD_OCR, METHOD_TEXT_LAYER, ExtractionError, extract_pdf, extract_plain_text, extract_text,
)
from tests.helpers import BENGALI_FONT_CANDIDATES, find_font, ocr_ready, scanned_pdf, text_image, text_pdf

needs_ocr = pytest.mark.skipif(not ocr_ready("eng"), reason="Tesseract with English data is not installed")


def test_text_pdf_uses_text_layer_and_keeps_page_numbers():
    result = extract_pdf(text_pdf(["Laboratory Report page one text", "Hemoglobin 13.5 g/dL on page two"]))
    assert [p.page for p in result.pages] == [1, 2]
    assert all(p.method == METHOD_TEXT_LAYER for p in result.pages)
    assert "Hemoglobin" in result.pages[1].text
    assert result.ocr_language is None  # no OCR was needed


def test_corrupted_pdf_raises_readable_error():
    with pytest.raises(ExtractionError, match="could not be opened"):
        extract_pdf(b"%PDF-1.7\n this is garbage")


def test_encrypted_pdf_is_rejected():
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    with pytest.raises(ExtractionError, match="password"):
        extract_pdf(data)


def test_blank_pdf_without_ocr_returns_no_text_and_warning():
    result = extract_pdf(text_pdf([""]), use_ocr=False)
    assert result.text == ""
    assert any("OCR is unavailable" in w for w in result.warnings)


def test_plain_text_extraction():
    assert extract_plain_text("Glucose 90 mg/dL".encode()).pages[0].text == "Glucose 90 mg/dL"


def test_unsupported_extension():
    with pytest.raises(ExtractionError):
        extract_text(b"abc", ".docx")


def test_corrupted_image_raises_readable_error():
    with pytest.raises(ExtractionError, match="could not be opened"):
        extract_text(b"\x89PNG\r\n\x1a\nnot really a png", ".png")


@needs_ocr
def test_image_ocr_reads_english_text():
    result = extract_text(text_image(["LABORATORY REPORT", "Hemoglobin 13.5 g/dL"]), ".png")
    assert result.pages[0].method == METHOD_OCR
    assert "hemoglobin" in result.text.lower()
    assert "13.5" in result.text


@needs_ocr
def test_scanned_pdf_is_ocrd_only_on_pages_without_text():
    scanned_page = text_image(["DISCHARGE SUMMARY", "Discharge date: 2026-02-10"])
    import pymupdf

    mixed = pymupdf.open(stream=scanned_pdf([scanned_page]), filetype="pdf")
    text_page = mixed.new_page()
    text_page.insert_text((72, 72), "This second page has a real text layer with enough characters.")
    data = mixed.tobytes()
    result = extract_pdf(data)
    assert result.pages[0].method == METHOD_OCR
    assert "discharge" in result.pages[0].text.lower()
    assert result.pages[1].method == METHOD_TEXT_LAYER


@pytest.mark.skipif(
    not ocr_ready("ben") or not find_font(BENGALI_FONT_CANDIDATES),
    reason="Tesseract Bengali data or a Bengali font is not installed",
)
def test_bengali_image_ocr_recognises_printed_lines():
    lines = ["রোগীর নাম: পরীক্ষা", "পরীক্ষার তারিখ: ১২/০১/২০২৬", "চিকিৎসাপত্র"]
    image = text_image(lines, font_path=find_font(BENGALI_FONT_CANDIDATES), size=44)
    text = extract_text(image, ".png").text
    for line in lines:
        assert line in text
