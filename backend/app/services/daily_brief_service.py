from __future__ import annotations

import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

from backend.app.config import settings
from backend.app.db import Database


CHINA_TZ = ZoneInfo("Asia/Shanghai")
MAX_AGE_DAYS = 14
PER_CATEGORY_LIMIT = {"tech": 25, "finance": 20, "politics": 15}
CATEGORY_NAMES = {"tech": "科技", "finance": "财经", "politics": "时政"}
ENTERTAINMENT_KEYWORDS = (
    "电影",
    "票房",
    "院线",
    "导演",
    "主演",
    "演员",
    "艺人",
    "明星",
    "综艺",
    "剧集",
    "上映",
    "演唱会",
    "音乐节",
    "奥斯卡",
    "金棕榈",
    "体育",
    "赛事",
)
FINANCE_NEWSFLASH_KEYWORDS = (
    "ai",
    "ipo",
    "上市",
    "融资",
    "并购",
    "财报",
    "营收",
    "利润",
    "估值",
    "基金",
    "美元",
    "人民币",
    "订单",
    "投资",
    "股权",
    "监管",
    "券商",
    "银行",
    "能源",
    "出口",
    "消费",
    "芯片",
    "大模型",
    "算力",
)


DEFAULT_DAILY_BRIEF_SOURCES: List[Dict[str, Any]] = [
    {"id": "github-trending", "name": "GitHub Trending", "type": "scrape", "url": "https://github.com/trending", "category": "tech", "enabled": True},
    {"id": "36kr-article", "name": "36氪文章", "type": "rss", "url": "https://36kr.com/feed-article", "category": "tech", "enabled": True},
    {"id": "36kr-newsflash", "name": "36氪快讯", "type": "rss", "url": "https://36kr.com/feed-newsflash", "category": "finance", "enabled": True},
    {"id": "infoq-cn", "name": "InfoQ 中文", "type": "rss", "url": "https://www.infoq.cn/feed", "category": "tech", "enabled": True},
    {"id": "openai-news", "name": "OpenAI News", "type": "rss", "url": "https://openai.com/news/rss.xml", "category": "tech", "enabled": True},
    {"id": "tldr-ai", "name": "TLDR AI", "type": "rss", "url": "https://tldr.tech/api/rss/ai", "category": "tech", "enabled": True},
    {"id": "smol-ai-news", "name": "Smol AI News", "type": "rss", "url": "https://news.smol.ai/rss.xml", "category": "tech", "enabled": True},
    {"id": "latent-space", "name": "Latent Space", "type": "rss", "url": "https://www.latent.space/feed", "category": "tech", "enabled": True},
    {"id": "mit-tech-review-ai", "name": "MIT Tech Review AI", "type": "rss", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "category": "tech", "enabled": True},
    {"id": "wsj-markets", "name": "WSJ Markets", "type": "rss", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "category": "finance", "enabled": True},
    {"id": "chinadaily-bizchina", "name": "China Daily Bizchina", "type": "rss", "url": "http://www.chinadaily.com.cn/rss/bizchina_rss.xml", "category": "finance", "enabled": True},
    {"id": "chinadaily-world", "name": "China Daily World", "type": "rss", "url": "http://www.chinadaily.com.cn/rss/world_rss.xml", "category": "politics", "enabled": True},
    {"id": "chinadaily-china", "name": "China Daily China", "type": "rss", "url": "http://www.chinadaily.com.cn/rss/china_rss.xml", "category": "politics", "enabled": True},
    {"id": "npr-world", "name": "NPR World", "type": "rss", "url": "https://feeds.npr.org/1004/rss.xml", "category": "politics", "enabled": True},
]


SYSTEM_PROMPT_DIGEST_ZH = """你是一名严谨的中文新闻编辑，负责把多源资讯整理成一份 5 分钟读完的每日简报。
输出必须是合法 JSON，字段固定为：
hero_headline: 10-25 字的一句话头条；
daily_overview: 150-220 字总览，覆盖科技、财经、时政；
tech_briefs: 3-5 条；
finance_briefs: 3-5 条；
politics_briefs: 2-3 条；
editor_note: 30-60 字中性短评；
keywords: 5-8 个关键词。
每条 brief 包含 title、url、source、summary、importance。url 必须从输入原样复制，不能编造。相同主题合并，英文内容翻译成中文，标题克制、摘要只写事实，不要 markdown，不要代码围栏。
严禁选择娱乐、影视、体育、明星、票房、社会猎奇新闻，除非它与上市公司、重大资本市场事件或政策事件直接相关。"""


class DailyBriefService:
    def __init__(
        self,
        db: Database,
        sources: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_url: Optional[str] = None,
    ):
        self.db = db
        self.sources = sources or DEFAULT_DAILY_BRIEF_SOURCES
        self.api_key = settings.daily_brief_api_key if api_key is None else api_key
        self.model = _normalize_model_id(model or settings.daily_brief_model)
        self.llm_url = llm_url or settings.daily_brief_llm_url

    def latest(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM daily_briefs ORDER BY generated_at DESC LIMIT 1")
        if not rows:
            return None
        return self._decode_brief(rows[0])

    def has_brief_for_date(self, brief_date: date) -> bool:
        rows = self.db.query(
            """
            SELECT *
            FROM daily_briefs
            WHERE brief_date = ? AND status IN ('completed_full', 'completed_partial')
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            [brief_date],
        )
        if not rows:
            return False
        return not self.should_regenerate(rows[0])

    def should_regenerate(self, brief: Optional[Dict[str, Any]]) -> bool:
        if not brief or not self.api_key:
            return False
        if brief.get("llm_model") != "fallback":
            return False
        error_message = str(brief.get("error_message") or "")
        return "未配置 LLM API" in error_message or "Client error '400 Bad Request'" in error_message

    def generate(
        self,
        report_date: Optional[date] = None,
        progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict[str, Any]:
        brief_date = report_date or datetime.now(CHINA_TZ).date()
        enabled_sources = [source for source in self.sources if source.get("enabled", True)]
        progress = progress or (lambda stage, processed, total: None)
        progress("抓取资讯源", 0, max(1, len(enabled_sources) + 2))

        articles: List[Dict[str, Any]] = []
        warnings: List[str] = []
        for index, source in enumerate(enabled_sources, start=1):
            try:
                articles.extend(self._fetch_source(source))
            except Exception as exc:
                warnings.append(f"{source.get('name') or source.get('id')}：{exc}")
                logging.warning("Daily brief source failed: %s", exc)
            progress("抓取资讯源", index, len(enabled_sources) + 2)

        articles = self._filter_articles(self._dedupe_articles(articles))
        self._save_articles(articles)
        progress("生成简报", len(enabled_sources) + 1, len(enabled_sources) + 2)

        report, llm_used, error_message = self._build_report(articles)
        if error_message:
            warnings.append(error_message)
        visible_error = _visible_error_message(warnings)
        brief_id = f"brief-{brief_date:%Y%m%d}"
        status = "completed_full" if articles and llm_used and not warnings else "completed_partial"
        if not articles:
            status = "completed_partial"
        generated_at = datetime.utcnow()
        row = {
            "id": brief_id,
            "brief_date": brief_date,
            "status": status,
            "hero_headline": report["hero_headline"],
            "daily_overview": report["daily_overview"],
            "tech_briefs_json": report["tech_briefs"],
            "finance_briefs_json": report["finance_briefs"],
            "politics_briefs_json": report["politics_briefs"],
            "editor_note": report["editor_note"],
            "keywords_json": report["keywords"],
            "article_count": len(articles),
            "source_count": len({article["source_id"] for article in articles}),
            "llm_model": self.model if llm_used else "fallback",
            "generated_at": generated_at,
            "error_message": visible_error,
            "payload_json": {
                "warnings": warnings,
                "llm_used": llm_used,
                "source_count": len(enabled_sources),
                "article_flow": self._article_flow(articles),
            },
        }
        self.db.upsert("daily_briefs", [row], ["id"])
        progress("简报完成", len(enabled_sources) + 2, len(enabled_sources) + 2)
        return {
            "brief_id": brief_id,
            "status": status,
            "article_count": len(articles),
            "source_count": row["source_count"],
            "llm_used": llm_used,
            "warnings": warnings,
            "visible_warning": visible_error,
        }

    def _fetch_source(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        source_type = source.get("type", "rss")
        if source_type == "api" and source.get("id") == "v2ex-hot":
            return self._fetch_v2ex(source)
        if source_type == "api" and source.get("id") == "hackernews":
            return self._fetch_hackernews(source)
        if source_type == "api" and source.get("id") == "attentionvc-ai":
            return self._fetch_attentionvc(source)
        if source_type == "scrape" and source.get("id") == "github-trending":
            return self._fetch_github_trending(source)
        return self._fetch_rss(source)

    def _fetch_rss(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = self._http_get_text(str(source["url"]))
        root = ET.fromstring(text)
        items = root.findall(".//item")
        if items:
            return [self._rss_item_to_article(item, source) for item in items[:20]]
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        return [self._atom_entry_to_article(entry, source) for entry in entries[:20]]

    def _fetch_v2ex(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = self._http_get_json(str(source["url"]))
        articles = []
        for item in data[:20] if isinstance(data, list) else []:
            articles.append(
                self._article(
                    source,
                    title=item.get("title"),
                    url=item.get("url"),
                    excerpt=item.get("content") or item.get("content_rendered"),
                    published_at=_from_timestamp(item.get("last_touched")),
                )
            )
        return articles

    def _fetch_hackernews(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        ids = self._http_get_json(f"{source['url']}/topstories.json")
        articles = []
        for item_id in ids[:20] if isinstance(ids, list) else []:
            item = self._http_get_json(f"{source['url']}/item/{item_id}.json")
            if not isinstance(item, dict) or item.get("type") != "story":
                continue
            articles.append(
                self._article(
                    source,
                    title=item.get("title"),
                    url=item.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                    excerpt=f"{item.get('score') or 0} points · {item.get('descendants') or 0} comments",
                    published_at=_from_timestamp(item.get("time")),
                )
            )
        return articles

    def _fetch_attentionvc(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = self._http_get_json(str(source["url"]))
        items = data.get("articles") or data.get("data") or data.get("items") if isinstance(data, dict) else data
        articles = []
        for item in items[:20] if isinstance(items, list) else []:
            articles.append(
                self._article(
                    source,
                    title=item.get("title") or item.get("text"),
                    url=item.get("url") or item.get("link"),
                    excerpt=item.get("summary") or item.get("description"),
                    published_at=_parse_datetime(item.get("published_at") or item.get("created_at")),
                )
            )
        return articles

    def _fetch_github_trending(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = self._http_get_text(str(source["url"]))
        repos: List[str] = []
        for match in re.finditer(r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"', text):
            repo = match.group(1)
            if repo not in repos:
                repos.append(repo)
            if len(repos) >= 20:
                break
        return [
            self._article(
                source,
                title=repo,
                url=f"https://github.com/{repo}",
                excerpt="GitHub Trending 今日热门项目",
                published_at=datetime.utcnow(),
            )
            for repo in repos
        ]

    def _http_get_text(self, url: str) -> str:
        with httpx.Client(timeout=settings.daily_brief_source_timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers=_headers())
            response.raise_for_status()
            return response.text

    def _http_get_json(self, url: str) -> Any:
        with httpx.Client(timeout=settings.daily_brief_source_timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers=_headers())
            response.raise_for_status()
            return response.json()

    def _build_report(self, articles: List[Dict[str, Any]]) -> tuple[Dict[str, Any], bool, Optional[str]]:
        if articles and self.api_key:
            try:
                return self._call_llm(articles), True, None
            except Exception as exc:
                return self._fallback_report(articles), False, f"LLM 简报降级：{exc}"
        if articles:
            return self._fallback_report(articles), False, "未配置 LLM API，已展示中文降级摘要。"
        return self._fallback_report([]), False, "资讯源暂时没有返回可用内容。"

    def _call_llm(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        compact = self._compact_articles(articles)
        user_prompt = "\n".join(
            [
                "根据候选新闻生成今日简报。响应必须是一个 JSON 对象，不要 markdown，不要解释。",
                "所有字符串使用中文。url 必须从候选条目原样复制。",
                "候选新闻：",
                json.dumps(compact, ensure_ascii=False),
            ]
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_DIGEST_ZH},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        data: Dict[str, Any]
        with httpx.Client(timeout=120) as client:
            try:
                data = self._post_llm(client, payload)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 400:
                    raise RuntimeError(_http_error_message(exc)) from exc
                relaxed_payload = dict(payload)
                relaxed_payload.pop("response_format", None)
                try:
                    data = self._post_llm(client, relaxed_payload)
                except httpx.HTTPStatusError as retry_exc:
                    raise RuntimeError(_http_error_message(retry_exc)) from retry_exc
        content = data["choices"][0]["message"]["content"]
        return self._normalize_report(json.loads(_extract_json(content)))

    def _post_llm(self, client: httpx.Client, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = client.post(
            self.llm_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def _fallback_report(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        grouped = self._selected_by_category(articles)
        count = len(articles)
        if not count:
            return {
                "hero_headline": "资讯源暂时无返回",
                "daily_overview": "后台已经尝试抓取国际科技、财经与时政资讯，但当前没有拿到可用内容。页面会保留这份降级记录，下一次自动任务会继续尝试。",
                "tech_briefs": [],
                "finance_briefs": [],
                "politics_briefs": [],
                "editor_note": "当前为降级简报，等待下一轮自动更新。",
                "keywords": ["资讯源", "自动简报", "降级"],
            }
        return {
            "hero_headline": "国际资讯简报已更新",
            "daily_overview": f"本次自动抓取 {count} 条国际资讯，覆盖科技、财经与时政来源。当前未使用 LLM 精编，先按来源新鲜度和类别均衡展示标题流，后续配置模型后会自动生成更凝练的编辑摘要。",
            "tech_briefs": [_brief_from_article(item) for item in grouped["tech"][:5]],
            "finance_briefs": [_brief_from_article(item) for item in grouped["finance"][:5]],
            "politics_briefs": [_brief_from_article(item) for item in grouped["politics"][:3]],
            "editor_note": "这是自动降级摘要，适合快速扫标题，重要内容仍建议点开原文确认。",
            "keywords": [CATEGORY_NAMES[key] for key, items in grouped.items() if items][:8],
        }

    def _compact_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected = []
        for category, limit in PER_CATEGORY_LIMIT.items():
            selected.extend(_round_robin([item for item in articles if item["category"] == category], limit))
        return [
            {
                "n": index + 1,
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "category": item["category"],
                "excerpt": (item.get("excerpt") or "")[:240],
                "published": _iso_or_empty(item.get("published_at")),
            }
            for index, item in enumerate(selected)
        ]

    def _selected_by_category(self, articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        return {
            category: _round_robin([item for item in articles if item["category"] == category], limit)
            for category, limit in PER_CATEGORY_LIMIT.items()
        }

    def _filter_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [article for article in articles if _is_brief_article(article)]

    def _article_flow(self, articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped = self._selected_by_category(articles)
        return {
            category: [_article_flow_item(item) for item in items[:20]]
            for category, items in grouped.items()
        }

    def _normalize_report(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "hero_headline": str(raw.get("hero_headline") or "今日资讯简报"),
            "daily_overview": str(raw.get("daily_overview") or ""),
            "tech_briefs": _normalize_briefs(raw.get("tech_briefs")),
            "finance_briefs": _normalize_briefs(raw.get("finance_briefs")),
            "politics_briefs": _normalize_briefs(raw.get("politics_briefs")),
            "editor_note": str(raw.get("editor_note") or ""),
            "keywords": [str(item) for item in (raw.get("keywords") or [])][:8],
        }

    def _save_articles(self, articles: List[Dict[str, Any]]) -> None:
        now = datetime.utcnow()
        rows = []
        for article in articles:
            rows.append(
                {
                    "source_id": article["source_id"],
                    "source": article["source"],
                    "category": article["category"],
                    "title": article["title"],
                    "url": article["url"],
                    "excerpt": article.get("excerpt"),
                    "published_at": article.get("published_at"),
                    "fetched_at": now,
                }
            )
        self.db.upsert("news_articles", rows, ["source_id", "url"])

    def _dedupe_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cutoff = datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)
        seen = set()
        clean = []
        for article in articles:
            if not article.get("title") or not article.get("url"):
                continue
            published = article.get("published_at")
            if isinstance(published, datetime) and published < cutoff:
                continue
            key = str(article["url"]).split("?")[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            clean.append(article)
        clean.sort(key=lambda item: item.get("published_at") or datetime.min, reverse=True)
        return clean

    def _article(
        self,
        source: Dict[str, Any],
        title: Any,
        url: Any,
        excerpt: Any = None,
        published_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        return {
            "source_id": str(source["id"]),
            "source": str(source.get("name") or source["id"]),
            "category": str(source.get("category") or "tech"),
            "title": _clean_text(title),
            "url": str(url or source.get("url") or ""),
            "excerpt": _clean_text(excerpt)[:500] if excerpt else "",
            "published_at": published_at,
        }

    def _rss_item_to_article(self, item: ET.Element, source: Dict[str, Any]) -> Dict[str, Any]:
        return self._article(
            source,
            title=_child_text(item, "title"),
            url=_child_text(item, "link") or _child_text(item, "guid"),
            excerpt=_child_text(item, "description"),
            published_at=_parse_datetime(_child_text(item, "pubDate") or _child_text(item, "date")),
        )

    def _atom_entry_to_article(self, entry: ET.Element, source: Dict[str, Any]) -> Dict[str, Any]:
        link = ""
        for child in entry.findall("{http://www.w3.org/2005/Atom}link"):
            if child.attrib.get("href"):
                link = child.attrib["href"]
                break
        return self._article(
            source,
            title=_child_text(entry, "{http://www.w3.org/2005/Atom}title"),
            url=link,
            excerpt=_child_text(entry, "{http://www.w3.org/2005/Atom}summary") or _child_text(entry, "{http://www.w3.org/2005/Atom}content"),
            published_at=_parse_datetime(_child_text(entry, "{http://www.w3.org/2005/Atom}published") or _child_text(entry, "{http://www.w3.org/2005/Atom}updated")),
        )

    def _decode_brief(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.loads(row.get("payload_json") or "{}")
        return {
            "id": row["id"],
            "brief_date": row.get("brief_date"),
            "status": row.get("status"),
            "hero_headline": row.get("hero_headline") or "",
            "daily_overview": row.get("daily_overview") or "",
            "tech_briefs": json.loads(row.get("tech_briefs_json") or "[]"),
            "finance_briefs": json.loads(row.get("finance_briefs_json") or "[]"),
            "politics_briefs": json.loads(row.get("politics_briefs_json") or "[]"),
            "editor_note": row.get("editor_note") or "",
            "keywords": json.loads(row.get("keywords_json") or "[]"),
            "article_count": row.get("article_count") or 0,
            "source_count": row.get("source_count") or 0,
            "llm_model": row.get("llm_model"),
            "generated_at": row.get("generated_at"),
            "error_message": row.get("error_message"),
            "article_flow": payload.get("article_flow") or {"tech": [], "finance": [], "politics": []},
            "payload": payload,
        }


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": "A-Share-Signal-DailyBrief/1.0 (+private research dashboard)",
        "Accept": "application/rss+xml, application/atom+xml, application/json, text/html;q=0.8, */*;q=0.5",
    }


def _normalize_model_id(model: str) -> str:
    aliases = {
        "v4-flash": "deepseek-v4-flash",
        "v4-pro": "deepseek-v4-pro",
    }
    clean = str(model or "").strip()
    return aliases.get(clean, clean)


def _http_error_message(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    detail = (response.text or "").strip()
    if len(detail) > 500:
        detail = f"{detail[:500]}..."
    return f"{response.status_code} {response.reason_phrase}: {detail or response.url}"


def _round_robin(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        buckets.setdefault(str(item["source_id"]), []).append(item)
    for bucket in buckets.values():
        bucket.sort(key=lambda row: row.get("published_at") or datetime.min, reverse=True)
    out: List[Dict[str, Any]] = []
    made_progress = True
    while len(out) < limit and made_progress:
        made_progress = False
        for bucket in buckets.values():
            if not bucket:
                continue
            out.append(bucket.pop(0))
            made_progress = True
            if len(out) >= limit:
                break
    return out


def _normalize_briefs(value: Any) -> List[Dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    briefs = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        briefs.append(
            {
                "title": str(item.get("title") or "")[:80],
                "url": str(item.get("url") or ""),
                "source": str(item.get("source") or ""),
                "summary": str(item.get("summary") or "")[:240],
                "importance": _normalize_importance(item.get("importance")),
            }
        )
    return briefs


def _normalize_importance(value: Any) -> int:
    if value is None:
        return 5
    if isinstance(value, (int, float)):
        return max(1, min(10, int(round(value))))
    text = str(value).strip().lower()
    aliases = {
        "high": 8,
        "important": 8,
        "高": 8,
        "高重要度": 8,
        "medium": 5,
        "mid": 5,
        "中": 5,
        "中等": 5,
        "low": 3,
        "低": 3,
        "低重要度": 3,
    }
    if text in aliases:
        return aliases[text]
    try:
        return max(1, min(10, int(float(text))))
    except Exception:
        return 5


def _brief_from_article(item: Dict[str, Any]) -> Dict[str, Any]:
    category = CATEGORY_NAMES.get(str(item.get("category") or ""), "资讯")
    title = item["title"][:60]
    excerpt = (item.get("excerpt") or item["title"])[:140]
    return {
        "title": f"{category}资讯：{title}",
        "url": item["url"],
        "source": item["source"],
        "summary": f"来自 {item['source']}：{excerpt}",
        "importance": 5,
    }


def _is_brief_article(item: Dict[str, Any]) -> bool:
    text = f"{item.get('title') or ''} {item.get('excerpt') or ''}".lower()
    if any(keyword.lower() in text for keyword in ENTERTAINMENT_KEYWORDS):
        return _has_market_context(text)
    if item.get("source_id") == "36kr-newsflash":
        return any(keyword.lower() in text for keyword in FINANCE_NEWSFLASH_KEYWORDS)
    return True


def _has_market_context(text: str) -> bool:
    return any(
        keyword in text
        for keyword in (
            "上市",
            "ipo",
            "财报",
            "营收",
            "利润",
            "并购",
            "融资",
            "股价",
            "市值",
            "监管",
        )
    )


def _article_flow_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": str(item.get("title") or "")[:120],
        "url": str(item.get("url") or ""),
        "source": str(item.get("source") or ""),
        "category": str(item.get("category") or ""),
        "summary": str(item.get("excerpt") or "")[:260],
        "published_at": _iso_or_empty(item.get("published_at")),
    }


def _visible_error_message(warnings: List[str]) -> Optional[str]:
    if not warnings:
        return None
    source_failures = [warning for warning in warnings if "：" in warning and not warning.startswith(("LLM", "未配置", "资讯源"))]
    other_warnings = [warning for warning in warnings if warning not in source_failures]
    parts = []
    if source_failures:
        parts.append(f"{len(source_failures)} 个资讯源暂不可用")
    for warning in other_warnings:
        parts.append(warning)
    return "；".join(parts)


def _child_text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return child.text or "" if child is not None else ""


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    try:
        parsed = parsedate_to_datetime(text)
    except Exception:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(CHINA_TZ).replace(tzinfo=None)
    return parsed


def _from_timestamp(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(float(value), tz=CHINA_TZ).replace(tzinfo=None)
    except Exception:
        return None


def _iso_or_empty(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return ""


def _extract_json(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        return cleaned[start : end + 1]
    return cleaned
