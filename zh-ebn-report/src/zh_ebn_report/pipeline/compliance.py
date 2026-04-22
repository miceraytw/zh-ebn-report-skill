"""Programmatic template-compliance checker.

Runs deterministic rules against the draft before CP7. Prompts can fail or lie
about word counts; this module is the boss. All rules read constants from
``zh_ebn_report.spec`` so the template is the single source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..models import (
    ComplianceIssueRecord,
    ComplianceReportRecord,
    OxfordLevel,
    Paper,
    RunState,
    Section,
    TopicVerdict,
)
from ..spec import (
    MIN_HIGH_LEVEL_EVIDENCE,
    MIN_REFERENCES,
    ReportKind,
    SectionSpec,
    section_order,
)

Severity = Literal["error", "warning"]


@dataclass
class ComplianceIssue:
    """One deterministic violation of the template spec."""

    section: str
    rule: str
    detail: str
    severity: Severity = "error"

    def format(self) -> str:
        tag = "❌" if self.severity == "error" else "⚠"
        return f"{tag} [{self.section}] {self.rule}: {self.detail}"


@dataclass
class ComplianceReport:
    issues: list[ComplianceIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary_zh(self) -> str:
        if not self.issues:
            return "✓ 全部通過模板規範"
        lines = [f"共 {len(self.errors)} 項錯誤、{len(self.warnings)} 項警示："]
        lines.extend(i.format() for i in self.issues)
        return "\n".join(lines)

    def issues_for_section(self, section: str) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.section == section]

    def to_record(self, *, retries_used: int = 0) -> ComplianceReportRecord:
        return ComplianceReportRecord(
            passed=self.passed,
            issues=[
                ComplianceIssueRecord(
                    section=i.section,
                    rule=i.rule,
                    detail=i.detail,
                    severity=i.severity,
                )
                for i in self.issues
            ],
            retries_used=retries_used,
        )


# ---------------------------------------------------------------------------
# CJK-character counting (matches human intuition for 中文字數)
# ---------------------------------------------------------------------------
_CJK_RE = re.compile(r"[一-鿿]")
_CITE_RE = re.compile(r"\[@[^\]]+\]")
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def count_cjk(text: str) -> int:
    """Count CJK ideographs only — excludes punctuation, English, numbers."""

    return len(_CJK_RE.findall(text))


def count_cjk_excluding_tables_and_cites(text: str) -> int:
    """Body-only CJK count: strip markdown tables and citation placeholders.

    Several sections have a rule like "字數不含表格本身"; this helper keeps the
    counter honest about what is actually prose.
    """

    stripped = _MARKDOWN_TABLE_RE.sub("", text)
    stripped = _CITE_RE.sub("", stripped)
    return count_cjk(stripped)


# ---------------------------------------------------------------------------
# Per-section rules
# ---------------------------------------------------------------------------
def _check_word_count(section: Section, spec: SectionSpec) -> list[ComplianceIssue]:
    count = count_cjk_excluding_tables_and_cites(section.content_zh)
    if spec.word_range.contains(count):
        return []
    return [
        ComplianceIssue(
            section=section.section_name,
            rule="word_count",
            detail=(
                f"實際 {count} 字，應落在 {spec.word_range.describe()}"
                "（自評 word_count_estimate 不算數，以 CJK 字數為準）"
            ),
        )
    ]


def _check_citation_coverage(
    section: Section, spec: SectionSpec, papers: list[Paper]
) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    placeholders = set(section.citation_placeholders)
    if spec.must_cite_at_least and len(placeholders) < spec.must_cite_at_least:
        issues.append(
            ComplianceIssue(
                section=section.section_name,
                rule="citation_min",
                detail=(
                    f"僅 {len(placeholders)} 處引文，模板要求至少 "
                    f"{spec.must_cite_at_least} 處"
                ),
            )
        )
    if spec.must_cite_all_papers and papers:
        citekeys_expected = {f"@{p.citekey()}" for p in papers}
        missing = citekeys_expected - placeholders
        if missing:
            issues.append(
                ComplianceIssue(
                    section=section.section_name,
                    rule="citation_coverage",
                    detail=(
                        f"未引用 {len(missing)} 篇文獻："
                        + ", ".join(sorted(missing))
                    ),
                )
            )
    # Banned generic tokens — Paper 1 / Paper 2 instead of author-year
    if spec.name == "評讀結果":
        body = section.content_zh
        banned = re.findall(r"Paper\s*[1-9]", body, flags=re.IGNORECASE)
        if banned:
            issues.append(
                ComplianceIssue(
                    section=section.section_name,
                    rule="author_year_reference",
                    detail=(
                        f"發現 {len(banned)} 處使用 Paper N 代號，"
                        "須改為作者姓氏＋年代"
                    ),
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Top-level checks
# ---------------------------------------------------------------------------
def check_sections(state: RunState, *, kind: ReportKind) -> ComplianceReport:
    """Run all deterministic rules on the assembled sections + topic + refs."""

    report = ComplianceReport()
    order = section_order(kind)
    sections_by_name = {s.section_name: s for s in state.sections}

    # 1. Required-section presence
    for spec in order:
        if spec.required and spec.name not in sections_by_name:
            report.issues.append(
                ComplianceIssue(
                    section=spec.name,
                    rule="missing_section",
                    detail="模板要求此章節但草稿未產出",
                )
            )

    # 2. Per-section rules
    papers = state.search_result.papers if state.search_result else []
    for spec in order:
        sec = sections_by_name.get(spec.name)
        if sec is None:
            continue
        report.issues.extend(_check_word_count(sec, spec))
        report.issues.extend(_check_citation_coverage(sec, spec, papers))

    # 3. Title must have a question form
    report.issues.extend(_check_title(state.topic_verdict))

    # 4. References
    report.issues.extend(_check_references(papers))

    return report


def _check_title(verdict: TopicVerdict | None) -> list[ComplianceIssue]:
    if verdict is None:
        return [
            ComplianceIssue(
                section="篇名",
                rule="missing_title",
                detail="尚無 topic_verdict，無法驗證篇名",
            )
        ]
    q = getattr(verdict, "refined_topic_zh_question", "") or ""
    markers = ("？", "?", "是否", "能否", "可否")
    if not any(m in q for m in markers):
        return [
            ComplianceIssue(
                section="篇名",
                rule="question_form",
                detail=(
                    f"refined_topic_zh_question={q!r} 非疑問句；"
                    "模板建議用疑問句式呈現 PICO"
                ),
            )
        ]
    return []


_HIGH_LEVELS = {OxfordLevel.I, OxfordLevel.II}


def _check_references(papers: list[Paper]) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    if len(papers) < MIN_REFERENCES:
        issues.append(
            ComplianceIssue(
                section="參考文獻",
                rule="min_count",
                detail=(
                    f"納入文獻僅 {len(papers)} 篇，模板要求至少 "
                    f"{MIN_REFERENCES} 篇"
                ),
            )
        )
    high_count = sum(1 for p in papers if p.oxford_level in _HIGH_LEVELS)
    if high_count < MIN_HIGH_LEVEL_EVIDENCE:
        issues.append(
            ComplianceIssue(
                section="參考文獻",
                rule="min_high_level_evidence",
                detail=(
                    f"高證據等級（Oxford I–II）僅 {high_count} 篇，"
                    f"模板要求至少 {MIN_HIGH_LEVEL_EVIDENCE} 篇"
                ),
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Prompt-feedback helper
# ---------------------------------------------------------------------------
def retry_feedback_for_section(
    section_name: str, report: ComplianceReport
) -> str | None:
    """Convert section-specific issues into a directive for a retry pass.

    Returned string is appended to the section writer's user prompt on retry;
    ``None`` if there is nothing to fix.
    """

    issues = report.issues_for_section(section_name)
    if not issues:
        return None
    lines = ["【上一次輸出未通過程式化驗證，請針對以下問題重寫】"]
    for i in issues:
        lines.append(f"- {i.rule}: {i.detail}")
    lines.append("請嚴格滿足所有規則後再次輸出 JSON。")
    return "\n".join(lines)
