"""Run the processing pipeline on the synthetic evaluation set and print measured metrics.

Usage:  python scripts/evaluate.py [--json results.json]

Documents marked as images or scanned PDFs are rendered at run time; they are skipped (and
reported as skipped) when Tesseract or the required language data or font is not installed.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carebridge.pipeline import process_document  # noqa: E402
from carebridge.records import to_record  # noqa: E402
from carebridge.storage import DocumentStore  # noqa: E402
from carebridge.summary import build_summary  # noqa: E402
from tests.helpers import (  # noqa: E402
    BENGALI_FONT_CANDIDATES, find_font, ocr_ready, scanned_pdf, text_image, text_pdf,
)

DATASET = ROOT / "tests" / "eval" / "dataset.json"


def build_file(doc: dict) -> tuple[str, bytes] | None:
    lines = doc["text"].split("\n")
    fmt = doc["format"]
    if fmt == "txt":
        return f"{doc['id']}.txt", doc["text"].encode("utf-8")
    if fmt == "text_pdf":
        return f"{doc['id']}.pdf", text_pdf([doc["text"]])
    if fmt == "image":
        return (f"{doc['id']}.png", text_image(lines)) if ocr_ready("eng") else None
    if fmt == "scanned_pdf":
        return (f"{doc['id']}.pdf", scanned_pdf([text_image(lines)])) if ocr_ready("eng") else None
    if fmt == "image_bengali":
        font = find_font(BENGALI_FONT_CANDIDATES)
        if not (ocr_ready("ben") and font):
            return None
        return f"{doc['id']}.png", text_image(lines, font_path=font, size=44)
    raise ValueError(f"unknown format {fmt}")


def ratio(tp: int, denominator: int) -> float | None:
    return round(tp / denominator, 3) if denominator else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="write detailed results to this file")
    args = parser.parse_args()
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))["documents"]

    rows, skipped = [], []
    lab_tp = lab_pred = lab_gold = 0
    med_tp = med_pred = med_gold = 0
    type_ok = date_ok = processed_ok = 0
    ocr_scores = []

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = DocumentStore(Path(tmp))
        for doc in dataset:
            built = build_file(doc)
            if built is None:
                skipped.append(doc["id"])
                continue
            name, data = built
            row = {"id": doc["id"], "format": doc["format"]}
            try:
                result = process_document(name, data, "Eval")
            except Exception as exc:  # report every failure as a processing failure
                row.update(processed=False, error=str(exc))
                lab_gold += len(doc["expected_labs"])
                med_gold += len(doc["expected_medications"])
                rows.append(row)
                continue
            processed_ok += 1
            store.save_document(result.to_record("Eval"), data)
            predicted_labs = {(r.field, r.value, r.unit.lower()) for r in result.details.lab_results}
            gold_labs = {(g["field"], g["value"], g["unit"].lower()) for g in doc["expected_labs"]}
            predicted_meds = {m.name.lower() for m in result.details.medications}
            gold_meds = {m.lower() for m in doc["expected_medications"]}
            lab_tp += len(predicted_labs & gold_labs)
            lab_pred += len(predicted_labs)
            lab_gold += len(gold_labs)
            med_tp += len(predicted_meds & gold_meds)
            med_pred += len(predicted_meds)
            med_gold += len(gold_meds)
            type_match = result.classification.label == doc["expected_type"]
            date_match = result.details.document_date.value == doc["expected_date"]
            type_ok += type_match
            date_ok += date_match
            if doc["format"] in {"image", "scanned_pdf", "image_bengali"}:
                score = difflib.SequenceMatcher(None, doc["text"], result.text).ratio()
                ocr_scores.append(score)
                row["ocr_similarity"] = round(score, 3)
            row.update(
                processed=True,
                predicted_type=result.classification.label,
                confidence=result.classification.confidence,
                type_correct=type_match,
                predicted_date=result.details.document_date.value,
                date_correct=date_match,
                labs_missed=sorted(map(list, gold_labs - predicted_labs)),
                labs_extra=sorted(map(list, predicted_labs - gold_labs)),
                meds_missed=sorted(gold_meds - predicted_meds),
                meds_extra=sorted(predicted_meds - gold_meds),
            )
            rows.append(row)

        # Summary factual support: every value line in the summary must appear in its source text.
        records = [to_record(r) for r in store.list_documents("Eval")]
        summary = build_summary(records, "Eval")
        claims = supported = 0
        for record in records:
            for lab in record.lab_results:
                claims += 1
                supported += lab["value"] in record.text and f"{lab['value']} {lab['unit']}".strip() in summary
            for med in record.medications:
                claims += 1
                supported += med["name"] in record.text and med["name"] in summary

    evaluated = len(rows)
    metrics = {
        "documents_in_dataset": len(dataset),
        "documents_evaluated": evaluated,
        "documents_skipped": skipped,
        "processing_success_rate": ratio(processed_ok, evaluated),
        "classification_accuracy": ratio(type_ok, evaluated),
        "date_accuracy": ratio(date_ok, evaluated),
        "lab_field_precision": ratio(lab_tp, lab_pred),
        "lab_field_recall": ratio(lab_tp, lab_gold),
        "medication_name_precision": ratio(med_tp, med_pred),
        "medication_name_recall": ratio(med_tp, med_gold),
        "mean_ocr_character_similarity": round(sum(ocr_scores) / len(ocr_scores), 3) if ocr_scores else None,
        "summary_claims_checked": claims,
        "summary_factual_support_rate": ratio(supported, claims),
    }
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print("\nPer-document errors:")
    for row in rows:
        problems = {k: v for k, v in row.items() if k in {"error", "labs_missed", "labs_extra", "meds_missed", "meds_extra"} and v}
        if not row.get("type_correct", True) or not row.get("date_correct", True) or problems or not row["processed"]:
            print(" -", row["id"], json.dumps({**problems, "type": row.get("predicted_type"), "date": row.get("predicted_date")}, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps({"metrics": metrics, "documents": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
