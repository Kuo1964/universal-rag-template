"""
通用型多產品雙軌 RAG 引擎 - 選配獨立 Web Portal 服務 (FastAPI)
提供跨產品知識庫檢索、文件入庫觸發與專家問答 HTTP API 與簡易網頁介面。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
import ingest
from profile_loader import list_available_profiles, load_active_profile
import rag_core
import vector_store

app = FastAPI(title="Universal Dual-Track RAG Portal", version="1.0.0")


class QueryRequest(BaseModel):
    """知識庫檢索與提問請求模型"""

    query: str
    top_k: int = 8


class IngestRequest(BaseModel):
    """知識庫增量建庫請求模型"""

    mode: str = "all"
    target_url: str = ""
    max_depth: int = 2
    max_pages: int = 50
    force: bool = False


@app.get("/", response_class=HTMLResponse)
def index_page() -> str:
    """提供乾淨語意化之獨立檢索測試網頁"""
    profile = load_active_profile()
    product_name = str(profile.get("product_name", "General Technical Product"))
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{product_name} - Dual-Track RAG Portal</title>
  <style>
    :root {{ --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --accent: #38bdf8; --border: #334155; }}
    body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 2rem; }}
    main {{ max-width: 880px; margin: 0 auto; background: var(--card); padding: 1.5rem; border-radius: 12px; border: 1px solid var(--border); }}
    input, button {{ padding: 0.65rem 1rem; border-radius: 8px; border: 1px solid var(--border); font-size: 1rem; }}
    input {{ width: 70%; background: var(--bg); color: var(--text); }}
    button {{ background: var(--accent); color: var(--bg); font-weight: 600; cursor: pointer; }}
    pre {{ white-space: pre-wrap; background: var(--bg); padding: 1rem; border-radius: 8px; border: 1px solid var(--border); margin-top: 1rem; }}
  </style>
</head>
<body>
  <main>
    <h1>{product_name} 雙軌 RAG 知識庫</h1>
    <p>支援 PDF 與網站遞迴擷取（ChromaDB + SQLite FTS5）。</p>
    <section>
      <input id="q" type="text" placeholder="請輸入技術問題或關鍵詞..." />
      <button onclick="runSearch()">雙軌檢索</button>
    </section>
    <pre id="out">準備就緒。</pre>
  </main>
  <script>
    async function runSearch() {{
      const q = document.getElementById('q').value;
      const out = document.getElementById('out');
      out.textContent = '檢索中...';
      const resp = await fetch('/api/search', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ query: q, top_k: 6 }})
      }});
      const data = await resp.json();
      out.textContent = JSON.stringify(data, null, 2);
    }}
  </script>
</body>
</html>"""


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    """健康檢查端點"""
    return {"status": "ok"}


@app.get("/api/stats")
def kb_stats() -> Dict[str, Any]:
    """回傳目前知識庫與啟用 Profile 之完整狀態"""
    profile = load_active_profile()
    return {
        "runtime": config.get_runtime_summary(),
        "product_id": profile.get("product_id"),
        "product_name": profile.get("product_name"),
        "available_profiles": list_available_profiles(),
        "fts_stats": vector_store.get_fts_stats(),
        "vector_count": vector_store.get_chroma_collection().count(),
    }


@app.post("/api/search")
def search_endpoint(req: QueryRequest) -> Dict[str, Any]:
    """免外部 API Key 的雙軌檢索 API"""
    results: List[Dict[str, Any]] = vector_store.query_kb(query_text=req.query, top_k=req.top_k)
    return {"query": req.query, "count": len(results), "results": results}


@app.post("/api/ask")
def ask_endpoint(req: QueryRequest) -> Dict[str, Any]:
    """完整專家問答 API（需設定 GEMINI_API_KEY 或 OPENAI_API_KEY）"""
    return rag_core.process_query(query_text=req.query, top_k=req.top_k)


@app.post("/api/ingest")
def ingest_endpoint(req: IngestRequest) -> Dict[str, Any]:
    """觸發 PDF 與網站增量建庫"""
    extra_urls: List[str] = []
    if req.target_url.strip():
        ingest.append_seed_url(req.target_url.strip())
        extra_urls.append(req.target_url.strip())

    return ingest.run_ingestion(
        mode=req.mode,
        force=req.force,
        max_depth=req.max_depth,
        max_pages=req.max_pages,
        extra_urls=extra_urls,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.SERVER_HOST, port=config.PORTAL_PORT)
