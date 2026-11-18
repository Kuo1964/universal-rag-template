"""
通用型多產品雙軌 RAG 引擎 - 系統設定檔
採用 100% 相對路徑與環境變數動態解析，確保跨電腦與跨 AI 智能體開箱即用。
"""

import os
from pathlib import Path
from typing import Dict


def load_dotenv_file(env_path: Path) -> None:
    """解析指定路徑之 .env 檔案並寫入尚未定義的環境變數"""
    if not env_path.is_file():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass


# 專案根目錄（基於檔案自身位置動態推導，絕不使用硬編碼絕對路徑）
BASE_DIR: Path = Path(__file__).resolve().parent

# 優先載入專案根目錄下的 .env 設定檔
load_dotenv_file(BASE_DIR / ".env")

# 產品設定檔 (Product Profiles) 目錄與當前啟用名稱
PROFILES_DIR: Path = BASE_DIR / "profiles"
ACTIVE_PROFILE: str = os.getenv("ACTIVE_PROFILE", "default").strip() or "default"

# 原始資料、PDF 與網頁擷取快取目錄
RAW_DATA_DIR: Path = BASE_DIR / "raw_data"
RAW_PDF_DIR: Path = RAW_DATA_DIR / "pdfs"
RAW_URLS_FILE: Path = RAW_DATA_DIR / "web_urls.txt"
MANIFEST_FILE: Path = RAW_DATA_DIR / "manifest.json"
GLOBAL_VISITED_URLS_FILE: Path = RAW_DATA_DIR / "global_visited_urls.json"
GLOBAL_CONTENT_HASHES_FILE: Path = RAW_DATA_DIR / "global_content_hashes.json"
GLOBAL_URL_QUEUE_FILE: Path = RAW_DATA_DIR / "global_url_queue.json"
EXTRACTED_IMAGES_DIR: Path = RAW_DATA_DIR / "extracted_images"

# 智慧定位向量庫目錄（環境變數 VECTOR_DB_PATH 優先，否則使用專案根目錄 ./vector_db）
_env_vdb_path = os.getenv("VECTOR_DB_PATH", "").strip()
VECTOR_DB_DIR: Path = Path(_env_vdb_path).expanduser().resolve() if _env_vdb_path else (BASE_DIR / "vector_db")

# 處理斷裂的符號連結（避免跨電腦遷移後軟連結失效）
if VECTOR_DB_DIR.is_symlink() and not VECTOR_DB_DIR.exists():
    VECTOR_DB_DIR.unlink()

# 確保必要目錄存在
for _dir in [PROFILES_DIR, RAW_DATA_DIR, RAW_PDF_DIR, EXTRACTED_IMAGES_DIR, VECTOR_DB_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# 確保預設 web_urls.txt 範本存在
if not RAW_URLS_FILE.exists():
    RAW_URLS_FILE.write_text(
        "# 請於此處逐行貼上要擷取的產品官方文件網址（支援動態 SPA 與同網域遞迴爬取）\n",
        encoding="utf-8",
    )

# ChromaDB 集合名稱（預設依當前 Profile 隔離，亦可由環境變數指定）
def get_collection_name(profile_name: str = "") -> str:
    """取得目前使用的 ChromaDB 集合名稱"""
    custom_name = os.getenv("CHROMA_COLLECTION_NAME", "").strip()
    if custom_name:
        return custom_name
    target_profile = (profile_name or os.getenv("ACTIVE_PROFILE", ACTIVE_PROFILE)).strip() or "default"
    safe_suffix = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in target_profile)
    return f"rag_kb_{safe_suffix}"


CHROMA_COLLECTION_NAME: str = get_collection_name()

# 向量嵌入設定（預設使用 fastembed 離線 ONNX 768 維模型，免依賴 Ollama）
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "fastembed").strip().lower()
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text").strip()
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()
VISION_MODEL: str = os.getenv("VISION_MODEL", "llama3.2-vision").strip()

# 選配 LLM 設定（僅在獨立呼叫 ask_expert 或啟動 Web Portal 時使用）
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()

# Web Portal 伺服器設定
PORTAL_PORT: int = int(os.getenv("PORTAL_PORT", "8888"))
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")

# 文本切片與圖片提取閾值參數
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))
MIN_IMAGE_WIDTH: int = int(os.getenv("MIN_IMAGE_WIDTH", "200"))
MIN_IMAGE_HEIGHT: int = int(os.getenv("MIN_IMAGE_HEIGHT", "150"))

# 供診斷用的路徑快照
def get_runtime_summary() -> Dict[str, str]:
    """回傳目前執行時期的關鍵路徑與組態摘要"""
    return {
        "base_dir": str(BASE_DIR),
        "active_profile": os.getenv("ACTIVE_PROFILE", ACTIVE_PROFILE),
        "vector_db_dir": str(VECTOR_DB_DIR),
        "collection_name": get_collection_name(),
        "embedding_provider": EMBEDDING_PROVIDER,
    }
