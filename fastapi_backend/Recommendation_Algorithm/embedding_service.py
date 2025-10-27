# -*- coding: utf-8 -*-
"""
简单同步版 embedding 服务
"""
from functools import lru_cache
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
# 768 维向量，直接用于 pgvector (float4[])
# 该模型在中文、英文、德文等多种语言上表现良好
# 参考：https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2
# 该模型在中文、英文、德文等多种语言上表现良好
# 参考：https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2
# 该模型在中文、英文、德文等多种语言上表现良好

@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    # 进程内只加载一次，gunicorn/uvicorn worker 会各自持有一份
    return SentenceTransformer(MODEL_NAME)

def get_embedding(text: str) -> List[float]:
    """
    将任意文本转 768 维向量，直接用于 pgvector (float4[])
    """
    if not text:
        return None
    model = _load_model()
    emb: np.ndarray = model.encode(text, normalize_embeddings=True)
    # 转成 Python list，SQLAlchemy 自动映射到 pg vector
    return emb.tolist()
