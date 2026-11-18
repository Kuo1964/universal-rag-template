---
description: 通用雙軌 RAG 知識庫檢索、出處標註與防幻覺稽核強制規則
globs: "**/*"
alwaysApply: true
---

# 通用雙軌 RAG 檢索與防幻覺防護欄 (Universal RAG Guardrails)

當回答任何屬於本專案知識庫領域的技術問題時，AI 智能體必須嚴格遵守以下工作規範：

## 1. 先檢索後作答 (Retrieve Before Answering)
* 面對產品架構、規格參數、指令語法、故障碼或設定步驟提問時，**必須先呼叫 `search_kb` MCP 工具**執行雙軌檢索（ChromaDB 語意 + SQLite FTS5 BM25）。
* 若使用者提供新的產品手冊 PDF 或官方文件網址，可透過 `ingest_kb` 工具將資料納入知識庫後再進行問答。

## 2. 強制出處標註 (Mandatory Grounded Citations)
* 每一條核心技術論點、硬體規格或指令操作步驟，**必須在句尾明確標註官方來源**：
  * PDF 來源格式：`[來源: <檔名.pdf>, 第 <頁碼> 頁]`
  * 網站來源格式：`[來源: <原始完整 URL>]`
* 若檢索結果中未包含相關記載，必須誠實宣告「知識庫中未記載」，嚴禁憑空猜測或捏造指令參數。

## 3. 輸出前自我稽核 (Pre-Response Grounding Audit)
* 生成技術回覆草稿後，應呼叫 `audit_grounding` MCP 工具驗證草稿是否違反當前產品 Profile 的禁用/廢棄指令清單，並確認來源標註完整無誤。

## 4. 可攜性與環境隔離規範
* 禁止在專案檔案或配置中寫死本機使用者絕對路徑。
* 檢索程式碼或除錯時，禁止掃描 `vector_db/`、`raw_data/`、`*.sqlite3` 與 `.venv/` 等大型資料與二進位目錄。
