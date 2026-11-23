"""Heuristic extraction of dates, laboratory values, medicines and providers.

Rules followed throughout:
- Values are copied as written; nothing is inferred, converted or filled in.
- Missing information stays empty ("").
- Every item keeps its source page and source line.
- Anything the rules are unsure about is marked with an ``uncertain`` reason.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .extraction import PageText

# --------------------------------------------------------------------------- dates

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

_ISO_RE = re.compile(r"\b((?:19|20)\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.]((?:19|20)\d{2})\b")
_D_MON_Y_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-]+({_MONTH_RE})\.?,?[\s\-]+((?:19|20)\d{{2}})\b", re.I)
_MON_D_Y_RE = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})\b", re.I)

_DATE_LABEL_RE = re.compile(
    r"(report(?:ed)?\s*(?:date|on)?|date\s*of\s*(?:report|visit|discharge|issue)|discharge\s*date|"
    r"visit\s*date|collection\s*date|collected\s*(?:on)?|sample\s*date|\bdate\b|\bdated\b|তারিখ)",
    re.I,
)
_BIRTH_RE = re.compile(r"\b(?:dob|d\.o\.b|date\s*of\s*birth|birth\s*date|born)\b|জন্ম", re.I)


# Labels that identify the date a document was issued rank above admission/collection dates.
_PRIMARY_LABEL_RE = re.compile(r"report|discharge|issue|visit|তারিখ|^\W*date\b|^\W*dated\b", re.I)
_SECONDARY_LABEL_RE = re.compile(r"admission|admitted|collect|sample|received|registered", re.I)


@dataclass
class DateCandidate:
    value: str  # ISO yyyy-mm-dd
    raw: str
    page: int
    source_line: str
    labelled: bool
    is_birth_date: bool
    uncertain: str = ""
    primary_label: bool = False


def _make_date(year: int, month: int, day: int) -> date | None:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed.year < 1900 or parsed > date.today() + timedelta(days=366):
        return None
    return parsed


_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _dates_in_line(original: str) -> list[tuple[int, date, str, str]]:
    """Return (start, date, raw text, uncertainty reason) for every date-like token in a line.

    Bengali digits are read as their ASCII equivalents; the raw text is returned as written.
    """
    line = original.translate(_BENGALI_DIGITS)
    found: list[tuple[int, date, str, str]] = []
    for m in _ISO_RE.finditer(line):
        d = _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.append((m.start(), d, m.group(0), ""))
    for m in _DMY_RE.finditer(line):
        first, second, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        reason = ""
        if first <= 12 and second <= 12 and first != second:
            reason = "day/month order is ambiguous; read as day-month-year"
        d = _make_date(year, second, first)
        if d is None and first <= 12:
            d = _make_date(year, first, second)
            reason = "read as month-day-year"
        if d:
            found.append((m.start(), d, m.group(0), reason))
    for m in _D_MON_Y_RE.finditer(line):
        d = _make_date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        if d:
            found.append((m.start(), d, m.group(0), ""))
    for m in _MON_D_Y_RE.finditer(line):
        d = _make_date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        if d:
            found.append((m.start(), d, m.group(0), ""))
    ordered = sorted(found, key=lambda x: x[0])
    return [(start, d, original[start : start + len(raw)], reason) for start, d, raw, reason in ordered]


def extract_dates(pages: list[PageText]) -> list[DateCandidate]:
    candidates = []
    for page in pages:
        for line in page.text.splitlines():
            cursor = 0
            for start, parsed, raw, reason in _dates_in_line(line):
                # Only the text between the previous date and this one labels this date.
                prefix = line[cursor:start]
                cursor = start + len(raw)
                candidates.append(
                    DateCandidate(
                        value=parsed.isoformat(),
                        raw=raw,
                        page=page.page,
                        source_line=line.strip(),
                        labelled=bool(_DATE_LABEL_RE.search(prefix)),
                        is_birth_date=bool(_BIRTH_RE.search(prefix)),
                        uncertain=reason,
                        primary_label=bool(_PRIMARY_LABEL_RE.search(prefix)) and not _SECONDARY_LABEL_RE.search(prefix),
                    )
                )
    return candidates


@dataclass
class DocumentDate:
    value: str | None  # ISO date or None when it could not be determined
    status: str  # "found" | "uncertain" | "missing"
    reason: str = ""
    source: DateCandidate | None = None


def choose_document_date(candidates: list[DateCandidate]) -> DocumentDate:
    """Pick the document date. Never invents one: returns status "missing" when none is found."""
    usable = [c for c in candidates if not c.is_birth_date]
    if not usable:
        return DocumentDate(None, "missing", "No document date was found in the text.")
    labelled = [c for c in usable if c.labelled]
    primary = [c for c in labelled if c.primary_label]
    chosen = (primary or labelled or usable)[0]
    reasons = []
    if chosen.uncertain:
        reasons.append(chosen.uncertain)
    if not labelled and len({c.value for c in usable}) > 1:
        reasons.append("several unlabelled dates were found; the first one was used")
    status = "uncertain" if reasons else "found"
    return DocumentDate(chosen.value, status, "; ".join(reasons), chosen)


# ------------------------------------------------------------------ lab results

_NUMBER = r"[<>]?\s?\d[\d,]*(?:\.\d+)?"
_UNIT_RE = (
    r"(?:g/dl|gm/dl|mg/dl|mg/l|g/l|mmol/l|µmol/l|umol/l|meq/l|iu/l|u/l|miu/l|µiu/ml|uiu/ml|ng/ml|ng/dl|pg/ml|pg|fl|"
    r"mm/hr|mm/1st hr|%|/cumm|/cmm|/µl|/ul|cells/µl|cells/ul|lakh/cumm|x\s?10\^?\d+/l|10\^?\d+/l|"
    r"thou/µl|thou/ul|k/µl|k/ul)"
)

# Canonical test name -> alias regex. Order matters: more specific tests first.
LAB_TESTS: list[tuple[str, str]] = [
    ("HbA1c", r"hba1c|hb\s?a1c|glycated ha?emoglobin|glycosylated ha?emoglobin"),
    ("Hemoglobin", r"ha?emoglobin|hgb|hb"),
    ("Fasting glucose", r"fasting (?:blood|plasma) (?:glucose|sugar)|fasting glucose|fbs|fbg"),
    ("Random glucose", r"random (?:blood|plasma) (?:glucose|sugar)|random glucose|rbs"),
    ("Glucose", r"(?:blood|plasma|serum) (?:glucose|sugar)|glucose"),
    ("Creatinine", r"(?:serum |s\.\s?)?creatinine"),
    ("Urea", r"(?:blood |serum )?urea|bun"),
    ("WBC", r"total wbc(?: count)?|wbc(?: count)?|white blood cells?(?: count)?|total (?:leu[ck]ocyte )?count|tlc"),
    ("RBC", r"rbc(?: count)?|red blood cells?(?: count)?|total rbc"),
    ("Platelets", r"platelet(?:s| count)?|plt"),
    ("ESR", r"esr"),
    ("Total cholesterol", r"total cholesterol|(?:serum )?cholesterol"),
    ("HDL cholesterol", r"hdl(?:[- ]cholesterol| ?-?c)?"),
    ("LDL cholesterol", r"ldl(?:[- ]cholesterol| ?-?c)?"),
    ("Triglycerides", r"triglycerides?|tg"),
    ("ALT (SGPT)", r"alt(?:\s*\(sgpt\))?|sgpt(?:\s*\(alt\))?"),
    ("AST (SGOT)", r"ast(?:\s*\(sgot\))?|sgot(?:\s*\(ast\))?"),
    ("Total bilirubin", r"(?:total |serum )?bilirubin(?: total)?"),
    ("TSH", r"tsh"),
    ("Sodium", r"sodium|na\+?"),
    ("Potassium", r"potassium|k\+?"),
]
_LAB_LINE_RES = [
    (name, re.compile(rf"^\s*(?:\d+[\.\)]\s*)?(?P<name>{aliases})\b(?P<rest>.*)$", re.I)) for name, aliases in LAB_TESTS
]
_FLAG = r"(?:\s*\(?(?:high|low|h|l)\)?(?![\w/]))?"
_VALUE_RE = re.compile(
    rf"^[\s:=\-\.\(\)a-z]{{0,30}}?(?P<value>{_NUMBER})(?![\d.,])\s*(?P<unit>{_UNIT_RE})?{_FLAG}(?![\w/])", re.I
)
_RANGE_START_RE = re.compile(r"^\s*(?:-|–|to)\s*\d")
_RANGE_RE = re.compile(
    rf"(?<![\d.,])(?P<range>(?:\d[\d,]*(?:\.\d+)?\s*(?:-|–|to)\s*\d[\d,]*(?:\.\d+)?|[<>≤≥]\s?\d[\d,]*(?:\.\d+)?)(?:\s*{_UNIT_RE})?)", re.I
)
_VALUE_ONLY_LINE_RE = re.compile(rf"^\s*(?P<value>{_NUMBER})(?![\d.,])\s*(?P<unit>{_UNIT_RE})?{_FLAG}(?P<rest>.*)$", re.I)
_ROW_NUMBER_RE = re.compile(r"^\s*\d+\s*[.)]\s*[^\d\s]")


@dataclass
class LabResult:
    field: str
    value: str
    unit: str
    reference_range: str
    page: int
    source_line: str
    source_excerpt: str
    uncertain: str = ""
    review_status: str = "needs_review"


def _range_after(text: str) -> str:
    m = _RANGE_RE.search(text)
    return m.group("range").strip() if m else ""


def extract_lab_results(pages: list[PageText]) -> list[LabResult]:
    """Find "<test name> <value> [unit] [reference range]" patterns, one test per line."""
    results: list[LabResult] = []
    for page in pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            for canonical, line_re in _LAB_LINE_RES:
                m = line_re.match(line)
                if not m:
                    continue
                rest = m.group("rest")
                value_match = _VALUE_RE.match(rest)
                if value_match and _RANGE_START_RE.match(rest[value_match.end("value"):]):
                    break  # the number starts a reference range, not a result
                reasons: list[str] = []
                source_line = line.strip()
                if value_match:
                    value = value_match.group("value").replace(" ", "")
                    unit = value_match.group("unit") or ""
                    reference = _range_after(rest[value_match.end():])
                else:
                    following = next((ln for ln in lines[index + 1 : index + 3] if ln.strip()), "")
                    next_match = _VALUE_ONLY_LINE_RE.match(following)
                    if (
                        not next_match
                        or _ROW_NUMBER_RE.match(following)
                        or _RANGE_START_RE.match(following[next_match.end("value"):])
                        or any(r.match(following) for _, r in _LAB_LINE_RES)
                    ):
                        break
                    value = next_match.group("value").replace(" ", "")
                    unit = next_match.group("unit") or ""
                    reference = _range_after(next_match.group("rest"))
                    reasons.append("value was on the following line")
                    source_line = f"{line.strip()} | {following.strip()}"
                if not unit:
                    reasons.append("unit not found")
                excerpt_start = max(0, index - 1)
                excerpt = " / ".join(ln.strip() for ln in lines[excerpt_start : index + 2] if ln.strip())
                results.append(
                    LabResult(
                        field=canonical,
                        value=value,
                        unit=unit,
                        reference_range=reference,
                        page=page.page,
                        source_line=source_line,
                        source_excerpt=excerpt[:240],
                        uncertain="; ".join(reasons),
                    )
                )
                break
    return results


# ------------------------------------------------------------------ medicines

_MED_LINE_RE = re.compile(
    r"^\s*(?:\d+[\.\)]\s*)?(?P<form>tab(?:let)?s?|cap(?:sule)?s?|syp|syrup|inj(?:ection)?|susp(?:ension)?|"
    r"drops?|oint(?:ment)?|cream|gel|inhaler|sachet|supp(?:ository)?)\b\.?\s+(?P<rest>.+)$",
    re.I,
)
_STRENGTH_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|iu|units?|%)(?:\s*/\s*\d*(?:\.\d+)?\s*(?:ml|g|tab))?\b", re.I)
_FREQUENCY_RE = re.compile(
    r"\b\d\s*\+\s*\d\s*\+\s*\d(?:\s*\+\s*\d)?\b|\b(?:once|twice|thrice|three times|four times)\s+(?:a\s+)?(?:daily|day)\b|"
    r"\b(?:od|bd|bid|tds|tid|qid|qds|hs|sos|prn|stat)\b|\bevery\s+\d+\s+hours?\b|"
    r"দিনে\s*\S+\s*বার|সকালে|দুপুরে|রাতে",
    re.I,
)
_DURATION_RE = re.compile(
    r"\b(?:x|for)\s*\d+\s*(?:days?|weeks?|months?)\b|\b\d+\s*(?:days?|weeks?|months?)\b|\bcontinue\b|"
    r"[০-৯\d]+\s*(?:দিন|সপ্তাহ|মাস)",
    re.I,
)


@dataclass
class Medication:
    form: str
    name: str
    strength_text: str
    frequency_text: str
    duration_text: str
    page: int
    source_line: str
    uncertain: str = ""


def extract_medications(pages: list[PageText]) -> list[Medication]:
    """Copy medicine lines that start with a dosage form (Tab., Cap., Syp., ...).

    Strength, frequency and duration are copied only when written on the same line.
    """
    meds: list[Medication] = []
    for page in pages:
        for line in page.text.splitlines():
            m = _MED_LINE_RE.match(line)
            if not m:
                continue
            rest = m.group("rest").strip()
            strength = _STRENGTH_RE.search(rest)
            frequency = _FREQUENCY_RE.search(rest)
            duration = _DURATION_RE.search(rest[frequency.end():] if frequency else rest)
            cut_points = [x.start() for x in (strength, frequency) if x]
            name = rest[: min(cut_points)] if cut_points else rest
            name = re.sub(r"[\s\-–:,]+$", "", name).strip()
            reasons = []
            if not frequency:
                reasons.append("frequency not found")
            meds.append(
                Medication(
                    form=m.group("form"),
                    name=name[:80],
                    strength_text=strength.group(0) if strength else "",
                    frequency_text=frequency.group(0) if frequency else "",
                    duration_text=duration.group(0) if duration else "",
                    page=page.page,
                    source_line=line.strip(),
                    uncertain="; ".join(reasons),
                )
            )
    return meds


# ------------------------------------------------------------------ people / places

_DOCTOR_RE = re.compile(r"\b(?:Dr|Doctor)\.?\s+(?P<name>[A-Z][A-Za-z\.\-']+(?:\s+[A-Z][A-Za-z\.\-']+){0,3})")
_FACILITY_RE = re.compile(
    r"^(?P<name>[^\n]{0,60}\b(?:hospital|clinic|medical college|medical centre|medical center|diagnostic(?:s)?(?: cent(?:er|re))?|"
    r"laboratory|labs?|healthcare|health care|nursing home)\b[^\n]{0,40})$",
    re.I,
)
_PATIENT_RE = re.compile(r"^\s*(?:patient(?:'s)?(?:\s*name)?|name of patient|রোগীর নাম)\s*[:\-]\s*(?P<name>.+)$", re.I)
_SKIP_FACILITY_RE = re.compile(r"\b(?:report|test|date|patient|ref)\b\s*[:\-]", re.I)


@dataclass
class TextField:
    value: str
    page: int
    source_line: str


def _first(pages: list[PageText], pattern: re.Pattern, group: str = "name", skip: re.Pattern | None = None) -> TextField | None:
    for page in pages:
        for line in page.text.splitlines():
            if skip and skip.search(line):
                continue
            m = pattern.search(line)
            if m:
                return TextField(m.group(group).strip(" .,:;-"), page.page, line.strip())
    return None


# ------------------------------------------------------------------ bundle


@dataclass
class ExtractedDetails:
    document_date: DocumentDate
    lab_results: list[LabResult] = field(default_factory=list)
    medications: list[Medication] = field(default_factory=list)
    doctor: TextField | None = None
    facility: TextField | None = None
    patient_name_in_document: TextField | None = None
    date_candidates: list[DateCandidate] = field(default_factory=list)

    def details_dict(self) -> dict:
        """Everything except lab results, as JSON-serialisable data."""
        return {
            "document_date": asdict(self.document_date),
            "medications": [asdict(m) for m in self.medications],
            "doctor": asdict(self.doctor) if self.doctor else None,
            "facility": asdict(self.facility) if self.facility else None,
            "patient_name_in_document": asdict(self.patient_name_in_document) if self.patient_name_in_document else None,
            "date_candidates": [asdict(c) for c in self.date_candidates[:20]],
        }


def extract_details(pages: list[PageText]) -> ExtractedDetails:
    candidates = extract_dates(pages)
    return ExtractedDetails(
        document_date=choose_document_date(candidates),
        lab_results=extract_lab_results(pages),
        medications=extract_medications(pages),
        doctor=_first(pages, _DOCTOR_RE),
        facility=_first(pages, _FACILITY_RE, skip=_SKIP_FACILITY_RE),
        patient_name_in_document=_first(pages, _PATIENT_RE),
        date_candidates=candidates,
    )
