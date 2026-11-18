"""
通用型多產品雙軌 RAG 引擎 - 原廠引述與防幻覺審計器 (Grounding Auditor)
動態讀取當前 Product Profile 的 CLI 白名單/禁用詞表與引述規範，對回答進行確定性檢核。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from profile_loader import load_active_profile


class GroundingAuditor:
    """產品無關的通用引述與指令合規審計器"""

    def __init__(self, profile_name: Optional[str] = None) -> None:
        self.profile: Dict[str, Any] = load_active_profile(profile_name)
        self.product_id: str = str(self.profile.get("product_id", "default_product"))
        self.cli_cfg: Dict[str, Any] = self.profile.get("cli_validation") or {}
        self.cli_enabled: bool = bool(self.cli_cfg.get("enabled", False))
        self.allowlist: Set[str] = {str(cmd).strip().lower() for cmd in (self.cli_cfg.get("allowlist") or []) if cmd}
        self.blocklist: Dict[str, Dict[str, str]] = {
            str(cmd).strip().lower(): info
            for cmd, info in (self.cli_cfg.get("blocklist") or {}).items()
            if cmd and isinstance(info, dict)
        }

    @staticmethod
    def extract_candidate_commands(text: str) -> List[str]:
        """從回覆文本中的行內程式碼或程式碼區塊萃取出疑似 CLI 指令首詞"""
        candidates: List[str] = []
        seen: Set[str] = set()

        # 萃取 `command ...` 或 ```bash\ncommand ...\n``` 中的指令
        code_spans = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", text, flags=re.DOTALL)
        inline_spans = re.findall(r"`([^`\n]+)`", text)

        for block in code_spans:
            for line in block.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                first_tok = stripped.split()[0].lstrip("$").strip()
                if re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{2,}$", first_tok):
                    low = first_tok.lower()
                    if low not in seen:
                        seen.add(low)
                        candidates.append(low)

        for inline in inline_spans:
            stripped = inline.strip()
            if not stripped:
                continue
            first_tok = stripped.split()[0].lstrip("$").strip()
            if re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{2,}$", first_tok):
                low = first_tok.lower()
                if low not in seen:
                    seen.add(low)
                    candidates.append(low)

        return candidates

    @staticmethod
    def check_citations(answer_text: str) -> Dict[str, Any]:
        """檢查回覆是否包含合法的 PDF 頁碼出處或網頁 URL 出處"""
        pdf_citations = re.findall(
            r"\[來源:\s*[^,\]]+\.pdf[^\]]*第\s*\d+\s*頁\]|第\s*\d+\s*頁",
            answer_text,
            flags=re.IGNORECASE,
        )
        web_citations = re.findall(r"https?://[^\s\)\]>\"']+", answer_text, flags=re.IGNORECASE)
        generic_citations = re.findall(r"\[來源:\s*[^\]]+\]", answer_text)

        total_hits = len(pdf_citations) + len(web_citations) + len(generic_citations)
        return {
            "has_valid_citations": total_hits > 0,
            "pdf_citation_count": len(pdf_citations),
            "web_citation_count": len(web_citations),
            "generic_citation_count": len(generic_citations),
        }

    def audit_response(
        self,
        query: str,
        answer_text: str,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        執行完整防幻覺稽核：
        1. 若 Profile 啟用 cli_validation，攔截 blocklist 禁用/廢棄指令。
        2. 若設定 allowlist，提示未在白名單且未在檢索文檔出現的可疑指令。
        3. 驗證回答是否具備官方來源標籤（PDF 頁碼或原始網頁 URL）。
        """
        violations: List[str] = []
        suggestions: List[str] = []

        if not answer_text or not answer_text.strip():
            return {
                "passed": False,
                "product_id": self.product_id,
                "has_valid_citations": False,
                "violations": ["回答內容為空，無法通過稽核。"],
                "suggestions": ["請先調用 search_kb 取得參考技術資料後再生成完整回答。"],
            }

        citation_status = self.check_citations(answer_text)
        if not citation_status["has_valid_citations"]:
            violations.append("缺少官方來源出處標註（必須附帶 PDF 頁碼標籤 `[來源: xxx.pdf, 第 N 頁]` 或原始網頁 `[來源: https://...]`）。")
            suggestions.append("請在每個核心技術論點與步驟末尾補上檢索結果提供的官方來源標籤。")

        if self.cli_enabled:
            candidate_cmds = self.extract_candidate_commands(answer_text)
            context_blob = " ".join(str(d.get("content", "")) for d in (retrieved_docs or [])).lower()

            for cmd in candidate_cmds:
                if cmd in self.blocklist:
                    info = self.blocklist[cmd]
                    replacement = info.get("replacement", "")
                    reason = info.get("reason", "此指令已於產品設定檔中列為禁用或廢棄指令。")
                    violations.append(f"偵測到禁用/幻覺指令 `{cmd}`：{reason}")
                    if replacement:
                        suggestions.append(f"請將 `{cmd}` 替換為官方標準指令：`{replacement}`")
                elif self.allowlist and cmd not in self.allowlist:
                    # 僅當指令也未出現於本次檢索文檔上下文中時才提出警告
                    if context_blob and cmd not in context_blob:
                        violations.append(f"偵測到未列於官方白名單且未見於檢索資料的指令 `{cmd}`。")
                        suggestions.append(f"請查證 `{cmd}` 是否為真實存在的原廠指令，或於檢索確認後補入 Profile allowlist。")

        return {
            "passed": len(violations) == 0,
            "product_id": self.product_id,
            "has_valid_citations": citation_status["has_valid_citations"],
            "citation_details": citation_status,
            "violations": violations,
            "suggestions": suggestions,
        }
