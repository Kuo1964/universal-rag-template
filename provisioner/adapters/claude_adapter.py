"""
Claude Code / Claude Desktop 適配器 (Claude Adapter)
負責在目標專案目錄建立/更新 CLAUDE.md 與專案級 claude.json MCP 配置。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from provisioner.base import AgentInstallResult, BaseAgentAdapter, get_default_rag_guardrails_markdown


class ClaudeAdapter(BaseAgentAdapter):
    """Claude Code 與 Claude Desktop 專案配置適配器"""

    name: str = "claude"
    display_name: str = "Claude Code / Claude Desktop"

    def detect(self, target_dir: Path) -> bool:
        """偵測是否包含 CLAUDE.md 或 .claude 目錄"""
        return (target_dir / "CLAUDE.md").is_file() or (target_dir / ".claude").is_dir()

    def install(
        self,
        target_dir: Path,
        mcp_command: Optional[str] = None,
        mcp_args: Optional[List[str]] = None,
        force: bool = False,
    ) -> AgentInstallResult:
        result = AgentInstallResult(agent_name=self.name, target_dir=target_dir)

        cmd = mcp_command or "./scripts/run_mcp.sh"
        args = mcp_args if mcp_args is not None else []

        # 1. 產生或非破壞性更新根目錄 CLAUDE.md
        claude_md = target_dir / "CLAUDE.md"
        rag_section_header = "## Universal Dual-Track RAG Integration"
        rag_section_body = (
            f"\n\n{rag_section_header}\n\n"
            "本專案已整合通用雙軌 RAG 知識庫與 MCP 伺服器 (`universal-rag-kb`)：\n\n"
            "### 核心規範\n"
            "1. 面對技術規格、架構、指令、故障排查問題時，優先調用 `search_kb` 工具。\n"
            "2. 嚴格遵守來源標註：PDF 請標記 `[來源: <檔名.pdf>, 第 <頁碼> 頁]`，網頁請標記 `[來源: <URL>]`。\n"
            "3. 輸出前建議調用 `audit_grounding` 進行防幻覺與出處標籤審計。\n"
            "4. 新手冊 PDF 可放入 `raw_data/pdfs/`，網站可寫入 `raw_data/web_urls.txt`，並調用 `ingest_kb` 建庫。\n"
        )

        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8")
            if rag_section_header not in content:
                claude_md.write_text(content + rag_section_body, encoding="utf-8")
                result.updated_files.append(claude_md)
            else:
                result.skipped_files.append(claude_md)
        else:
            claude_md.write_text("# Claude Code Instructions\n" + rag_section_body, encoding="utf-8")
            result.created_files.append(claude_md)

        # 2. 寫入專案級 claude.json MCP 設定檔
        claude_json = target_dir / "claude.json"
        claude_mcp_config: Dict[str, Any] = {
            "mcpServers": {
                "universal-rag-kb": {
                    "command": cmd,
                    "args": args,
                }
            }
        }

        if claude_json.exists() and not force:
            try:
                existing = json.loads(claude_json.read_text(encoding="utf-8"))
                if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
                    existing["mcpServers"] = {}
                if existing.get("mcpServers", {}).get("universal-rag-kb") == claude_mcp_config["mcpServers"]["universal-rag-kb"]:
                    result.skipped_files.append(claude_json)
                else:
                    existing["mcpServers"]["universal-rag-kb"] = claude_mcp_config["mcpServers"]["universal-rag-kb"]
                    claude_json.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                    result.updated_files.append(claude_json)
            except Exception:
                claude_json.write_text(json.dumps(claude_mcp_config, ensure_ascii=False, indent=2), encoding="utf-8")
                result.updated_files.append(claude_json)
        else:
            claude_json.write_text(json.dumps(claude_mcp_config, ensure_ascii=False, indent=2), encoding="utf-8")
            result.created_files.append(claude_json)

        # 3. 同時在 .claude/ 目錄下放置備援 mcp.json（相容部分 Claude Code 版本）
        claude_dir = target_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        dot_claude_mcp = claude_dir / "mcp.json"
        if not dot_claude_mcp.exists() or force:
            dot_claude_mcp.write_text(json.dumps(claude_mcp_config, ensure_ascii=False, indent=2), encoding="utf-8")
            result.created_files.append(dot_claude_mcp)
        else:
            result.skipped_files.append(dot_claude_mcp)

        result.notes.append("Claude Code 使用者亦可直接於終端執行: claude mcp add universal-rag-kb -- " + cmd)
        return result
