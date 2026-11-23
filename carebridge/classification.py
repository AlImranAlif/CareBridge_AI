"""Rule-based document classification with a confidence indicator.

Rules are plain data (CATEGORY_RULES) so they can be reviewed and extended without
touching the scoring code. When no rule fires, the result is UNKNOWN rather than a
forced guess, and low-confidence results ask the user to confirm the type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

LAB_REPORT = "Laboratory report"
PRESCRIPTION = "Prescription"
DISCHARGE_SUMMARY = "Discharge summary"
IMAGING_REPORT = "Medical imaging report"
CONSULTATION = "Doctor consultation"
DIAGNOSTIC_REPORT = "Diagnostic report"
OTHER = "Other medical document"
UNKNOWN = "Unknown"
TYPE_CONFIRMATION_WARNING = "The document type could not be identified confidently. Please confirm it."

DOCUMENT_TYPES = [LAB_REPORT, PRESCRIPTION, DISCHARGE_SUMMARY, IMAGING_REPORT, CONSULTATION, DIAGNOSTIC_REPORT, OTHER, UNKNOWN]

STRONG = 3
WEAK = 1

# (regex, weight). Patterns run against lower-cased, whitespace-normalised text.
CATEGORY_RULES: dict[str, list[tuple[str, int]]] = {
    LAB_REPORT: [
        (r"\blab(?:oratory)? (?:report|test|investigation)s?\b", STRONG),
        (r"\b(?:pathology|biochemistry|haematology|hematology) report\b", STRONG),
        (r"\bcomplete blood count\b|\bcbc\b", STRONG),
        (r"\breference (?:range|interval|value)\b|\bnormal range\b", WEAK),
        (r"\bspecimen\b|\bsample (?:type|collected)\b", WEAK),
        (r"\bh(?:a)?emoglobin\b|\bglucose\b|\bcreatinine\b|\bcholesterol\b|\bplatelet", WEAK),
        (r"পরীক্ষার ফল|ল্যাব রিপোর্ট", STRONG),
    ],
    PRESCRIPTION: [
        (r"\bprescription\b", STRONG),
        (r"(?m)^\s*rx\b|\brx[:\.]", STRONG),
        (r"(?m)^\s*(?:\d+[\.\)]\s*)?(?:tab|cap|syp|inj|susp)\.?\s+[a-z]", WEAK),
        (r"\b\d\s*\+\s*\d\s*\+\s*\d\b", WEAK),
        (r"\bdosage\b|\bafter meals?\b|\bbefore meals?\b", WEAK),
        (r"প্রেসক্রিপশন|চিকিৎসাপত্র|ব্যবস্থাপত্র", STRONG),
    ],
    DISCHARGE_SUMMARY: [
        (r"\bdischarge (?:summary|certificate|note)\b", STRONG),
        (r"\bdate of (?:admission|discharge)\b|\badmission date\b|\bdischarge date\b", WEAK),
        (r"\bhospital course\b|\bcondition (?:at|on) discharge\b", STRONG),
        (r"ছাড়পত্র", STRONG),
    ],
    IMAGING_REPORT: [
        (r"\b(?:radiology|imaging) report\b", STRONG),
        (r"\bx-?ray\b|\bradiograph\b", STRONG),
        (r"\bultrasonograph?y\b|\bultrasound\b|\busg\b", STRONG),
        (r"\bct scan\b|\bcomputed tomography\b|\bmri\b|\bmagnetic resonance\b|\bmammogra", STRONG),
        (r"\bimpression\s*:|\bfindings\s*:", WEAK),
        (r"এক্স-?রে|আল্ট্রাসনোগ্রাফি", STRONG),
    ],
    CONSULTATION: [
        (r"\bconsultation (?:note|report)?\b|\bclinic(?:al)? notes?\b|\bprogress note\b", STRONG),
        (r"\bchief complaints?\b|\bhistory of present(?:ing)? illness\b|\bc/c\b", WEAK),
        (r"\bon examination\b|\bo/e\b|\bfollow[- ]up visit\b", WEAK),
    ],
    DIAGNOSTIC_REPORT: [
        (r"\becg\b|\bekg\b|\belectrocardiogra", STRONG),
        (r"\bechocardiogra|\bendoscopy\b|\bcolonoscopy\b|\bspirometry\b|\beeg\b", STRONG),
        (r"\bhistopatholog|\bbiopsy report\b|\bcytology\b", STRONG),
        (r"\bdiagnostic report\b", STRONG),
    ],
}


@dataclass
class ClassificationResult:
    label: str
    confidence: str  # "high" | "medium" | "low"
    scores: dict[str, int] = field(default_factory=dict)
    matched: dict[str, list[str]] = field(default_factory=dict)

    @property
    def needs_confirmation(self) -> bool:
        return self.confidence == "low"


def normalise_for_rules(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").lower())


def classify(text: str, filename: str = "") -> ClassificationResult:
    """Score each category by its matching rules and return the best label with a confidence.

    Text matches count fully; filename matches count once at weak weight, because filenames
    are user-controlled and often generic.
    """
    body = normalise_for_rules(text)
    name = normalise_for_rules(re.sub(r"[_\-.]+", " ", filename))
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for label, rules in CATEGORY_RULES.items():
        score = 0
        for pattern, weight in rules:
            hit = re.search(pattern, body)
            if hit:
                score += weight
                matched.setdefault(label, []).append(hit.group(0).strip())
            elif name and re.search(pattern, name):
                score += WEAK
                matched.setdefault(label, []).append(f"filename: {pattern}")
        if score:
            scores[label] = score
    if not scores:
        return ClassificationResult(UNKNOWN, "low", scores, matched)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_label, best = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if best >= 4 and best - runner_up >= 2:
        confidence = "high"
    elif best >= 3 and best > runner_up:
        confidence = "medium"
    else:
        confidence = "low"
    return ClassificationResult(best_label, confidence, scores, matched)
