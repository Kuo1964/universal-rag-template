"""
通用型多產品雙軌 RAG 引擎 - 產品設定檔載入器 (Product Profile Loader)
負責解析 profiles/*.yaml，動態注入專家角色設定、同義詞擴展、CLI 防幻覺規則與爬蟲過濾器。
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

import config

DEFAULT_PROFILE_TEMPLATE: Dict[str, Any] = {
    "product_id": "default_product",
    "product_name": "General Technical Product",
    "expert_persona": "你是一位精通本產品系列架構、安裝配置、故障排除與最佳實踐的原廠首席技術顧問。",
    "citation_format": "[來源: {source}, 第 {page} 頁]",
    "web_citation_format": "[來源: {url}]",
    "synonyms": {},
    "cli_validation": {
        "enabled": False,
        "allowlist": [],
        "blocklist": {},
    },
    "domain_guardrails": [
        "每一條核心技術論點、操作步驟與指令，必須在段落末尾標註官方來源（PDF 頁碼或原始網頁 URL）。",
        "若知識庫檢索結果未記載該功能或參數，必須誠實宣告官方未記載，嚴禁臆測。",
    ],
    "crawler": {
        "same_domain_only": True,
        "same_path_prefix": True,
        "url_allow_patterns": [],
        "url_exclude_extensions": [".zip", ".exe", ".iso", ".tar", ".gz", ".dmg", ".pkg", ".msi"],
        "auto_download_pdfs": True,
        "use_playwright_fallback": True,
    },
}


def get_default_profile() -> Dict[str, Any]:
    """取得預設通用設定檔的深拷貝"""
    return copy.deepcopy(DEFAULT_PROFILE_TEMPLATE)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """將覆寫字典遞迴合併至基礎範本中"""
    merged = copy.deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = copy.deepcopy(val)
    return merged


def resolve_profile_path(profile_name: Optional[str] = None) -> Optional[Path]:
    """解析設定檔名稱對應之 YAML 檔案路徑"""
    target = (profile_name or os.getenv("ACTIVE_PROFILE", config.ACTIVE_PROFILE)).strip() or "default"
    clean_name = target[:-5] if target.endswith(".yaml") else target

    candidates: List[Path] = [
        config.PROFILES_DIR / f"{clean_name}.yaml",
        config.PROFILES_DIR / f"{clean_name}.yml",
        config.PROFILES_DIR / "examples" / f"{clean_name}.yaml",
        config.PROFILES_DIR / "examples" / f"{clean_name}.yml",
    ]
    direct_path = Path(target)
    if direct_path.is_file():
        candidates.insert(0, direct_path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_active_profile(profile_name: Optional[str] = None) -> Dict[str, Any]:
    """載入當前啟用的產品 YAML 設定檔，並與預設結構安全合併"""
    base = get_default_profile()
    profile_path = resolve_profile_path(profile_name)
    if profile_path is None:
        return base

    try:
        raw_text = profile_path.read_text(encoding="utf-8")
        loaded = yaml.safe_load(raw_text) or {}
        if not isinstance(loaded, dict):
            return base
        merged = _deep_merge(base, loaded)
        merged["_profile_path"] = str(profile_path)
        return merged
    except Exception:
        return base


def list_available_profiles() -> List[str]:
    """列出 profiles/ 目錄下所有可用的設定檔名稱"""
    if not config.PROFILES_DIR.exists():
        return []
    found: List[str] = []
    for path in sorted(config.PROFILES_DIR.rglob("*.yaml")):
        rel = path.relative_to(config.PROFILES_DIR)
        found.append(str(rel.with_suffix("")))
    return found
