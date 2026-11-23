from carebridge.extraction import PageText
from carebridge.fields import choose_document_date, extract_dates, extract_details, extract_lab_results, extract_medications


def pages(text: str, page: int = 1) -> list[PageText]:
    return [PageText(page, text, "test")]


LAB = """CITY DIAGNOSTIC CENTRE
LABORATORY REPORT
Patient Name: Demo Patient
DOB: 01/02/1990
Report Date: 12 Jan 2026
Hemoglobin: 13.5 g/dL (12.0 - 16.0)
HbA1c 5.4 % <5.7
Fasting Blood Glucose 92 mg/dL 70-100
Serum Creatinine 0.9 mg/dl 0.6-1.2
Total WBC Count 7,500 /cumm 4000-11000
Platelet Count
250000
"""


def test_lab_values_units_ranges_and_pages():
    results = {r.field: r for r in extract_lab_results(pages(LAB, page=3))}
    assert results["Hemoglobin"].value == "13.5"
    assert results["Hemoglobin"].unit == "g/dL"
    assert results["Hemoglobin"].reference_range == "12.0 - 16.0"
    assert results["HbA1c"].value == "5.4" and results["HbA1c"].reference_range == "<5.7"
    assert results["Fasting glucose"].value == "92"
    assert results["Creatinine"].unit == "mg/dl"
    assert results["WBC"].value == "7,500"
    assert all(r.page == 3 for r in results.values())
    assert "Hemoglobin" not in results["HbA1c"].field


def test_value_on_next_line_is_marked_uncertain():
    platelets = next(r for r in extract_lab_results(pages(LAB)) if r.field == "Platelets")
    assert platelets.value == "250000"
    assert "following line" in platelets.uncertain
    assert "unit not found" in platelets.uncertain


def test_missing_values_are_not_invented():
    assert extract_lab_results(pages("Hemoglobin estimation\nMethod: photometry")) == []


def test_date_formats():
    values = [c.value for c in extract_dates(pages("2026-01-12\n12/01/2026\n12 January, 2026\nJan 12, 2026\n25.12.2025"))]
    assert values == ["2026-01-12", "2026-01-12", "2026-01-12", "2026-01-12", "2025-12-25"]


def test_ambiguous_day_month_is_uncertain():
    chosen = choose_document_date(extract_dates(pages("Date: 03/04/2026")))
    assert chosen.value == "2026-04-03"
    assert chosen.status == "uncertain"


def test_birth_date_is_not_used_as_document_date():
    chosen = choose_document_date(extract_dates(pages("DOB: 1990-02-01\nReport Date: 2026-01-12")))
    assert chosen.value == "2026-01-12"


def test_missing_date_stays_missing():
    chosen = choose_document_date(extract_dates(pages("No date here. DOB: 1990-02-01")))
    assert chosen.value is None and chosen.status == "missing"


def test_invalid_dates_are_ignored():
    assert extract_dates(pages("2026-13-45 and 31/02/2026")) == []


def test_medications_copied_as_written():
    meds = extract_medications(pages("Rx\n1. Tab. Napa 500 mg 1+0+1 x 7 days\nCap. Omep 20mg before meals\nSyp. Ace"))
    assert [m.name for m in meds] == ["Napa", "Omep", "Ace"]
    assert meds[0].strength_text == "500 mg" and meds[0].frequency_text == "1+0+1" and meds[0].duration_text == "x 7 days"
    assert meds[1].frequency_text == "" and "frequency not found" in meds[1].uncertain
    assert meds[2].strength_text == ""  # dosage is never inferred


def test_details_bundle_doctor_facility_patient():
    details = extract_details(pages(LAB + "Dr. Ayesha Rahman\n"))
    assert details.doctor.value == "Ayesha Rahman"
    assert details.facility.value == "CITY DIAGNOSTIC CENTRE"
    assert details.patient_name_in_document.value == "Demo Patient"
    assert details.document_date.value == "2026-01-12"


def test_bengali_digits_in_dates():
    candidate = extract_dates(pages("পরীক্ষার তারিখ: ২৫/১২/২০২৫"))[0]
    assert candidate.value == "2025-12-25"
    assert candidate.raw == "২৫/১২/২০২৫"
    assert candidate.labelled


def test_discharge_date_preferred_over_admission_date():
    text = "Date of admission: 2026-01-03\nDate of discharge: 2026-01-07"
    assert choose_document_date(extract_dates(pages(text))).value == "2026-01-07"


def test_report_date_preferred_over_collection_date():
    text = "Collected on: 2026-01-02\nReported on: 2026-01-04"
    assert choose_document_date(extract_dates(pages(text))).value == "2026-01-04"


def test_leap_day_today_does_not_crash(monkeypatch):
    import datetime as real_datetime

    from carebridge import fields

    class LeapDate(real_datetime.date):
        @classmethod
        def today(cls):
            return cls(2028, 2, 29)

    monkeypatch.setattr(fields, "date", LeapDate)
    assert choose_document_date(extract_dates(pages("Report date: 2028-02-20"))).value == "2028-02-20"


def test_birth_date_label_does_not_hide_report_date_on_same_line():
    text = "Report date: 2026-02-12    DOB: 1980-05-01"
    assert choose_document_date(extract_dates(pages(text))).value == "2026-02-12"


def test_collection_label_does_not_leak_to_report_date_on_same_line():
    text = "Collected: 2026-02-10   Reported: 2026-02-12"
    assert choose_document_date(extract_dates(pages(text))).value == "2026-02-12"


def test_lab_value_with_attached_flag_keeps_decimal():
    (lab,) = extract_lab_results(pages("Glucose 5.6H mmol/L 3.9-5.5"))
    assert lab.value == "5.6"


def test_comma_reference_range_kept_whole():
    (lab,) = extract_lab_results(pages("WBC 12,500 /cumm 4,000-11,000"))
    assert lab.value == "12,500"
    assert lab.reference_range.startswith("4,000-11,000")


def test_reference_range_only_row_is_not_a_result():
    assert extract_lab_results(pages("Hemoglobin 13.0-17.0 g/dL")) == []


def test_next_numbered_row_is_not_taken_as_value():
    text = "1. Hemoglobin\n2. Glucose 5.4 mmol/L"
    labs = extract_lab_results(pages(text))
    assert [(lab.field, lab.value) for lab in labs] == [("Glucose", "5.4")]


def test_document_title_is_not_a_facility():
    details = extract_details(pages("Laboratory Report\nGreen Valley Clinic\nHemoglobin 13.1 g/dL"))
    assert details.facility.value == "Green Valley Clinic"


def test_trailing_birth_label_excludes_date():
    text = "Demo Patient 1980-05-01 (DOB)\nSample note"
    assert choose_document_date(extract_dates(pages(text))).value is None
    assert choose_document_date(extract_dates(pages("1980-05-01 (DOB)   Visit: 2026-02-12"))).value == "2026-02-12"


def test_comma_after_decimal_value():
    (lab,) = extract_lab_results(pages("Glucose 5.6, mmol/L, 3.9-5.5"))
    assert lab.value == "5.6"


def test_dash_between_value_and_range():
    (lab,) = extract_lab_results(pages("Hemoglobin 12.5 - 13.0-17.0 g/dL"))
    assert lab.value == "12.5" and lab.reference_range.startswith("13.0-17.0")
