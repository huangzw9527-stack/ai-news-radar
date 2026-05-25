"""采集阶段的 AI 相关性预筛（仅用于标记了 keyword_filter 的信源）。"""

import re
from typing import List

_BASE_KEYWORDS = [
    "AI", "人工智能", "artificial intelligence",
    "机器学习", "machine learning", "深度学习", "deep learning",
    "大模型", "大语言模型", "LLM", "语言模型",
    "GPT", "ChatGPT", "Claude", "Gemini", "Llama",
    "DeepSeek", "Qwen", "通义", "文心", "Kimi", "MiniMax",
    "开源模型", "基座模型", "foundation model",
    "智能体", "Agent", "RAG", "Copilot",
    "AIGC", "生成式", "多模态", "multimodal",
    "GPU", "TPU", "芯片", "算力", "推理", "微调", "fine-tun",
    "AI治理", "AI安全", "AI监管", "AI伦理",
    "融资", "估值", "并购",
]


def _build_regex(keywords: List[str]) -> re.Pattern:
    patterns = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if re.match(r'^[a-zA-Z]+$', kw) and len(kw) <= 4:
            patterns.append(rf'\b{re.escape(kw)}\b')
        else:
            patterns.append(re.escape(kw))
    if not patterns:
        return re.compile(r'(?!)')
    return re.compile("|".join(patterns), re.IGNORECASE)


# 模块加载时即用 _BASE_KEYWORDS 初始化，不再需要外部预热
_BASE_RE = _build_regex(_BASE_KEYWORDS)


def is_ai_related(title: str, summary: str = "") -> bool:
    """判断标题/摘要是否包含基础 AI 关键词。仅供 keyword_filter=true 的信源调用。"""
    return bool(_BASE_RE.search(f"{title} {summary}"))
