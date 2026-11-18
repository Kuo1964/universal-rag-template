#!/usr/bin/env bash
# 新電腦一鍵初始化腳本：建立獨立 Python 虛擬環境、安裝依賴並初始化目錄結構
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

echo "🚀 初始化通用多產品雙軌 RAG 專案：${PROJECT_ROOT}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ 找不到 python3，請先安裝 Python 3.10+。"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "📦 正在建立虛擬環境 .venv..."
  python3 -m venv .venv
fi

echo "📥 正在安裝相依套件 (requirements.txt)..."
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/pip" install -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "📝 已建立預設 .env（使用 fastembed 離線 768 維向量，免安裝 Ollama 或外部 API Key）"
fi

mkdir -p raw_data/pdfs vector_db
if [ ! -f "raw_data/web_urls.txt" ]; then
  cat << 'EOF' > raw_data/web_urls.txt
# 請於此處逐行貼上要擷取的產品官方文件網址（支援動態 SPA 與同網域遞迴爬取）
EOF
fi

echo "✅ 環境初始化完成！"
echo "下一步："
echo "  1. 將產品 PDF 放入 raw_data/pdfs/ 或將文件網址填入 raw_data/web_urls.txt"
echo "  2. 用 IBM Bob 或其他支援 MCP 的智能體開啟此目錄，即可自動連線使用！"
