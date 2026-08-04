"""
backend/ai_assistant/embedding_service.py
──────────────────────────────────────────
提供向量 Embedding 计算工具函数。

调用 LiteLLM Embeddings API（与现有 AI 配置复用同一 api_base/api_key）。
若 embed_model 未配置，或调用失败，静默返回 None（降级为 LIKE 关键词搜索）。

AI 配置（通过后端 ai_cfg 表）新增可选字段：
  {
    "embed_model": "nomic-embed-text",   // Ollama 本地；或 "text-embedding-3-small"
    "embed_dim":   768                    // 向量维度，需与模型匹配，默认 768
  }
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def _get_ai_cfg() -> dict:
    """从后端 AI 配置读取 ai_cfg，失败返回空字典。"""
    try:
        from ..routers.ai_chat import _get_ai_config
        cfg = _get_ai_config(owner_gid="")
        return dict(cfg or {})
    except Exception:
        return {}


def compute_embedding(text: str) -> list[float] | None:
    """
    将文本转换为 float 向量（embedding）。
    - 成功：返回 list[float]
    - embed_model 未配置 / 调用失败：返回 None（调用方降级 LIKE 搜索）
    """
    if not text or not text.strip():
        return None
    try:
        ai_cfg = _get_ai_cfg()
        embed_model: str = (ai_cfg.get("embed_model") or "").strip()
        if not embed_model:
            return None

        import litellm
        resp = litellm.embedding(
            model=embed_model,
            input=[text.strip()[:2000]],   # 截断过长文本
            api_base=ai_cfg.get("api_base") or None,
            api_key=ai_cfg.get("api_key")  or None,
        )
        vec = resp.data[0]["embedding"]
        return vec
    except Exception as e:
        logger.debug(f"[EmbeddingService] 向量计算跳过（降级 LIKE）: {e}")
        return None


def get_embed_dim() -> int:
    """读取配置中的向量维度，默认 768。"""
    try:
        ai_cfg = _get_ai_cfg()
        return int(ai_cfg.get("embed_dim") or 768)
    except Exception:
        return 768
