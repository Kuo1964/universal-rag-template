"""
通用型多產品雙軌 RAG 引擎 - 統一增量建庫引擎 (PDF + 網站遞迴擷取)
同步將文件寫入 ChromaDB 向量資料庫與 SQLite FTS5 全文檢索索引，實現零遺漏雙軌檢索。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import config
from parser import calculate_file_hash, crawl_website, parse_pdf
from profile_loader import load_active_profile
from vector_store import (
    add_chunks_to_db,
    build_fts_index,
    delete_source_from_db,
    index_web_chunks_to_fts,
)


def load_manifest() -> Dict[str, Any]:
    """讀取目前知識庫的已處理文件清單 (manifest.json)"""
    if not config.MANIFEST_FILE.exists():
        return {}
    try:
        return json.loads(config.MANIFEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(manifest: Dict[str, Any]) -> None:
    """持久化儲存知識庫已處理清單"""
    config.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json_set(file_path: Path) -> Set[str]:
    """從 JSON 檔案載入字串集合"""
    if not file_path.exists():
        return set()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_json_set(file_path: Path, values: Set[str]) -> None:
    """將字串集合寫回 JSON 檔案"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(sorted(values), ensure_ascii=False, indent=2), encoding="utf-8")


def append_seed_url(url: str) -> bool:
    """將新網站 URL 寫入 raw_data/web_urls.txt（若尚未存在）"""
    clean_url = url.strip()
    if not clean_url:
        return False

    config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_lines: List[str] = []
    if config.RAW_URLS_FILE.exists():
        existing_lines = config.RAW_URLS_FILE.read_text(encoding="utf-8").splitlines()

    if any(line.strip() == clean_url for line in existing_lines):
        return False

    with open(config.RAW_URLS_FILE, "a", encoding="utf-8") as f:
        if existing_lines and existing_lines[-1].strip():
            f.write("\n")
        f.write(f"{clean_url}\n")
    return True


def _ingest_pdfs(manifest: Dict[str, Any], force: bool = False, enable_vision: bool = False) -> Dict[str, int]:
    """掃描 raw_data/pdfs/*.pdf 並執行增量向量化與 FTS5 索引"""
    config.RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(config.RAW_PDF_DIR.glob("*.pdf"))
    processed_pdfs = 0
    new_chunks = 0

    for pdf_path in pdf_files:
        src_name = pdf_path.name
        file_hash = calculate_file_hash(pdf_path)
        prev_record = manifest.get(src_name)

        if not force and isinstance(prev_record, dict) and prev_record.get("hash") == file_hash:
            continue

        delete_source_from_db(src_name)
        text_chunks, image_records = parse_pdf(pdf_path, extract_images=enable_vision)
        written = add_chunks_to_db(text_chunks)

        manifest[src_name] = {
            "type": "pdf",
            "hash": file_hash,
            "chunks": written,
            "images": len(image_records),
        }
        processed_pdfs += 1
        new_chunks += written
        print(f"  ├─ [PDF 入庫] {src_name}：寫入 {written} 個 Chunks")

    build_fts_index(force=force)
    return {"pdfs_processed": processed_pdfs, "pdf_chunks_added": new_chunks}


def _ingest_websites(
    manifest: Dict[str, Any],
    force: bool = False,
    max_depth: int = 2,
    max_pages: int = 200,
    extra_urls: Optional[List[str]] = None,
    fetcher: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """讀取 web_urls.txt 與指定網址，執行同範圍遞迴爬取並同步寫入雙軌知識庫"""
    seed_urls: List[str] = []
    if config.RAW_URLS_FILE.exists():
        for line in config.RAW_URLS_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped not in seed_urls:
                seed_urls.append(stripped)

    for url in extra_urls or []:
        clean = url.strip()
        if clean and clean not in seed_urls:
            seed_urls.append(clean)

    if not seed_urls:
        return {"web_pages_processed": 0, "web_chunks_added": 0, "errors": []}

    global_visited = set() if force else _load_json_set(config.GLOBAL_VISITED_URLS_FILE)
    global_hashes = set() if force else _load_json_set(config.GLOBAL_CONTENT_HASHES_FILE)
    profile = load_active_profile()

    pages_processed = 0
    web_chunks_added = 0
    errors: List[str] = []

    for seed_url in seed_urls:
        if pages_processed >= max_pages:
            break
        remaining = max_pages - pages_processed
        crawl_res = crawl_website(
            seed_url=seed_url,
            max_depth=max_depth,
            max_pages=remaining,
            global_visited=global_visited,
            global_hashes=global_hashes,
            profile=profile,
            fetcher=fetcher,
        )
        errors.extend(crawl_res.get("errors", []))

        for page_item in crawl_res.get("pages", []):
            page_url = page_item["url"]
            source_name = page_item["source_name"]
            chunks = page_item["chunks"]
            full_text = page_item["full_text"]

            delete_source_from_db(source_name)
            written = add_chunks_to_db(chunks)
            index_web_chunks_to_fts(url=page_url, source_name=source_name, text=full_text)

            manifest[source_name] = {
                "type": "web",
                "url": page_url,
                "chunks": written,
            }
            pages_processed += 1
            web_chunks_added += written
            print(f"  ├─ [網頁入庫] {page_url}：寫入 {written} 個 Chunks")

    _save_json_set(config.GLOBAL_VISITED_URLS_FILE, global_visited)
    _save_json_set(config.GLOBAL_CONTENT_HASHES_FILE, global_hashes)
    return {
        "web_pages_processed": pages_processed,
        "web_chunks_added": web_chunks_added,
        "errors": errors,
    }


def run_ingestion(
    mode: str = "all",
    force: bool = False,
    max_depth: int = 2,
    max_pages: int = 200,
    enable_vision: bool = False,
    extra_urls: Optional[List[str]] = None,
    fetcher: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """
    執行統一增量知識庫建置流程：
    先處理網站擷取（可能順帶下載頁面中的官方 PDF），再掃描 raw_data/pdfs/ 納入所有 PDF。
    """
    normalized_mode = (mode or "all").strip().lower()
    manifest = {} if force else load_manifest()

    summary: Dict[str, Any] = {
        "mode": normalized_mode,
        "pdfs_processed": 0,
        "pdf_chunks_added": 0,
        "web_pages_processed": 0,
        "web_chunks_added": 0,
        "errors": [],
    }

    if normalized_mode in ("all", "web", "url", "url-only"):
        web_stats = _ingest_websites(
            manifest=manifest,
            force=force,
            max_depth=max_depth,
            max_pages=max_pages,
            extra_urls=extra_urls,
            fetcher=fetcher,
        )
        summary.update(web_stats)

    if normalized_mode in ("all", "pdf", "pdf-only"):
        pdf_stats = _ingest_pdfs(
            manifest=manifest,
            force=force,
            enable_vision=enable_vision,
        )
        summary.update(pdf_stats)

    save_manifest(manifest)
    return summary


def main() -> None:
    """命令列執行入口"""
    arg_parser = argparse.ArgumentParser(description="通用多產品雙軌 RAG 知識庫增量建庫工具")
    arg_parser.add_argument(
        "--mode",
        choices=["all", "pdf", "web"],
        default="all",
        help="建庫模式：all（PDF 與網站）、pdf（僅 PDF）、web（僅網站）",
    )
    arg_parser.add_argument("--add-url", type=str, default="", help="新增一筆網站種子網址並立即納入建庫")
    arg_parser.add_argument("--force", action="store_true", help="忽略快取，強制重建全部文件與網頁索引")
    arg_parser.add_argument("--max-depth", type=int, default=2, help="網站遞迴爬取最大深度")
    arg_parser.add_argument("--max-pages", type=int, default=200, help="單次最多爬取網頁數量")
    arg_parser.add_argument("--enable-vision", action="store_true", help="啟用 PDF 技術圖表提取（選配）")
    args = arg_parser.parse_args()

    extra_urls: List[str] = []
    if args.add_url.strip():
        append_seed_url(args.add_url.strip())
        extra_urls.append(args.add_url.strip())

    result = run_ingestion(
        mode=args.mode,
        force=args.force,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        enable_vision=args.enable_vision,
        extra_urls=extra_urls,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
