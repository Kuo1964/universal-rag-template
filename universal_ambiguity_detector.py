"""
通用型多產品雙軌 RAG 引擎 - 跨架構意圖消歧與衝突評估器
動態依據當前啟用之 Product Profile 領域邊界，判斷提問是否存在版本或規格衝突。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

import config
from profile_loader import load_active_profile


class UniversalAmbiguityDetector:
    """產品無關的動態提問衝突與歧義檢測器"""

    @staticmethod
    def _build_clash_prompt(profile: Dict[str, Any]) -> str:
        """依據目前啟用的 Product Profile 組合審查系統提示詞"""
        product_name = str(profile.get("product_name", "General Technical Product"))
        guardrails: List[str] = [str(g) for g in (profile.get("domain_guardrails") or [])]
        guardrails_text = "\n".join(f"- {g}" for g in guardrails) if guardrails else "- 無額外特定限制"

        return (
            f"你是一位嚴謹的 {product_name} 首席技術架構師審查官。\n"
            f"請審查使用者的【技術提問】，並參照以下產品領域邊界規則，判斷提問是否存在嚴重的規格衝突、版本生命週期矛盾或操作維度混淆：\n"
            f"{guardrails_text}\n\n"
            "請以嚴格純 JSON 格式輸出：\n"
            "{\n"
            '  "has_clash": true | false,\n'
            '  "clash_type": "VERSION_LIFECYCLE | HARDWARE_BOUNDARY | OPERATION_DIMENSION | MISSING_PREREQUISITE | NONE",\n'
            '  "clash_summary": "一句話總結衝突焦點",\n'
            '  "detailed_explanation": "詳細說明衝突原因",\n'
            '  "branch_a": {"intent_desc": "情境 A", "official_approach": "標準處理方向"},\n'
            '  "branch_b": {"intent_desc": "情境 B", "official_approach": "標準處理方向"}\n'
            "}\n"
            '若提問明確且無矛盾，請僅輸出 {"has_clash": false}。'
        )

    @classmethod
    def evaluate_clash(
        cls,
        query_text: str,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """動態評估使用者提問是否存在領域衝突；若無設定外部 LLM 金鑰則安全略過"""
        if not query_text or not query_text.strip():
            return {"has_clash": False}

        profile = load_active_profile(profile_name)
        system_prompt = cls._build_clash_prompt(profile)
        prompt = f"{system_prompt}\n\n【使用者提問】：{query_text}"

        if config.LLM_PROVIDER == "openai" and config.OPENAI_API_KEY:
            return cls._call_openai_clash(prompt)
        if config.GEMINI_API_KEY:
            return cls._call_gemini_clash(prompt)
        if config.OPENAI_API_KEY:
            return cls._call_openai_clash(prompt)

        return {"has_clash": False}

    @staticmethod
    def _call_gemini_clash(prompt: str) -> Dict[str, Any]:
        """呼叫 Gemini API 執行 JSON 衝突檢測"""
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 1024,
                    "responseMimeType": "application/json",
                },
            }
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        raw_txt = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                        parsed = json.loads(raw_txt)
                        if isinstance(parsed, dict):
                            return parsed
        except Exception as exc:
            print(f"[警告] Gemini 動態衝突評估異常: {exc}")
        return {"has_clash": False}

    @staticmethod
    def _call_openai_clash(prompt: str) -> Dict[str, Any]:
        """呼叫 OpenAI 相容 API 執行 JSON 衝突檢測"""
        try:
            url = f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
            payload = {
                "model": config.OPENAI_MODEL,
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            }
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw_txt = choices[0].get("message", {}).get("content", "").strip()
                        parsed = json.loads(raw_txt)
                        if isinstance(parsed, dict):
                            return parsed
        except Exception as exc:
            print(f"[警告] OpenAI 動態衝突評估異常: {exc}")
        return {"has_clash": False}
