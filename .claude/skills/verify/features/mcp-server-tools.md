# MCP 伺服器與防幻覺審計驗證 (MCP Server & Grounding Audit)

驗證標準 Model Context Protocol 伺服器之工具導出與審計行為。

## Sub-features

- `MCP-01`：`mcp_server.py` 導出 `search_kb`, `audit_grounding`, `ingest_kb`, `get_kb_stats`。
- `MCP-02`：`cli.py audit` 阻斷禁用指令並驗證來源標籤。

## How to get to it (user POV)

- 終端機指令：`.venv/bin/python cli.py audit --answer "..."`
- 智能體調用：透過 FastMCP stdio 通道調用工具

## Driving it with cli.py

```bash
.venv/bin/python cli.py audit --answer "請執行 satask stopnode [來源: sg248542.pdf, 第 10 頁]"
```

## Gotchas

- 未標註出處之回答會被 `audit_grounding` 標記為未通過並給予補全建議。
