# zh-ebn-report-codex-skill

[![Build & Release Skill](https://github.com/miceraytw/zh-ebn-report-skill/actions/workflows/release.yml/badge.svg)](https://github.com/miceraytw/zh-ebn-report-skill/actions/workflows/release.yml)
[![GitHub Release](https://img.shields.io/github/v/release/miceraytw/zh-ebn-report-skill?include_prereleases&label=skill%20version)](https://github.com/miceraytw/zh-ebn-report-skill/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Codex-adapted fork of `zh-ebn-report-skill`，用於台灣護理人員撰寫實證護理報告（實證讀書報告、實證案例分析）。專為護理進階制度 N1-N4 升等、台灣護理學會與台灣實證護理學會審查格式而設計，並保留原本的 5A pipeline、知識庫、Python pipeline 與 utility CLI。

## 這個 skill 給誰用

給台灣護理人員。只要輸入一個還不夠明確的主題，例如「早期下床」「壓瘡」「譫妄的處理」，這份 skill 會帶著你跑完實證 5A 步驟，最後產出可供升等審查的報告草稿。

## 能做什麼

- 選題把關：把模糊題目具體化，避開五大地雷主題
- PICO 建構：輸出中英並列 PICO，限制錯誤 comparison 與模糊 outcome
- 六件套搜尋策略：主詞、同義字、MeSH、CINAHL Heading、Boolean、欄位碼
- CASP 評讀：對應研究設計套用不同 checklist，並標示 Oxford 2011 證據等級
- 綜整整合：分析跨篇一致性、矛盾點、整體證據強度與台灣臨床可行性
- 分節撰寫：依報告類型生成章節草稿
- 語氣守門與 APA 7 檢查：修正台灣護理寫作腔調與格式
- DOI 驗證、去識別化檢查、審稿 checkpoint 與最終 DOCX 輸出

## Pipeline 設計

這份 skill 的核心不是單純的 prompt，而是一條固定的 5A pipeline：

1. Ask
2. Acquire
3. Appraise
4. Apply
5. Audit

Pipeline 內部保留 10 個具名角色：

1. 題目守門員
2. PICO 建構員
3. 搜尋策略師
4. CASP 評讀員 × N
5. 綜整整合員
6. 分節撰寫員 × 4-6
7. 語氣守門員
8. APA 7 格式員
9. 個案敘事員
10. 應用審計員

在 Codex 版本中，這 10 個角色代表固定的 phase 與責任分工，不代表每次都一定要真的啟動多代理。若執行環境支援且使用者明確要求平行代理，可把互不依賴的 phase 並行化；否則就由單一 Codex session 依同一套流程逐段完成。

## Codex 版定位

這個 repo 原本帶有明確的 Claude / Anthropic 執行路徑。轉成 Codex 版本後，區分如下：

- `SKILL.md` 已可作為 Codex skill 入口使用
- 互動式協作可由 Codex 直接沿用同一條 5A + 10-role pipeline
- Python pipeline 的內建 LLM backend 現在支援 `codex`、`claude_code`、`anthropic`、`auto`
- 也就是說，skill 入口與底層 CLI backend 現在都已經能辨識 Codex 路徑

如果你的目標是用 Codex 做寫作協作、PICO、評讀、章節草稿與審稿 checkpoint，現在已經可用。`zh-ebn-report run` 也可以嘗試透過 `LLM_BACKEND=codex` 跑完整自動化，但實際 subprocess 執行仍取決於本機 `codex` CLI 的權限與登入狀態。

## 安裝與本地使用

若要使用 Python pipeline 的搜尋、CrossRef 驗證與 Quarto 渲染功能：

```bash
cd zh-ebn-report
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env

# 驗證
zh-ebn-report --help
zh-ebn-report tools --help
```

若只使用 skill 層的互動協作，可直接讀取 [zh-ebn-report/SKILL.md](./zh-ebn-report/SKILL.md) 與其中引用的 `references/`。

## Skill 內容

```text
zh-ebn-report/
├── SKILL.md
├── references/
│   ├── ai-disclosure.md
│   ├── appraisal-tools.md
│   ├── case-report-template.md
│   ├── gordon-11-patterns.md
│   ├── phrasing-bank.md
│   ├── pico-and-search.md
│   ├── reading-report-template.md
│   ├── subagent-roles.md
│   └── topic-selection.md
├── src/zh_ebn_report/
│   ├── cli.py
│   ├── cli_tools.py
│   ├── clients/
│   ├── pipeline/
│   ├── prompts/
│   ├── renderers/
│   ├── spec/
│   ├── state.py
│   └── utils/
├── templates/
├── examples/
├── tests/
├── pyproject.toml
└── .env.example
```

## 執行模式

### 模式 A：Codex 互動協作模式

適合選題、PICO、搜尋策略、CASP 評讀、章節草稿、語氣修正與 checkpoint 審稿。這個模式保留同樣的 pipeline，但由 Codex 依技能規則執行，不要求底層 CLI 改成 Codex backend。

常見搭配方式：

```bash
zh-ebn-report init --type reading --topic "早期下床" --ward "一般外科" --level N2 --i-accept-audit-responsibility
zh-ebn-report tools pubmed-search --query "..." --year-start 2021 --year-end 2026 --max 25
zh-ebn-report tools validate-dois --run-id <id> --write-back
zh-ebn-report render <id>
```

### 模式 B：Python 自動化模式

若要用現有內建 backend 跑自動化 phase，仍須使用專案目前支援的 backend：

```bash
export LLM_BACKEND=codex
# 或
export LLM_BACKEND=claude_code
# 或
export LLM_BACKEND=anthropic

zh-ebn-report init ...
zh-ebn-report run --resume <run-id>
```

`LLM_BACKEND=codex` 需要系統上可執行 `codex` CLI；`LLM_BACKEND=claude_code` 需要 `claude` CLI；`LLM_BACKEND=anthropic` 需要相應 API 金鑰。`LLM_BACKEND=auto` 會優先選 `codex`，再選 `claude_code`，最後才回退到 `anthropic`。

## AI 使用規範（2026 版台灣護理學會）

這份 skill 依台灣護理學會與台灣實證護理學會規範設計。AI 可協助生成草稿，但：

- AI 不列為作者
- 必須在研究方法或致謝段主動揭露工具名稱、版本與使用方式
- 作者必須逐節審閱與修訂 AI 產出
- 作者必須簽署 Audit 責任聲明
- 建議將 AI 輔助生成部分作為補充資料一併提交

Pipeline 會自動附上必要的揭露與審稿紀錄文件，但最終責任仍在使用者。

## License

[MIT License](LICENSE) © 2026 htlin222
