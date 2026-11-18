"""
通用型多產品雙軌 RAG 引擎 - 完整自動化單元與整合測試套件
驗證項目：
1. 跨機器可攜性檢查（零本機硬編碼絕對路徑）
2. Product Profile 載入、合併與切換
3. PDF 與網站遞迴擷取雙軌寫入 (ChromaDB + SQLite FTS5) 與混合檢索
4. GroundingAuditor 防幻覺指令攔截與出處標註驗證
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict

import fitz  # PyMuPDF

# 確保優先匯入 universal-rag-template 根目錄模組
TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
if str(TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_ROOT))

import config
from grounding_auditor import GroundingAuditor
import ingest
from parser import extract_clean_page_content, should_follow_link
from profile_loader import list_available_profiles, load_active_profile
import vector_store


class TestUniversalRagTemplate(unittest.TestCase):
    """通用型雙軌 RAG 範本完整回歸測試"""

    def setUp(self) -> None:
        """建立隔離的臨時資料與向量庫目錄，避免污染真實環境"""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="universal_rag_test_"))
        self._orig_raw_dir = config.RAW_DATA_DIR
        self._orig_pdf_dir = config.RAW_PDF_DIR
        self._orig_urls_file = config.RAW_URLS_FILE
        self._orig_manifest_file = config.MANIFEST_FILE
        self._orig_visited_file = config.GLOBAL_VISITED_URLS_FILE
        self._orig_hashes_file = config.GLOBAL_CONTENT_HASHES_FILE
        self._orig_vdb_dir = config.VECTOR_DB_DIR
        self._orig_images_dir = config.EXTRACTED_IMAGES_DIR

        config.RAW_DATA_DIR = self.temp_dir / "raw_data"
        config.RAW_PDF_DIR = config.RAW_DATA_DIR / "pdfs"
        config.RAW_URLS_FILE = config.RAW_DATA_DIR / "web_urls.txt"
        config.MANIFEST_FILE = config.RAW_DATA_DIR / "manifest.json"
        config.GLOBAL_VISITED_URLS_FILE = config.RAW_DATA_DIR / "global_visited_urls.json"
        config.GLOBAL_CONTENT_HASHES_FILE = config.RAW_DATA_DIR / "global_content_hashes.json"
        config.VECTOR_DB_DIR = self.temp_dir / "vector_db"
        config.EXTRACTED_IMAGES_DIR = config.RAW_DATA_DIR / "extracted_images"

        config.RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
        config.VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        vector_store.reset_vector_store_cache()

    def tearDown(self) -> None:
        """還原設定並清除臨時測試目錄"""
        vector_store.reset_vector_store_cache()
        config.RAW_DATA_DIR = self._orig_raw_dir
        config.RAW_PDF_DIR = self._orig_pdf_dir
        config.RAW_URLS_FILE = self._orig_urls_file
        config.MANIFEST_FILE = self._orig_manifest_file
        config.GLOBAL_VISITED_URLS_FILE = self._orig_visited_file
        config.GLOBAL_CONTENT_HASHES_FILE = self._orig_hashes_file
        config.VECTOR_DB_DIR = self._orig_vdb_dir
        config.EXTRACTED_IMAGES_DIR = self._orig_images_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_hardcoded_local_user_paths(self) -> None:
        """驗證整個 universal-rag-template 專案不包含任何寫死的本機絕對路徑"""
        # 以動態拼接方式組合比對詞，避免測試程式碼自身觸發比對
        forbidden_tokens = ["/Users/" + "johnkuo", "GoogleDrive-" + "johnyhkuo"]
        text_suffixes = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".txt", ".example"}

        for path in TEMPLATE_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".venv", "__pycache__", "vector_db", ".pytest_cache"} for part in path.parts):
                continue
            if path.suffix in text_suffixes or path.name in {".gitignore", ".env.example"}:
                content = path.read_text(encoding="utf-8", errors="ignore")
                for token in forbidden_tokens:
                    self.assertNotIn(
                        token,
                        content,
                        msg=f"檔案 {path} 含有寫死的本機路徑 '{token}'，違反跨電腦可攜性規範",
                    )

    def test_profile_loading_and_switching(self) -> None:
        """驗證預設與範例 Product Profile 皆可正常載入與列舉"""
        available = list_available_profiles()
        self.assertIn("default", available)
        self.assertIn("examples/ibm_flashsystem", available)

        default_prof = load_active_profile("default")
        self.assertEqual(default_prof["product_id"], "default_product")
        self.assertFalse(default_prof["cli_validation"]["enabled"])
        self.assertEqual(default_prof["crawler"]["url_allow_patterns"], [])

        ibm_prof = load_active_profile("examples/ibm_flashsystem")
        self.assertEqual(ibm_prof["product_id"], "ibm_flashsystem")
        self.assertTrue(ibm_prof["cli_validation"]["enabled"])
        self.assertIn("chnodeip", ibm_prof["cli_validation"]["blocklist"])

    def test_generic_web_link_filtering_and_html_cleaning(self) -> None:
        """驗證網站爬蟲不再受限於特定產品關鍵字，且能正確過濾外部網域與執行檔"""
        default_prof = load_active_profile("default")
        crawler_cfg = default_prof["crawler"]

        # 非 FlashSystem 的一般產品技術文件網站應允許追蹤同路徑子頁
        self.assertTrue(
            should_follow_link(
                "https://docs.example.com/myproduct/install.html",
                base_domain="docs.example.com",
                base_path_prefix="/myproduct",
                crawler_cfg=crawler_cfg,
            )
        )
        # 應過濾跨網域與壓縮檔
        self.assertFalse(
            should_follow_link(
                "https://other-site.com/myproduct/install.html",
                base_domain="docs.example.com",
                base_path_prefix="/myproduct",
                crawler_cfg=crawler_cfg,
            )
        )
        self.assertFalse(
            should_follow_link(
                "https://docs.example.com/myproduct/sdk.tar.gz",
                base_domain="docs.example.com",
                base_path_prefix="/myproduct",
                crawler_cfg=crawler_cfg,
            )
        )

        sample_html = (
            "<html><head><script>alert(1);</script></head>"
            "<body><nav>Menu</nav><main><h1>NovaRouter Setup</h1>"
            "<p>Use <code>novacli cluster init</code> to initialize.</p>"
            "<a href='guide.html'>Guide</a></main></body></html>"
        )
        clean_md, links = extract_clean_page_content(sample_html)
        self.assertIn("NovaRouter Setup", clean_md)
        self.assertNotIn("Menu", clean_md)
        self.assertNotIn("alert(1)", clean_md)
        self.assertIn("guide.html", links)

    def test_dual_track_pdf_and_web_ingestion_and_query(self) -> None:
        """驗證 PDF 與網站遞迴擷取可同步寫入 ChromaDB + SQLite FTS5 並支援雙軌查詢"""
        # 1. 建立測試用新產品 PDF 手冊
        pdf_path = config.RAW_PDF_DIR / "novarouter_admin_guide.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            "NovaRouter X900 Hardware Specification\n"
            "Token: NRX900-BGP-QUORUM-7788\n"
            "Each NovaRouter X900 supports dual redundant power supplies and 100GbE QSFP28 uplinks.",
        )
        doc.save(str(pdf_path))
        doc.close()

        # 2. 建立模擬的多層網站頁面（不依賴外部網路）
        mock_pages: Dict[str, str] = {
            "https://docs.novarouter.io/v2/index.html": (
                "<html><body><main><h1>NovaRouter v2 Docs</h1>"
                "<p>Welcome to NovaRouter v2 documentation portal.</p>"
                "<a href='cluster.html'>Cluster Guide</a></main></body></html>"
            ),
            "https://docs.novarouter.io/v2/cluster.html": (
                "<html><body><main><h1>NovaRouter Cluster Initialization</h1>"
                "<p>Run command: novacli cluster bootstrap --quorum-token NRX900-WEB-9911</p>"
                "</main></body></html>"
            ),
        }

        def fake_fetcher(url: str) -> str:
            return mock_pages.get(url, "")

        # 3. 執行統一建庫（同時匯入 PDF 與網站遞迴爬取）
        summary = ingest.run_ingestion(
            mode="all",
            force=True,
            max_depth=2,
            max_pages=10,
            extra_urls=["https://docs.novarouter.io/v2/index.html"],
            fetcher=fake_fetcher,
        )

        self.assertEqual(summary["pdfs_processed"], 1)
        self.assertGreaterEqual(summary["pdf_chunks_added"], 1)
        self.assertEqual(summary["web_pages_processed"], 2)
        self.assertGreaterEqual(summary["web_chunks_added"], 2)

        fts_stats = vector_store.get_fts_stats()
        self.assertEqual(fts_stats["pdf_files"], 1)
        self.assertEqual(fts_stats["web_pages"], 2)

        # 4. 驗證雙軌檢索可精確命中 PDF 專屬碼與網頁專屬碼
        pdf_hits = vector_store.query_kb("NRX900-BGP-QUORUM-7788", top_k=5)
        self.assertTrue(
            any("novarouter_admin_guide.pdf" in str(h["metadata"].get("source", "")) for h in pdf_hits),
            msg=f"未從雙軌檢索命中新 PDF，實際回傳: {pdf_hits}",
        )

        web_hits = vector_store.query_kb("NRX900-WEB-9911", top_k=5)
        self.assertTrue(
            any(h["metadata"].get("url") == "https://docs.novarouter.io/v2/cluster.html" for h in web_hits),
            msg=f"未從雙軌檢索命中遞迴爬取的網頁 URL，實際回傳: {web_hits}",
        )

    def test_grounding_auditor_citations_and_profile_blocklist(self) -> None:
        """驗證防幻覺審計器對來源標註與 Profile 禁用指令的攔截能力"""
        default_auditor = GroundingAuditor(profile_name="default")
        # 缺少出處標註應判不通過
        missing_cite = default_auditor.audit_response(
            "如何初始化叢集？",
            "請執行 `novacli cluster bootstrap` 完成叢集初始化。",
        )
        self.assertFalse(missing_cite["passed"])
        self.assertFalse(missing_cite["has_valid_citations"])

        # 附帶網頁 URL 或 PDF 頁碼後應通過
        valid_web_cite = default_auditor.audit_response(
            "如何初始化叢集？",
            "請執行 `novacli cluster bootstrap` 完成叢集初始化 [來源: https://docs.novarouter.io/v2/cluster.html]。",
        )
        self.assertTrue(valid_web_cite["passed"])
        self.assertTrue(valid_web_cite["has_valid_citations"])

        # 切換至範例 Profile 後，應能攔截禁用 CLI 指令
        ibm_auditor = GroundingAuditor(profile_name="examples/ibm_flashsystem")
        blocked_res = ibm_auditor.audit_response(
            "如何修改節點 IP？",
            "請執行 `chnodeip -ip 10.0.0.1` [來源: sg248542.pdf, 第 10 頁]。",
        )
        self.assertFalse(blocked_res["passed"])
        self.assertTrue(any("chnodeip" in v for v in blocked_res["violations"]))
        self.assertTrue(any("chportethernet" in s for s in blocked_res["suggestions"]))


if __name__ == "__main__":
    unittest.main()
