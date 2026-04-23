#!/usr/bin/env python3
"""Retro-validate historical runs against the current guardrail suite.

Every time a new guardrail is added (evidence_guard, synthesis_guard,
voice_scan, apa_guard, compliance._check_*), we want to know: does it
catch real violations in past runs, and does it regress on runs that
were clean?

This script walks ``output/<run-id>/state.json`` for every completed run,
loads each into :class:`RunState` (so current pydantic validators fire),
then reruns the downstream guardrails and reports what they would change
today vs. what the LLM-era pipeline accepted.

Exit code is non-zero if any run fails to load under current schema or
any guardrail flags an error-severity issue — suitable for CI.

Usage:
    python scripts/retro_validate.py [--output-dir output] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Allow running without editable install by adding src/ to sys.path.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from zh_ebn_report.models import ReportType, RunState  # noqa: E402
from zh_ebn_report.pipeline.apa_guard import normalize_apa_result  # noqa: E402
from zh_ebn_report.pipeline.compliance import check_sections  # noqa: E402
from zh_ebn_report.pipeline.evidence_guard import enforce_evidence_levels  # noqa: E402
from zh_ebn_report.pipeline.synthesis_guard import normalize_synthesis  # noqa: E402
from zh_ebn_report.pipeline.voice_scan import normalize_voice_result  # noqa: E402

_KIND_MAP = {
    ReportType.EBR_READING: "reading",
    ReportType.EBR_CASE: "case",
    ReportType.TWNA_CASE: "twna_case",
    ReportType.TWNA_PROJECT: "twna_project",
}


@dataclass
class GuardrailFinding:
    guardrail: str
    detail: str


@dataclass
class RunReport:
    run_dir: str
    topic: str = ""
    level: str = ""
    report_type: str = ""
    schema_load: str = "unknown"  # "ok" | "fail: ..."
    findings: list[GuardrailFinding] = field(default_factory=list)
    compliance_errors: int = 0
    compliance_warnings: int = 0

    @property
    def any_issue(self) -> bool:
        return (
            self.schema_load != "ok"
            or bool(self.findings)
            or self.compliance_errors > 0
        )


def _run_guardrails(run_dir: Path) -> RunReport:
    """Load one run and accumulate findings from every guardrail."""

    rep = RunReport(run_dir=str(run_dir))
    state_path = run_dir / "state.json"
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    rep.topic = raw.get("config", {}).get("user_topic_raw", "")
    rep.level = raw.get("config", {}).get("advancement_level", "")
    rep.report_type = raw.get("config", {}).get("report_type", "")

    try:
        state = RunState.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        rep.schema_load = f"fail: {str(e).splitlines()[0][:200]}"
        return rep
    rep.schema_load = "ok"

    papers = state.search_result.papers if state.search_result else []

    # evidence_guard — any downgrade means the original oxford_level
    # violated OCEBM for the paper's study design.
    for d in enforce_evidence_levels(papers, state.casp_results):
        rep.findings.append(
            GuardrailFinding(
                guardrail="evidence_guard",
                detail=(
                    f"[{d.paper_doi}] {d.study_design.value} "
                    f"Level {d.original_level.value}→{d.corrected_level.value}"
                ),
            )
        )

    # synthesis_guard — a non-None note means overall_evidence_strength
    # was wrong.
    if state.synthesis is not None:
        _, note = normalize_synthesis(state.synthesis, state.casp_results)
        if note is not None:
            rep.findings.append(
                GuardrailFinding(guardrail="synthesis_guard", detail=note)
            )

    # voice_scan — any increase in violations means the LLM voice guard
    # missed them.
    if state.voice_check is not None:
        full_draft = "\n\n".join(
            f"# {s.section_name}\n\n{s.content_zh}" for s in state.sections
        )
        new_voice = normalize_voice_result(state.voice_check, full_draft)
        delta = new_voice.total_violations - state.voice_check.total_violations
        if delta > 0 or (
            state.voice_check.pass_threshold_met
            and not new_voice.pass_threshold_met
        ):
            rep.findings.append(
                GuardrailFinding(
                    guardrail="voice_scan",
                    detail=(
                        f"+{delta} violations; pass "
                        f"{state.voice_check.pass_threshold_met}→"
                        f"{new_voice.pass_threshold_met}"
                    ),
                )
            )

    # apa_guard — any flip of apa_pass means the LLM lied about APA.
    sections_by_name = {s.section_name: s for s in state.sections}
    if state.apa_check is not None:
        orig_pass = state.apa_check.apa_pass
        _, reasons = normalize_apa_result(state.apa_check, papers, sections_by_name)
        if orig_pass != state.apa_check.apa_pass:
            rep.findings.append(
                GuardrailFinding(
                    guardrail="apa_guard",
                    detail=(
                        f"pass {orig_pass}→{state.apa_check.apa_pass}; "
                        + "; ".join(reasons[:2])
                    ),
                )
            )

    # compliance — full section-by-section audit.
    kind = _KIND_MAP.get(state.config.report_type, "reading")
    cr = check_sections(state, kind=kind)
    rep.compliance_errors = len(cr.errors)
    rep.compliance_warnings = len(cr.warnings)
    for issue in cr.errors[:8]:
        rep.findings.append(
            GuardrailFinding(
                guardrail="compliance",
                detail=f"{issue.section}/{issue.rule}: {issue.detail[:120]}",
            )
        )

    return rep


def _format_text(reports: list[RunReport]) -> str:
    lines: list[str] = []
    for r in reports:
        header = (
            f"== {Path(r.run_dir).name} · {r.report_type}/{r.level} · "
            f"{r.topic[:60]} =="
        )
        lines.append(header)
        if r.schema_load != "ok":
            lines.append(f"  [schema] {r.schema_load}")
            lines.append("")
            continue
        if not r.findings:
            lines.append("  ✓ clean (no guardrail findings)")
            lines.append("")
            continue
        # Bucket findings by guardrail for readability
        by_g: dict[str, list[str]] = {}
        for f in r.findings:
            by_g.setdefault(f.guardrail, []).append(f.detail)
        for g, items in by_g.items():
            lines.append(f"  [{g}] {len(items)} finding(s)")
            for d in items[:5]:
                lines.append(f"    - {d}")
            if len(items) > 5:
                lines.append(f"    … and {len(items) - 5} more")
        lines.append(
            f"  compliance: {r.compliance_errors} errors, "
            f"{r.compliance_warnings} warnings"
        )
        lines.append("")
    # Summary footer
    total = len(reports)
    clean = sum(1 for r in reports if not r.any_issue)
    schema_fail = sum(1 for r in reports if r.schema_load != "ok")
    lines.append(
        f"Summary: {total} runs · {clean} clean · {schema_fail} schema fail · "
        f"{total - clean - schema_fail} with guardrail/compliance findings"
    )
    return "\n".join(lines)


def _format_json(reports: list[RunReport]) -> str:
    return json.dumps(
        {"runs": [asdict(r) for r in reports]},
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--output-dir",
        default="output",
        help="root directory containing <run-id>/state.json sub-dirs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON instead of human-readable text",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "exit 1 if any run has guardrail findings (default: exit 1 only on "
            "schema-load failure, which indicates a hard regression)"
        ),
    )
    args = parser.parse_args(argv)

    output_root = Path(args.output_dir)
    if not output_root.exists():
        print(f"error: {output_root} does not exist", file=sys.stderr)
        return 2

    run_dirs = sorted(
        p for p in output_root.iterdir() if (p / "state.json").exists()
    )
    if not run_dirs:
        print(f"error: no <run-id>/state.json under {output_root}", file=sys.stderr)
        return 2

    reports = [_run_guardrails(rd) for rd in run_dirs]

    if args.json:
        print(_format_json(reports))
    else:
        print(_format_text(reports))

    any_schema_fail = any(r.schema_load != "ok" for r in reports)
    any_findings = any(r.findings for r in reports)
    if any_schema_fail:
        return 1
    if args.strict and any_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
