from carebridge.pipeline import process_document
from carebridge.records import filter_records, sort_timeline, to_record
from carebridge.storage import DocumentStore
from carebridge.summary import build_summary

DOCS = {
    "lab_jun.txt": b"LABORATORY REPORT\nDate: 2026-06-19\nHemoglobin: 13.8 g/dL\nGlucose: 96 mg/dL",
    "lab_jan.txt": b"LABORATORY REPORT\nDate: 2026-01-12\nHemoglobin: 13.5 g/dL",
    "rx.txt": b"PRESCRIPTION\nDate: 2026-03-08\nTab. Napa 500 mg 1+0+1 x 5 days\nDr. Test Doctor",
    "undated_note.txt": b"Some synthetic note without any date or known keywords",
}


def make_records(tmp_path):
    store = DocumentStore(tmp_path)
    for name, data in DOCS.items():
        store.save_document(process_document(name, data, "P").to_record("P"), data)
    return [to_record(r) for r in store.list_documents("P")]


def test_timeline_sorted_oldest_first_with_undated_last(tmp_path):
    ordered = sort_timeline(make_records(tmp_path))
    assert [r.filename for r in ordered] == ["lab_jan.txt", "rx.txt", "lab_jun.txt", "undated_note.txt"]
    assert ordered[-1].display_date == "Date unknown"


def test_filter_by_type_and_search(tmp_path):
    records = make_records(tmp_path)
    assert {r.filename for r in filter_records(records, ["Laboratory report"])} == {"lab_jan.txt", "lab_jun.txt"}
    assert [r.filename for r in filter_records(records, query="napa")] == ["rx.txt"]
    assert [r.filename for r in filter_records(records, query="UNDATED")] == ["undated_note.txt"]


def test_summary_sections_and_source_references(tmp_path):
    summary = build_summary(make_records(tmp_path), "P")
    for heading in ["1. OVERVIEW", "2. CHRONOLOGICAL RECORD", "3. LABORATORY VALUES", "4. DOCUMENTED HISTORY",
                    "5. MISSING OR UNCERTAIN INFORMATION", "6. SOURCE DOCUMENTS"]:
        assert heading in summary
    assert "13.5 g/dL [D1, p.1]" in summary
    assert "13.8 g/dL [D3, p.1]" in summary
    assert "Tab Napa 500 mg (frequency as written: 1+0+1; duration as written: x 5 days) [D2, p.1]" in summary
    assert "Date not identified: undated_note.txt [D4]" in summary
    assert "D4: undated_note.txt" in summary
    assert "not a diagnosis" in summary


def test_summary_support_every_value_appears_in_its_source(tmp_path):
    records = make_records(tmp_path)
    for record in records:
        for lab in record.lab_results:
            assert lab["value"] in record.text
            assert lab["unit"] in record.text


def test_empty_summary(tmp_path):
    assert "No documents are stored" in build_summary([], "P")


def test_confirming_type_clears_type_warning(tmp_path):
    store = DocumentStore(tmp_path)
    data = DOCS["undated_note.txt"]
    record = process_document("undated_note.txt", data, "P").to_record("P")
    store.save_document(record, data)
    assert any("Please confirm" in w for w in to_record(store.get_document(record["id"])).warnings)
    store.update_document_type(record["id"], "Other medical document")
    assert not any("Please confirm" in w for w in to_record(store.get_document(record["id"])).warnings)
