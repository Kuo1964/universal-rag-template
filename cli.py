#!/usr/bin/env python3
"""
通用多產品雙軌 RAG 引擎 - 統一命令列介面 (Universal CLI)
提供一鍵式跨 Agent 配置 (install)、MCP 伺服器啟動 (mcp)、資料建庫 (ingest)、
終端檢索 (search)、防幻覺審計 (audit) 與知識庫統計 (stats)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

# 確保當前目錄位於 sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from grounding_auditor import GroundingAuditor
import ingest
from profile_loader import list_available_profiles, load_active_profile
from provisioner import install_for_agents, list_supported_agents
import vector_store


def cmd_install(args: argparse.Namespace) -> int:
    """執行一鍵跨 Agent 配置 (Claude Code, Bob, Codex, Antigravity, Cursor)"""
    target_dir = Path(args.dir).resolve() if args.dir else BASE_DIR
    print(f"🚀 正在為目錄配置 AI Agent 擴充環境: {target_dir}")
    print(f"🎯 目標代理: {args.agent} (支援: {', '.join(list_supported_agents())}, all, auto)\n")

    results = install_for_agents(
        target_dir=target_dir,
        agent_choice=args.agent,
        mcp_command=args.cmd,
        mcp_args=args.args,
        force=args.force,
    )

    for res in results:
        print(res.summary())
        print()

    print("🎉 跨代理配置作業已全數完成！")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """啟動 MCP 伺服器 (stdio 協定)"""
    import mcp_server

    mcp_server.mcp.run()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """終端雙軌混合檢索"""
    query = " ".join(args.query).strip()
    if not query:
        print("❌ 請提供檢索關鍵字或提問。範例: universal-rag search '硬體接線規範'")
        return 1

    profile = load_active_profile()
    product_name = str(profile.get("product_name", "General Technical Product"))
    print(f"🔍 正在雙軌檢索 [{product_name}]: {query}\n" + "=" * 60)

    results = vector_store.query_kb(query_text=query, top_k=args.top_k)
    if not results:
        print("⚠️ 未檢索到相關資料。請先放入 PDF 或新增網址執行建庫。")
        return 0

    for idx, item in enumerate(results, 1):
        meta = item.get("metadata", {})
        score = item.get("similarity_score", 0.0)
        channel = item.get("channel", "hybrid")
        doc_type = meta.get("type", "pdf")
        content = item.get("content", "")

        if doc_type == "web" or "url" in meta:
            src_str = f"🌐 網頁: {meta.get('url', meta.get('source'))}"
        else:
            src_str = f"📄 PDF: {meta.get('source')}, 第 {meta.get('page', 1)} 頁"

        print(f"[{idx}] ({channel} | 信心度: {score:.2f}) {src_str}")
        print(content[:300].strip() + ("..." if len(content) > 300 else ""))
        print("-" * 60)

    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """終端防幻覺與出處審計"""
    answer_text = args.answer.strip()
    query_text = args.query.strip()
    if not answer_text:
        print("❌ 請提供要審計的回答草稿。")
        return 1

    auditor = GroundingAuditor()
    report = auditor.audit_response(query=query_text, answer_text=answer_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") else 2


def cmd_ingest(args: argparse.Namespace) -> int:
    """執行 PDF 與網站遞迴擷取建庫"""
    extra_urls: List[str] = []
    if args.add_url:
        ingest.append_seed_url(args.add_url)
        extra_urls.append(args.add_url)

    res = ingest.run_ingestion(
        mode=args.mode,
        force=args.force,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        enable_vision=args.enable_vision,
        extra_urls=extra_urls,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """查詢知識庫狀態"""
    profile = load_active_profile()
    fts_stats = vector_store.get_fts_stats()
    vector_cnt = vector_store.get_chroma_collection().count()
    manifest = ingest.load_manifest()

    print("📊 知識庫狀態報告")
    print(f"- 啟用產品: {profile.get('product_name')} ({profile.get('product_id')})")
    print(f"- 向量庫 Chunks 總數: {vector_cnt}")
    print(f"- FTS5 索引總行數: {fts_stats.get('total_fts_rows')} (PDF: {fts_stats.get('pdf_files')} 檔, 網頁: {fts_stats.get('web_pages')} 頁)")
    print(f"- 已索引 Manifest 筆數: {len(manifest)}")
    print(f"- 可用 Profiles: {', '.join(list_available_profiles())}")
    return 0


def main() -> None:
    """CLI 主入口與命令解析器"""
    parser = argparse.ArgumentParser(
        prog="universal-rag",
        description="通用多產品雙軌 RAG 引擎與多智能體配置工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # install 命令
    p_install = subparsers.add_parser("install", help="為 Claude, Bob, Codex, Antigravity, Cursor 等 Agent 一鍵註冊設定")
    p_install.add_argument("--agent", default="all", help="目標代理: all, auto, claude, bob, codex, antigravity, cursor")
    p_install.add_argument("--dir", default="", help="目標專案目錄（預設當前專案）")
    p_install.add_argument("--cmd", default="", help="自訂 MCP 啟動指令")
    p_install.add_argument("--args", nargs="*", default=None, help="自訂 MCP 啟動參數")
    p_install.add_argument("--force", action="store_true", help="強制覆寫既有配置")
    p_install.set_defaults(func=cmd_install)

    # mcp 命令
    p_mcp = subparsers.add_parser("mcp", help="啟動 Model Context Protocol (MCP) 伺服器")
    p_mcp.set_defaults(func=cmd_mcp)

    # search 命令
    p_search = subparsers.add_parser("search", help="終端執行雙軌混合檢索")
    p_search.add_argument("query", nargs="+", help="查詢詞")
    p_search.add_argument("--top-k", type=int, default=6, help="回傳筆數")
    p_search.set_defaults(func=cmd_search)

    # audit 命令
    p_audit = subparsers.add_parser("audit", help="審計回答草稿之出處標註與禁用指令")
    p_audit.add_argument("--query", default="", help="原始問題")
    p_audit.add_argument("--answer", required=True, help="回答草稿文本")
    p_audit.set_defaults(func=cmd_audit)

    # ingest 命令
    p_ingest = subparsers.add_parser("ingest", help="執行 PDF 與網站遞迴擷取建庫")
    p_ingest.add_argument("--mode", choices=["all", "pdf", "web"], default="all")
    p_ingest.add_argument("--add-url", default="", help="新增網站網址並立即爬取入庫")
    p_ingest.add_argument("--max-depth", type=int, default=2)
    p_ingest.add_argument("--max-pages", type=int, default=50)
    p_ingest.add_argument("--enable-vision", action="store_true")
    p_ingest.add_argument("--force", action="store_true")
    p_ingest.set_defaults(func=cmd_ingest)

    # stats 命令
    p_stats = subparsers.add_parser("stats", help="顯示知識庫與設定檔統計")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    exit_code = args.func(args)
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
