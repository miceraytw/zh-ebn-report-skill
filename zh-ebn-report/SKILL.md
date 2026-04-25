---
name: zh-ebn-report-codex
description: 台灣護理人員撰寫實證護理報告（實證讀書報告、實證案例分析）的完整教練技能，專為護理進階制度 N1-N4 升等、台灣護理學會與台灣實證護理學會審查格式而設計。當使用者提到「實證護理報告」、「實證案例分析」、「實證讀書報告」、「N2 報告」、「N3 報告」、「N4 報告」、「護理進階報告」、「護理升等」、「PICO」、「5A 步驟」、「CASP 評讀」、「護理 EBP」、「EBN」、「evidence-based nursing」、「實證照護」、「證據等級」、「文獻評讀」，或任何護理人員詢問升等寫作、臨床問題轉化為實證主題、實證文獻搜尋策略、CASP 評讀表、Oxford 證據等級、APA 第 7 版格式、實證介入應用至個案、護理常規挑戰、去除護理迷思等情境，務必觸發此技能。即使使用者只是隨口問「我要寫報告」、「我要升 N3」、「幫我找主題」、「幫我設 PICO」、「這篇文獻要怎麼評讀」，也應主動啟動以提供完整的結構、句型與審查通過率最高的寫作策略。
---

# 台灣護理實證報告寫作教練

這個技能協助台灣護理人員完成符合台灣護理學會與台灣實證護理學會審查標準的實證報告，涵蓋實證讀書報告與實證案例分析兩種類型。最終目的是幫助護理師通過 N2/N3/N4 進階審查，或產出可投稿的學術作品。

## 這份技能涵蓋哪些報告類型

| 類型 | 差別 | 對應層級 | 篇幅 |
|---|---|---|---|
| 實證讀書報告（EBR） | 評析幾篇文獻後做邏輯性綜整，無個案應用 | N1、N2 為主 | 約 8-15 頁 |
| 實證案例分析（EBP case analysis） | 將實證結果應用於一位真實病人並評估成效 | N3 以上 | 約 15-25 頁 |

N4 以上多已進入系統性文獻回顧或護理專案研究，本技能不涵蓋這塊。

## 寫作前的身分確認

在動筆前，先跟使用者釐清以下四件事，用以決定使用哪個模板與深度：

1. 要寫哪一種報告？（讀書報告 / 案例分析）
2. 是哪一級進階？（N1-N4，或是投稿競賽）
3. 病房別與個案條件是什麼？（決定主題合理性與可行性）
4. 醫院有沒有專用格式範本？（有的話以醫院範本為準，本技能補足內容）

如果這些都還沒確定，不要急著起草；先用最少問題把需求補齊，再決定是否進入 pipeline。

## 核心工作流程：實證 5A 步驟

所有實證報告都圍繞這五個步驟，缺一不可（讀書報告可到 Appraise 即可，案例分析必須跑完五步）：

1. Ask - 形成可回答的臨床問題（PICO）
2. Acquire - 搜尋最佳文獻證據
3. Appraise - 嚴格評讀證據（CASP + Oxford 證據等級）
4. Apply - 臨床應用到個案（僅案例分析）
5. Audit - 結果評值（僅案例分析）

詳細每一步的操作方式、常見錯誤、句型範例，見對應的 `references/` 檔案。

## Codex 版本的執行原則

本技能搭配 `zh-ebn-report` Python CLI（位於專案根的 `src/zh_ebn_report/`），以 10 個具名角色完成報告草稿。對 Codex 而言，這 10 個角色是必須保留的 pipeline 邏輯，不一定代表每次都要真的開多個 agent。

使用時遵守下列原則：

1. 先確認使用者目前位於哪個階段，再只載入必要的 `references/` 檔案，不要一次把所有參考資料灌進上下文。
2. 優先保留原本 phase 順序、checkpoint 與輸入輸出契約；不要把 5A 壓扁成一般作文協助。
3. 若使用者明確要求平行代理、委派或多代理協作，且當前執行環境支援，才把可並行的角色分派出去。
4. 若沒有明確授權多代理，仍要保留同樣 pipeline，但由 Codex 在單一執行緒中依序完成各角色工作。
5. 只要某一步已有 Python CLI 或既有 prompt / guardrail 可做，就優先使用專案現成能力，不要任意改寫流程。
6. 使用者在 9 個 checkpoint 的審稿責任不能省略；Codex 可以幫忙起草與整理，但不能把 HITL 審稿步驟吃掉。

## 自動化 Pipeline 與 HITL 審稿角色分工

使用者的角色是 HITL 審稿者：在 9 個 checkpoint 介入決策、批准或要求重寫，最終文字仍須以自己的話重寫送審。

Subagent / role 分工詳見 `references/subagent-roles.md`：

| # | 角色 | 並行條件 |
|---|---|---|
| 1 | 題目守門員 | 否 |
| 2 | PICO 建構員 | 否 |
| 3 | 搜尋策略師 | 否 |
| 4 | CASP 評讀員 × N | 同批文獻可並行 |
| 5 | 綜整整合員 | 否 |
| 6 | 分節撰寫員 × 4-6 | 各節互不依賴時可並行 |
| 7 | 語氣守門員 | 可與 8 並行 |
| 8 | APA 7 格式員 | 可與 7 並行 |
| 9 | 個案敘事員（案例分析） | 可與 10 並行 |
| 10 | 應用審計員（案例分析） | 可與 9 並行 |

dispatch 原則：彼此輸入沒依賴的角色，一律視為可並行 phase。若當前不能或不適合開多代理，就依同樣角色邏輯逐段執行，不得省略角色責任。

## CLI 介面

```bash
zh-ebn-report init --type reading|case --topic "..."
zh-ebn-report run --resume <run-id>
zh-ebn-report topic|pico|search|appraise|synthesise|write|check|render
zh-ebn-report render --final
zh-ebn-report status <run-id>
```

## LLM 後端與 Codex 的關係

這個專案目前內建的 pipeline 後端支援 `codex` / `claude_code` / `anthropic` / `auto`；這是專案實作細節，不是 skill 入口要改寫的地方。Codex 版 skill 的責任是：

- 在互動協作時，沿用同一套 5A + 10-role pipeline。
- 需要真正執行 CLI 時，如實說明此專案目前支援哪些後端與其執行限制。
- 若使用者只是要寫作協助、選題、PICO、評讀或章節草稿，Codex 可以直接依同一 pipeline 協作，不必偽裝成 Claude。

目前可辨識的 backend：

- `LLM_BACKEND=codex`：以 subprocess 呼叫 `codex exec`
- `LLM_BACKEND=claude_code`：以 subprocess 呼叫 `claude -p`
- `LLM_BACKEND=anthropic`：直接走 Anthropic SDK
- `LLM_BACKEND=auto`：自動偵測（優先 `codex`，其次 `claude`）

相關實作見 `clients/llm.py`、`clients/codex_cli.py`、`clients/claude_code_cli.py`、`clients/anthropic.py`。

## Guardrail 架構

pipeline 不只靠 LLM 自律。凡是可機械驗證的規則，都由 Python guardrail 覆寫或擋下：

- `pipeline/evidence_guard.py`：Oxford Level 不可高於 study design 上限
- `pipeline/synthesis_guard.py`：從 CASP levels + contradictions 機械推導整體證據強度
- `pipeline/voice_scan.py`：掃描禁用詞並重算 `pass_threshold_met`
- `pipeline/apa_guard.py`：依 DOI 驗證、citation 存在性與格式問題推導 `apa_pass`
- `pipeline/compliance.py`：句型、字數、引文、匿名、privacy、絕對用語、citation 捏造防線

每次新增或修改 guardrail 後執行：

```bash
python scripts/retro_validate.py
```

可用來確認 guardrail 能否抓到歷史違規並避免回歸。`--json` 可供 CI 使用；`--strict` 會在任何 guardrail 發現問題時退出碼 1。

## 台灣護理強化

### 1. 華藝 Airiti 匯入

除 RIS 外新增 CSV 支援：

- `zh-ebn-report search <run-id> --airiti-csv <file.csv>`
- 學位論文固定 `StudyDesign.OTHER` + `OxfordLevel.IV`
- 中文作者姓名以純 CJK 規則產生 citekey surname
- 匯出流程：Airiti Library -> 勾選文獻 -> 書目管理 -> CSV 匯出

實作見 `clients/manual_import.py:_airiti_csv_to_records`。

### 2. Gordon 11 項功能性健康型態

TWNA 個案報告 / 護理專案 `護理評估` 節的標準骨架：

- 參考：`references/gordon-11-patterns.md`
- 撰寫 role：`prompts/section_writer_護理評估.md`
- Compliance：`_check_gordon_11_coverage`
- 只對 `twna_case` / `twna_project` 類型觸發

### 3. AI 關鍵字調整

PubMed 初次檢索若不在 100-1000 甜蜜區，可選啟用一輪 LLM 調整：

- 啟用：`ENABLE_KEYWORD_TUNER=1`
- 觸發：初輪 hits < 50 或 > 5000
- Prompt：`prompts/keyword_tuner.md`
- 決策：`pipeline/keyword_tuner.pick_better`
- 上限一輪

## Audit Artifact Store

每個 run 會在 `output/<run-id>/artifacts/` 留下完整中間產物供審查：

```text
artifacts/
  _index.jsonl
  blobs/<sha256>.txt
  llm/<ISO>_<caller>_<tier>_<id>.json
  guardrails/<name>/<ISO>_{before,after,summary}.json
```

LLM record 含 caller、tier、model、backend、duration、prompt hash、response hash 與 parsed response。Guardrail 紀錄保留 LLM 原始判讀與 Python 覆寫後版本。

實作見 `pipeline/audit.py` 與 `clients/audited.py`。

## 最終輸出與倫理守則

Pipeline 最終輸出 `<報告>-DRAFT.docx`，含搜尋歷程表、CASP 評讀表、PRISMA 風格流程圖、AI 協作聲明頁。若 `templates/reference.docx` 存在，會做為樣式母本套用；否則使用 pandoc 預設樣式。

依 2026 年台灣護理學會與台灣實證護理學會規範：

- AI 可以完整生成草稿，但使用者必須 audit、揭露、承擔責任
- CLI 啟動必須傳 `--i-accept-audit-responsibility`
- Pipeline 自動附三份必要文件：AI 使用揭露段落、Audit 責任聲明、Subagent 執行紀錄
- 檔名預設帶 `-DRAFT`
- `render --final` 只能在明確完成審閱後使用
- AI 不得列為作者；揭露段落須載明工具名稱、模型、版本、具體使用方式

詳見 `references/ai-disclosure.md`。

## 使用這份技能的流程

根據使用者所處的階段，依下列次序提供協助。

### 情境 A：使用者還在選題

先讀 `references/topic-selection.md`，幫使用者判斷題目可不可行，避免五大地雷主題。

本階段 role：題目守門員（1）-> CP1。

### 情境 B：使用者已有題目，要設 PICO

讀 `references/pico-and-search.md`，套用 PICO 結構，注意：

- 中英並列
- 標明問題型態（Therapy / Harm / Diagnosis / Prognosis）
- Outcome 盡量量化、可觀察

本階段 role：PICO 建構員（2）-> CP2。

### 情境 C：要做文獻搜尋與評讀

讀 `references/pico-and-search.md` 與 `references/appraisal-tools.md`。

關鍵提醒：

- 搜尋歷程要可重現
- 六件套搜尋策略要完整
- 初始篇數以 100-1000 為甜蜜區
- 正向與反向引文追蹤都要做
- DOI 逐篇驗證
- 評讀工具要對應研究設計
- 證據等級依 Oxford 2011

本階段 role：搜尋策略師（3）-> CP3 -> CP4 -> CASP 評讀員 × N（4）-> CP5。

### 情境 D：要把實證結果用到個案

讀 `references/case-report-template.md`。重點：

- 要有護理師原話直接引語
- 要有個案或家屬原話直接引語
- 要有具體時間點
- 結果要同時呈現客觀量測與主觀感受
- 個案資料必須先去識別化

本階段 role：綜整整合員（5）-> CP6 -> 個案敘事員 + 應用審計員（9、10）-> 分節撰寫員 × 6（6）-> CP7。

### 情境 E：要寫結論與討論

讀 `references/phrasing-bank.md`。結論段標準動作：

1. 回應 PICO 的結論
2. 承認研究限制
3. 納入本地脈絡考量
4. 提出對未來臨床與教育的建議

本階段 role：分節撰寫員（6，結論節）-> 語氣守門員 + APA 7 格式員（7、8）-> CP8 -> Quarto render -> CP9。

## 寫作風格的核心守則

台灣實證護理報告有固定腔調，不符合會被當成外行。核心原則：

- 自稱用「筆者」，不用「我」
- 個案不叫「病人」，叫「個案」或「案○」
- 動詞偏書面語
- 中文文獻在前、英文文獻在後，依 APA 第 7 版
- 儘量引用近 5 年文獻，除非是重要經典研究

更多句型見 `references/phrasing-bank.md`。

## 審查通過率最高的寫作策略

1. 題目要具體而不宏大。
2. 搜尋歷程越透明越好。
3. 至少納入 2-4 篇高證據等級文獻。
4. CASP 評讀表要完整附上。
5. 案例分析要有真實應用記錄。
6. 討論段要體現反思與在地限制。
7. AI 協作必須揭露、審閱並承擔責任。

## 常見陷阱與錯誤

- Comparison 寫成「無介入」
- 把實證讀書報告寫成一般文獻回顧
- 證據等級亂標
- CASP 表只有打勾沒有說明
- 個案資料未去識別化
- 參考文獻未使用 APA 7

## 參考文件索引

依需要載入：

- `references/case-report-template.md`：實證案例分析模板
- `references/reading-report-template.md`：實證讀書報告模板
- `references/pico-and-search.md`：PICO 與搜尋策略
- `references/appraisal-tools.md`：CASP 與 Oxford 等級
- `references/phrasing-bank.md`：台灣護理報告標準句型
- `references/subagent-roles.md`：10 個角色的輸入輸出契約
- `references/topic-selection.md`：選題指引與五大地雷主題
- `references/ai-disclosure.md`：AI 使用揭露與責任聲明
