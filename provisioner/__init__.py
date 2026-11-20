"""
通用多智能體配置適配器模組 (Multi-Agent Provisioner)
支援一鍵為 Claude Code, OpenAI Codex, Antigravity, IBM Bob, Cursor/Windsurf 產生並同步 MCP 配置與規則。
"""

from provisioner.base import AgentInstallResult, BaseAgentAdapter
from provisioner.manager import (
    detect_active_agents,
    get_adapter,
    install_for_agents,
    list_supported_agents,
)

__all__ = [
    "AgentInstallResult",
    "BaseAgentAdapter",
    "detect_active_agents",
    "get_adapter",
    "install_for_agents",
    "list_supported_agents",
]
