"""State persistence for a single pipeline run.

A run lives under ``output/<run-id>/`` with the following layout::

    output/<run-id>/
        state.json              # RunState JSON, resumable
        checkpoint_log.json     # append-only HITL decision log
        search_history.csv      # human-readable 搜尋歷程表
        casp/*.json             # per-paper CASP results
        sections/*.md           # per-section drafts
        report-DRAFT.docx       # final Quarto output
        quarto/                 # intermediate .qmd files
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .config import PipelineConfig
from .models import Checkpoint, RunConfig, RunState


def new_run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def run_dir(pipeline_cfg: PipelineConfig, run_id: str) -> Path:
    d = pipeline_cfg.output_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(pipeline_cfg: PipelineConfig, run_id: str) -> Path:
    return run_dir(pipeline_cfg, run_id) / "state.json"


def checkpoint_log_path(pipeline_cfg: PipelineConfig, run_id: str) -> Path:
    return run_dir(pipeline_cfg, run_id) / "checkpoint_log.json"


def save_state(pipeline_cfg: PipelineConfig, state: RunState) -> Path:
    state.updated_at = datetime.utcnow()
    path = state_path(pipeline_cfg, state.config.run_id)
    path.write_text(
        state.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    return path


def load_state(pipeline_cfg: PipelineConfig, run_id: str) -> RunState:
    path = state_path(pipeline_cfg, run_id)
    if not path.exists():
        raise FileNotFoundError(f"No state found for run {run_id}: {path}")
    return RunState.model_validate_json(path.read_text(encoding="utf-8"))


def init_state(pipeline_cfg: PipelineConfig, config: RunConfig) -> RunState:
    state = RunState(config=config)
    save_state(pipeline_cfg, state)
    return state


def append_checkpoint(
    pipeline_cfg: PipelineConfig,
    state: RunState,
    cp: Checkpoint,
) -> None:
    state.checkpoints.append(cp)
    save_state(pipeline_cfg, state)

    log_path = checkpoint_log_path(pipeline_cfg, state.config.run_id)
    existing: list[dict[str, object]] = []
    if log_path.exists():
        existing = json.loads(log_path.read_text(encoding="utf-8"))
    existing.append(json.loads(cp.model_dump_json()))
    log_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
