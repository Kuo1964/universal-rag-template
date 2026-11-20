"""
跨智能體配置管理器 (Multi-Agent Provisioner Manager)
整合並調度各 Agent 適配器，提供統一的自動偵測、一鍵安裝與報告輸出。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from provisioner.adapters import (
    AntigravityAdapter,
    BobAdapter,
    ClaudeAdapter,
    CodexAdapter,
    CursorAdapter,
)
from provisioner.base import AgentInstallResult, BaseAgentAdapter

_REGISTERED_ADAPTERS: Dict[str, BaseAgentAdapter] = {
    "bob": BobAdapter(),
    "claude": ClaudeAdapter(),
    "codex": CodexAdapter(),
    "antigravity": AntigravityAdapter(),
    "cursor": CursorAdapter(),
}


def list_supported_agents() -> List[str]:
    """列出所有受支援的 AI 代理名稱"""
    return list(_REGISTERED_ADAPTERS.keys())


def get_adapter(name: str) -> Optional[BaseAgentAdapter]:
    """依名稱取得特定適配器"""
    return _REGISTERED_ADAPTERS.get(name.strip().lower())


def detect_active_agents(target_dir: Path) -> List[str]:
    """自動偵測目標目錄中存在哪些 AI 代理的特徵檔案"""
    detected: List[str] = []
    for name, adapter in _REGISTERED_ADAPTERS.items():
        if adapter.detect(target_dir):
            detected.append(name)
    return detected


def install_for_agents(
    target_dir: Path,
    agent_choice: str = "all",
    mcp_command: Optional[str] = None,
    mcp_args: Optional[List[str]] = None,
    force: bool = False,
) -> List[AgentInstallResult]:
    """
    一鍵為指定的 AI 代理（或所有支援代理）安裝 MCP 配置、規則手冊與技能檔案。

    Args:
        target_dir: 要配置的專案目錄
        agent_choice: 'all' | 'bob' | 'claude' | 'codex' | 'antigravity' | 'cursor' | 'auto'
        mcp_command: 自訂 MCP 啟動指令（預設自動推導相對路徑）
        mcp_args: 自訂 MCP 啟動參數
        force: 是否強制覆蓋既有檔案

    Returns:
        各平台的安裝回報清單
    """
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    choice = (agent_choice or "all").strip().lower()
    selected_names: List[str] = []

    if choice == "all":
        selected_names = list(_REGISTERED_ADAPTERS.keys())
    elif choice == "auto":
        selected_names = detect_active_agents(target_dir)
        if not selected_names:
            # 若無特定特徵，預設為所有主流代理皆配置
            selected_names = list(_REGISTERED_ADAPTERS.keys())
    else:
        # 支援逗號分隔多選，如 "claude,cursor"
        for part in choice.split(","):
            clean = part.strip().lower()
            if clean in _REGISTERED_ADAPTERS:
                selected_names.append(clean)
            elif clean:
                print(f"[警告] 不支援的代理名稱: {clean}，已略過。支援清單: {list_supported_agents()}")

    results: List[AgentInstallResult] = []
    for name in selected_names:
        adapter = _REGISTERED_ADAPTERS[name]
        res = adapter.install(
            target_dir=target_dir,
            mcp_command=mcp_command,
            mcp_args=mcp_args,
            force=force,
        )
        results.append(res)

    return results
