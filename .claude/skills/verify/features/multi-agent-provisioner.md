# 跨 Agent 一鍵配置引擎驗證 (Multi-Agent Provisioner)

驗證 `cli.py install` 是否能自動為 Claude Code, OpenAI Codex, Antigravity, IBM Bob, Cursor/Windsurf 產生並同步專屬配置。

## Sub-features

- `PROV-01`：`--agent all` 在目標目錄產生 5 大平台的設定檔。
- `PROV-02`：`--agent <name>` 針對特定平台精準配置。
- `PROV-03`：非破壞性更新與冪等性（重複執行不破壞使用者既有設定）。

## How to get to it (user POV)

- 指令：`.venv/bin/python cli.py install --agent all --dir <path>`

## Driving it with cli.py

```bash
TEST_DIR=$(mktemp -d /tmp/verify-universal-XXXXXX)
.venv/bin/python cli.py install --agent all --dir "$TEST_DIR"
test -f "$TEST_DIR/CLAUDE.md" && echo "Claude: OK"
test -f "$TEST_DIR/.bob/mcp.json" && echo "Bob: OK"
test -f "$TEST_DIR/AGENTS.md" && echo "Codex: OK"
test -f "$TEST_DIR/mcp_config.json" && echo "Antigravity: OK"
test -f "$TEST_DIR/.cursor/mcp.json" && echo "Cursor: OK"
rm -rf "$TEST_DIR"
```

## Gotchas

- macOS 的 `/tmp` 為 `/private/tmp` 的符號連結，路徑比對時需注意符號連結解析。
