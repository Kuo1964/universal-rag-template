"""
Cursor / Windsurf 適配器 (Cursor & Windsurf Adapter)
負責在目標專案目錄建立/更新 .cursor/mcp.json、.cursorrules 與 .windsurfrules
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from provisioner.base import AgentInstallResult, BaseAgentAdapter, get_default_rag_guardrails_markdown


class CursorAdapter(BaseAgentAdapter):
    """Cursor 與 Windsurf IDE 專案配置適配器"""

    name: str = "cursor"
    display_name: str = "Cursor / Windsurf"

    def detect(self, target_dir: Path) -> bool:
        """偵測是否包含 .cursor 目錄、.cursorrules 或 .windsurfrules"""
        return (
            (target_dir / ".cursor").is_dir()
            or (target_dir / ".cursorrules").is_file()
            or (target_dir / ".windsurfrules").is_file()
        )

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

        # 1. 寫入 .cursor/mcp.json
        cursor_dir = target_dir / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cursor_mcp = cursor_dir / "mcp.json"

        mcp_payload: Dict[str, Any] = {
            "mcpServers": {
                "universal-rag-kb": {
                    "command": cmd,
                    "args": args,
                }
            }
        }

        if cursor_mcp.exists() and not force:
            try:
                existing = json.loads(cursor_mcp.read_text(encoding="utf-8"))
                if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
                    existing["mcpServers"] = {}
                if existing.get("mcpServers", {}).get("universal-rag-kb") == mcp_payload["mcpServers"]["universal-rag-kb"]:
                    result.skipped_files.append(cursor_mcp)
                else:
                    existing["mcpServers"]["universal-rag-kb"] = mcp_payload["mcpServers"]["universal-rag-kb"]
                    cursor_mcp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                    result.updated_files.append(cursor_mcp)
            except Exception:
                cursor_mcp.write_text(json.dumps(mcp_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                result.updated_files.append(cursor_mcp)
        else:
            cursor_mcp.write_text(json.dumps(mcp_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            result.created_files.append(cursor_mcp)

        # 2. 寫入或更新 .cursorrules
        cursorrules = target_dir / ".cursorrules"
        rules_header = "## Universal Dual-Track RAG Integration"
        rules_content = (
            f"\n\n{rules_header}\n"
            "- 面對技術架構、指令、規格、故障排查問題時，優先調用 MCP 工具 `search_kb` 檢索官方手冊與網頁。\n"
            "- 嚴格標記來源標籤：PDF 請附 `[來源: <檔名.pdf>, 第 <頁碼> 頁]`，網頁請附 `[來源: <URL>]`。\n"
            "- 生成回答後，建議調用 `audit_grounding` 檢核指令白名單與出處完整性。\n"
        )
        if cursorrules.exists():
            content = cursorrules.read_text(encoding="utf-8")
            if rules_header not in content:
                cursorrules.write_text(content + rules_content, encoding="utf-8")
                result.updated_files.append(cursorrules)
            else:
                result.skipped_files.append(cursorrules)
        else:
            cursorrules.write_text("# Cursor Rules\n" + rules_content, encoding="utf-8")
            result.created_files.append(cursorrules)

        # 3. 亦同步相容 .windsurfrules (Windsurf IDE)
        windsurfrules = target_dir / ".windsurfrules"
        if not windsurfrules.exists() or force:
            windsurfrules.write_text("# Windsurf Rules\n" + rules_content, encoding="utf-8")
            result.created_files.append(windsurfrules)
        else:
            result.skipped_files.append(windsurfrules)

        result.notes.append("Cursor 與 Windsurf 會自動從 .cursor/mcp.json 與 rules 載入工具與準則。")
        return result
