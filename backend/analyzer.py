import json
import re
from typing import List, Dict, Any, Tuple
from backend.llm.base import BaseLLMProvider

SYSTEM_PROMPT = """你是一位资深AI产业分析师，专注于挖掘AI前沿动态对企业的战略价值。
分析时请严格基于提供的新闻内容，不要虚构数据。
所有输出内容必须使用中文。
输出必须是合法的JSON格式，不要包含任何 markdown 标记或额外说明。
不要输出任何思考过程，直接输出JSON。"""

_CAT_LIMITS = {
    "模型发布": 3, "产品动态": 3,
    "产业商业": 2, "研究论文": 2,
    "实操技巧": 2, "观点深度": 2,
}

_SCAN_MAX = 30
_TRANSLATE_BATCH = 15  # 一次性批量翻译过多易触发 JSON 截断/输出不全


class Analyzer:
    def __init__(
        self,
        llm: BaseLLMProvider,
        topics: List[Dict] = None,
        categories: List[str] = None,
    ):
        self.llm = llm
        self.topics = topics or []
        self.categories = categories or []
        self._topics_text = self._build_topics_text()
        self._categories_text = "、".join(self.categories) if self.categories else "模型发布、产品动态、产业商业、研究论文、实操技巧、观点深度"

    def _build_topics_text(self) -> str:
        if not self.topics:
            return ""
        parts = []
        for t in self.topics:
            name = t.get("name", "")
            desc = t.get("description", "").strip()
            kws = "、".join(t.get("keywords", []))
            part = f"【{name}】\n{desc}"
            if kws:
                part += f"\n关键词：{kws}"
            parts.append(part)
        return "\n\n".join(parts)

    def analyze(self, news_list: List[Dict], scan_extras: List[Dict] = None) -> Dict[str, Any]:
        if not news_list:
            return {"news": [], "briefing": {"headlines": [], "categorized": [], "scan": []}}

        print(f"[Analyzer] 接收预排序新闻 {len(news_list)} 条，进入分析", flush=True)

        print(f"[Analyzer] 逐条分析 {len(news_list)} 条新闻...", flush=True)
        (titles, summaries, briefs, why_matters, main_categories,
         aux_tags, concepts, principles) = self._analyze_news_items(news_list)

        for i, item in enumerate(news_list):
            cn_title = titles.get(str(i + 1), "")
            if cn_title:
                item["title_cn"] = cn_title
            # 回写 main_category 到 item（供 briefing 分组）
            cat = main_categories.get(str(i + 1), "")
            if cat:
                item["main_category"] = cat

        briefing = self._generate_briefing(news_list, summaries, briefs, why_matters, main_categories)

        # 追加未深度分析的条目到扫描层：英文/混合语言标题批量翻成中文
        # （评分与翻译都对全量做，展示截断仅在最末）
        scan_extras = scan_extras or []
        scan_translations = self._translate_scan_titles(scan_extras) if scan_extras else {}
        for i, item in enumerate(scan_extras):
            zh = scan_translations.get(i)
            briefing["scan"].append({
                "id": item.get("id", ""),
                "title": zh or item.get("title_cn") or item["title"],
                "url": item.get("url", ""),
                "source_name": item.get("source_name", ""),
                "score": item.get("score"),
                "published_at": item.get("published_at", ""),
            })

        # 展示截断：scan_extras 已按分数降序，截前 _SCAN_MAX 条即"评分最高的剩余"
        briefing["scan"] = briefing["scan"][:_SCAN_MAX]

        # 实际进入报告展示的新闻 ID（供 pipeline 写入 top10_ids 标记已用）
        displayed_ids: List[str] = []
        for section in ("headlines", "categorized", "scan"):
            for item in briefing.get(section, []):
                nid = item.get("id")
                if nid:
                    displayed_ids.append(nid)

        return {
            "news": news_list,
            "briefing": briefing,
            "displayed_ids": displayed_ids,
            "summaries": summaries,
            "main_categories": main_categories,
            "aux_tags": aux_tags,
            "concepts": concepts,
            "principles": principles,
        }

    def _analyze_news_items(
        self, news_list: List[Dict]
    ) -> Tuple[Dict, Dict, Dict, Dict, Dict, Dict, Dict, Dict]:
        all_titles = {}
        all_summaries = {}
        all_briefs = {}
        all_why_matters = {}
        all_main_categories = {}
        all_aux_tags = {}
        all_concepts = {}
        all_principles = {}

        def _extract(k_str, v):
            if v.get("title"): all_titles[k_str] = v["title"]
            if v.get("summary"): all_summaries[k_str] = v["summary"]
            if v.get("brief"): all_briefs[k_str] = v["brief"]
            if v.get("why_matters"): all_why_matters[k_str] = v["why_matters"]
            if v.get("main_category"): all_main_categories[k_str] = v["main_category"]
            if v.get("aux_tags"): all_aux_tags[k_str] = v["aux_tags"]
            if v.get("concept"): all_concepts[k_str] = v["concept"]
            if v.get("principle"): all_principles[k_str] = v["principle"]

        batch_size = 5
        for batch_start in range(0, len(news_list), batch_size):
            batch_end = min(batch_start + batch_size, len(news_list))
            batch_nums = list(range(batch_start + 1, batch_end + 1))
            try:
                result = self._analyze_batch(news_list, batch_nums)
                for k in batch_nums:
                    k_str = str(k)
                    if k_str in result:
                        _extract(k_str, result[k_str])
            except Exception as e:
                print(f"[Analyzer] batch {batch_start//batch_size + 1} error: {e}", flush=True)

        missing = [i for i in range(1, len(news_list) + 1) if str(i) not in all_summaries]
        if missing:
            print(f"[Analyzer] {len(missing)} 条缺少分析，逐条重试: {missing}", flush=True)
            for idx in missing:
                try:
                    result = self._analyze_single(news_list, idx)
                    _extract(str(idx), result)
                except Exception as e:
                    print(f"[Analyzer] 单条重试 #{idx} 失败: {e}", flush=True)

        return (all_titles, all_summaries, all_briefs, all_why_matters,
                all_main_categories, all_aux_tags, all_concepts, all_principles)

    def _analyze_batch(self, news_list: List[Dict], batch_nums: List[int]) -> Dict:
        news_text = "\n\n".join(
            f"【新闻{i}】标题:{news_list[i-1]['title']}\n来源:{news_list[i-1]['source_name']}\n内容:{news_list[i-1]['full_text'][:600]}"
            for i in batch_nums
        )

        categories_json = json.dumps(self.categories, ensure_ascii=False) if self.categories else '["模型发布", "产品动态", "产业商业", "研究论文", "实操技巧", "观点深度"]'

        example_json = json.dumps({
            "items": {str(i): {
                "title": "中文标题",
                "summary": "约200字通俗摘要",
                "brief": "60字以内极简摘要",
                "why_matters": "一句话说清楚为什么值得关注",
                "main_category": self.categories[0] if self.categories else "模型发布",
                "aux_tags": ["标签1", "标签2"],
                "concept": "核心概念，60字以内",
                "principle": "技术原理或运行机制，80字以内",
            } for i in batch_nums}
        }, ensure_ascii=False, indent=2)

        topics_brief = self._topics_text[:400] if self._topics_text else "AI行业动态"

        prompt = f"""分析以下新闻，全部用中文输出。

监控话题：
{topics_brief}

{news_text}

针对每条新闻输出8个字段：
- title: 中文标题（已是中文则不变）
- summary: 约200字通俗摘要，用大白话说清楚谁做了什么、用什么技术、达到什么效果、为什么值得关注
- brief: 60字以内的极简摘要，用于列表展示
- why_matters: 一句话说清楚为什么值得关注（面向非技术决策者）
- main_category: 从以下标签中选1个最匹配的：{categories_json}
- aux_tags: 3个以内辅助标签（自由发挥，可以是厂商名/模态/技术方向等）
- concept: 本则新闻引入或涉及的核心概念，60字以内
- principle: 背后的技术原理或运行机制，80字以内

直接输出JSON：
{example_json}"""

        resp = self.llm.chat(SYSTEM_PROMPT, prompt)
        print(f"[Analyzer] batch response (first 300): {resp[:300]}", flush=True)
        data = self._parse_json(resp)

        items = data.get("items", {})
        if not items:
            return {}
        return {str(k): v for k, v in items.items() if isinstance(v, dict)}

    def _analyze_single(self, news_list: List[Dict], idx: int) -> Dict:
        item = news_list[idx - 1]
        topics_brief = self._topics_text[:300] if self._topics_text else "AI行业动态"
        categories_json = json.dumps(self.categories, ensure_ascii=False) if self.categories else '["模型发布", "产品动态", "产业商业", "研究论文", "实操技巧", "观点深度"]'
        example_cat = self.categories[0] if self.categories else "模型发布"

        prompt = f"""分析以下新闻，全部用中文输出。

监控话题：
{topics_brief}

标题:{item['title']}
来源:{item['source_name']}
内容:{item['full_text'][:800]}

输出8个字段：
- title: 中文标题（已是中文则不变）
- summary: 约200字通俗摘要
- brief: 60字以内极简摘要
- why_matters: 一句话说清楚为什么值得关注
- main_category: 从{categories_json}中选1个最匹配的
- aux_tags: 3个以内辅助标签
- concept: 核心概念，60字以内
- principle: 技术原理或运行机制，80字以内

直接输出JSON：
{{"title": "...", "summary": "...", "brief": "...", "why_matters": "...", "main_category": "{example_cat}", "aux_tags": ["标签1"], "concept": "...", "principle": "..."}}"""

        resp = self.llm.chat(SYSTEM_PROMPT, prompt)
        print(f"[Analyzer] single #{idx} response (first 200): {resp[:200]}", flush=True)
        return self._parse_json(resp)

    def _generate_briefing(
        self,
        news_list: List[Dict],
        summaries: Dict,
        briefs: Dict,
        why_matters: Dict,
        main_categories: Dict,
    ) -> Dict:
        # 头条要闻：前3条
        headlines = []
        for i, item in enumerate(news_list[:3]):
            k = str(i + 1)
            headlines.append({
                "id": item.get("id", ""),
                "title": item.get("title_cn") or item["title"],
                "url": item.get("url", ""),
                "source_name": item.get("source_name", ""),
                "published_at": item.get("published_at", ""),
                "summary": summaries.get(k, ""),
                "why_matters": why_matters.get(k, ""),
                "main_category": main_categories.get(k, ""),
                "score": item.get("score"),
            })

        # 分类精选：第4条起，按类别限额分配
        categorized = []
        cat_counts: Dict[str, int] = {}
        offset = len(headlines)
        for i, item in enumerate(news_list[offset:offset + 15], offset + 1):
            k = str(i)
            cat = main_categories.get(k, "")
            limit = _CAT_LIMITS.get(cat, 2)
            if cat_counts.get(cat, 0) >= limit:
                continue
            categorized.append({
                "id": item.get("id", ""),
                "title": item.get("title_cn") or item["title"],
                "url": item.get("url", ""),
                "source_name": item.get("source_name", ""),
                "published_at": item.get("published_at", ""),
                "brief": briefs.get(k, summaries.get(k, "")[:80]),
                "main_category": cat,
                "score": item.get("score"),
            })
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            if len(categorized) >= 12:
                break

        # 一句话扫描：剩余条目最多5条
        used_count = len(headlines) + len(categorized)
        scan = []
        for item in news_list[used_count:used_count + 5]:
            scan.append({
                "id": item.get("id", ""),
                "title": item.get("title_cn") or item["title"],
                "url": item.get("url", ""),
                "source_name": item.get("source_name", ""),
                "score": item.get("score"),
                "published_at": item.get("published_at", ""),
            })

        return {"headlines": headlines, "categorized": categorized, "scan": scan}

    def _translate_scan_titles(self, items: List[Dict]) -> Dict[int, str]:
        """批量把扫描层非中文标题译成中文。返回 {原索引: 译文}。失败的条目缺席（前端 fallback 原标题）。"""
        needs: List[Tuple[int, str]] = []
        for i, it in enumerate(items):
            title = (it.get("title_cn") or it.get("title") or "").strip()
            if not title:
                continue
            zh = sum(1 for c in title if "一" <= c <= "鿿")
            if zh / max(len(title), 1) < 0.3:
                needs.append((i, title))
        if not needs:
            return {}

        result: Dict[int, str] = {}
        for batch_start in range(0, len(needs), _TRANSLATE_BATCH):
            batch = needs[batch_start: batch_start + _TRANSLATE_BATCH]
            try:
                translations = self._translate_titles_batch([t for _, t in batch])
            except Exception as e:
                print(f"[Analyzer] scan title batch {batch_start // _TRANSLATE_BATCH + 1} failed: {e}", flush=True)
                continue
            for j, (orig_idx, _) in enumerate(batch):
                if j < len(translations) and translations[j]:
                    result[orig_idx] = translations[j]

        missing = [(idx, t) for idx, t in needs if idx not in result]
        if missing:
            print(f"[Analyzer] {len(missing)} 条扫描标题缺译，逐条重试", flush=True)
            for orig_idx, title in missing:
                try:
                    translations = self._translate_titles_batch([title])
                    if translations and translations[0]:
                        result[orig_idx] = translations[0]
                except Exception as e:
                    print(f"[Analyzer] scan title 单条重试 #{orig_idx} 失败: {e}", flush=True)
        return result

    def _translate_titles_batch(self, titles: List[str]) -> List[str]:
        """把一批标题翻译成简体中文，返回译文列表（失败位置为空串/缺席）。"""
        listing = "\n".join(f"{j+1}. {t}" for j, t in enumerate(titles))
        prompt = f"""把以下推文/新闻标题逐条翻译成简体中文，保留专有名词原文（OpenAI、GPT-5、Claude 等），保持简洁地道。
输出 JSON 数组，按顺序与输入对应：

{listing}

直接输出 JSON 数组，例如 ["中文标题1", "中文标题2"]，不要任何额外说明。"""
        resp = self.llm.chat(SYSTEM_PROMPT, prompt)
        return self._parse_translation_array(resp, expected_len=len(titles))

    def _parse_translation_array(self, text: str, expected_len: int) -> List[str]:
        """从 LLM 响应中稳健抽取字符串数组。

        覆盖几类常见异常输出：<think> 标签、markdown 围栏、多段 [...]（思考片段 +
        答案）、最外层把答案再包一层（[[...]]）等。单条场景下若全无可解析数组，
        把首个非空行作为译文兜底，避免连续抛 'Extra data' / 'Expecting value'。
        """
        raw = text
        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        if "<think>" in text:
            tail = text.split("</think>", 1)[-1].strip()
            text = tail or raw.split("<think>", 1)[0].strip()

        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()

        candidates: List[List[str]] = []
        i = 0
        while i < len(text):
            if text[i] != '[':
                i += 1
                continue
            bracketed = self._match_brackets(text, i)
            if not bracketed:
                i += 1
                continue
            try:
                val = json.loads(bracketed)
            except json.JSONDecodeError:
                i += 1
                continue
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                candidates.append([v.strip() for v in val])
                i += len(bracketed)
            else:
                # 顶层不是 list[str]（如 list[list] 或含 <think>），向内一步继续找
                i += 1

        if candidates:
            for cand in candidates:
                if len(cand) == expected_len:
                    return cand
            return candidates[0]

        if expected_len == 1:
            for line in text.splitlines():
                stripped = line.strip().strip('"').strip("'").strip()
                if stripped:
                    return [stripped]
        return []

    def _match_brackets(self, text: str, start: int) -> str | None:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    # ------------------------------------------------------------------
    # JSON 解析工具
    # ------------------------------------------------------------------
    def _parse_json(self, text: str) -> Dict:
        raw = text
        text = text.strip()

        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        if "<think>" in text:
            text = text.split("</think>")[-1].strip()
            if not text:
                text = raw.split("<think>")[0].strip()

        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()

        json_text = self._extract_largest_json_object(text)
        if json_text:
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_text = self._extract_largest_json_object(raw)
        if json_text:
            return json.loads(json_text)

        raise ValueError(f"Cannot parse JSON from response (length={len(raw)}): {raw[:500]}")

    def _extract_largest_json_object(self, text: str) -> str | None:
        candidates = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                result = self._match_braces(text, i)
                if result:
                    candidates.append(result)
                    i += len(result)
                    continue
            i += 1
        if not candidates:
            return None
        return max(candidates, key=len)

    def _match_braces(self, text: str, start: int) -> str | None:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None
