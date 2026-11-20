# Universal Dual-Track RAG 功能驗證地圖

本目錄記載通用雙軌 RAG 系統的所有使用者與代理接觸介面，驗證時請依對應功能檔案依序操作：

## 功能清單

1. [跨 Agent 一鍵配置引擎 (`provisioner`)](./multi-agent-provisioner.md)：驗證 `cli.py install --agent all` 是否能為 Claude Code、Bob、Codex、Antigravity、Cursor 自動產生正確無誤的配置。
2. [雙軌混合檢索 (`vector_store`)](./dual-track-rag-search.md)：驗證 ChromaDB 語意向量 + SQLite FTS5 BM25 是否能精確命中 PDF 內容與網頁內容。
3. [PDF 與網站動態爬蟲建庫 (`ingest`)](./pdf-and-web-ingestion.md)：驗證增量建庫、網址遞迴擷取與 HTML 清理。
4. [MCP 伺服器與防幻覺審計 (`mcp_server`)](./mcp-server-tools.md)：驗證 `search_kb`、`audit_grounding`、`ingest_kb` 工具行為。
