# 範例 1：讀書報告——壓傷翻身頻率

示範如何使用 zh-ebn-report pipeline 產出一份實證讀書報告。

## 題目

**糊題目**：「預防壓傷的翻身頻率」

**期待**：pipeline 的題目守門員會把它具體化為類似「臥床成人每 2 小時翻身與每 4 小時翻身預防壓傷之效果比較」。

## 執行指令

```bash
# 1. 確認 ANTHROPIC_API_KEY 已寫入 /Users/htlin/ebn-report/.env
# 2. 初始化
zh-ebn-report init \
    --type reading \
    --topic "預防壓傷的翻身頻率" \
    --ward "內科加護病房" \
    --level N2 \
    --scenario "ICU 多為長時間臥床個案，現行常規每 2 小時翻身；人力吃緊時常延遲。筆者想檢視是否有實證支持延長至 3-4 小時。" \
    --i-accept-audit-responsibility

# init 會回傳 run-id，例如 20260423-093021-a3f2c8

# 3. End-to-end 跑完 9 個 checkpoint
zh-ebn-report run <run-id>

# 或逐階段
zh-ebn-report topic    <run-id>
zh-ebn-report pico     <run-id>
zh-ebn-report search   <run-id>  # 若有 Cochrane/CINAHL RIS：--cochrane-ris X.ris
zh-ebn-report appraise <run-id>
zh-ebn-report synthesise <run-id>
zh-ebn-report write    <run-id>
zh-ebn-report check    <run-id>
zh-ebn-report render   <run-id>
```

## 產出

- `output/<run-id>/report-DRAFT.docx` — 主要草稿
- `output/<run-id>/state.json` — 結構化狀態
- `output/<run-id>/checkpoint_log.json` — HITL 決策紀錄
- `output/<run-id>/quarto/` — Quarto 中間檔
