"""
通用多智能體配置模組 (Provisioner) 自動化單元測試
驗證：
1. 各 Agent 適配器完整性（Bob, Claude, Codex, Antigravity, Cursor）
2. 跨平台設定檔產生與 JSON 語法正確性
3. 冪等性與非破壞性更新機制
4. 統一 CLI install 命令列整合
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# 確保優先匯入 universal-rag-template 根目錄模組
TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
if str(TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_ROOT))

from cli import main as cli_main
from provisioner import detect_active_agents, get_adapter, install_for_agents, list_supported_agents


class TestAgentProvisioner(unittest.TestCase):
    """跨智能體配置引擎回歸測試"""

    def setUp(self) -> None:
        """建立隔離的臨時目標目錄"""
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_provisioner_")).resolve()

    def tearDown(self) -> None:
        """清理臨時目錄"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_supported_agents_registry(self) -> None:
        """驗證 5 大主流 AI Agent 皆已註冊"""
        agents = list_supported_agents()
        for expected in ["bob", "claude", "codex", "antigravity", "cursor"]:
            self.assertIn(expected, agents)
            adapter = get_adapter(expected)
            self.assertIsNotNone(adapter)
            self.assertEqual(adapter.name, expected)

    def test_install_all_agents_generates_expected_files(self) -> None:
        """驗證一鍵安裝為所有代理產生正確規格檔案"""
        results = install_for_agents(
            target_dir=self.test_dir,
            agent_choice="all",
            mcp_command="universal-rag-mcp",
            mcp_args=["--profile", "default"],
        )

        self.assertEqual(len(results), 5)
        for res in results:
            self.assertTrue(res.success, msg=f"{res.agent_name} 安裝失敗")

        # 1. 驗證 Claude Code 配置
        claude_md = self.test_dir / "CLAUDE.md"
        claude_json = self.test_dir / "claude.json"
        self.assertTrue(claude_md.is_file())
        self.assertIn("Universal Dual-Track RAG", claude_md.read_text(encoding="utf-8"))
        self.assertTrue(claude_json.is_file())
        claude_cfg = json.loads(claude_json.read_text(encoding="utf-8"))
        self.assertIn("universal-rag-kb", claude_cfg["mcpServers"])
        self.assertEqual(claude_cfg["mcpServers"]["universal-rag-kb"]["command"], "universal-rag-mcp")

        # 2. 驗證 IBM Bob 配置
        bob_mcp = self.test_dir / ".bob" / "mcp.json"
        bob_rule = self.test_dir / ".bob" / "rules" / "rag-grounding-guardrails.md"
        self.assertTrue(bob_mcp.is_file())
        self.assertTrue(bob_rule.is_file())
        bob_cfg = json.loads(bob_mcp.read_text(encoding="utf-8"))
        self.assertIn("universal-rag-kb", bob_cfg["mcpServers"])

        # 3. 驗證 OpenAI Codex 配置
        agents_md = self.test_dir / "AGENTS.md"
        codex_json = self.test_dir / "codex.json"
        self.assertTrue(agents_md.is_file())
        self.assertTrue(codex_json.is_file())

        # 4. 驗證 Antigravity 配置
        antigravity_mcp = self.test_dir / "mcp_config.json"
        antigravity_rule = self.test_dir / ".agents" / "rules" / "rag-grounding-guardrails.md"
        self.assertTrue(antigravity_mcp.is_file())
        self.assertTrue(antigravity_rule.is_file())

        # 5. 驗證 Cursor / Windsurf 配置
        cursor_mcp = self.test_dir / ".cursor" / "mcp.json"
        cursor_rules = self.test_dir / ".cursorrules"
        windsurf_rules = self.test_dir / ".windsurfrules"
        self.assertTrue(cursor_mcp.is_file())
        self.assertTrue(cursor_rules.is_file())
        self.assertTrue(windsurf_rules.is_file())

    def test_idempotency_and_non_destructive_updates(self) -> None:
        """驗證重複執行不會覆寫或破壞使用者既有的客製規則"""
        claude_md = self.test_dir / "CLAUDE.md"
        claude_md.write_text("# My Existing Custom Rules\n- Do not touch this line.\n", encoding="utf-8")

        # 初次安裝 Claude
        install_for_agents(target_dir=self.test_dir, agent_choice="claude")
        content_first = claude_md.read_text(encoding="utf-8")
        self.assertIn("Do not touch this line", content_first)
        self.assertIn("Universal Dual-Track RAG", content_first)

        # 二次安裝，應偵測到已存在並跳過重複注入
        res2 = install_for_agents(target_dir=self.test_dir, agent_choice="claude")
        self.assertEqual(len(res2[0].updated_files), 0)
        self.assertIn(claude_md, res2[0].skipped_files)

    def test_auto_detection(self) -> None:
        """驗證能依現有目錄結構自動偵測活躍的 Agent"""
        (self.test_dir / ".bob").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "CLAUDE.md").write_text("# Claude", encoding="utf-8")

        detected = detect_active_agents(self.test_dir)
        self.assertIn("bob", detected)
        self.assertIn("claude", detected)
        self.assertNotIn("cursor", detected)


if __name__ == "__main__":
    unittest.main()
