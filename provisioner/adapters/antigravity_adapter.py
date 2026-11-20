"""
Google Antigravity 適配器 (Antigravity Adapter)
負責在目標專案目錄建立/更新 .agents/、AGENTS.md 與 mcp_config.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from provisioner.base import AgentInstallResult, BaseAgentAdapter, get_default_rag_guardrails_markdown


class AntigravityAdapter(BaseAgentAdapter):
    """Google Antigravity 專案配置適配器"""

    name: str = "antigravity"
    display_name: str = "Google Antigravity"

    def detect(self, target_dir: Path) -> bool:
        """偵測是否包含 .agents 目錄或 mcp_config.json"""
        return (target_dir / ".agents").is_dir() or (target_dir / "mcp_config.json").is_file()

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

        agents_dir = target_dir / ".agents"
        rules_dir = agents_dir / "rules"
        skills_dir = agents_dir / "skills"

        for d in [agents_dir, rules_dir, skills_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 1. 產生或更新 mcp_config.json
        mcp_file = target_dir / "mcp_config.json"
        mcp_payload: Dict[str, Any] = {
            "mcpServers": {
                "universal-rag-kb": {
                    "command": cmd,
                    "args": args,
                }
            }
        }

        if mcp_file.exists() and not force:
            try:
                existing = json.loads(mcp_file.read_text(encoding="utf-8"))
                if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
                    existing["mcpServers"] = {}
                if existing.get("mcpServers", {}).get("universal-rag-kb") == mcp_payload["mcpServers"]["universal-rag-kb"]:
                    result.skipped_files.append(mcp_file)
                else:
                    existing["mcpServers"]["universal-rag-kb"] = mcp_payload["mcpServers"]["universal-rag-kb"]
                    mcp_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                    result.updated_files.append(mcp_file)
            except Exception:
                mcp_file.write_text(json.dumps(mcp_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                result.updated_files.append(mcp_file)
        else:
            mcp_file.write_text(json.dumps(mcp_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            result.created_files.append(mcp_file)

        # 2. 寫入 .agents/rules/rag-grounding-guardrails.md
        guardrail_file = rules_dir / "rag-grounding-guardrails.md"
        guardrail_content = (
            "---\n"
            "description: 通用雙軌 RAG 知識庫檢索、出處標註與防幻覺稽核強制規則\n"
            "globs: '**/*'\n"
            "alwaysApply: true\n"
            "---\n\n" + get_default_rag_guardrails_markdown()
        )
        if not guardrail_file.exists() or force:
            guardrail_file.write_text(guardrail_content, encoding="utf-8")
            result.created_files.append(guardrail_file)
        else:
            result.skipped_files.append(guardrail_file)

        # 3. 產生或更新根目錄 AGENTS.md
        agents_md = target_dir / "AGENTS.md"
        rag_section_header = "## Universal Dual-Track RAG Integration"
        rag_section_body = (
            f"\n\n{rag_section_header}\n\n"
            "本專案已整合通用雙軌 RAG 知識庫與 MCP 伺服器 (`universal-rag-kb`)：\n\n"
            "### 核心規範\n"
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

        result.notes.append("Antigravity 開啟本專案時會自動從 mcp_config.json 與 .agents/ 載入工具與規範。")
        return result
