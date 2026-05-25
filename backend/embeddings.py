"""共享的句向量模型单例，供去重和排名等模块复用，避免重复加载。"""

_model = None
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model
