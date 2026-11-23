"""CareBridge AI - Streamlit user interface.

All processing, storage and summary logic lives in the ``carebridge`` package; this file only
renders the interface and calls into it.
"""

from __future__ import annotations

import logging
import re
import os
from collections import Counter
from pathlib import Path

import streamlit as st

from carebridge.classification import DOCUMENT_TYPES
from carebridge.demo import DEMO_DOCUMENTS, DEMO_PATIENT
from carebridge.extraction import ExtractionError, ocr_language, ocr_status
from carebridge.pipeline import process_document
from carebridge.records import DocumentRecord, filter_records, sort_timeline, to_record
from carebridge.storage import DocumentStore, StorageError
from carebridge.summary import build_summary
from carebridge.validation import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, ValidationError, validate_upload

logging.basicConfig(level=os.environ.get("CAREBRIDGE_LOG_LEVEL", "WARNING"))

BASE = Path(__file__).parent
DATA_DIR = Path(os.environ.get("CAREBRIDGE_DATA_DIR", BASE / "data"))

st.set_page_config(page_title="CareBridge AI", page_icon="🩺", layout="wide")


@st.cache_resource
def get_store(data_dir: str) -> DocumentStore:
    return DocumentStore(Path(data_dir))


try:
    store = get_store(str(DATA_DIR))
except StorageError as exc:
    st.error(f"{exc} Check that {DATA_DIR} is writable.")
    st.stop()

st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
.hero {padding: 1.4rem 1.6rem; border-radius: 18px; background: linear-gradient(115deg,#102d46,#176b75); color:white; margin-bottom:1rem;}
.hero h1 {color:white; margin:0; font-size:2.2rem;}
.hero p {color:#d8edf0; margin:.4rem 0 0 0;}
div[data-testid="stMetric"] {background:#f7fafc;padding:14px;border:1px solid #e2e8f0;border-radius:12px}
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero"><h1>🩺 CareBridge AI</h1><p>Your medical history, connected and understandable.</p></div>',
    unsafe_allow_html=True,
)
st.warning(
    "Prototype for demonstration only. Use synthetic or de-identified records. This app does not diagnose, "
    "recommend treatment, or replace a healthcare professional."
)

# ----------------------------------------------------------------------------- helpers


def save_upload(name: str, data: bytes, patient: str) -> tuple[str, str, str | None]:
    """Validate, de-duplicate, process and store one file. Returns (level, message, document id)."""
    try:
        validated = validate_upload(name, data)
    except ValidationError as exc:
        return "error", f"{md(name)}: {md(exc)}", None
    duplicate = store.find_duplicate(validated.sha256, patient)
    if duplicate:
        return "warning", f"{md(validated.safe_name)}: already stored for {md(patient)} as \"{md(duplicate['filename'])}\". Skipped.", None
    try:
        processed = process_document(name, data, patient)
        record = processed.to_record(patient)
        store.save_document(record, data)
    except (ValidationError, ExtractionError, StorageError) as exc:
        return "error", f"{md(validated.safe_name)}: {md(exc)}", None
    level = "warning" if processed.warnings else "success"
    message = (
        f"{md(validated.safe_name)}: saved as **{record['doc_type']}** (confidence: {record['classification_confidence']}); "
        f"extraction: {record['extraction_method']}; {len(processed.details.lab_results)} lab value(s), "
        f"{len(processed.details.medications)} medicine line(s)."
    )
    if processed.warnings:
        message += "\n\n" + "\n".join(f"- {md(w)}" for w in processed.warnings)
    return level, message, record["id"]


def load_demo_records() -> None:
    for filename, text in DEMO_DOCUMENTS:
        save_upload(filename, text.encode("utf-8"), DEMO_PATIENT)


_TYPE_SELECTOR_PREFIXES = ("up", "tl")


def md(text: object) -> str:
    """Escape Markdown so document-derived text is shown literally (no links or remote images)."""
    return re.sub(r"([\\`*_{}\[\]()<>#+\-.!|~])", r"\\\1", str(text))


def _save_type_choice(doc_id: str, widget_key: str) -> None:
    store.update_document_type(doc_id, st.session_state[widget_key])
    for prefix in _TYPE_SELECTOR_PREFIXES:
        other = f"{prefix}_type_{doc_id}"
        if other != widget_key:
            st.session_state.pop(other, None)


def type_selector(record: DocumentRecord, key_prefix: str) -> None:
    options = DOCUMENT_TYPES if record.doc_type in DOCUMENT_TYPES else [record.doc_type, *DOCUMENT_TYPES]
    label = "Confirm document type" if record.needs_type_confirmation else "Document type"
    key = f"{key_prefix}_type_{record.id}"
    choice = st.selectbox(
        label, options, index=options.index(record.doc_type), key=key,
        on_change=_save_type_choice, args=(record.id, key),
    )
    if record.needs_type_confirmation and st.button("Confirm type", key=f"{key_prefix}_confirm_{record.id}"):
        store.update_document_type(record.id, choice)
        st.rerun()


def render_record_details(record: DocumentRecord) -> None:
    left, right = st.columns([1, 1])
    with left:
        date_note = ""
        if record.date_status == "uncertain":
            date_note = f" - uncertain: {(record.details.get('document_date') or {}).get('reason', '')}"
        elif not record.doc_date:
            date_note = " - not found in the document"
        st.markdown(f"**Document date:** {record.doc_date or 'Unknown'}{date_note}")
        confidence = "confirmed by user" if record.type_confirmed else f"detected, confidence {record.classification_confidence}"
        st.markdown(f"**Type:** {record.doc_type} ({confidence})")
        st.markdown(f"**Extraction method:** {record.extraction_method}  \n**Uploaded:** {record.created_at}")
        st.caption(f"SHA-256: {record.sha256[:20]}…")
    with right:
        type_selector(record, "tl")
        for key, label in (("doctor", "Doctor named"), ("facility", "Facility named"), ("patient_name_in_document", "Patient name in document")):
            item = record.details.get(key)
            if item:
                st.markdown(f"**{label}:** {md(item['value'])} (page {item['page']})")
    for warning in record.warnings:
        st.warning(md(warning))

    st.markdown("**Laboratory values (candidates - check against the source)**")
    if record.lab_results:
        columns = ["field", "value", "unit", "reference_range", "page", "uncertain", "source_excerpt"]
        st.dataframe([{c: lab.get(c, "") for c in columns} for lab in record.lab_results], hide_index=True)
    else:
        st.caption("No supported laboratory values were detected.")
    if record.medications:
        st.markdown("**Medicine lines (copied as written; nothing is inferred)**")
        columns = ["form", "name", "strength_text", "frequency_text", "duration_text", "page", "uncertain", "source_line"]
        st.dataframe([{c: med.get(c, "") for c in columns} for med in record.medications], hide_index=True)

    st.markdown("**Source text**")
    pages = record.pages or [{"page": 1, "text": record.text, "method": record.extraction_method}]
    if len(pages) > 1:
        number = st.selectbox("Page", [p["page"] for p in pages], key=f"page_{record.id}")
        page = next(p for p in pages if p["page"] == number)
    else:
        page = pages[0]
    st.text_area(
        f"Page {page['page']} · {page.get('method', '')}", page.get("text", ""), height=220, disabled=True, key=f"src_{record.id}_{page['page']}"
    )

    original = store.read_file({"id": record.id, "storage_name": record.storage_name})
    action_left, action_right = st.columns([1, 1])
    with action_left:
        if original is not None:
            st.download_button(
                "Download original document", original, file_name=record.filename,
                mime=record.media_type or "application/octet-stream", key=f"dl_{record.id}",
            )
        else:
            st.caption("Original file is missing from local storage.")
    with action_right:
        confirm = st.checkbox("I want to delete this record and its file", key=f"delc_{record.id}")
        if st.button("Delete record", key=f"del_{record.id}", disabled=not confirm):
            try:
                store.delete_document(record.id)
            except StorageError as exc:
                st.error(str(exc))
            else:
                st.rerun()


# ----------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Patient profile")
    patients = store.list_patients()
    new_label = "+ New profile"
    if "pending_profile" in st.session_state:
        st.session_state["profile"] = st.session_state.pop("pending_profile")
    if st.session_state.get("profile") not in [*patients, new_label]:
        st.session_state.pop("profile", None)
    choice = st.selectbox("Profile", [*patients, new_label] if patients else [new_label], key="profile")
    if choice == new_label:
        patient = st.text_input("Display name for new profile", value=DEMO_PATIENT if not patients else "").strip()
    else:
        patient = choice
    st.caption("Profiles only group records on this computer. There is no login or access control.")
    status = ocr_status()
    st.divider()
    if status.available:
        st.success(f"OCR available ({ocr_language()})")
    else:
        st.info(f"OCR unavailable: {status.message} Text-based PDFs and .txt files still work.")

records = [to_record(r) for r in store.list_documents(patient)] if patient else []

tab_dash, tab_upload, tab_timeline, tab_summary, tab_data = st.tabs(
    ["🏠 Dashboard", "📤 Upload documents", "🗂️ Health timeline", "📝 Summary", "🔒 Data & privacy"]
)

# ----------------------------------------------------------------------------- dashboard

with tab_dash:
    st.subheader(f"Dashboard · {patient or 'no profile selected'}")
    if not records:
        st.info("No records for this profile yet. Upload a document, or load the synthetic demo records.")
        if st.button("Load synthetic demo records"):
            load_demo_records()
            st.session_state["pending_profile"] = DEMO_PATIENT
            st.rerun()
    else:
        needs_review = [r for r in records if r.needs_type_confirmation or r.warnings]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Documents", len(records))
        m2.metric("Document types", len({r.doc_type for r in records}))
        m3.metric("Lab values extracted", sum(len(r.lab_results) for r in records))
        m4.metric("Need review", len(needs_review))
        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Documents by category**")
            st.bar_chart(dict(Counter(r.doc_type for r in records)))
        with right:
            st.markdown("**Recent uploads**")
            for r in records[:5]:
                flag = " · ⚠️ needs review" if r in needs_review else ""
                st.markdown(f"- {r.created_at[:16].replace('T', ' ')} · {md(r.doc_type)} · {md(r.filename)}{flag}")
            undated = sum(1 for r in records if not r.doc_date)
            if undated:
                st.caption(f"{undated} document(s) have no identified date and appear at the end of the timeline.")

# ----------------------------------------------------------------------------- upload

with tab_upload:
    st.subheader("Upload medical documents")
    if not patient:
        st.info("Enter a profile name in the sidebar first.")
    c1, c2 = st.columns([1, 1])
    with c1:
        uploads = st.file_uploader(
            "PDF, image or plain-text file",
            type=[e.lstrip(".") for e in ALLOWED_EXTENSIONS],
            accept_multiple_files=True,
            disabled=not patient,
        )
        st.caption(
            f"Up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per file. Files are checked by content, not only by extension. "
            "Images and scanned PDFs need Tesseract OCR."
        )
    with c2:
        st.info(
            "**What happens after upload?**\n\n1. The file is validated and checked for duplicates.\n"
            "2. Text is extracted (OCR only for pages without a text layer).\n3. A document type is suggested with a confidence level.\n"
            "4. Dates, lab values and medicine lines are copied where recognisable.\n5. The original file stays the source of truth."
        )
    if uploads and patient and st.button("Process and save", type="primary"):
        results = []
        progress = st.progress(0.0)
        for index, upload in enumerate(uploads, start=1):
            with st.status(f"Processing {upload.name}…", expanded=False) as status_box:
                level, message, doc_id = save_upload(upload.name, upload.getvalue(), patient)
                status_box.update(label=f"{upload.name}: {level}", state="error" if level == "error" else "complete")
            results.append((level, message, doc_id))
            progress.progress(index / len(uploads))
        st.session_state["last_results"] = results
        if any(doc_id for _, _, doc_id in results):
            st.session_state["pending_profile"] = patient
        st.rerun()
    for level, message, doc_id in st.session_state.get("last_results", []):
        getattr(st, level)(message)
        row = store.get_document(doc_id) if doc_id else None
        if row is not None:
            record = to_record(row)
            if record.needs_type_confirmation:
                type_selector(record, "up")

# ----------------------------------------------------------------------------- timeline

with tab_timeline:
    st.subheader("Patient health timeline")
    if not records:
        st.info("No records yet. Add a document in the Upload tab or load the demo records from the Dashboard.")
    else:
        f1, f2, f3 = st.columns([2, 2, 1])
        types = f1.multiselect("Filter by type", sorted({r.doc_type for r in records}))
        query = f2.text_input("Search file names and extracted text")
        only_review = f3.checkbox("Needs review only")
        shown = sort_timeline(filter_records(records, types, query))
        if only_review:
            shown = [r for r in shown if r.needs_type_confirmation or r.warnings]
        st.caption(f"Showing {len(shown)} of {len(records)} documents · oldest first · undated documents last")
        for r in shown:
            flags = []
            if r.needs_type_confirmation:
                flags.append("type unconfirmed")
            if r.date_status != "found":
                flags.append("date " + ("uncertain" if r.doc_date else "unknown"))
            title = f"{r.display_date} · {md(r.doc_type)} · {md(r.filename)}" + (f"  ⚠️ {', '.join(flags)}" if flags else "")
            with st.expander(title):
                render_record_details(r)

# ----------------------------------------------------------------------------- summary

with tab_summary:
    st.subheader("Record summary")
    st.caption(
        "Built from stored, extracted information with a fixed template. No AI model is used and nothing is interpreted. "
        "References like [D2, p.1] point to the source documents listed at the end."
    )
    if not records:
        st.info("No records to summarise yet.")
    else:
        summary = build_summary(records, patient)
        st.text_area("Reviewable summary", summary, height=420)
        st.download_button("Download summary (.txt)", summary, file_name="carebridge_patient_summary.txt")

# ----------------------------------------------------------------------------- data & privacy

with tab_data:
    st.subheader("Where your data is")
    st.markdown(
        f"""
- Original files: `{store.uploads_dir}`
- Metadata and extracted text: SQLite database `{store.db_path}`
- Nothing is uploaded to any external or AI service. Text extraction and OCR run on this computer.
- Data is **not encrypted** and there is **no login**. Anyone with access to this computer or folder can read it.
"""
    )
    if store.last_backup:
        st.info(f"The database was upgraded to a new schema. A backup of the previous version was saved as `{store.last_backup.name}`.")
    st.subheader("Delete data")
    if records:
        st.markdown(f"Delete all **{len(records)}** document(s) and files for profile **{md(patient)}**.")
        typed = st.text_input("Type the profile name to confirm")
        if st.button("Delete all records for this profile", type="secondary", disabled=typed != patient):
            try:
                count = store.delete_patient_documents(patient)
            except StorageError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("last_results", None)
                st.success(f"Deleted {count} document(s).")
                st.rerun()
    else:
        st.caption("No records for this profile.")
    st.subheader("Privacy, safety and limitations")
    st.markdown(
        """
- Use synthetic or de-identified documents for this prototype.
- This demo has no production-grade authentication, encryption-at-rest, access controls, audit logging or clinical validation.
- Do not upload real patient records to a public deployment.
- Extracted values are candidate text matches and must be checked against the original document.
- No diagnosis, treatment recommendation or medication advice is provided.
"""
    )
    st.caption("CareBridge AI · Engineering prototype · Built for demonstration with synthetic/sample data.")
