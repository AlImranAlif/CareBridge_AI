"""Extractive, template-based health-history summary.

Only stored, extracted information is used. No AI model is called, nothing is interpreted,
and every line points back to a numbered source document (D1, D2, ...).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from .records import DocumentRecord, sort_timeline

DISCLAIMER = (
    "This summary lists information copied from uploaded documents by rule-based extraction. "
    "It is not a diagnosis or medical advice, and it may be incomplete or wrong. "
    "Check every item against the original document."
)


def _ref(refs: dict[str, str], record: DocumentRecord, page=None) -> str:
    return f"[{refs[record.id]}{f', p.{page}' if page else ''}]"


def build_summary(records: list[DocumentRecord], patient_name: str) -> str:
    ordered = sort_timeline(records)
    refs = {r.id: f"D{i}" for i, r in enumerate(ordered, start=1)}
    lines: list[str] = [
        f"CareBridge AI - record summary for {patient_name}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        DISCLAIMER,
        "",
        "1. OVERVIEW",
    ]
    if not ordered:
        lines.append("No documents are stored for this profile.")
        return "\n".join(lines)
    dated = [r.doc_date for r in ordered if r.doc_date]
    lines.append(f"Documents: {len(ordered)}")
    for doc_type, count in Counter(r.doc_type for r in ordered).most_common():
        lines.append(f"- {doc_type}: {count}")
    if dated:
        lines.append(f"Date range of dated documents: {min(dated)} to {max(dated)}")
    undated = len(ordered) - len(dated)
    if undated:
        lines.append(f"Documents without an identified date: {undated}")

    lines += ["", "2. CHRONOLOGICAL RECORD"]
    for r in ordered:
        lines.append(f"- {r.display_date}: {r.doc_type} - {r.filename} {_ref(refs, r)}")

    lines += ["", "3. LABORATORY VALUES (as written in the source; not interpreted)"]
    by_test: dict[str, list[tuple[DocumentRecord, dict]]] = defaultdict(list)
    for r in ordered:
        for lab in r.lab_results:
            if lab.get("review_status") == "rejected":
                continue
            by_test[lab["field"]].append((r, lab))
    if not by_test:
        lines.append("No laboratory values were extracted.")
    for test in sorted(by_test):
        lines.append(f"{test}:")
        for r, lab in by_test[test]:
            parts = [f"{lab['value']} {lab.get('unit', '')}".strip()]
            if lab.get("reference_range"):
                parts.append(f"reference range in document: {lab['reference_range']}")
            if lab.get("uncertain"):
                parts.append(f"UNCERTAIN: {lab['uncertain']}")
            lines.append(f"  - {r.display_date}: {'; '.join(parts)} {_ref(refs, r, lab.get('page'))}")

    lines += ["", "4. DOCUMENTED HISTORY (copied from documents)"]
    history = False
    for r in ordered:
        for med in r.medications:
            text = " ".join(x for x in [med.get("form", ""), med.get("name", ""), med.get("strength_text", "")] if x)
            extra = "; ".join(
                f"{k}: {med[v]}" for k, v in (("frequency as written", "frequency_text"), ("duration as written", "duration_text")) if med.get(v)
            )
            lines.append(f"- {r.display_date}: medicine listed - {text}{f' ({extra})' if extra else ''} {_ref(refs, r, med.get('page'))}")
            history = True
        for key, label in (("doctor", "Doctor named"), ("facility", "Facility named")):
            item = r.details.get(key)
            if item:
                lines.append(f"- {r.display_date}: {label}: {item['value']} {_ref(refs, r, item.get('page'))}")
                history = True
    if not history:
        lines.append("No medicines, doctors or facilities were extracted.")
    lines.append("Diagnoses and clinical findings are not extracted automatically; read the source documents.")

    lines += ["", "5. MISSING OR UNCERTAIN INFORMATION"]
    gaps = []
    for r in ordered:
        if not r.doc_date:
            gaps.append(f"- Date not identified: {r.filename} {_ref(refs, r)}")
        elif r.date_status == "uncertain":
            reason = (r.details.get("document_date") or {}).get("reason", "")
            gaps.append(f"- Date uncertain ({reason or 'see document'}): {r.filename} {_ref(refs, r)}")
        if r.needs_type_confirmation:
            gaps.append(f"- Document type not confirmed (detected: {r.doc_type}): {r.filename} {_ref(refs, r)}")
        for lab in r.lab_results:
            if lab.get("uncertain") and lab.get("review_status") != "rejected":
                gaps.append(f"- {lab['field']} value uncertain ({lab['uncertain']}) {_ref(refs, r, lab.get('page'))}")
        for med in r.medications:
            if med.get("uncertain"):
                gaps.append(f"- Medicine '{med.get('name', '')}': {med['uncertain']} {_ref(refs, r, med.get('page'))}")
        for warning in r.warnings:
            if "date" not in warning.lower() and "type" not in warning.lower():
                gaps.append(f"- {warning} {_ref(refs, r)}")
    lines += gaps or ["No gaps were flagged by the extraction rules (this does not mean the record is complete)."]

    lines += ["", "6. SOURCE DOCUMENTS"]
    for r in ordered:
        lines.append(
            f"{refs[r.id]}: {r.filename} | type: {r.doc_type} | uploaded: {r.created_at} | "
            f"extraction: {r.extraction_method} | SHA-256: {r.sha256[:16]}"
        )
    return "\n".join(lines)
