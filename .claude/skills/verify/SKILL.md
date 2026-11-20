---
name: verify
description: "驅動 Universal Dual-Track RAG 知識庫與跨 Agent 工具進行實機端對端驗證。當需要證明雙軌檢索、PDF/網站擷取、跨 Agent 一鍵配置或 MCP 工具真正可用時使用。"
---

# Universal Dual-Track RAG 專案驗證指南 (`verify`)

本技能為 AI 代理提供「檢驗環境 → 依 Feature Map 真實驅動 → 擷取客觀證據 → 驗證結束清理」的標準作業流程。

## Launch & Doctor

驗證各項工具與命令列之前，先執行健康檢查：

```bash
# 1. 執行核心單元與整合測試
.venv/bin/python -m unittest discover -s tests -v

# 2. 檢驗 MCP 與知識庫運行狀態
.venv/bin/python cli.py stats
```

- **就緒判定：** 所有 9 項測試案例皆回傳 `OK`，且 `cli.py stats` 成功輸出啟用產品與資料庫行數。

## Drive

依據 `features/` 目錄下的 Feature Map 逐項驅動：
- [雙軌檢索與同義詞擴展](features/dual-track-rag-search.md)
- [跨 Agent 一鍵配置引擎](features/multi-agent-provisioner.md)
- [PDF 與網站遞迴擷取入庫](features/pdf-and-web-ingestion.md)
- [MCP 伺服器與防幻覺審計工具](features/mcp-server-tools.md)

## Evidence

- 測試輸出日誌與 Exit Code。
- 臨時目錄中產生的 Agent 設定檔（`CLAUDE.md`, `.bob/mcp.json`, `AGENTS.md` 等）完整性。
- 檢索回傳結果中的 PDF 頁碼標籤與網頁原始 URL。

## Cleanup

- 刪除測試過程中建立的 `/tmp/verify-*` 暫存目錄。
- 確保未遺留未關閉的背景進程。
