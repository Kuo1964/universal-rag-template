"""
IBM Bob 適配器 (IBM Bob Provisioner Adapter)
負責在目標專案目錄建立/更新 .bob/mcp.json、.bob/rules/ 與 .bob/skills/
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from provisioner.base import AgentInstallResult, BaseAgentAdapter, get_default_rag_guardrails_markdown


class BobAdapter(BaseAgentAdapter):
    """IBM Bob (Project Bob) 專案配置適配器"""

    name: str = "bob"
    display_name: str = "IBM Bob"

    def detect(self, target_dir: Path) -> bool:
        """偵測是否包含 .bob/ 目錄"""
        return (target_dir / ".bob").is_dir()

    def install(
        self,
        target_dir: Path,
        mcp_command: Optional[str] = None,
        mcp_args: Optional[List[str]] = None,
        force: bool = False,
    ) -> AgentInstallResult:
        result = AgentInstallResult(agent_name=self.name, target_dir=target_dir)

        bob_dir = target_dir / ".bob"
        rules_dir = bob_dir / "rules"
        skills_dir = bob_dir / "skills"

        for d in [bob_dir, rules_dir, skills_dir]:
            d.mkdir(parents=True, exist_ok=True)

        cmd = mcp_command or "./scripts/run_mcp.sh"
        args = mcp_args if mcp_args is not None else []

        # 1. 寫入或更新 .bob/mcp.json
        mcp_file = bob_dir / "mcp.json"
        mcp_payload: Dict[str, Any] = {
            "mcpServers": {
                "universal-rag-kb": {
                    "command": cmd,
                    "args": args,
                    "disabled": False,
                    "alwaysAllow": [
                        "search_kb",
                        "audit_grounding",
                        "get_kb_stats",
                    ],
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

        # 2. 寫入 .bob/rules/rag-grounding-guardrails.md
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

        # 3. 寫入 .bob/rules/product-domain-rules.md
        domain_file = rules_dir / "product-domain-rules.md"
        if not domain_file.exists() or force:
            domain_file.write_text(
                "---\n"
                "description: 產品領域邊界與規範（依據 profiles/<ACTIVE_PROFILE>.yaml 維護）\n"
                "globs: '**/*'\n"
                "alwaysApply: true\n"
                "---\n\n"
                "# 產品領域防護規則\n\n"
                "回答本產品技術問題時，必須依據 `search_kb` 回傳之官方文檔為準據，並附帶真實來源標註。\n",
                encoding="utf-8",
            )
            result.created_files.append(domain_file)
        else:
            result.skipped_files.append(domain_file)

        # 4. 初始化 .bob/skills/ 目錄與技能指南
        init_skill_dir = skills_dir / "init-product-rag"
        init_skill_dir.mkdir(parents=True, exist_ok=True)
        init_skill_file = init_skill_dir / "SKILL.md"
        if not init_skill_file.exists() or force:
            init_skill_file.write_text(
                "---\n"
                "name: init-product-rag\n"
                "description: 掃描 raw_data/pdfs/ 與網址，自動提煉產品領域規則並建立雙軌知識庫。\n"
                "---\n\n"
                "# 客製化新產品 RAG 知識庫引導技能\n\n"
                "1. 檢視 `raw_data/pdfs/` 檔案與 `raw_data/web_urls.txt` 網址。\n"
                "2. 建立專屬 `profiles/<product>.yaml`。\n"
                "3. 調用 `ingest_kb` 建立雙軌索引。\n",
                encoding="utf-8",
            )
            result.created_files.append(init_skill_file)

        result.notes.append("IBM Bob 開啟本專案時會自動載入 .bob/mcp.json，無需額外手動配置。")
        return result
