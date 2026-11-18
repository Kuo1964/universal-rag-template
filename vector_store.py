"""
通用型多產品雙軌 RAG 引擎 - 雙軌向量與全文檢索模組 (ChromaDB + SQLite FTS5)
支援全量 PDF 目錄與網站擷取頁面雙軌索引，無任何特定產品或檔名硬編碼。
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings
import fitz  # PyMuPDF

import config
from embedding_adapter import UniversalEmbeddingFunction
from profile_loader import load_active_profile

_CHROMA_LOCK = threading.RLock()
_FTS_LOCK = threading.RLock()
_CHROMA_CLIENT: Optional[Any] = None
_CHROMA_COLLECTION: Optional[Any] = None
_ACTIVE_DB_KEY: Optional[str] = None


def reset_vector_store_cache() -> None:
    """重設 ChromaDB 單例連線快取（主要用於切換設定檔或隔離單元測試）"""
    global _CHROMA_CLIENT, _CHROMA_COLLECTION, _ACTIVE_DB_KEY
    with _CHROMA_LOCK:
        _CHROMA_CLIENT = None
        _CHROMA_COLLECTION = None
        _ACTIVE_DB_KEY = None


def get_chroma_collection(collection_name: Optional[str] = None) -> Any:
    """取得或建立 ChromaDB 集合（線程安全單例模式）"""
    global _CHROMA_CLIENT, _CHROMA_COLLECTION, _ACTIVE_DB_KEY
    target_collection = collection_name or config.get_collection_name()
    target_key = f"{config.VECTOR_DB_DIR}::{target_collection}"

    with _CHROMA_LOCK:
        if _CHROMA_COLLECTION is not None and _ACTIVE_DB_KEY == target_key:
            return _CHROMA_COLLECTION

        config.VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        _CHROMA_CLIENT = chromadb.PersistentClient(
            path=str(config.VECTOR_DB_DIR),
            settings=Settings(anonymized_telemetry=False, allow_reset=False),
        )
        embedding_fn = UniversalEmbeddingFunction()
        _CHROMA_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(
            name=target_collection,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        _ACTIVE_DB_KEY = target_key
        return _CHROMA_COLLECTION


def add_chunks_to_db(chunks: List[Dict[str, Any]], collection_name: Optional[str] = None) -> int:
    """將切分後的文字 Chunk 批次寫入 ChromaDB 向量知識庫"""
    if not chunks:
        return 0

    collection = get_chroma_collection(collection_name=collection_name)
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for chunk in chunks:
        cid = str(chunk.get("id") or chunk.get("chunk_id") or uuid.uuid4())
        text = str(chunk.get("content") or chunk.get("text") or "").strip()
        meta = dict(chunk.get("metadata") or {})
        if not text:
            continue
        ids.append(cid)
        documents.append(text)
        metadatas.append(meta)

    if not ids:
        return 0

    # 分批寫入以避免單次超過 ChromaDB batch 上限
    batch_size = 200
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
    return len(ids)


def delete_source_from_db(source_name: str, collection_name: Optional[str] = None) -> None:
    """依來源名稱安全移除 ChromaDB 與 FTS5 中的舊資料"""
    collection = get_chroma_collection(collection_name=collection_name)
    collection.delete(where={"source": source_name})

    db_path = get_fts_db_path()
    if db_path.exists():
        with _FTS_LOCK:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("DELETE FROM fts_documents WHERE source = ?", (source_name,))
                conn.execute("DELETE FROM indexed_sources WHERE source_key = ?", (source_name,))
                conn.commit()
            finally:
                conn.close()


def is_pure_toc_chunk(text: str) -> bool:
    """過濾純目錄點線導覽或無實質技術內容之連結清單"""
    if not text:
        return False
    text_lower = text.lower()
    if "abbreviations and acronyms" in text_lower or ("glossary" in text_lower and "filter on titles" in text_lower):
        return True

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    link_lines = [line for line in lines if line.startswith("- [") or line.startswith("* [")]
    dot_lines = [line for line in lines if "...." in line or "····" in line or "   . " in line]
    return (len(link_lines) / len(lines)) >= 0.45 or (len(dot_lines) / len(lines)) >= 0.35


def get_fts_db_path() -> Path:
    """取得目前 SQLite FTS5 資料庫路徑"""
    config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return config.RAW_DATA_DIR / "knowledge_fts.sqlite3"


def _ensure_fts_schema(conn: sqlite3.Connection) -> None:
    """確保 FTS5 虛擬表與來源追蹤表存在"""
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_documents
        USING fts5(doc_type UNINDEXED, source, page UNINDEXED, url UNINDEXED, content, tokenize='unicode61')
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexed_sources (
            source_key TEXT PRIMARY KEY,
            doc_type TEXT,
            signature TEXT
        )
        """
    )


def build_fts_index(force: bool = False) -> str:
    """自動掃描 raw_data/pdfs/*.pdf 下所有 PDF 並建立/增量更新 SQLite FTS5 索引"""
    db_path = get_fts_db_path()
    config.RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(config.RAW_PDF_DIR.glob("*.pdf"))

    with _FTS_LOCK:
        conn = sqlite3.connect(str(db_path))
        try:
            _ensure_fts_schema(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT source_key, signature FROM indexed_sources WHERE doc_type = 'pdf'")
            existing = dict(cursor.fetchall())

            for pdf_path in pdf_files:
                src_name = pdf_path.name
                try:
                    stat = pdf_path.stat()
                    signature = f"{stat.st_size}:{int(stat.st_mtime)}"
                except OSError:
                    continue

                if not force and existing.get(src_name) == signature:
                    continue

                cursor.execute("DELETE FROM fts_documents WHERE doc_type = 'pdf' AND source = ?", (src_name,))
                rows_to_insert: List[tuple[str, str, int, str, str]] = []
                try:
                    with fitz.open(pdf_path) as doc:
                        for page_idx in range(len(doc)):
                            try:
                                text = doc[page_idx].get_text("text") or ""
                                clean = text.strip()
                                if len(clean) >= 40 and not is_pure_toc_chunk(clean):
                                    rows_to_insert.append(("pdf", src_name, page_idx + 1, "", clean))
                            except Exception:
                                continue
                except Exception as doc_err:
                    print(f"[警告] 解析 PDF 納入 FTS5 失敗 ({src_name}): {doc_err}")
                    continue

                if rows_to_insert:
                    cursor.executemany(
                        "INSERT INTO fts_documents (doc_type, source, page, url, content) VALUES (?, ?, ?, ?, ?)",
                        rows_to_insert,
                    )
                cursor.execute(
                    "INSERT OR REPLACE INTO indexed_sources (source_key, doc_type, signature) VALUES (?, 'pdf', ?)",
                    (src_name, signature),
                )
                conn.commit()
        finally:
            conn.close()
    return str(db_path)


def index_web_chunks_to_fts(url: str, source_name: str, text: str) -> None:
    """將網站擷取下來的頁面全文寫入 SQLite FTS5，實現網頁精確關鍵字檢索"""
    clean_text = (text or "").strip()
    if not clean_text:
        return

    db_path = get_fts_db_path()
    with _FTS_LOCK:
        conn = sqlite3.connect(str(db_path))
        try:
            _ensure_fts_schema(conn)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM fts_documents WHERE doc_type = 'web' AND url = ?", (url,))
            cursor.execute(
                "INSERT INTO fts_documents (doc_type, source, page, url, content) VALUES (?, ?, ?, ?, ?)",
                ("web", source_name, 1, url, clean_text),
            )
            cursor.execute(
                "INSERT OR REPLACE INTO indexed_sources (source_key, doc_type, signature) VALUES (?, 'web', ?)",
                (url, str(len(clean_text))),
            )
            conn.commit()
        finally:
            conn.close()


def _extract_fts_tokens(query_text: str, expanded_terms: Optional[List[str]] = None) -> List[str]:
    """萃取安全的 FTS5 檢索關鍵詞（支援中英文詞彙與連字號拆解）"""
    raw_terms = [query_text] + (expanded_terms or [])
    tokens: List[str] = []
    seen = set()

    for term in raw_terms:
        # 擷取英數複合詞與連續中文字詞
        for match in re.findall(r"[A-Za-z0-9][A-Za-z0-9\.\-_]*|[\u4e00-\u9fff]{2,}", str(term)):
            cleaned = match.lower().strip(".-_")
            if len(cleaned) < 2:
                continue
            if cleaned not in seen:
                seen.add(cleaned)
                tokens.append(cleaned)
            if "-" in cleaned:
                for sub in cleaned.split("-"):
                    if len(sub) >= 2 and sub not in seen:
                        seen.add(sub)
                        tokens.append(sub)
    return tokens


def _format_fts_or_query(tokens: List[str], limit: int = 14) -> str:
    """安全組裝 FTS5 MATCH OR 查詢語法"""
    safe_terms: List[str] = []
    for tok in tokens[:limit]:
        cleaned = tok.replace('"', "").strip()
        if cleaned:
            safe_terms.append(f'"{cleaned}"')
    return " OR ".join(safe_terms)


def expand_query_with_profile(query_text: str, profile: Optional[Dict[str, Any]] = None) -> List[str]:
    """依據目前啟用的 Product Profile 同義詞表進行查詢擴展"""
    active_profile = profile or load_active_profile()
    synonyms: Dict[str, List[str]] = active_profile.get("synonyms") or {}
    q_lower = query_text.lower()
    expanded: List[str] = []

    for key, values in synonyms.items():
        key_lower = str(key).lower()
        val_list = [str(v) for v in (values or [])]
        matched = key_lower in q_lower or any(v.lower() in q_lower for v in val_list)
        if matched:
            if key_lower not in expanded:
                expanded.append(key_lower)
            for v in val_list:
                if v not in expanded:
                    expanded.append(v)
    return expanded


def search_fts_bm25(
    query_text: str,
    expanded_terms: Optional[List[str]] = None,
    top_k: int = 15,
) -> List[Dict[str, Any]]:
    """執行 SQLite FTS5 BM25 精確檢索（涵蓋所有已索引 PDF 與網頁）"""
    db_path = build_fts_index()
    tokens = _extract_fts_tokens(query_text, expanded_terms)
    fts_expr = _format_fts_or_query(tokens)
    if not fts_expr:
        return []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT doc_type, source, page, url, content, bm25(fts_documents) AS rank_score
            FROM fts_documents
            WHERE fts_documents MATCH ?
            ORDER BY rank_score
            LIMIT ?
            """,
            (fts_expr, top_k * 2),
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as exc:
        print(f"[警告] FTS5 檢索發生異常: {exc}")
        return []

    results: List[Dict[str, Any]] = []
    for doc_type, source, page, url, content, rank_score in rows:
        # bm25() 分數越負代表越相關，轉換為 0~1 之間的正向分數
        norm_score = 1.0 / (1.0 + max(0.0, 10.0 + float(rank_score or 0.0)) * 0.1)
        snippet = content[:1800] if len(content) > 1800 else content
        meta: Dict[str, Any] = {
            "source": source,
            "page": int(page or 1),
            "type": doc_type,
        }
        if url:
            meta["url"] = url
        results.append(
            {
                "content": snippet,
                "metadata": meta,
                "similarity_score": round(min(0.99, max(0.35, norm_score)), 4),
                "channel": "fts5",
            }
        )
    return results[:top_k]


def query_kb(
    query_text: str,
    top_k: int = 10,
    collection_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    執行雙軌混合檢索（ChromaDB 語意向量 + SQLite FTS5 BM25 精確匹配），
    自動融合當前 Profile 的同義詞擴展並回傳去重排序後的技術內容。
    """
    if not query_text or not query_text.strip():
        return []

    profile = load_active_profile()
    expanded_terms = expand_query_with_profile(query_text, profile=profile)
    enhanced_query = f"{query_text} {' '.join(expanded_terms)}".strip()

    # 軌道 1：ChromaDB 語意檢索
    vector_results: List[Dict[str, Any]] = []
    try:
        collection = get_chroma_collection(collection_name=collection_name)
        total_count = collection.count()
        if total_count > 0:
            n_results = min(max(top_k, 5), total_count)
            raw_res = collection.query(
                query_texts=[enhanced_query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            docs = (raw_res.get("documents") or [[]])[0]
            metas = (raw_res.get("metadatas") or [[]])[0]
            dists = (raw_res.get("distances") or [[]])[0]

            for doc, meta, dist in zip(docs, metas, dists):
                if is_pure_toc_chunk(doc):
                    continue
                score = max(0.0, min(1.0, 1.0 - float(dist)))
                vector_results.append(
                    {
                        "content": doc,
                        "metadata": meta or {},
                        "similarity_score": round(score, 4),
                        "channel": "vector",
                    }
                )
    except Exception as exc:
        print(f"[警告] ChromaDB 向量檢索失敗: {exc}")

    # 軌道 2：SQLite FTS5 BM25 精確關鍵字檢索
    fts_results = search_fts_bm25(query_text, expanded_terms=expanded_terms, top_k=top_k)

    # 雙軌結果融合與去重
    merged: Dict[str, Dict[str, Any]] = {}
    for item in vector_results + fts_results:
        meta = item.get("metadata", {})
        src = str(meta.get("source", ""))
        page = str(meta.get("page", 1))
        url = str(meta.get("url", ""))
        prefix = item.get("content", "")[:120].strip()
        dedup_key = f"{src}::{page}::{url}::{prefix}"

        if dedup_key not in merged:
            merged[dedup_key] = dict(item)
        else:
            # 雙軌同時命中時提升綜合信心分數
            existing = merged[dedup_key]
            existing["similarity_score"] = round(
                min(1.0, max(existing["similarity_score"], item["similarity_score"]) + 0.12),
                4,
            )
            existing["channel"] = "hybrid"

    ranked = sorted(merged.values(), key=lambda x: x.get("similarity_score", 0.0), reverse=True)
    return ranked[:top_k]


def get_fts_stats() -> Dict[str, int]:
    """回傳目前 FTS5 資料庫已索引之 PDF 與網頁統計數量"""
    db_path = get_fts_db_path()
    if not db_path.exists():
        return {"pdf_files": 0, "web_pages": 0, "total_fts_rows": 0}

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_fts_schema(conn)
        pdf_cnt = conn.execute("SELECT COUNT(*) FROM indexed_sources WHERE doc_type = 'pdf'").fetchone()[0]
        web_cnt = conn.execute("SELECT COUNT(*) FROM indexed_sources WHERE doc_type = 'web'").fetchone()[0]
        row_cnt = conn.execute("SELECT COUNT(*) FROM fts_documents").fetchone()[0]
        return {
            "pdf_files": int(pdf_cnt),
            "web_pages": int(web_cnt),
            "total_fts_rows": int(row_cnt),
        }
    finally:
        conn.close()
