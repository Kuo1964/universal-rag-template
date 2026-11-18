---
description: 產品領域邊界與 CLI/術語防護規則（依據目前啟用之 profiles/<ACTIVE_PROFILE>.yaml 動態維護）
globs: "**/*"
alwaysApply: true
---

# 產品領域防護規則 (Product Domain Rules)

本檔案定義目前啟用產品線的領域邊界、同義詞與指令規範，會隨著 `profiles/<ACTIVE_PROFILE>.yaml` 切換或透過 `init-product-rag` 技能自動更新。

## 預設通用模式 (`profiles/default.yaml`)
* **適用範圍**：任何放入 `raw_data/pdfs/` 的產品手冊與 `raw_data/web_urls.txt` 中的技術文件網站。
* **網站爬取策略**：預設採同網域且同路徑前綴遞迴擷取（無特定產品字詞限制），並自動清理導覽列轉為乾淨 Markdown 寫入雙軌索引。
* **指令與規格約束**：回答任何產品指令或架構邊界時，必須以 `search_kb` 檢索回傳之文檔與當前 `profiles/<ACTIVE_PROFILE>.yaml` 所列之 `domain_guardrails` 與 `cli_validation` 為最高準據。
* **切換新產品提示**：若要客製化專屬產品線，請執行 `init-product-rag` 技能建立新的 YAML 設定檔並於 `.env` 更新 `ACTIVE_PROFILE`。
