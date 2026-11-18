# Universal Dual-Track RAG Engine Context

Product-agnostic, zero-hardcoded-path Retrieval-Augmented Generation (RAG) template with dual-track retrieval (ChromaDB + SQLite FTS5) and Model Context Protocol (MCP) integration for IBM Bob and multi-agent systems.

## Language & Domain Vocabulary

### Retrieval & Indexing Architecture

**Dual-Track Hybrid Retrieval**:
Combining semantic vector similarity (ChromaDB with 768-d embeddings) and exact lexical BM25 matching (SQLite FTS5 across all PDFs and scraped web pages).
_Avoid_: Vector-only search, naive keyword grep

**Product Profile (`profiles/*.yaml`)**:
Declarative YAML configuration defining `expert_persona`, `synonyms`, `cli_validation` (allowlist/blocklist), `domain_guardrails`, and `crawler` rules for any target product line.
_Avoid_: Hardcoded product prompts, inline keyword filters

**Zero-Server Default Embedding**:
Offline 768-dimensional vector inference powered by `fastembed` (`nomic-embed-text-v1.5` ONNX), removing mandatory dependency on external Ollama servers during initial setup.
_Avoid_: Mandatory external vector API, unseeded random embeddings

**Grounded Citation Audit (`audit_grounding`)**:
Deterministic post-generation verification checking answer drafts against product-specific CLI blocklists and mandatory source citation tags (PDF page numbers or scraped URLs).
_Avoid_: Unverified LLM answers, ungrounded claims
