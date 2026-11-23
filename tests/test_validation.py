import pytest

from carebridge.validation import ValidationError, detect_signature, safe_filename, validate_upload
from tests.helpers import text_image, text_pdf


def test_accepts_valid_pdf_png_jpeg_txt():
    assert validate_upload("r.pdf", text_pdf(["Hello"])).media_type == "application/pdf"
    assert validate_upload("r.png", text_image(["x"])).media_type == "image/png"
    assert validate_upload("r.JPG", text_image(["x"], fmt="JPEG")).media_type == "image/jpeg"
    assert validate_upload("r.txt", "Hemoglobin 13 g/dL".encode()).media_type == "text/plain"


def test_rejects_unsupported_extension():
    with pytest.raises(ValidationError, match="Unsupported"):
        validate_upload("malware.exe", b"MZ\x90\x00")


def test_rejects_mismatched_signature():
    with pytest.raises(ValidationError, match="do not match"):
        validate_upload("fake.pdf", b"MZ this is not a pdf")
    with pytest.raises(ValidationError, match="do not match"):
        validate_upload("fake.png", text_pdf(["x"]))


def test_rejects_empty_and_oversized_files():
    with pytest.raises(ValidationError, match="empty"):
        validate_upload("a.pdf", b"")
    with pytest.raises(ValidationError, match="larger"):
        validate_upload("a.pdf", b"%PDF-" + b"0" * 2048, max_bytes=1024)


def test_rejects_binary_disguised_as_text():
    with pytest.raises(ValidationError):
        validate_upload("notes.txt", b"\x00\x01\x02binary")
    with pytest.raises(ValidationError):
        validate_upload("notes.txt", text_pdf(["x"]))


def test_safe_filename_strips_paths_and_special_characters():
    assert safe_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert safe_filename("C:\\Users\\x\\report.PDF") == "report.pdf"
    assert safe_filename('a<b>:"c|?.png') == "a_b___c__.png"
    assert safe_filename("") == "document"
    assert safe_filename("রিপোর্ট.pdf") == "রিপোর্ট.pdf"
    assert len(safe_filename("a" * 500 + ".pdf")) <= 120


def test_detect_signature():
    assert detect_signature(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert detect_signature(b"hello") is None
