"""Appendix generators: search history table, CASP summary, PRISMA flow, subagent log.

Letters (A / B / C / D) come from ``spec.APPENDIX_ORDER`` so the template is the
single source of truth for ordering and labelling.
"""

from __future__ import annotations

from ..models import CaspResult, Paper, RunState, SearchResult

_LETTER_SEARCH = "A"
_LETTER_CASP = "B"
_LETTER_PRISMA = "C"
_LETTER_SUBAGENT = "D"


def search_history_qmd(sr: SearchResult, *, letter: str = _LETTER_SEARCH) -> str:
    lines = [
        f"# 附錄 {letter}：搜尋歷程表",
        "",
        "| # | 關鍵字 | 資料庫 | 欄位限定 | 初始篇數 | 去重後 | 納入條件 | 排除條件 | 納入數 | 備註 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(sr.history, 1):
        lines.append(
            f"| {i} | {row.keywords[:60]} | {row.database.value} | {row.field_limit} "
            f"| {row.initial_hits} | {row.deduplicated_hits} "
            f"| {row.inclusion_criteria} | {row.exclusion_criteria} "
            f"| {row.included_count} | {row.note} |"
        )
    return "\n".join(lines) + "\n"


def casp_summary_qmd(
    casp_results: list[CaspResult], papers: list[Paper], *, letter: str = _LETTER_CASP
) -> str:
    paper_by_doi = {p.doi: p for p in papers if p.doi}
    lines = [f"# 附錄 {letter}：CASP 評讀彙整", ""]
    for c in casp_results:
        p = paper_by_doi.get(c.paper_doi)
        title = p.title if p else "(無對應 paper metadata)"
        year = p.year if p else "?"
        lines.append(f"## {title} ({year})")
        lines.append("")
        lines.append(f"- **工具**: {c.tool_used.value}")
        lines.append(f"- **Oxford 等級**: {c.oxford_level_2011.value}")
        lines.append(f"- **效度**: {c.validity_zh}")
        lines.append(f"- **重要性**: {c.importance_zh}")
        lines.append(f"- **台灣可用性**: {c.applicability_zh}")
        lines.append("")
        lines.append("| # | 問題 | 答案 | 說明 |")
        lines.append("|---|---|---|---|")
        for item in c.checklist_items:
            lines.append(
                f"| {item.q_no} | {item.question_zh} | {item.answer} | {item.rationale_zh} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def prisma_flow_qmd(sr: SearchResult, *, letter: str = _LETTER_PRISMA) -> str:
    """ASCII-art PRISMA flow; rendered as a pre block in DOCX."""

    by_db: dict[str, int] = {}
    for row in sr.history:
        by_db[row.database.value] = by_db.get(row.database.value, 0) + row.initial_hits
    total_initial = sum(by_db.values())
    final = len(sr.papers)
    dedup_inferred = max(total_initial - final, 0)

    lines = [
        f"# 附錄 {letter}：PRISMA 風格流程圖",
        "",
        "```",
        "Identification",
    ]
    for db, n in by_db.items():
        lines.append(f"    {db}: {n} 篇")
    lines.extend(
        [
            f"    合計初始命中：{total_initial} 篇",
            "",
            "Screening / Dedup",
            f"    去重與排除：-{dedup_inferred}",
            "",
            f"Included: {final} 篇",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def subagent_log_qmd(state: RunState, *, letter: str = _LETTER_SUBAGENT) -> str:
    lines = [f"# 附錄 {letter}：Subagent 執行紀錄（AI 使用追溯）", ""]
    lines.append("| CP | 時間 | 使用者選擇 | 備註 |")
    lines.append("|---|---|---|---|")
    # De-duplicate by cp_id, keep latest entry per CP
    latest: dict[str, object] = {}
    for c in state.checkpoints:
        latest[c.cp_id.value] = c
    for cp_id in sorted(latest.keys()):
        c = latest[cp_id]  # type: ignore[assignment]
        lines.append(
            f"| {c.cp_id.value} | {c.timestamp.isoformat(timespec='seconds')} "  # type: ignore[attr-defined]
            f"| {c.user_choice} | {c.rationale or ''} |"  # type: ignore[attr-defined]
        )
    lines.append("")
    if state.compliance_report is not None:
        cr = state.compliance_report
        lines.append("")
        lines.append("## 模板規範 Compliance 檢核結果")
        lines.append("")
        status = "✓ 通過" if cr.passed else "✗ 未通過"
        lines.append(f"- 狀態：{status}")
        lines.append(f"- 自動重寫次數：{cr.retries_used}")
        if cr.issues:
            lines.append("- 項目：")
            for i in cr.issues:
                tag = "❌" if i.severity == "error" else "⚠"
                lines.append(f"    - {tag} [{i.section}] {i.rule}: {i.detail}")
        lines.append("")
    return "\n".join(lines) + "\n"
