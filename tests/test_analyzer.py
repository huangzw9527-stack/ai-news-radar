import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.analyzer import Analyzer
from backend.llm.base import BaseLLMProvider

class MockLLM(BaseLLMProvider):
    def __init__(self):
        super().__init__("mock", "")
    def chat(self, system: str, user: str) -> str:
        items = {}
        for i in range(1, 11):
            items[str(i)] = {
                "title": f"中文标题{i}",
                "summary": f"摘要{i}",
                "brief": f"简摘{i}",
                "why_matters": f"为什么值得关注{i}",
                "main_category": "模型发布",
                "aux_tags": ["标签1"],
                "concept": "概念",
                "principle": "原理",
            }
        return json.dumps({"items": items})

def make_news(id_):
    return {
        "id": id_,
        "title": f"新闻{id_}",
        "summary": "摘要",
        "full_text": "全文",
        "score": 50.0,
        "url": f"https://ex.com/{id_}",
        "source_name": "Test",
        "institution": "Test",
        "indicator": "academic"
    }

def test_analyze_returns_report_structure():
    news_list = [make_news(f"id{i}") for i in range(1, 4)]
    analyzer = Analyzer(llm=MockLLM())
    result = analyzer.analyze(news_list)
    assert "top10" in result
    assert "briefing" in result
    assert "headlines" in result["briefing"]
    assert "categorized" in result["briefing"]
    assert "scan" in result["briefing"]

def test_analyze_empty_returns_empty():
    analyzer = Analyzer(llm=MockLLM())
    result = analyzer.analyze([])
    assert result["top10"] == []
    assert result["briefing"] == {"headlines": [], "categorized": [], "scan": []}

def test_analyze_passes_through_preranked_news():
    """analyze() 直接接收预排序新闻，不做 LLM 重排序"""
    news_list = [make_news(f"id{i}") for i in range(1, 6)]  # 5条
    analyzer = Analyzer(llm=MockLLM())
    result = analyzer.analyze(news_list)
    assert len(result["top10"]) == 5
    # 顺序保持不变
    for i, item in enumerate(result["top10"]):
        assert item["id"] == f"id{i+1}"


def make_scan_extra(id_):
    return {
        "id": id_,
        "title": f"中文新闻{id_}",
        "title_cn": f"中文新闻{id_}",
        "summary": "摘要",
        "score": 10.0,
        "url": f"https://ex.com/{id_}",
        "source_name": "Test",
        "published_at": "",
    }


def test_briefing_scan_capped_to_30():
    """briefing.scan 总数 ≤ 30，scan_extras 按降序截前 N 条补足。"""
    news_list = [make_news(f"id{i}") for i in range(1, 4)]  # 3条进深度
    scan_extras = [make_scan_extra(f"e{i}") for i in range(1, 51)]  # 50条扫描层
    analyzer = Analyzer(llm=MockLLM())
    result = analyzer.analyze(news_list, scan_extras=scan_extras)
    assert len(result["briefing"]["scan"]) <= 30
    # 评分最高的 scan_extras 应优先入选（e1 在前）
    titles = [s["title"] for s in result["briefing"]["scan"]]
    assert "中文新闻e1" in titles
    assert "中文新闻e50" not in titles


def test_displayed_ids_only_includes_briefing_items():
    """displayed_ids 应等于 briefing 各区段实际展示的新闻 ID 集合，
    未进入 briefing.scan 的 scan_extras 不应被算作已用。"""
    news_list = [make_news(f"id{i}") for i in range(1, 4)]
    scan_extras = [make_scan_extra(f"e{i}") for i in range(1, 51)]
    analyzer = Analyzer(llm=MockLLM())
    result = analyzer.analyze(news_list, scan_extras=scan_extras)

    displayed = set(result["displayed_ids"])

    expected = set()
    for section in ("headlines", "categorized", "scan"):
        for item in result["briefing"][section]:
            if item.get("id"):
                expected.add(item["id"])

    assert displayed == expected
    # 排在 30 名外的 e50 既不在 scan 也不在 displayed_ids
    assert "e50" not in displayed


# ---------------------------------------------------------------------------
# _parse_translation_array：稳健解析 LLM 返回的翻译数组
# ---------------------------------------------------------------------------
def test_parse_translation_array_plain_array():
    a = Analyzer(llm=MockLLM())
    assert a._parse_translation_array('["中文1", "中文2"]', expected_len=2) == ["中文1", "中文2"]


def test_parse_translation_array_handles_multi_array_response():
    """模型有时输出'思考数组 + 答案数组'两段；旧的贪婪 regex 会触发 'Extra data'，
    新实现按出现顺序取第一段 list[str]，避免抛错。"""
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('["analysis"]\n["实际翻译"]', expected_len=1)
    assert out == ["analysis"]


def test_parse_translation_array_prefers_length_matching():
    """多段都是 list[str] 时，优先返回长度等于 expected_len 的那段。"""
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('["a", "b", "c"]\n["X", "Y"]', expected_len=2)
    assert out == ["X", "Y"]


def test_parse_translation_array_strips_think_tag():
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('<think>思考过程</think>\n["翻译"]', expected_len=1)
    assert out == ["翻译"]


def test_parse_translation_array_handles_unclosed_think():
    """<think> 打开但未闭合时，取 <think> 之前的内容。"""
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('["翻译"]\n<think>未闭合', expected_len=1)
    assert out == ["翻译"]


def test_parse_translation_array_strips_markdown_fence():
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('```json\n["翻译"]\n```', expected_len=1)
    assert out == ["翻译"]


def test_parse_translation_array_walks_into_nested_outer_array():
    """模型把答案包成 [[...]]：外层非 list[str]，向内继续找。"""
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('[["翻译1", "翻译2"]]', expected_len=2)
    assert out == ["翻译1", "翻译2"]


def test_parse_translation_array_single_item_plain_text_fallback():
    """单条场景下，若无可解析数组，取首个非空行作为译文。"""
    a = Analyzer(llm=MockLLM())
    assert a._parse_translation_array('翻译标题', expected_len=1) == ["翻译标题"]
    assert a._parse_translation_array('"带引号的译文"', expected_len=1) == ["带引号的译文"]


def test_parse_translation_array_multi_item_no_plaintext_fallback():
    """多条场景下，无可解析数组应返回空，避免把散文当成单条译文。"""
    a = Analyzer(llm=MockLLM())
    assert a._parse_translation_array('一堆解释文本而没有数组', expected_len=3) == []


def test_parse_translation_array_handles_bare_value_after_open_bracket():
    """复刻线上 'Expecting value: line 1 column 2' 的形态：
    最外层 [ 之后第一个字符不是合法 JSON 值（如 <think>），
    应跳过外层、继续向内找真正的 list[str]。"""
    a = Analyzer(llm=MockLLM())
    out = a._parse_translation_array('[<think>th</think>\n["翻译"]]', expected_len=1)
    assert out == ["翻译"]
