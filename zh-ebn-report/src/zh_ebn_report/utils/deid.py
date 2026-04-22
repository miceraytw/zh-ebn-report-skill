"""De-identification detector for case reports.

Blocks the pipeline before Apply/Audit phase if any identifying patterns slip
through: Taiwan ID numbers, medical record numbers, birth dates, phone numbers,
obvious name fields.

Regex layer catches structural patterns; the orchestrator can additionally send
the material through a Haiku-tier LLM for semantic scan (handled in
:mod:`pipeline.case_narrator`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Taiwan National ID: 1 letter + 9 digits (A123456789)
_TW_ID = re.compile(r"\b[A-Z][12]\d{8}\b")
# Taiwan medical record numbers: usually 6-9 digits, but we look for obvious "病歷號: ..." markers
_MRN_LABELED = re.compile(r"(?:病歷號|MRN|chart no\.?|medical record)\s*[:：=]?\s*([A-Z0-9\-]{5,15})", re.IGNORECASE)
# Phone numbers (Taiwan): 09xx-xxx-xxx, 0x-xxxx-xxxx, or 10 consecutive digits starting with 0
_TW_PHONE = re.compile(r"\b0\d{2,3}[-\s]?\d{3,4}[-\s]?\d{3,4}\b")
# Birth date in various formats
_BIRTH = re.compile(
    r"\b(?:19|20)\d{2}[-/年.]\s*\d{1,2}[-/月.]\s*\d{1,2}[日]?\b"
)
# Labeled name markers: "姓名：王小明" / "Patient: John Doe"
_NAME_LABELED = re.compile(
    r"(?:姓名|Name|Patient|個案姓名)\s*[:：=]\s*([^\n，,；;]{2,30})",
    re.IGNORECASE,
)


@dataclass
class DeidFinding:
    category: str
    match: str
    position: int


@dataclass
class DeidReport:
    findings: list[DeidFinding]

    @property
    def passed(self) -> bool:
        return not self.findings


def scan(text: str) -> DeidReport:
    findings: list[DeidFinding] = []

    for pat, label in (
        (_TW_ID, "TW_ID"),
        (_TW_PHONE, "TW_PHONE"),
        (_BIRTH, "BIRTH_DATE"),
    ):
        for m in pat.finditer(text):
            findings.append(DeidFinding(category=label, match=m.group(0), position=m.start()))

    for m in _MRN_LABELED.finditer(text):
        findings.append(DeidFinding(category="MRN", match=m.group(0), position=m.start()))

    for m in _NAME_LABELED.finditer(text):
        findings.append(DeidFinding(category="NAME", match=m.group(0), position=m.start()))

    return DeidReport(findings=findings)
