"""
通用型多產品雙軌 RAG 引擎 - MCP (Model Context Protocol) 伺服器
專為 IBM Bob、Antigravity、Claude Desktop、Cursor 等第三方 AI 智能體設計。
前 4 項核心工具完全免外部 LLM API 金鑰，直接由宿主智能體調用執行檢索、建庫與防幻覺審計。
"""

from __future__ import annotations

import json
from typing import List

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

import config
from grounding_auditor import GroundingAuditor
import ingest
from profile_loader import list_available_profiles, load_active_profile
import vector_store

mcp = FastMCP("Universal-DualTrack-RAG-KB")


@mcp.tool()
def search_kb(query: str, top_k: int = 8) -> str:
    """
    執行雙軌混合檢索（ChromaDB 語意向量 + SQLite FTS5 BM25 全文檢索），
    同時支援已入庫之 PDF 手冊與網站擷取頁面，並隨附當前產品 Profile 的領域防護欄約束。
    此工具免外部 API Key，直接回傳檢索證據供智能體推理解答。

    Args:
        query: 使用者的技術提問或關鍵字
        top_k: 回傳最相關的技術片段數量（預設 8）
    """
    profile = load_active_profile()
    results = vector_store.query_kb(query_text=query, top_k=top_k)

    guardrails = [str(g) for g in (profile.get("domain_guardrails") or [])]
    guardrails_str = "\n".join(f"- {rule}" for rule in guardrails)
    product_name = str(profile.get("product_name", "General Technical Product"))

    if not results:
        return (
            f"【產品線：{product_name}】未在知識庫中檢索到與「{query}」相關的內容。\n"
            "請確認已將產品 PDF 放入 `raw_data/pdfs/` 或透過 `ingest_kb` 擷取官方網站。"
        )

    blocks: List[str] = [
        f"## 產品領域防護欄 ({product_name})\n{guardrails_str}\n",
        "## 雙軌檢索參考資料",
    ]
    for idx, item in enumerate(results, 1):
        meta = item.get("metadata") or {}
        score = float(item.get("similarity_score", 0.0))
        channel = item.get("channel", "hybrid")
        content = item.get("content", "")
        source = meta.get("source", "未知來源")
        page = meta.get("page", 1)
        doc_type = meta.get("type", "pdf")

        if doc_type == "web" or "url" in meta:
            url = meta.get("url", source)
            header = f"### [結果 {idx}] ({channel} | 分數: {score:.2f}) 🌐 網頁來源: {url}"
        else:
            header = f"### [結果 {idx}] ({channel} | 分數: {score:.2f}) 📄 PDF 來源: {source}, 第 {page} 頁"

        blocks.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(blocks)


@mcp.tool()
def audit_grounding(query: str, draft_answer: str) -> str:
    """
    對智能體草擬的技術回答執行確定性防幻覺稽核。
    依當前 Product Profile 檢查是否誤用禁用/廢棄指令，以及是否附帶合法的 PDF 頁碼或網頁 URL 來源標籤。

    Args:
        query: 原始使用者提問
        draft_answer: 智能體準備輸出給使用者的草稿回答
    """
    docs = vector_store.query_kb(query_text=query, top_k=6)
    auditor = GroundingAuditor()
    report = auditor.audit_response(query=query, answer_text=draft_answer, retrieved_docs=docs)
    return json.dumps(report, ensure_ascii=False, indent=2)


@mcp.tool()
def ingest_kb(
    mode: str = "all",
    target_url: str = "",
    max_depth: int = 2,
    max_pages: int = 50,
    force: bool = False,
) -> str:
    """
    觸發知識庫增量更新，同時支援 PDF 手冊掃描與指定網站遞迴擷取。
    寫入 ChromaDB 向量庫與 SQLite FTS5 全文檢索索引。

    Args:
        mode: 建庫模式 ('all' | 'pdf' | 'web')
        target_url: 選填，指定欲爬取之產品技術文件網址（會自動寫入 raw_data/web_urls.txt 並遞迴擷取）
        max_depth: 網站遞迴爬取最大深度（預設 2）
        max_pages: 單次最多爬取頁數（預設 50）
        force: 是否忽略快取強制重建（預設 False）
    """
    extra_urls: List[str] = []
    if target_url.strip():
        ingest.append_seed_url(target_url.strip())
        extra_urls.append(target_url.strip())

    try:
        summary = ingest.run_ingestion(
            mode=mode,
            force=force,
            max_depth=max_depth,
            max_pages=max_pages,
            extra_urls=extra_urls,
        )
        return "✅ 知識庫建置完成：\n" + json.dumps(summary, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"❌ 建置知識庫時發生錯誤: {exc}"


@mcp.tool()
def get_kb_stats() -> str:
    """取得目前啟用的產品 Profile、向量庫路徑、可用 Profiles 與已索引 PDF/網頁筆數統計"""
    profile = load_active_profile()
    fts_stats = vector_store.get_fts_stats()
    vector_count = vector_store.get_chroma_collection().count()
    manifest = ingest.load_manifest()
    pdf_manifest_cnt = sum(1 for v in manifest.values() if isinstance(v, dict) and v.get("type") == "pdf")
    web_manifest_cnt = sum(1 for v in manifest.values() if isinstance(v, dict) and v.get("type") == "web")

    payload = {
        "product_id": profile.get("product_id"),
        "product_name": profile.get("product_name"),
        "available_profiles": list_available_profiles(),
        "runtime": config.get_runtime_summary(),
        "vector_chunks_count": vector_count,
        "manifest_counts": {"pdf_files": pdf_manifest_cnt, "web_pages": web_manifest_cnt},
        "fts5_stats": fts_stats,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def ask_expert(query: str, top_k: int = 15) -> str:
    """
    （選配）調用後端獨立 RAG 推理引擎回答問題。
    注意：需於 .env 設定 GEMINI_API_KEY 或 OPENAI_API_KEY；若未設定外部金鑰，請改用 search_kb + audit_grounding。

    Args:
        query: 技術提問
        top_k: 檢索相關片段筆數
    """
    import rag_core

    result = rag_core.process_query(query_text=query, top_k=top_k)
    return str(result.get("answer", "無法取得回答。"))


if __name__ == "__main__":
    mcp.run()
