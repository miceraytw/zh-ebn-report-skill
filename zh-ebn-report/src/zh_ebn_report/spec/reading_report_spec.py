"""Reading-report / case-report template spec (single source of truth).

These numbers come straight from
``zh-ebn-report/references/reading-report-template.md`` and
``case-report-template.md``. Prompts, compliance checker and renderer must
read from here — never hard-code a word range elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WordRange:
    """CJK-character count range (inclusive)."""

    min: int
    max: int

    def contains(self, n: int) -> bool:
        return self.min <= n <= self.max

    def describe(self) -> str:
        if self.min == self.max:
            return f"約 {self.min} 字"
        return f"{self.min}–{self.max} 字"


@dataclass(frozen=True)
class SectionSpec:
    name: str
    word_range: WordRange
    required: bool
    must_cite_all_papers: bool = False
    must_cite_at_least: int = 0
    description: str = ""


# ---------------------------------------------------------------------------
# Reading-report section order (8-chapter structure)
# ---------------------------------------------------------------------------
# Matches reading-report-template.md §報告完整骨架 (摘要 + 7 main chapters).
# 「參考文獻」章由 Quarto/CSL 自動產出，不屬於 section writer 範圍。
READING_SECTION_ORDER: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="摘要",
        word_range=WordRange(180, 260),  # 模板「約 200 字」，±30% 作為硬區間
        required=True,
        description="單段連續敘述；背景/方法/結果/結論各 1–2 句；末附 3–5 組中英並列關鍵詞。不得含引文。",
    ),
    SectionSpec(
        name="前言",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_at_least=3,
        description="背景重要性→現行照護不足→動機→報告概述。至少 3 處引文。",
    ),
    SectionSpec(
        name="主題設定",
        word_range=WordRange(200, 400),
        required=True,
        description="PICO 四要素（中英並列）＋ 問題型態（Therapy/Harm/Diagnosis/Prognosis）；以表格呈現。",
    ),
    SectionSpec(
        name="搜尋策略",
        word_range=WordRange(500, 800),
        required=True,
        description="資料庫清單、六件套策略、Limits、搜尋歷程（起始→去重→納入）、引文追蹤、DOI 驗證。",
    ),
    SectionSpec(
        name="評讀結果",
        word_range=WordRange(500, 1000),
        required=True,
        must_cite_all_papers=True,
        description="摘要表 + 逐篇 CASP 要點（設計/樣本/主要結果/Oxford 等級）。每篇至少引用一次。",
    ),
    SectionSpec(
        name="綜整",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_all_papers=True,
        description="跨篇一致性、矛盾與解釋、整體證據強度、台灣脈絡可行度。依 Oxford 等級由高至低敘述。",
    ),
    SectionSpec(
        name="應用建議",
        word_range=WordRange(300, 600),
        required=True,
        description="假想應用情境：目標族群、建議措施 3–5 項、執行注意事項、成效評值指標。",
    ),
    SectionSpec(
        name="結論",
        word_range=WordRange(200, 300),
        required=True,
        description="回應 PICO、承認限制、對臨床/教育/研究的具體建議（不可含糊）。",
    ),
)


# ---------------------------------------------------------------------------
# Case-report section order (case-report-template.md §報告完整骨架)
# ---------------------------------------------------------------------------
# 案例分析保留既有 6 章制，僅把字數常數集中於此。
CASE_SECTION_ORDER: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="摘要",
        word_range=WordRange(200, 300),
        required=True,
        description="五要素單段：個案特徵、臨床困境、實證方法、主要發現、應用結果。",
    ),
    SectionSpec(
        name="前言",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_at_least=2,
        description="選案動機、現行常規及依據、筆者察覺的問題點、引出 5A。",
    ),
    SectionSpec(
        name="個案介紹",
        word_range=WordRange(700, 1200),
        required=True,
        description="條列式客觀資料：基本資料、病史、身體評估、檢驗、心理/社會/靈性。",
    ),
    SectionSpec(
        name="方法",
        word_range=WordRange(700, 1200),
        required=True,
        description="PICO + 搜尋策略 + 評讀工具；案例分析合併成單節敘述。",
    ),
    SectionSpec(
        name="綜整",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_all_papers=True,
        description="跨篇一致性、矛盾、整體證據強度、應用到本個案的可行度。",
    ),
    SectionSpec(
        name="應用與評值",
        word_range=WordRange(1000, 1500),
        required=True,
        description="Apply（介入計畫、實施、挑戰）+ Audit（時間軸、前後客觀量表、偏差說明）。",
    ),
    SectionSpec(
        name="結論",
        word_range=WordRange(200, 400),
        required=True,
        description="回應 PICO、個案貢獻、對臨床與未來研究的建議。",
    ),
)


# ---------------------------------------------------------------------------
# Global constants
# ---------------------------------------------------------------------------
MIN_REFERENCES: int = 5
"""reading-report-template.md §參考文獻：至少 5 篇。"""

MIN_HIGH_LEVEL_EVIDENCE: int = 2
"""reading-report-template.md §參考文獻：至少 2 篇高證據等級（SR/MA/RCT；Oxford I–II）。"""

APPENDIX_ORDER: tuple[str, ...] = (
    "A",  # 搜尋歷程表
    "B",  # CASP 評讀彙整
    "C",  # PRISMA 風格流程圖
    "D",  # Subagent 執行紀錄
)


# ---------------------------------------------------------------------------
# Lookup helpers (per-kind to avoid cross-kind overrides for shared names)
# ---------------------------------------------------------------------------
SECTION_WORD_RANGE_READING: dict[str, WordRange] = {
    s.name: s.word_range for s in READING_SECTION_ORDER
}
SECTION_WORD_RANGE_CASE: dict[str, WordRange] = {
    s.name: s.word_range for s in CASE_SECTION_ORDER
}


ReportKind = Literal["reading", "case"]


def word_range_for(kind: ReportKind, section_name: str) -> WordRange | None:
    table = SECTION_WORD_RANGE_READING if kind == "reading" else SECTION_WORD_RANGE_CASE
    return table.get(section_name)


def section_order(kind: ReportKind) -> tuple[SectionSpec, ...]:
    if kind == "reading":
        return READING_SECTION_ORDER
    return CASE_SECTION_ORDER


def section_names(kind: ReportKind, *, exclude_abstract: bool = False) -> list[str]:
    order = section_order(kind)
    if exclude_abstract:
        return [s.name for s in order if s.name != "摘要"]
    return [s.name for s in order]


def required_section_names(kind: ReportKind) -> list[str]:
    return [s.name for s in section_order(kind) if s.required]
