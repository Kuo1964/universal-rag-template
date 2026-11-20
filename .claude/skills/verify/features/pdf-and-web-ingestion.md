# PDF 與網站遞迴擷取入庫驗證 (PDF & Web Ingestion)

驗證 `ingest.py` 增量建庫管道，涵蓋 PDF 手冊解析與動態 SPA 網站同網域遞迴爬取。

## Sub-features

- `INGEST-01`：`cli.py ingest --mode pdf` 增量掃描 `raw_data/pdfs/`。
- `INGEST-02`：`cli.py ingest --mode web --add-url <url>` 動態抓取網站並遞迴解析子頁面。
- `INGEST-03`：自動排除導覽列雜訊並轉換為乾淨 Markdown Chunks。

## How to get to it (user POV)

- 指令：`.venv/bin/python cli.py ingest --mode all`

## Driving it with cli.py

```bash
.venv/bin/python cli.py ingest --mode web --add-url https://example.com --max-pages 2
```

## Gotchas

- 大型 PDF 解析需短暫時間，若未安裝 Playwright 則自動降級為純靜態 HTTP 解析。
