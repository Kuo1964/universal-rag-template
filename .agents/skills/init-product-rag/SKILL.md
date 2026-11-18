---
name: init-product-rag
description: 引導智能體掃描使用者放入的新產品 PDF 手冊或官方文件網站，自動提煉產品專有名詞、同義詞、CLI 白名單/禁用詞與爬蟲規則，生成客製化 profiles/<product>.yaml 與知識庫索引。
---

# 客製化新產品 RAG 知識庫引導技能 (Init Product RAG)

當使用者希望將本專案應用到「新的產品系列」（包含新 PDF 與新技術網站）時，請依序執行以下 4 個步驟完成全自動客製化：

## 步驟 1：盤點資料來源（PDF + 網站）
1. 檢查 `raw_data/pdfs/` 目錄下有哪些新產品 PDF 檔案。
2. 檢查 `raw_data/web_urls.txt` 是否已填入產品官方文件網站，或詢問使用者是否要提供官方文件入口網址。
3. 確認產品線代號（`product_id`，小寫英文與底線）與產品名稱（`product_name`）。

## 步驟 2：抽樣分析領域語彙與結構特徵
1. 若有 PDF，使用 `.venv/bin/python` 透過 `fitz`（PyMuPDF）抽樣讀取前幾頁目錄、關鍵章節與 CLI/術語表。
2. 若為技術網站，先呼叫 `ingest_kb(mode="web", target_url="<網址>", max_depth=1, max_pages=10)` 或以 Python 檢查頁面結構與 URL 路徑前綴。
3. 提煉以下關鍵領域資產（參考 `profiles/examples/ibm_flashsystem.yaml` 結構）：
   * `expert_persona`：該產品原廠資深技術顧問的人設描述。
   * `synonyms`：常見縮寫與同義詞擴展表（提升雙軌檢索召回率）。
   * `cli_validation`：若產品有官方 CLI，整理常見標準指令 `allowlist` 及常見廢棄/誤用指令 `blocklist`。
   * `domain_guardrails`：產品硬體/軟體物理邊界與強制注意事項。
   * `crawler`：確認目標網站是否需限定 `url_allow_patterns` 或關閉 `same_path_prefix`。

## 步驟 3：產出產品設定檔並同步防護規則
1. 將提煉結果寫入 `profiles/<product_id>.yaml`。
2. 同步更新 `.bob/rules/product-domain-rules.md` 與 `.agents/rules/product-domain-rules.md`，納入該產品的領域邊界摘要。
3. 更新 `.env`（若不存在則自 `.env.example` 複製）中的 `ACTIVE_PROFILE=<product_id>`。

## 步驟 4：建立雙軌知識庫並執行首輪檢索驗證
1. 呼叫 `ingest_kb(mode="all")` MCP 工具（或執行 `.venv/bin/python ingest.py --mode all`），同步完成 PDF 與網站的 ChromaDB + SQLite FTS5 雙軌索引。
2. 呼叫 `get_kb_stats` 確認已索引 PDF 數、網頁數與向量筆數大於 0。
3. 執行一題代表性技術問題測試 `search_kb` ➔ 生成回答 ➔ `audit_grounding` 閉環，確認 `passed: true` 後回報使用者完成客製化！
