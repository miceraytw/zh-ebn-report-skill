"""Utility CLI for Claude Code orchestration mode.

When Claude Code session drives the pipeline, it dispatches LLM work through
Agent tool subagents (haiku/opus) — **no Anthropic SDK call happens inside the
Python process**. Python only runs the non-LLM chores:

- Database searches (PubMed / Scopus / Embase / OpenAlex)
- CrossRef DOI validation
- De-identification scan
- Cross-database deduplication
- State persistence (read/patch state.json)
- Checkpoint logging
- Quarto render (already lives under cli.py as ``render``)

Every command emits structured JSON to stdout so Claude Code can pipe directly
into an Agent tool's input or a ``save-output`` call.

Invoke via: ``zh-ebn-report tools <command> ...``
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from .clients.crossref import CrossrefClient
from .clients.pubmed import PubMedClient
from .config import AppConfig
from .models import Checkpoint, CheckpointId, Paper, RunState, SourceDB
from .state import append_checkpoint, load_state, save_state
from .utils.dedup import dedup
from .utils.deid import scan as deid_scan

console = Console(stderr=True)  # logs go to stderr; JSON payload goes to stdout
tools_app = typer.Typer(
    help="Utility commands for Claude Code orchestration mode (no LLM call).",
    no_args_is_help=True,
)


def _cfg() -> AppConfig:
    load_dotenv()
    return AppConfig.load()


def _stdout_json(obj: object) -> None:
    """Write JSON to stdout for Claude Code to pipe."""

    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------------------
# Database search utilities
# ---------------------------------------------------------------------------


@tools_app.command("pubmed-search")
def pubmed_search(
    query: Annotated[str, typer.Option("--query", "-q", help="PubMed Boolean query")],
    max_results: Annotated[int, typer.Option("--max", help="Max PMIDs to fetch")] = 20,
    year_start: Annotated[Optional[int], typer.Option("--year-start")] = None,
    year_end: Annotated[Optional[int], typer.Option("--year-end")] = None,
    count_only: Annotated[bool, typer.Option("--count-only", help="Only return total hit count")] = False,
) -> None:
    """Run a PubMed query. Returns JSON {count, papers: [{title, authors, year, journal, doi, abstract}...]}."""

    cfg = _cfg()
    full_query = query
    if year_start and year_end:
        full_query += f" AND {year_start}:{year_end}[dp]"

    async def _run() -> dict[str, object]:
        async with PubMedClient(cfg.dbs.pubmed) as pc:
            total = await pc.count(full_query)
            if count_only:
                return {"count": total, "query": full_query}
            pmids = await pc.search_pmids(full_query, retmax=max_results)
            hits = await pc.fetch_metadata(pmids)
            papers = [
                {
                    "pmid": h.pmid,
                    "title": h.title,
                    "authors": h.authors,
                    "year": h.year,
                    "journal": h.journal,
                    "doi": h.doi,
                    "abstract": h.abstract,
                    "source_db": "PubMed",
                }
                for h in hits
            ]
            return {"count": total, "retrieved": len(papers), "query": full_query, "papers": papers}

    _stdout_json(asyncio.run(_run()))


@tools_app.command("validate-dois")
def validate_dois(
    papers_file: Annotated[
        Optional[Path],
        typer.Option("--papers-file", help="JSON file with papers array; each needs 'doi', 'title', 'year', 'authors'"),
    ] = None,
    run_id: Annotated[
        Optional[str],
        typer.Option("--run-id", help="Instead of file, validate DOIs in a run's search_result.papers"),
    ] = None,
    write_back: Annotated[
        bool,
        typer.Option("--write-back", help="If --run-id, update state.json papers with doi_validated/doi_metadata_matches"),
    ] = False,
) -> None:
    """CrossRef DOI validation. Returns per-paper {doi, resolvable, matches, mismatch_details}."""

    cfg = _cfg()

    if papers_file:
        papers_data = json.loads(papers_file.read_text(encoding="utf-8"))
    elif run_id:
        state = load_state(cfg.pipeline, run_id)
        if state.search_result is None:
            typer.echo("No search_result in state", err=True)
            raise typer.Exit(1)
        papers_data = [p.model_dump() for p in state.search_result.papers]
    else:
        typer.echo("Provide --papers-file or --run-id", err=True)
        raise typer.Exit(2)

    async def _run() -> list[dict[str, object]]:
        async with CrossrefClient(cfg.dbs.crossref_mailto) as cc:
            results = []
            for p in papers_data:
                if not p.get("doi"):
                    results.append({"doi": None, "resolvable": False, "matches_paper": None, "mismatch_details": "no DOI"})
                    continue
                first_surname = None
                authors = p.get("authors") or []
                if authors:
                    name = authors[0]
                    first_surname = name.split(",")[0].strip() if "," in name else name.strip().split()[-1]
                chk = await cc.validate(
                    p["doi"],
                    expected_title=p.get("title"),
                    expected_year=p.get("year"),
                    expected_first_author_surname=first_surname,
                )
                results.append(
                    {
                        "doi": p["doi"],
                        "resolvable": chk.resolvable,
                        "matches_paper": chk.matches_paper,
                        "mismatch_details": chk.mismatch_details,
                        "crossref_title": chk.metadata.title if chk.metadata else None,
                        "crossref_year": chk.metadata.year if chk.metadata else None,
                    }
                )
            return results

    results = asyncio.run(_run())

    if run_id and write_back:
        state = load_state(cfg.pipeline, run_id)
        if state.search_result:
            by_doi = {r["doi"]: r for r in results}
            updated = []
            for p in state.search_result.papers:
                r = by_doi.get(p.doi)
                if r:
                    updated.append(
                        p.model_copy(
                            update={
                                "doi_validated": bool(r["resolvable"]),
                                "doi_metadata_matches": r["matches_paper"],
                            }
                        )
                    )
                else:
                    updated.append(p)
            state.search_result.papers = updated
            save_state(cfg.pipeline, state)
            console.print(f"[green]✓[/] Wrote back {len(updated)} papers to state")

    _stdout_json(results)


# ---------------------------------------------------------------------------
# De-identification
# ---------------------------------------------------------------------------


@tools_app.command("deid-scan")
def deid_scan_cmd(
    path: Annotated[Path, typer.Argument(help="File to scan (YAML/TXT/MD)")],
) -> None:
    """Regex-based de-identification scan. Returns JSON of findings."""

    text = path.read_text(encoding="utf-8")
    report = deid_scan(text)
    _stdout_json(
        {
            "file": str(path),
            "passed": report.passed,
            "findings": [
                {"category": f.category, "match": f.match, "position": f.position}
                for f in report.findings
            ],
        }
    )


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


@tools_app.command("dedup")
def dedup_cmd(
    papers_file: Annotated[
        Optional[Path],
        typer.Option("--papers-file", help="JSON array of papers to deduplicate"),
    ] = None,
    run_id: Annotated[
        Optional[str],
        typer.Option("--run-id", help="Deduplicate state.search_result.papers in place"),
    ] = None,
) -> None:
    """Cross-database dedup via DOI + title-prefix matching."""

    cfg = _cfg()

    if papers_file:
        data = json.loads(papers_file.read_text(encoding="utf-8"))
        papers = [Paper.model_validate(p) for p in data]
    elif run_id:
        state = load_state(cfg.pipeline, run_id)
        if state.search_result is None:
            typer.echo("No search_result in state", err=True)
            raise typer.Exit(1)
        papers = state.search_result.papers
    else:
        typer.echo("Provide --papers-file or --run-id", err=True)
        raise typer.Exit(2)

    result = dedup(papers)
    _stdout_json(
        {
            "unique_count": len(result.unique),
            "duplicate_count": result.duplicate_count,
            "unique_dois": [p.doi for p in result.unique],
            "groups": [
                {
                    "canonical_doi": g.canonical.doi,
                    "canonical_title": g.canonical.title,
                    "duplicate_count": len(g.duplicates),
                    "duplicate_sources": [d.source_db.value for d in g.duplicates],
                }
                for g in result.groups
                if g.duplicates
            ],
        }
    )

    if run_id:
        state = load_state(cfg.pipeline, run_id)
        if state.search_result:
            state.search_result.papers = result.unique
            save_state(cfg.pipeline, state)
            console.print(f"[green]✓[/] In-place dedup: {len(result.unique)} unique / {result.duplicate_count} removed")


# ---------------------------------------------------------------------------
# State manipulation (for Claude Code to save subagent outputs)
# ---------------------------------------------------------------------------


@tools_app.command("dump-state")
def dump_state(
    run_id: Annotated[str, typer.Argument()],
    field: Annotated[
        Optional[str],
        typer.Option("--field", help="Dotted path to extract (e.g. 'pico_result.pico')"),
    ] = None,
) -> None:
    """Print state.json (or a subfield) as JSON."""

    cfg = _cfg()
    state = load_state(cfg.pipeline, run_id)
    data = json.loads(state.model_dump_json(exclude_none=False))
    if field:
        for part in field.split("."):
            if isinstance(data, dict):
                data = data.get(part)
            else:
                data = None
                break
    _stdout_json(data)


@tools_app.command("update-state")
def update_state(
    run_id: Annotated[str, typer.Argument()],
    field: Annotated[str, typer.Option("--field", "-f", help="Dotted path (e.g. 'pico_result')")],
    value_file: Annotated[
        Optional[Path], typer.Option("--value-file", help="JSON file with new value")
    ] = None,
    value_json: Annotated[
        Optional[str], typer.Option("--value-json", help="Inline JSON value (careful with shell quoting)")
    ] = None,
) -> None:
    """Patch state.json at a dotted path. Revalidates against Pydantic schema."""

    if not value_file and not value_json:
        typer.echo("Provide --value-file or --value-json", err=True)
        raise typer.Exit(2)

    cfg = _cfg()
    state = load_state(cfg.pipeline, run_id)
    data = json.loads(state.model_dump_json())

    new_value = (
        json.loads(value_file.read_text(encoding="utf-8"))
        if value_file
        else json.loads(value_json)  # type: ignore[arg-type]
    )

    parts = field.split(".")
    cursor = data
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = new_value

    validated = RunState.model_validate(data)
    validated.updated_at = datetime.utcnow()
    save_state(cfg.pipeline, validated)
    console.print(f"[green]✓[/] state.{field} updated for run {run_id}")


@tools_app.command("append-section")
def append_section(
    run_id: Annotated[str, typer.Argument()],
    section_file: Annotated[Path, typer.Option("--file", help="Section JSON file")],
) -> None:
    """Append a Section dict to state.sections (validates schema, keeps existing)."""

    from .models import Section

    cfg = _cfg()
    state = load_state(cfg.pipeline, run_id)
    section_data = json.loads(section_file.read_text(encoding="utf-8"))
    section = Section.model_validate(section_data)
    # Replace any existing section with same name, else append
    replaced = False
    for i, s in enumerate(state.sections):
        if s.section_name == section.section_name:
            state.sections[i] = section
            replaced = True
            break
    if not replaced:
        state.sections.append(section)
    save_state(cfg.pipeline, state)
    console.print(f"[green]✓[/] Section '{section.section_name}' {'replaced' if replaced else 'appended'} ({section.word_count_estimate} 字)")


# ---------------------------------------------------------------------------
# Checkpoint logging
# ---------------------------------------------------------------------------


@tools_app.command("approve-cp")
def approve_cp(
    run_id: Annotated[str, typer.Argument()],
    cp_id: Annotated[str, typer.Argument(help="CP1-CP9")],
    choice: Annotated[str, typer.Option("--choice", help="批准/套用/修改/重跑/棄題/確認")] = "批准",
    rationale: Annotated[Optional[str], typer.Option("--rationale")] = None,
) -> None:
    """Append a HITL checkpoint decision to state.checkpoints."""

    cfg = _cfg()
    state = load_state(cfg.pipeline, run_id)
    cp = Checkpoint(
        cp_id=CheckpointId(cp_id),
        timestamp=datetime.utcnow(),
        user_choice=choice,
        rationale=rationale,
        phase_snapshot_path=str(cfg.pipeline.output_root / run_id / "state.json"),
    )
    append_checkpoint(cfg.pipeline, state, cp)
    console.print(f"[green]✓[/] {cp_id}: {choice}" + (f" — {rationale}" if rationale else ""))


# ---------------------------------------------------------------------------
# Paper selection helper
# ---------------------------------------------------------------------------


@tools_app.command("select-papers")
def select_papers(
    run_id: Annotated[str, typer.Argument()],
    dois_file: Annotated[
        Optional[Path],
        typer.Option("--dois-file", help="Newline-separated DOI list (one per line; optional `TAB design TAB oxford`)"),
    ] = None,
    dois: Annotated[
        Optional[str],
        typer.Option("--dois", help="Comma-separated DOIs (no design/oxford)"),
    ] = None,
    default_design: Annotated[str, typer.Option("--design")] = "Other",
    default_oxford: Annotated[str, typer.Option("--oxford")] = "III",
) -> None:
    """Narrow state.search_result.papers to the selected DOIs; set study_design & oxford_level."""

    cfg = _cfg()
    state = load_state(cfg.pipeline, run_id)
    if state.search_result is None:
        typer.echo("No search_result in state", err=True)
        raise typer.Exit(1)

    wanted: dict[str, tuple[str, str]] = {}
    if dois_file:
        for line in dois_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            doi = parts[0]
            design = parts[1] if len(parts) > 1 else default_design
            oxford = parts[2] if len(parts) > 2 else default_oxford
            wanted[doi] = (design, oxford)
    elif dois:
        for doi in dois.split(","):
            wanted[doi.strip()] = (default_design, default_oxford)
    else:
        typer.echo("Provide --dois-file or --dois", err=True)
        raise typer.Exit(2)

    selected = []
    for p in state.search_result.papers:
        if p.doi in wanted:
            design, oxford = wanted[p.doi]
            selected.append(
                p.model_copy(update={"study_design": design, "oxford_level": oxford})
            )
    state.search_result.papers = selected
    save_state(cfg.pipeline, state)
    console.print(f"[green]✓[/] Selected {len(selected)} papers")
    _stdout_json(
        [
            {"doi": p.doi, "design": p.study_design.value, "oxford": p.oxford_level.value, "title": p.title[:80]}
            for p in selected
        ]
    )


@tools_app.command("export-abstracts")
def export_abstracts(
    run_id: Annotated[str, typer.Argument()],
    out_dir: Annotated[Optional[Path], typer.Option("--out-dir")] = None,
) -> None:
    """Write one markdown file per included paper to ``output/<run-id>/inclusions/``."""

    cfg = _cfg()
    state = load_state(cfg.pipeline, run_id)
    if state.search_result is None:
        typer.echo("No search_result in state", err=True)
        raise typer.Exit(1)
    target = out_dir or (cfg.pipeline.output_root / run_id / "inclusions")
    target.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for i, p in enumerate(state.search_result.papers, 1):
        safe_doi = p.doi.replace("/", "_") if p.doi else f"noDOI-{i}"
        fname = target / f"paper_{i}_{safe_doi}.md"
        body = (
            f"# Paper {i}\n"
            f"Title: {p.title}\n"
            f"Authors: {', '.join(p.authors[:5])}\n"
            f"Year: {p.year}\n"
            f"Journal: {p.journal}\n"
            f"DOI: {p.doi}\n"
            f"Study Design: {p.study_design.value}\n"
            f"Oxford: {p.oxford_level.value}\n\n"
            f"## Abstract\n\n{p.abstract or '(no abstract available)'}\n"
        )
        fname.write_text(body, encoding="utf-8")
        written.append(str(fname))

    _stdout_json({"wrote": written, "count": len(written), "out_dir": str(target)})
