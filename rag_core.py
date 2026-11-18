"""
通用型多產品雙軌 RAG 引擎 - 選配獨立推理核心 (RAG Core)
僅在需要由後端獨立調用 Gemini / OpenAI / Ollama 進行問答時使用（如 ask_expert 或 Web Portal）。
若透過 IBM Bob 等智能體直接調用 search_kb + audit_grounding，無需使用此模組與外部 API 金鑰。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

import config
from grounding_auditor import GroundingAuditor
from profile_loader import load_active_profile
from universal_ambiguity_detector import UniversalAmbiguityDetector
import vector_store


def build_system_prompt(profile: Optional[Dict[str, Any]] = None) -> str:
    """依據目前啟用之 Product Profile 動態組裝專家系統提示詞"""
    active = profile or load_active_profile()
    persona = str(active.get("expert_persona", "你是一位精通本產品系列的資深技術顧問。"))
    product_name = str(active.get("product_name", "General Technical Product"))
    guardrails = [str(g) for g in (active.get("domain_guardrails") or [])]
    guardrails_block = "\n".join(f"- {rule}" for rule in guardrails)

    return (
        f"{persona}\n\n"
        f"【當前服務產品線】：{product_name}\n"
        f"【必須嚴格遵守的領域與引述防護欄】：\n{guardrails_block}\n\n"
        "【回答原則】：\n"
        "1. 僅依據檢索提供的技術參考資料作答，嚴禁編造未出現的指令、參數或規格。\n"
        "2. 每個核心步驟與技術論點文末必須附上 PDF 頁碼（如 `[來源: xxx.pdf, 第 N 頁]`）或原始網頁 URL（如 `[來源: https://...]`）。\n"
        "3. 若參考資料不足以回答問題，請誠實說明官方資料未記載。"
    )


def format_context_blocks(docs: List[Dict[str, Any]]) -> str:
    """將雙軌檢索結果格式化為 LLM 可讀的參考上下文"""
    blocks: List[str] = []
    for idx, doc in enumerate(docs, 1):
        meta = doc.get("metadata") or {}
        src = meta.get("source", "未知來源")
        doc_type = meta.get("type", "pdf")
        page = meta.get("page", 1)
        url = meta.get("url", "")
        score = doc.get("similarity_score", 0.0)
        if doc_type == "web" and url:
            header = f"[資料 {idx} | 網頁來源: {url} | 相關度: {score:.2f}]"
        else:
            header = f"[資料 {idx} | PDF 來源: {src}, 第 {page} 頁 | 相關度: {score:.2f}]"
        blocks.append(f"{header}\n{doc.get('content', '')}")
    return "\n\n---\n\n".join(blocks)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """依 config.LLM_PROVIDER 呼叫 Gemini、OpenAI 或本機 Ollama"""
    provider = config.LLM_PROVIDER
    if provider == "gemini" and config.GEMINI_API_KEY:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if "text" in p).strip()

    if provider == "openai" and config.OPENAI_API_KEY:
        url = f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
        payload = {
            "model": config.OPENAI_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    if provider == "ollama":
        payload = {
            "model": config.OLLAMA_HOST and "llama3.2:latest",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{config.OLLAMA_HOST.rstrip('/')}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()

    raise RuntimeError(
        "尚未設定外部 LLM API 金鑰 (GEMINI_API_KEY / OPENAI_API_KEY)。"
        "若您正在 IBM Bob 等 AI 智能體中使用，請直接調用 search_kb 與 audit_grounding 工具，無需外部金鑰。"
    )


def process_query(
    query_text: str,
    top_k: int = 12,
    profile_name: Optional[str] = None,
) -> Dict[str, Any]:
    """執行完整的雙軌檢索、消歧檢測、生成與防幻覺稽核流程"""
    profile = load_active_profile(profile_name)
    clash_info = UniversalAmbiguityDetector.evaluate_clash(query_text, profile_name=profile_name)
    docs = vector_store.query_kb(query_text=query_text, top_k=top_k)

    if not docs:
        return {
            "answer": "目前知識庫中未檢索到與此提問相關的文件或網頁內容，請先放入 PDF 或設定網址執行建庫。",
            "sources": [],
            "audit": {"passed": True, "violations": [], "suggestions": []},
            "clash": clash_info,
        }

    system_prompt = build_system_prompt(profile)
    context_text = format_context_blocks(docs)
    clash_note = ""
    if clash_info.get("has_clash"):
        clash_note = f"\n\n【偵測到潛在規格/概念衝突提醒】：{json.dumps(clash_info, ensure_ascii=False)}\n"

    user_prompt = (
        f"【使用者提問】：\n{query_text}\n"
        f"{clash_note}\n"
        f"【雙軌檢索參考資料】：\n{context_text}\n\n"
        "請使用繁體中文給出精準、結構化且附帶來源標註的解答。"
    )

    try:
        answer_text = _call_llm(system_prompt, user_prompt)
    except Exception as exc:
        return {
            "answer": f"無法執行獨立 LLM 生成（{exc}）。以下為檢索到的原始參考資料：\n\n{context_text}",
            "sources": [d.get("metadata", {}) for d in docs],
            "audit": {"passed": False, "violations": [str(exc)], "suggestions": []},
            "clash": clash_info,
        }

    auditor = GroundingAuditor(profile_name=profile_name)
    audit_res = auditor.audit_response(query_text, answer_text, retrieved_docs=docs)

    return {
        "answer": answer_text,
        "sources": [d.get("metadata", {}) for d in docs],
        "audit": audit_res,
        "clash": clash_info,
    }
