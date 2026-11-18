"""
通用型多產品雙軌 RAG 引擎 - 通用向量嵌入轉接器 (Universal Embedding Adapter)
支援 Zero-Server 預設 fastembed (ONNX 768 維)、選配 Ollama 與安全確定性特徵投影回退。
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, List, Optional

import chromadb
import httpx

import config

logger = logging.getLogger(__name__)


class UniversalEmbeddingFunction(chromadb.EmbeddingFunction):
    """
    通用向量嵌入適配器（768 維）
    優先順序依 EMBEDDING_PROVIDER 決定：
    - fastembed（預設）：離線 ONNX nomic-embed-text-v1.5 推論，新電腦免裝 Ollama
    - ollama：連線本機或遠端 Ollama API，失敗時自動回退 fastembed
    - 安全防線：特徵雜湊投影 768 維 L2 正規化向量，確保極端環境零崩潰
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        host: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.provider: str = (provider or config.EMBEDDING_PROVIDER or "fastembed").strip().lower()
        self.model_name: str = (model_name or config.EMBEDDING_MODEL or "nomic-embed-text").strip()
        self.host: str = (host or config.OLLAMA_HOST or "http://localhost:11434").rstrip("/")
        self.timeout: float = timeout
        self._fastembed_model: Any = None
        self._fastembed_init_attempted: bool = False

    @staticmethod
    def name() -> str:
        """回傳 ChromaDB 識別用之 Embedding Function 名稱"""
        return "universal_768d_embedding"

    def _get_fastembed_model(self) -> Any:
        """延遲載入 fastembed ONNX 模型（768 維度）"""
        if not self._fastembed_init_attempted:
            self._fastembed_init_attempted = True
            try:
                from fastembed import TextEmbedding

                self._fastembed_model = TextEmbedding("nomic-ai/nomic-embed-text-v1.5")
                logger.info("已成功載入 fastembed nomic-embed-text-v1.5 ONNX 模型。")
            except Exception as exc:
                logger.debug("無法載入 fastembed (%s)，將使用備援機制。", exc)
                self._fastembed_model = None
        return self._fastembed_model

    def _embed_via_fastembed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """嘗試透過 fastembed 產生向量"""
        model = self._get_fastembed_model()
        if model is None:
            return None
        try:
            vectors = list(model.embed(texts))
            return [[float(val) for val in vec] for vec in vectors]
        except Exception as exc:
            logger.warning("fastembed 向量計算失敗: %s", exc)
            return None

    def _embed_via_ollama(self, texts: List[str]) -> Optional[List[List[float]]]:
        """嘗試透過 Ollama API 產生 768 維向量"""
        try:
            embeddings: List[List[float]] = []
            for text in texts:
                resp = httpx.post(
                    f"{self.host}/api/embeddings",
                    json={"model": self.model_name, "prompt": text},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
                vec = payload.get("embedding")
                if not isinstance(vec, list) or len(vec) != 768:
                    raise ValueError("Ollama 回傳向量格式或維度不為 768")
                embeddings.append([float(v) for v in vec])
            return embeddings
        except Exception as exc:
            logger.warning("Ollama Embedding 連線失敗 (%s)，啟動自動回退。", exc)
            return None

    @staticmethod
    def _generate_fallback_vector(text: str, dim: int = 768) -> List[float]:
        """當無外部模型或離線套件尚未就緒時之確定性 768 維特徵投影向量（L2 正規化）"""
        raw_vals: List[float] = []
        salt = 0
        while len(raw_vals) < dim:
            digest = hashlib.sha512(f"{text}_{salt}".encode("utf-8")).digest()
            for byte_val in digest:
                raw_vals.append((float(byte_val) / 255.0) - 0.5)
                if len(raw_vals) >= dim:
                    break
            salt += 1

        norm = math.sqrt(sum(val * val for val in raw_vals)) or 1.0
        return [val / norm for val in raw_vals]

    def __call__(self, input: List[str]) -> List[List[float]]:
        """計算輸入文字清單的 768 維向量列表"""
        if not input:
            return []

        if self.provider == "ollama":
            result = self._embed_via_ollama(input)
            if result is not None:
                return result
            result = self._embed_via_fastembed(input)
            if result is not None:
                return result
        else:
            result = self._embed_via_fastembed(input)
            if result is not None:
                return result
            # 若預設 fastembed 尚未安裝，嘗試本機是否剛好有運行 Ollama
            result = self._embed_via_ollama(input)
            if result is not None:
                return result

        logger.info("使用安全確定性特徵投影產生 768 維向量。")
        return [self._generate_fallback_vector(text, dim=768) for text in input]
