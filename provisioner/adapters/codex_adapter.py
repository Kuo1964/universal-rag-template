"""
OpenAI Codex / 通用 Coding Agent 適配器 (Codex Adapter)
負責在目標專案目錄建立/更新 AGENTS.md 與 codex.json MCP 配置。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from provisioner.base import AgentInstallResult, BaseAgentAdapter


class CodexAdapter(BaseAgentAdapter):
    """OpenAI Codex 與通用跨平台 Agent 專案配置適配器"""

    name: str = "codex"
    display_name: str = "OpenAI Codex"

    def detect(self, target_dir: Path) -> bool:
        """偵測是否包含 codex.json 或 AGENTS.md"""
        return (target_dir / "codex.json").is_file() or (target_dir / "AGENTS.md").is_file()

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

        # 1. 產生或非破壞性更新 AGENTS.md
        agents_md = target_dir / "AGENTS.md"
        rag_section_header = "## Universal Dual-Track RAG Integration"
        rag_section_body = (
            f"\n\n{rag_section_header}\n\n"
            "本專案已整合通用雙軌 RAG 知識庫與 MCP 伺服器 (`universal-rag-kb`)：\n\n"
            "### 智能體操作守則\n"
            "1. 面對技術規格、架構、指令、故障排查問題時，優先調用 `search_kb` 工具。\n"
            "2. 嚴格遵守出處標註（PDF 頁碼或原始網頁 URL）。\n"
            "3. 輸出前建議調用 `audit_grounding` 進行防幻覺檢核。\n"
            "4. 新增 PDF 請放入 `raw_data/pdfs/`，網址放入 `raw_data/web_urls.txt`，並調用 `ingest_kb`。\n"
        )

        if agents_md.exists():
            content = agents_md.read_text(encoding="utf-8")
            if rag_section_header not in content:
                agents_md.write_text(content + rag_section_body, encoding="utf-8")
                result.updated_files.append(agents_md)
            else:
                result.skipped_files.append(agents_md)
        else:
            agents_md.write_text("# Agent Instructions\n" + rag_section_body, encoding="utf-8")
            result.created_files.append(agents_md)

        # 2. 寫入 codex.json MCP 設定檔
        codex_json = target_dir / "codex.json"
        codex_payload: Dict[str, Any] = {
            "mcpServers": {
                "universal-rag-kb": {
                    "command": cmd,
                    "args": args,
                }
            }
        }

        if codex_json.exists() and not force:
            try:
                existing = json.loads(codex_json.read_text(encoding="utf-8"))
                if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
                    existing["mcpServers"] = {}
                if existing.get("mcpServers", {}).get("universal-rag-kb") == codex_payload["mcpServers"]["universal-rag-kb"]:
                    result.skipped_files.append(codex_json)
                else:
                    existing["mcpServers"]["universal-rag-kb"] = codex_payload["mcpServers"]["universal-rag-kb"]
                    codex_json.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                    result.updated_files.append(codex_json)
            except Exception:
                codex_json.write_text(json.dumps(codex_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                result.updated_files.append(codex_json)
        else:
            codex_json.write_text(json.dumps(codex_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            result.created_files.append(codex_json)

        result.notes.append("Codex 執行時會自動從 AGENTS.md 載入知識庫操作守則。")
        return result
