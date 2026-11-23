import pytest

from carebridge.classification import (
    CONSULTATION, DIAGNOSTIC_REPORT, DISCHARGE_SUMMARY, IMAGING_REPORT, LAB_REPORT, PRESCRIPTION, UNKNOWN, classify,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("LABORATORY REPORT\nHemoglobin 13 g/dL\nReference range 12-16", LAB_REPORT),
        ("Rx\nTab. Napa 500 mg 1+0+1\nTab. Seclo 20 mg 1+0+1 before meals", PRESCRIPTION),
        ("DISCHARGE SUMMARY\nDate of admission: 2026-01-01\nHospital course: uneventful", DISCHARGE_SUMMARY),
        ("ULTRASONOGRAPHY OF WHOLE ABDOMEN\nFindings: ...\nImpression: ...", IMAGING_REPORT),
        ("Consultation note\nChief complaints: cough\nOn examination: ...", CONSULTATION),
        ("ECG REPORT\nRhythm: sinus", DIAGNOSTIC_REPORT),
        ("চিকিৎসাপত্র\nট্যাবলেট", PRESCRIPTION),
    ],
)
def test_classifies_known_types(text, expected):
    assert classify(text).label == expected


def test_unknown_when_no_rule_matches():
    result = classify("Hello, this is a letter about a meeting.")
    assert result.label == UNKNOWN
    assert result.needs_confirmation


def test_rx_is_not_matched_inside_words():
    # The original prototype matched "rx" as a substring (e.g. in "proxy").
    assert classify("Proxy server configuration notes").label == UNKNOWN


def test_weak_single_signal_is_low_confidence():
    result = classify("Glucose was discussed")
    assert result.label == LAB_REPORT
    assert result.confidence == "low"


def test_strong_signals_are_high_confidence():
    result = classify("LABORATORY REPORT\nComplete Blood Count\nHemoglobin 13 g/dL\nReference range 12-16")
    assert result.confidence == "high"


def test_filename_only_contributes_weakly():
    result = classify("No useful text", "prescription_scan.pdf")
    assert result.label == PRESCRIPTION
    assert result.confidence == "low"
