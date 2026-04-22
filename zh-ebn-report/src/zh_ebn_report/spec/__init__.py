"""Template specification (single source of truth).

All constants describing the reading-report / case-report templates live here,
so prompts, orchestrator, compliance checker and renderer share one authority.
"""

from .reading_report_spec import (
    APPENDIX_ORDER,
    CASE_SECTION_ORDER,
    MIN_HIGH_LEVEL_EVIDENCE,
    MIN_REFERENCES,
    READING_SECTION_ORDER,
    SECTION_WORD_RANGE_CASE,
    SECTION_WORD_RANGE_READING,
    ReportKind,
    SectionSpec,
    WordRange,
    required_section_names,
    section_names,
    section_order,
    word_range_for,
)

__all__ = [
    "APPENDIX_ORDER",
    "CASE_SECTION_ORDER",
    "MIN_HIGH_LEVEL_EVIDENCE",
    "MIN_REFERENCES",
    "READING_SECTION_ORDER",
    "SECTION_WORD_RANGE_CASE",
    "SECTION_WORD_RANGE_READING",
    "ReportKind",
    "SectionSpec",
    "WordRange",
    "required_section_names",
    "section_names",
    "section_order",
    "word_range_for",
]
