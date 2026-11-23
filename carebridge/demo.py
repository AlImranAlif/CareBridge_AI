"""Synthetic demo records. All names, values and facilities are invented for interface testing."""

from __future__ import annotations

DEMO_PATIENT = "Demo Patient"

DEMO_DOCUMENTS: list[tuple[str, str]] = [
    (
        "sample_lab_jan.txt",
        "LABORATORY REPORT\nPatient: Demo Patient\nDate: 2026-01-12\n"
        "Hemoglobin: 13.5 g/dL\nGlucose: 92 mg/dL\nCreatinine: 0.9 mg/dL",
    ),
    (
        "sample_prescription_mar.txt",
        "PRESCRIPTION\nPatient: Demo Patient\nDate: 2026-03-08\nFollow-up: 4 weeks\n"
        "Note: Sample synthetic record for UI demonstration.",
    ),
    (
        "sample_lab_jun.txt",
        "LABORATORY REPORT\nPatient: Demo Patient\nDate: 2026-06-19\n"
        "Hemoglobin: 13.8 g/dL\nGlucose: 96 mg/dL\nCreatinine: 0.9 mg/dL",
    ),
    (
        "sample_ultrasound_undated.txt",
        "SYNTHETIC IMAGING CENTRE\nULTRASONOGRAPHY REPORT\nPatient: Demo Patient\n"
        "Findings: Sample synthetic text for interface testing only.\n"
        "Impression: Synthetic demo record - no clinical meaning.",
    ),
]
