import streamlit as st
from pathlib import Path
from datetime import datetime
import sqlite3, uuid, re, hashlib, json
from io import BytesIO

try:
    import fitz
except Exception:
    fitz = None
try:
    from PIL import Image
except Exception:
    Image = None
try:
    import pytesseract
except Exception:
    pytesseract = None

BASE = Path(__file__).parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
DB = DATA / "carebridge.db"
UPLOADS.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="CareBridge AI", page_icon="🩺", layout="wide")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, patient_name TEXT, filename TEXT, doc_type TEXT,
        doc_date TEXT, extracted_text TEXT, extracted_json TEXT,
        created_at TEXT, sha256 TEXT
    )""")
    conn.commit()
    return conn

def classify(text, filename):
    t = (text + " " + filename).lower()
    if any(x in t for x in ["prescription", "rx", "dosage", "চিকিৎসাপত্র", "প্রেসক্রিপশন"]):
        return "Prescription"
    if any(x in t for x in ["laboratory", "lab report", "hemoglobin", "glucose", "creatinine", "পরীক্ষার ফল"]):
        return "Laboratory report"
    if any(x in t for x in ["discharge", "admission", "hospital course", "ছাড়পত্র"]):
        return "Discharge summary"
    return "Other medical document"

def extract_text(file_bytes, filename):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not fitz:
            return "", "PDF reader dependency unavailable. Install requirements."
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in doc)
        if text.strip():
            return text, "PDF text layer"
        if pytesseract and Image:
            chunks = []
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(BytesIO(pix.tobytes("png")))
                chunks.append(pytesseract.image_to_string(img, lang="eng+ben"))
            return "\n".join(chunks), "OCR"
        return "", "Scanned PDF detected. Install Tesseract OCR to extract scanned pages."
    if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
        if not pytesseract or not Image:
            return "", "Image OCR dependencies unavailable. Install Tesseract OCR and requirements."
        img = Image.open(BytesIO(file_bytes))
        return pytesseract.image_to_string(img, lang="eng+ben"), "OCR"
    return "", "Unsupported file type"

def extract_fields(text):
    # Conservative demo extraction: captures candidate values, not clinical interpretation.
    patterns = [
        ("Hemoglobin", r"(?i)\b(?:hemoglobin|haemoglobin|hb)\b\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(g/dl|gm/dl)?"),
        ("Glucose", r"(?i)\b(?:blood glucose|glucose|fbs|rbs)\b\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl|mmol/l)?"),
        ("Creatinine", r"(?i)\bcreatinine\b\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mg/dl)?"),
        ("WBC", r"(?i)\b(?:wbc|white blood cell(?: count)?)\b\s*[:\-]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:/cumm|cells/ul)?"),
    ]
    found = []
    for label, pattern in patterns:
        for m in re.finditer(pattern, text):
            val = m.group(1)
            unit = m.group(2) or ""
            found.append({"field": label, "value": val, "unit": unit, "source_excerpt": text[max(0,m.start()-45):min(len(text),m.end()+45)].replace("\n"," ")})
    return found

def get_docs():
    with db() as conn:
        return conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()

def delete_doc(doc_id):
    with db() as conn:
        row = conn.execute("SELECT filename FROM documents WHERE id=?", (doc_id,)).fetchone()
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
    if row:
        p = UPLOADS / doc_id
        if p.exists():
            p.unlink()

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
.hero {padding: 1.4rem 1.6rem; border-radius: 18px; background: linear-gradient(115deg,#102d46,#176b75); color:white; margin-bottom:1rem;}
.hero h1 {color:white; margin:0; font-size:2.2rem;}
.hero p {color:#d8edf0; margin:.4rem 0 0 0;}
.small-muted {color:#64748b;font-size:.86rem}
div[data-testid="stMetric"] {background:#f7fafc;padding:14px;border:1px solid #e2e8f0;border-radius:12px}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>🩺 CareBridge AI</h1><p>Your medical history, connected and understandable.</p></div>', unsafe_allow_html=True)
st.warning("Prototype for demonstration only. Use synthetic or de-identified records. This app does not diagnose, recommend treatment, or replace a healthcare professional.")

tab1, tab2, tab3 = st.tabs(["📤 Add records", "🗂️ Health timeline", "🔒 Privacy & project notes"])

with tab1:
    st.subheader("Add a medical document")
    c1, c2 = st.columns([1, 1])
    with c1:
        patient = st.text_input("Patient display name", value="Demo Patient")
        uploaded = st.file_uploader("Upload PDF or image", type=["pdf","png","jpg","jpeg","webp"])
        st.caption("Supported: text-based PDFs and images. Scanned PDFs/images require Tesseract OCR installed on your computer.")
    with c2:
        st.info("**What happens after upload?**\n\n1. Text is extracted from the document.\n2. A document category is suggested.\n3. Candidate fields are extracted where recognizable.\n4. The original document remains the source of truth.")
    if uploaded and st.button("Process and save document", type="primary"):
        raw = uploaded.getvalue()
        doc_id = str(uuid.uuid4())
        text, method = extract_text(raw, uploaded.name)
        if not text.strip():
            st.error(method if method else "No readable text was found. Try a clearer image or text-based PDF.")
        else:
            doc_type = classify(text, uploaded.name)
            fields = extract_fields(text)
            date_match = re.search(r"\b(20\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))\b", text)
            doc_date = date_match.group(1) if date_match else "Date not identified"
            digest = hashlib.sha256(raw).hexdigest()
            with db() as conn:
                conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
                    (doc_id, patient.strip() or "Demo Patient", uploaded.name, doc_type, doc_date,
                     text, json.dumps(fields), datetime.now().isoformat(timespec="seconds"), digest))
                conn.commit()
            (UPLOADS / doc_id).write_bytes(raw)
            st.success(f"Saved as {doc_type}. Extraction method: {method}.")
            st.rerun()

with tab2:
    docs = get_docs()
    st.subheader("Patient health timeline")
    if not docs:
        st.info("No records yet. Add a document in the first tab, or load the synthetic demo records below.")
        if st.button("Load synthetic demo records"):
            demo = [
                ("Demo Patient","sample_lab_jan.txt","Laboratory report","2026-01-12",
                 "LABORATORY REPORT\nPatient: Demo Patient\nDate: 2026-01-12\nHemoglobin: 13.5 g/dL\nGlucose: 92 mg/dL\nCreatinine: 0.9 mg/dL"),
                ("Demo Patient","sample_prescription_mar.txt","Prescription","2026-03-08",
                 "PRESCRIPTION\nPatient: Demo Patient\nDate: 2026-03-08\nFollow-up: 4 weeks\nNote: Sample synthetic record for UI demonstration."),
                ("Demo Patient","sample_lab_jun.txt","Laboratory report","2026-06-19",
                 "LABORATORY REPORT\nPatient: Demo Patient\nDate: 2026-06-19\nHemoglobin: 13.8 g/dL\nGlucose: 96 mg/dL\nCreatinine: 0.9 mg/dL")
            ]
            with db() as conn:
                for name, fn, typ, dt, txt in demo:
                    did = str(uuid.uuid4())
                    conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
                        (did,name,fn,typ,dt,txt,json.dumps(extract_fields(txt)),datetime.now().isoformat(timespec="seconds"),hashlib.sha256(txt.encode()).hexdigest()))
                    (UPLOADS / did).write_text(txt, encoding="utf-8")
                conn.commit()
            st.rerun()
    else:
        patients = sorted(set(r["patient_name"] for r in docs))
        selected = st.selectbox("Select patient", patients)
        selected_docs = [r for r in docs if r["patient_name"] == selected]
        m1,m2,m3 = st.columns(3)
        m1.metric("Documents", len(selected_docs))
        m2.metric("Document types", len(set(r["doc_type"] for r in selected_docs)))
        all_fields = []
        for r in selected_docs:
            try: all_fields.extend(json.loads(r["extracted_json"]))
            except: pass
        m3.metric("Candidate values", len(all_fields))
        st.markdown("#### Chronological records")
        for r in sorted(selected_docs, key=lambda x: x["doc_date"] if x["doc_date"] != "Date not identified" else "9999"):
            with st.expander(f'{r["doc_date"]} · {r["doc_type"]} · {r["filename"]}'):
                st.write("**Extracted candidate information**")
                fields = json.loads(r["extracted_json"])
                if fields:
                    st.dataframe(fields, use_container_width=True, hide_index=True)
                else:
                    st.caption("No supported numeric fields were detected.")
                st.write("**Source text preview**")
                st.text((r["extracted_text"] or "")[:1800])
                st.caption(f'SHA-256: {r["sha256"][:20]}…')
                if st.button("Delete this record", key="del_"+r["id"]):
                    delete_doc(r["id"])
                    st.rerun()
        st.markdown("#### AI-assisted health summary")
        summary_lines = [
            f'Patient: {selected}',
            f'Records available: {len(selected_docs)}',
            "This summary lists information found in uploaded documents; it is not a diagnosis."
        ]
        for r in selected_docs:
            summary_lines.append(f'- {r["doc_date"]}: {r["doc_type"]} ({r["filename"]})')
            for item in json.loads(r["extracted_json"]):
                summary_lines.append(f'  - {item["field"]}: {item["value"]} {item["unit"]} [source: {r["filename"]}]')
        summary = "\n".join(summary_lines)
        st.text_area("Reviewable summary", summary, height=220)
        st.download_button("Download summary (.txt)", summary, file_name="carebridge_patient_summary.txt")
        st.caption("The current MVP uses deterministic extraction and templated summarization. It does not call an external LLM.")

with tab3:
    st.subheader("Privacy, safety and limitations")
    st.markdown("""
- Use synthetic or de-identified documents for this competition prototype.
- Files are stored locally in this project's `data/uploads` folder and metadata in SQLite.
- This demo has no production-grade authentication, encryption-at-rest, cloud access controls or clinical validation.
- Do not upload real patient records to a public deployment.
- Extracted values are candidate text matches and must be checked against the original document.
- No diagnosis, treatment recommendation or medication advice is provided.
""")
    st.subheader("Suggested next engineering milestones")
    st.markdown("""
1. Add real authentication and patient-level authorization.
2. Add encrypted object storage and audit logging.
3. Improve Bangla OCR and test on a labeled document set.
4. Add human review of extracted fields before records are finalized.
5. Add expiring, consent-based sharing tokens.
6. Evaluate extraction accuracy and summary factual consistency against annotated synthetic documents.
""")
    st.caption("CareBridge AI · Competition MVP · Built for demonstration with synthetic/sample data.")
