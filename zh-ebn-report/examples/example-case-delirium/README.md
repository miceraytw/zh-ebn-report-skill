# 範例 2：案例分析——加護病房譫妄的非藥物介入

示範案例分析的完整流程，包含去識別化檢查、個案敘事員、應用審計員。

## 題目與個案

**糊題目**：「譫妄的處理」

**期待**：題目守門員具體化為「高齡加護病房個案採用非藥物介入（現實導向 + 環境調整）相較於 routine care 對譫妄改善之效果」。

**個案**：70 歲男性，肺炎插管後於加護病房出現譫妄（CAM 陽性）。

## 個案資料檔案

`case-deidentified.yaml`（已去識別化，範例，可視需求擴充）。

## 執行指令

```bash
zh-ebn-report init \
    --type case \
    --topic "譫妄的處理" \
    --ward "內科加護病房" \
    --level N3 \
    --scenario "高齡個案插管後譫妄頻發；現行以藥物為主，筆者想評估非藥物介入的可行性" \
    --case-file ./case-deidentified.yaml \
    --i-accept-audit-responsibility

zh-ebn-report run <run-id>
```

## 特殊步驟

案例分析在 Phase 5（綜整）後會執行 Phase 5.5：
- **個案敘事員** 平行產出個案介紹段 + 診斷推理段
- **應用審計員** 平行產出應用段 + 評值段

Pipeline 在 Apply 階段前以 `utils/deid.py` 檢查個案資料，若命中姓名、病歷號、身分證、出生日期、電話等 pattern，會退件要求重新處理。
