"""Normalisation applied to extracted text before classification and field extraction."""

from __future__ import annotations

import re
import unicodedata

_LIGATURES = {"\ufb01": "fi", "\ufb02": "fl", "\u00a0": " ", "\u200b": ""}


def clean_text(text: str) -> str:
    """Normalise Unicode, remove control characters and collapse redundant whitespace.

    Line breaks are kept because field extraction is line-oriented.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C" or ch in "\u200c\u200d")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
