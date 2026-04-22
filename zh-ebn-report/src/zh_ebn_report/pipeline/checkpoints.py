"""HITL checkpoints.

Each checkpoint presents a summary to the user via the terminal and prompts for
a decision. Decisions are logged to ``checkpoint_log.json``.

The ``auto_yes`` mode can be used for batch/testing but **CP1, CP4, CP9 cannot
be skipped** (ethical floor).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ..config import PipelineConfig
from ..models import Checkpoint, CheckpointId, OxfordLevel, RunState
from ..spec import MIN_HIGH_LEVEL_EVIDENCE, MIN_REFERENCES
from ..state import append_checkpoint, state_path

console = Console()

_MUST_CONFIRM: set[CheckpointId] = {
    CheckpointId.CP1,
    CheckpointId.CP4,
    CheckpointId.CP9,
}


@dataclass
class CheckpointSpec:
    cp_id: CheckpointId
    title: str
    default_choice: str
    choices: list[str]
    body: str  # Rich-renderable text summarizing what the user is approving


def prompt(
    pipeline_cfg: PipelineConfig,
    state: RunState,
    spec: CheckpointSpec,
    *,
    auto_yes: bool = False,
) -> str:
    """Show the checkpoint panel and return the user's choice."""

    console.print(Panel(spec.body, title=f"[bold cyan]{spec.cp_id.value}: {spec.title}[/]", border_style="cyan"))

    can_auto = auto_yes and spec.cp_id not in _MUST_CONFIRM
    # Headless override: for must-confirm CPs, require the caller to have
    # already written a decision via `tools approve-cp` (or set the
    # ZH_EBN_REPORT_NONINTERACTIVE_CONFIRM env var for explicit opt-in). Raise
    # a clear error instead of dropping into an EOF-aborted Rich prompt.
    non_tty = not sys.stdin.isatty()
    if not can_auto and spec.cp_id in _MUST_CONFIRM and non_tty:
        confirm_env = os.environ.get("ZH_EBN_REPORT_NONINTERACTIVE_CONFIRM", "").lower()
        if confirm_env in {"1", "true", "yes"}:
            choice = spec.default_choice
            console.print(
                f"[yellow]non-TTY + ZH_EBN_REPORT_NONINTERACTIVE_CONFIRM=1: "
                f"套用預設 [bold]{choice}[/][/]"
            )
            rationale = "headless-confirm via env"
            cp = Checkpoint(
                cp_id=spec.cp_id,
                timestamp=datetime.utcnow(),
                user_choice=choice,
                rationale=rationale,
                phase_snapshot_path=str(state_path(pipeline_cfg, state.config.run_id)),
            )
            append_checkpoint(pipeline_cfg, state, cp)
            return choice
        raise RuntimeError(
            f"{spec.cp_id.value} 為倫理防線，須於 TTY 互動確認；"
            "若在 Claude Code／CI 等無 TTY 環境執行，請先用 "
            "`zh-ebn-report tools approve-cp` 寫入決策，或設 "
            "ZH_EBN_REPORT_NONINTERACTIVE_CONFIRM=1 明確同意。"
        )
    if can_auto:
        choice = spec.default_choice
        console.print(f"[yellow]auto_yes: 套用預設選項 [bold]{choice}[/][/]")
    else:
        if auto_yes and spec.cp_id in _MUST_CONFIRM:
            console.print(
                f"[red]{spec.cp_id.value} 為倫理防線，不可跳過；請人工確認。[/]"
            )
        choice = Prompt.ask(
            "選擇 (輸入選項)",
            choices=spec.choices,
            default=spec.default_choice,
        )
    rationale = None
    if choice in {"修改", "修改需求", "重跑"}:
        rationale = Prompt.ask("請說明修改/重跑原因（選填，Enter 跳過）", default="")
        rationale = rationale or None

    cp = Checkpoint(
        cp_id=spec.cp_id,
        timestamp=datetime.utcnow(),
        user_choice=choice,
        rationale=rationale,
        phase_snapshot_path=str(state_path(pipeline_cfg, state.config.run_id)),
    )
    append_checkpoint(pipeline_cfg, state, cp)
    return choice


# ---------------------------------------------------------------------------
# Convenience builders for each CP
# ---------------------------------------------------------------------------


def cp1_summary(state: RunState) -> CheckpointSpec:
    v = state.topic_verdict
    if v is None:
        raise RuntimeError("CP1 called before topic_verdict populated")
    body = (
        f"[bold]使用者題目[/]: {state.config.user_topic_raw}\n"
        f"[bold]Refined（陳述）[/]: {v.refined_topic_zh}\n"
        f"[bold]Refined（疑問）[/]: {v.refined_topic_zh_question}\n"
        f"[bold]English[/]: {v.refined_topic_en}\n"
        f"[bold]Verdict[/]: {v.verdict}\n"
        f"[bold]理由[/]: {v.rationale_zh}\n"
    )
    if v.landmine_flags:
        body += f"[red]地雷旗標[/]: {', '.join(v.landmine_flags)}\n"
    if v.alternative_topics_zh:
        body += (
            "[yellow]替代題目建議[/]:\n"
            + "\n".join(f" - {t}" for t in v.alternative_topics_zh)
        )
    return CheckpointSpec(
        cp_id=CheckpointId.CP1,
        title="題目可行性裁決",
        default_choice="批准",
        choices=["批准", "修改", "棄題"],
        body=body,
    )


def cp2_summary(state: RunState) -> CheckpointSpec:
    pr = state.pico_result
    if pr is None:
        raise RuntimeError("CP2 called before pico_result populated")
    p = pr.pico
    body = (
        f"P = {p.population_zh} ({p.population_en})\n"
        f"I = {p.intervention_zh} ({p.intervention_en})\n"
        f"C = {p.comparison_zh} ({p.comparison_en})\n"
        f"O = {p.outcome_zh} ({p.outcome_en})\n"
        f"問題型態：{p.question_type.value}\n"
    )
    if pr.validation_warnings:
        body += "[yellow]警告:[/]\n" + "\n".join(f" - {w}" for w in pr.validation_warnings)
    return CheckpointSpec(
        cp_id=CheckpointId.CP2,
        title="PICO 確認",
        default_choice="批准",
        choices=["批准", "修改"],
        body=body,
    )


def cp3_summary(state: RunState) -> CheckpointSpec:
    sr = state.search_result
    if sr is None or sr.strategy is None:
        raise RuntimeError("CP3 called before search strategy populated")
    s = sr.strategy.six_piece_strategy
    pred = sr.strategy.predicted_hits_per_db
    body = (
        f"[bold]PubMed Boolean[/]:\n{s.boolean_query_pubmed}\n\n"
        f"[bold]預估命中[/]:\n"
        f"  PubMed: {pred.pubmed}  Scopus: {pred.scopus}  Embase: {pred.embase}\n"
        f"  Cochrane / CINAHL / 華藝：手動匯入\n\n"
        f"[bold]Tuning Plan[/]:\n"
        f"  太窄時：{', '.join(sr.strategy.tuning_plan.if_too_narrow)}\n"
        f"  太寬時：{', '.join(sr.strategy.tuning_plan.if_too_wide)}"
    )
    return CheckpointSpec(
        cp_id=CheckpointId.CP3,
        title="搜尋策略批准",
        default_choice="批准",
        choices=["批准", "重跑"],
        body=body,
    )


def cp4_summary(state: RunState) -> CheckpointSpec:
    sr = state.search_result
    if sr is None:
        raise RuntimeError("CP4 called before search_result populated")
    table = Table(title="初步納入清單（已去重 + DOI 驗證）")
    table.add_column("#", justify="right")
    table.add_column("Year")
    table.add_column("Design")
    table.add_column("Oxford")
    table.add_column("DOI OK")
    table.add_column("Title (trunc)")
    for i, p in enumerate(sr.papers[:20], 1):
        table.add_row(
            str(i),
            str(p.year),
            p.study_design.value,
            p.oxford_level.value,
            "✓" if p.doi_validated else ("—" if not p.doi else "✗"),
            p.title[:60] + ("…" if len(p.title) > 60 else ""),
        )
    # Convert the table to text via Rich's export
    with console.capture() as cap:
        console.print(table)
    body = cap.get()
    body += f"\n\n共 {len(sr.papers)} 篇；請確認是否進入 CASP 評讀。"
    # Template compliance warnings (reading-report-template.md §參考文獻)
    high_levels = {OxfordLevel.I, OxfordLevel.II}
    high_count = sum(1 for p in sr.papers if p.oxford_level in high_levels)
    if len(sr.papers) < MIN_REFERENCES:
        body += (
            f"\n[red]⚠ 納入 {len(sr.papers)} 篇低於模板下限 "
            f"{MIN_REFERENCES} 篇；建議擴大搜尋或放寬納入條件後重跑。[/]"
        )
    if high_count < MIN_HIGH_LEVEL_EVIDENCE:
        body += (
            f"\n[red]⚠ 高證據等級（Oxford I–II）僅 {high_count} 篇，"
            f"模板要求至少 {MIN_HIGH_LEVEL_EVIDENCE} 篇。[/]"
        )
    return CheckpointSpec(
        cp_id=CheckpointId.CP4,
        title="最終納入篇數確認",
        default_choice="批准",
        choices=["批准", "修改"],
        body=body,
    )


def cp5_summary(state: RunState) -> CheckpointSpec:
    if not state.casp_results:
        raise RuntimeError("CP5 called before casp_results populated")
    flagged = [
        c
        for c in state.casp_results
        if c.warnings.sample_size_below_30
        or c.warnings.p_value_insignificant_but_strong_claim
        or c.warnings.single_site_study
    ]
    body = (
        f"完成 {len(state.casp_results)} 篇 CASP 評讀；"
        f"其中 {len(flagged)} 篇有警示旗標。\n\n"
    )
    for c in flagged[:5]:
        flags = []
        if c.warnings.sample_size_below_30:
            flags.append("樣本<30")
        if c.warnings.p_value_insignificant_but_strong_claim:
            flags.append("p值高但推論強")
        if c.warnings.single_site_study:
            flags.append("單中心")
        body += f"[yellow]{c.paper_doi}[/] → {', '.join(flags)}\n"
    return CheckpointSpec(
        cp_id=CheckpointId.CP5,
        title="CASP 警示抽樣審核",
        default_choice="批准",
        choices=["批准", "修改", "重跑"],
        body=body,
    )


def cp6_summary(state: RunState) -> CheckpointSpec:
    s = state.synthesis
    if s is None:
        raise RuntimeError("CP6 called before synthesis populated")
    body = (
        f"[bold]整體證據強度[/]: {s.overall_evidence_strength}\n"
        f"[bold]矛盾點數[/]: {len(s.contradictions_zh)}\n\n"
        f"[bold]綜合建議摘要[/]:\n{s.recommended_intervention_summary_zh}\n\n"
        f"[bold]台灣脈絡可行度[/]:\n{s.clinical_feasibility_taiwan_zh}"
    )
    return CheckpointSpec(
        cp_id=CheckpointId.CP6,
        title="綜整結論批准",
        default_choice="批准",
        choices=["批准", "修改", "重跑"],
        body=body,
    )


def cp7_summary(state: RunState) -> CheckpointSpec:
    import re

    cjk_re = re.compile(r"[一-鿿]")
    body = ""
    # Compliance panel first (programmatic truth)
    cr = state.compliance_report
    if cr is not None:
        if cr.passed:
            body += "[green]✓ 模板規範全部通過[/]"
            if cr.retries_used:
                body += f"（compliance 重寫 {cr.retries_used} 次後通過）"
            body += "\n\n"
        else:
            errors = [i for i in cr.issues if i.severity == "error"]
            warnings = [i for i in cr.issues if i.severity == "warning"]
            body += (
                f"[red]✗ 模板規範未通過[/]（已重寫 {cr.retries_used} 次）："
                f" {len(errors)} 項錯誤、{len(warnings)} 項警示\n"
            )
            for i in cr.issues[:12]:
                tag = "❌" if i.severity == "error" else "⚠"
                body += f"  {tag} [{i.section}] {i.rule}: {i.detail}\n"
            if len(cr.issues) > 12:
                body += f"  …另有 {len(cr.issues) - 12} 項\n"
            body += "\n"
    # Section previews with actual CJK counts
    for sec in state.sections:
        actual = len(cjk_re.findall(sec.content_zh))
        body += (
            f"[bold]{sec.section_name}[/] (實際 {actual} 字 / "
            f"LLM 自評 {sec.word_count_estimate})\n"
        )
        body += sec.content_zh[:200] + ("…" if len(sec.content_zh) > 200 else "") + "\n\n"
    default = "批准" if (cr is None or cr.passed) else "重跑"
    return CheckpointSpec(
        cp_id=CheckpointId.CP7,
        title="各節草稿 + 模板規範 review",
        default_choice=default,
        choices=["批准", "重跑"],
        body=body,
    )


def cp8_summary(state: RunState) -> CheckpointSpec:
    vc = state.voice_check
    ac = state.apa_check
    if vc is None or ac is None:
        raise RuntimeError("CP8 called before voice/APA check")
    body = (
        f"[bold]語氣檢查[/]: "
        f"{vc.total_violations} 項違規；通過={vc.pass_threshold_met}\n"
        f"[bold]APA 檢查[/]: "
        f"{len(ac.format_issues)} 項格式問題；通過={ac.apa_pass}\n"
    )
    if not vc.pass_threshold_met:
        body += "\n[red]⚠ 語氣未通過，建議退回重寫違規節[/]"
    if not ac.apa_pass:
        body += "\n[red]⚠ APA 未通過，請修正或要求 pipeline 重跑[/]"
    return CheckpointSpec(
        cp_id=CheckpointId.CP8,
        title="語氣與 APA 檢查",
        default_choice="套用" if vc.pass_threshold_met and ac.apa_pass else "重跑",
        choices=["套用", "重跑"],
        body=body,
    )


def cp9_summary(state: RunState) -> CheckpointSpec:
    body = (
        f"[bold]DOCX 路徑[/]: {state.rendered_docx_path}\n\n"
        "[yellow]必附之三份文件 AI 聲明：[/]\n"
        " 1. AI 使用揭露段落（研究方法或致謝）\n"
        " 2. Audit 責任聲明（封面或末頁）\n"
        " 3. Subagent 執行紀錄（補充資料）\n\n"
        "[yellow]請確認 DOCX 三份文件皆已附入。[/]"
    )
    return CheckpointSpec(
        cp_id=CheckpointId.CP9,
        title="最終輸出確認（含 AI 聲明）",
        default_choice="確認",
        choices=["確認", "重跑"],
        body=body,
    )
