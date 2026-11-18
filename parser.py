"""
通用型多產品雙軌 RAG 引擎 - PDF 與網站遞迴擷取解析器
同時支援 PyMuPDF PDF 切片解析、httpx 靜態抓取與 Playwright 動態 SPA 渲染，
並完全依據當前 Product Profile 的 crawler 規則決定是否追蹤子連結。
"""

from __future__ import annotations

import hashlib
import io
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import httpx
import markdownify
from PIL import Image

import config
from profile_loader import load_active_profile

_DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def calculate_file_hash(file_path: Path) -> str:
    """計算檔案的 SHA-256 雜湊值，用於增量更新比對"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_text_chunks(
    text: str,
    source_name: str,
    page_num: int = 1,
    doc_type: str = "pdf",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """將長文本切分為含重疊區間的標準語意片段 (Chunks)"""
    chunks: List[Dict[str, Any]] = []
    clean_text = (text or "").strip()
    if not clean_text:
        return chunks

    chunk_size = max(200, config.CHUNK_SIZE)
    overlap = min(config.CHUNK_OVERLAP, chunk_size // 2)
    step = max(1, chunk_size - overlap)

    start = 0
    chunk_idx = 0
    while start < len(clean_text):
        end = start + chunk_size
        chunk_text = clean_text[start:end].strip()
        if chunk_text:
            meta: Dict[str, Any] = {
                "source": source_name,
                "page": int(page_num),
                "type": doc_type,
                "chunk_index": chunk_idx,
            }
            if extra_metadata:
                meta.update(extra_metadata)

            chunks.append(
                {
                    "chunk_id": f"{source_name}_p{page_num}_c{chunk_idx}",
                    "text": chunk_text,
                    "metadata": meta,
                }
            )
        chunk_idx += 1
        if end >= len(clean_text):
            break
        start += step

    return chunks


def parse_pdf(pdf_path: Path, extract_images: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """解析單一 PDF 檔案，萃取純文字 Chunks 與選配之技術圖表圖片"""
    source_name = pdf_path.name
    pdf_stem = pdf_path.stem
    text_chunks: List[Dict[str, Any]] = []
    image_records: List[Dict[str, Any]] = []

    pdf_image_dir = config.EXTRACTED_IMAGES_DIR / pdf_stem
    if extract_images:
        pdf_image_dir.mkdir(parents=True, exist_ok=True)

    try:
        with fitz.open(pdf_path) as doc:
            for page_idx in range(len(doc)):
                actual_page = page_idx + 1
                try:
                    page = doc[page_idx]
                    try:
                        page_text = page.get_text("text", flags=fitz.TEXTFLAGS_SEARCH)
                    except Exception:
                        page_text = page.get_text("text")

                    if page_text and page_text.strip():
                        text_chunks.extend(
                            create_text_chunks(
                                page_text,
                                source_name=source_name,
                                page_num=actual_page,
                                doc_type="pdf",
                            )
                        )

                    if not extract_images:
                        continue

                    try:
                        image_list = page.get_images(full=True)
                    except Exception:
                        image_list = []

                    for img_idx, img_info in enumerate(image_list):
                        if not img_info:
                            continue
                        xref = img_info[0]
                        try:
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image.get("image") if base_image else None
                            if not image_bytes or len(image_bytes) < 100:
                                continue

                            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                                width, height = pil_img.size
                                if width >= config.MIN_IMAGE_WIDTH and height >= config.MIN_IMAGE_HEIGHT:
                                    img_filename = f"page_{actual_page}_img_{img_idx}.jpg"
                                    save_path = pdf_image_dir / img_filename
                                    pil_img.convert("RGB").save(save_path, "JPEG", quality=90)
                                    image_records.append(
                                        {
                                            "image_id": f"{pdf_stem}_p{actual_page}_img{img_idx}",
                                            "image_path": str(save_path),
                                            "pdf_name": source_name,
                                            "page_number": actual_page,
                                            "width": width,
                                            "height": height,
                                        }
                                    )
                        except Exception:
                            continue
                except Exception as page_err:
                    print(f"  [警告] 解析 PDF 頁面失敗 ({source_name} 第 {actual_page} 頁): {page_err}")
                    continue
    except Exception as doc_err:
        print(f"  [錯誤] 開啟 PDF 失敗 ({source_name}): {doc_err}")

    return text_chunks, image_records


def fetch_rendered_html_with_playwright(url: str) -> str:
    """使用 Playwright 無頭瀏覽器渲染動態 JavaScript SPA 網頁"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [提示] 未安裝 playwright，略過動態瀏覽器渲染。")
        return ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                context = browser.new_context(
                    user_agent=_DEFAULT_HEADERS["User-Agent"],
                    extra_http_headers={"Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"},
                )
                page = context.new_page()
                page.route(
                    "**/*.{png,jpg,jpeg,svg,gif,webp,ico,woff,woff2,ttf,eot,css,mp4,avi,mkv}",
                    lambda route: route.abort(),
                )
                time.sleep(random.uniform(0.15, 0.35))
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                try:
                    page.wait_for_selector("article, main, #maincontent, .content, .markdown-body", timeout=4000)
                except Exception:
                    pass

                html = page.content()
                for frame in page.frames:
                    try:
                        frame_html = frame.content()
                        if len(frame_html) > 500 and frame_html not in html:
                            html += "\n" + frame_html
                    except Exception:
                        continue
                context.close()
                return html
            finally:
                browser.close()
    except Exception as exc:
        print(f"  [警告] Playwright 渲染網頁失敗 ({url}): {exc}")
        return ""


def extract_clean_page_content(html_content: str) -> Tuple[str, List[str]]:
    """從原始 HTML 清理導覽雜訊並萃取乾淨 Markdown 內文與所有超連結"""
    soup = BeautifulSoup(html_content or "", "html.parser")

    links: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag["href"]).strip()
        if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
            links.append(href)

    for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        element.decompose()

    md_text = markdownify.markdownify(
        str(soup),
        heading_style="ATX",
        escape_asterisks=False,
        bullets="-",
    )

    if "403: Forbidden" in md_text and "cannot be displayed" in md_text:
        return "", []

    clean_lines: List[str] = []
    for raw_line in md_text.splitlines():
        stripped = raw_line.strip()
        if stripped or (clean_lines and clean_lines[-1]):
            clean_lines.append(stripped)

    return "\n".join(clean_lines).strip(), links


def should_follow_link(
    full_link: str,
    base_domain: str,
    base_path_prefix: str,
    crawler_cfg: Dict[str, Any],
) -> bool:
    """依據 Product Profile 中的 crawler 規則判斷是否追蹤此子連結"""
    parsed = urlparse(full_link)
    if parsed.scheme not in ("http", "https"):
        return False

    exclude_exts = [str(ext).lower() for ext in (crawler_cfg.get("url_exclude_extensions") or [])]
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in exclude_exts):
        return False

    if crawler_cfg.get("same_domain_only", True) and parsed.netloc != base_domain:
        return False

    if crawler_cfg.get("same_path_prefix", True) and base_path_prefix:
        if not parsed.path.startswith(base_path_prefix):
            return False

    allow_patterns = [str(p).lower() for p in (crawler_cfg.get("url_allow_patterns") or []) if str(p).strip()]
    if allow_patterns:
        link_lower = full_link.lower()
        if not any(pat in link_lower for pat in allow_patterns):
            return False

    return True


def download_pdf_safely(pdf_url: str) -> Optional[Path]:
    """在爬蟲發現 PDF 連結時安全下載至 raw_data/pdfs/ 目錄"""
    try:
        clean_url = pdf_url.split("?")[0].split("#")[0]
        file_name = Path(urlparse(clean_url).path).name
        if not file_name.lower().endswith(".pdf"):
            return None

        config.RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
        save_path = config.RAW_PDF_DIR / file_name
        if save_path.exists():
            return save_path

        with httpx.Client(timeout=30.0, follow_redirects=True, headers=_DEFAULT_HEADERS) as client:
            resp = client.get(pdf_url)
            if resp.status_code == 200 and resp.content:
                save_path.write_bytes(resp.content)
                return save_path
    except Exception as exc:
        print(f"  [警告] 下載 PDF 失敗 ({pdf_url}): {exc}")
    return None


def parse_single_page(
    url: str,
    use_playwright: Optional[bool] = None,
    profile: Optional[Dict[str, Any]] = None,
    fetcher: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """
    抓取並解析單一技術網頁，回傳 Chunks、同範圍子連結與發現的 PDF 連結。
    參數 fetcher 可供測試注入假 HTML，避免測試依賴外部網路。
    """
    active_profile = profile or load_active_profile()
    crawler_cfg: Dict[str, Any] = active_profile.get("crawler") or {}
    allow_playwright = (
        bool(use_playwright)
        if use_playwright is not None
        else bool(crawler_cfg.get("use_playwright_fallback", True))
    )

    clean_target_url = url.strip().split("#")[0]
    base_parsed = urlparse(clean_target_url)
    base_domain = base_parsed.netloc
    path_parts = base_parsed.path.rstrip("/").split("/")[:-1]
    base_path_prefix = "/".join(path_parts)

    result: Dict[str, Any] = {
        "url": clean_target_url,
        "source_name": f"web_{hashlib.md5(clean_target_url.encode('utf-8')).hexdigest()[:12]}",
        "full_text": "",
        "chunks": [],
        "links": [],
        "pdf_links": [],
        "error": None,
    }

    try:
        html_content = ""
        if fetcher is not None:
            html_content = fetcher(clean_target_url)
        else:
            with httpx.Client(timeout=30.0, follow_redirects=True, headers=_DEFAULT_HEADERS) as client:
                resp = client.get(clean_target_url)
                if resp.status_code == 200:
                    html_content = resp.text

            # 偵測到空白或前端 SPA 殼層時自動回退 Playwright 渲染
            if allow_playwright and (len(html_content) < 1500 or "digitalData" in html_content):
                rendered = fetch_rendered_html_with_playwright(clean_target_url)
                if rendered and len(rendered) >= len(html_content):
                    html_content = rendered

        if not html_content:
            result["error"] = "Empty HTML content"
            return result

        page_text, raw_links = extract_clean_page_content(html_content)
        if not page_text:
            result["error"] = "No extractable text"
            return result

        source_name = result["source_name"]
        chunks = create_text_chunks(
            page_text,
            source_name=source_name,
            page_num=1,
            doc_type="web",
            extra_metadata={"url": clean_target_url, "parent_url": clean_target_url},
        )
        result["full_text"] = page_text
        result["chunks"] = chunks

        base_join_url = clean_target_url.split("?")[0]
        if not base_join_url.endswith("/") and "." not in Path(urlparse(base_join_url).path).name:
            base_join_url += "/"

        valid_links: List[str] = []
        pdf_links: List[str] = []
        for raw_link in raw_links:
            full_link = urljoin(base_join_url, raw_link).split("#")[0]
            if full_link.lower().endswith(".pdf"):
                pdf_links.append(full_link)
                continue
            if should_follow_link(full_link, base_domain, base_path_prefix, crawler_cfg):
                valid_links.append(full_link)

        result["links"] = sorted(set(valid_links))
        result["pdf_links"] = sorted(set(pdf_links))
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def crawl_website(
    seed_url: str,
    max_depth: int = 2,
    max_pages: int = 100,
    global_visited: Optional[Set[str]] = None,
    global_hashes: Optional[Set[str]] = None,
    profile: Optional[Dict[str, Any]] = None,
    fetcher: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """從種子網址出發執行同範圍廣度優先 (BFS) 遞迴擷取"""
    active_profile = profile or load_active_profile()
    crawler_cfg: Dict[str, Any] = active_profile.get("crawler") or {}
    auto_download_pdfs = bool(crawler_cfg.get("auto_download_pdfs", True))

    visited_local: Set[str] = set()
    visited_global = global_visited if global_visited is not None else set()
    hashes_global = global_hashes if global_hashes is not None else set()

    queue: List[Tuple[str, int]] = [(seed_url.strip().split("#")[0], 0)]
    pages_data: List[Dict[str, Any]] = []
    downloaded_pdfs: List[str] = []
    errors: List[str] = []

    while queue and len(visited_local) < max_pages:
        current_url, depth = queue.pop(0)
        if not current_url or current_url in visited_local or current_url in visited_global:
            continue

        visited_local.add(current_url)
        visited_global.add(current_url)

        page_res = parse_single_page(current_url, profile=active_profile, fetcher=fetcher)
        if page_res.get("error"):
            errors.append(f"{current_url}: {page_res['error']}")
            continue

        content_hash = hashlib.md5(page_res["full_text"].encode("utf-8")).hexdigest()
        if content_hash not in hashes_global:
            hashes_global.add(content_hash)
            pages_data.append(page_res)

        if auto_download_pdfs and fetcher is None:
            for pdf_link in page_res.get("pdf_links", []):
                saved = download_pdf_safely(pdf_link)
                if saved is not None:
                    downloaded_pdfs.append(str(saved))

        if depth < max_depth:
            for child_link in page_res.get("links", []):
                if child_link not in visited_local and child_link not in visited_global:
                    queue.append((child_link, depth + 1))

    return {
        "seed_url": seed_url,
        "pages_crawled": len(visited_local),
        "pages_indexed": len(pages_data),
        "pages": pages_data,
        "downloaded_pdfs": downloaded_pdfs,
        "errors": errors,
    }
