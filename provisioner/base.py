"""
通用多智能體配置適配器 (Multi-Agent Provisioner) - 抽象基底與共用資料結構
定義跨 AI 智能體（Claude Code, Codex, Antigravity, IBM Bob, Cursor 等）的擴充協定。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class AgentInstallResult:
    """各平台配置結果回報"""

    agent_name: str
    target_dir: Path
    created_files: List[Path] = field(default_factory=list)
    updated_files: List[Path] = field(default_factory=list)
    skipped_files: List[Path] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    success: bool = True

    def summary(self) -> str:
        """回傳簡明繁體中文摘要"""
        status_icon = "✅" if self.success else "❌"
        lines = [f"{status_icon} [{self.agent_name.upper()}] 安裝於 {self.target_dir}"]
        if self.created_files:
            lines.append(f"  ├─ 新建檔案 ({len(self.created_files)}): " + ", ".join(f.name for f in self.created_files))
        if self.updated_files:
            lines.append(f"  ├─ 更新檔案 ({len(self.updated_files)}): " + ", ".join(f.name for f in self.updated_files))
        if self.notes:
            for note in self.notes:
                lines.append(f"  └─ 💡 {note}")
        return "\n".join(lines)


class BaseAgentAdapter(ABC):
    """跨 AI 智能體配置適配器基底類別"""

    name: str = "base"
    display_name: str = "Base Agent"

    @abstractmethod
    def detect(self, target_dir: Path) -> bool:
        """檢查目標目錄或環境是否屬於此 Agent 的運作環境"""
        ...

    @abstractmethod
    def install(
        self,
        target_dir: Path,
        mcp_command: Optional[str] = None,
        mcp_args: Optional[List[str]] = None,
        force: bool = False,
    ) -> AgentInstallResult:
        """為目標專案目錄注入該 Agent 所需的 MCP 配置、規則手冊與技能檔案"""
        ...


def get_default_rag_guardrails_markdown() -> str:
    """提供標準通用雙軌 RAG 規範 Markdown 內容"""
    return """# 通用雙軌 RAG 知識庫規範與防幻覺防護欄 (Universal RAG Guardrails)

當回答任何涉及產品架構、技術規格、設定指令、故障排除或最佳實踐的提問時，AI 代理必須強制遵守以下準則：

## 1. 先檢索後作答 (Retrieve Before Answering)
* 面對具體技術問題時，**必須先調用 `search_kb` 工具**執行雙軌混合檢索（ChromaDB 語意向量 + SQLite FTS5 BM25 全文檢索）。
* 若知識庫無資料，可引導使用者放置 PDF 或透過 `ingest_kb` 擷取官方網站。

## 2. 嚴格強制出處標註 (Mandatory Source Citations)
* 每一條核心架構論點、作業步驟與指令，**必須在文末標註官方真實來源**：
  * PDF 手冊出處格式：`[來源: <檔名.pdf>, 第 <頁碼> 頁]`
  * 網站文件出處格式：`[來源: <原始完整網址 URL>]`
* 若檢索結果未記載該功能或參數，必須誠實回覆「官方知識庫中未記載」，嚴格禁止憑空猜測或偽造未經驗證的假指令。

## 3. 輸出前防幻覺審計 (Pre-Response Grounding Audit)
* 生成最終技術回覆前，建議調用 `audit_grounding` 工具對回答草稿進行確定性檢核（檢查是否使用禁用/廢棄指令，以及是否具備有效來源標籤）。
"""
