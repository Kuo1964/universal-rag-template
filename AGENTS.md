# Agent Instructions

本專案為**通用型多產品雙軌 RAG 知識庫與 MCP 引擎**，支援跨電腦部署並可即時套用至 IBM Bob、Antigravity、Claude Desktop、Cursor 等任何支援 MCP 的 AI 智能體。

## 核心工作流指南

- 檢索知識庫請優先呼叫 `search_kb` MCP 工具（ChromaDB + SQLite FTS5 雙軌混合檢索）。
- 回答必須附帶來源標籤（`[來源: xxx.pdf, 第 N 頁]` 或 `[來源: https://...]`），並透過 `audit_grounding` 進行合規檢查。
- 當要導入新產品系列時，請執行 `.bob/skills/init-product-rag/SKILL.md`（或 `.agents/skills/init-product-rag/SKILL.md`）。

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues via the `gh` CLI (inferred from `git remote -v`). See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default canonical triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` and `docs/adr/` at the repo root). See `docs/agents/domain.md`.
