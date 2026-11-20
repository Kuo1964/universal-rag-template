# 雙軌混合檢索驗證 (Dual-Track RAG Search)

驗證 ChromaDB 語意向量檢索與 SQLite FTS5 BM25 全文檢索在同義詞擴展下的融合排序行為。

## Sub-features

- `SEARCH-01`：終端執行 `cli.py search "<關鍵詞>"` 回傳結構化結果。
- `SEARCH-02`：Profile 同義詞自動擴展（提升縮寫與專有名詞召回率）。
- `SEARCH-03`：結果標籤精確顯示 PDF 來源頁碼或原始網頁 URL。

## How to get to it (user POV)

- 終端機指令：`.venv/bin/python cli.py search "<query>"`
- MCP 工具：調用 `search_kb(query="...", top_k=6)`

## Driving it with cli.py

```bash
.venv/bin/python cli.py search "叢集初始化與高可用"
```

**可觀察結果：**
Exit Code 0，回傳結果片段與信心分數。

## Gotchas

- 知識庫若尚未匯入任何文件或爬取網址，會提示請先執行建庫。
