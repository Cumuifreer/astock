from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from backend.app.config import settings
from backend.app.db import Database


DEFAULT_DAILY_BRIEF_SOURCES: List[Dict[str, Any]] = []


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
        self.sources = sources if sources is not None else DEFAULT_DAILY_BRIEF_SOURCES
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
        return False

    def generate(
        self,
        report_date: Optional[date] = None,
        progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict[str, Any]:
        raise RuntimeError("资讯简报生成已禁用；只读取 DuckDB 已有简报。")

    def _fetch_source(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise RuntimeError("资讯简报外部抓取已禁用；只读取 DuckDB 已有简报。")

    def _call_llm(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise RuntimeError("资讯简报 LLM 生成已禁用；只读取 DuckDB 已有简报。")

    def _post_llm(self, client: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("资讯简报 LLM 生成已禁用；只读取 DuckDB 已有简报。")

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


def _normalize_model_id(model: str) -> str:
    aliases = {
        "v4-flash": "deepseek-v4-flash",
        "v4-pro": "deepseek-v4-pro",
    }
    clean = str(model or "").strip()
    return aliases.get(clean, clean)


def _http_error_message(exc: Any) -> str:
    response = exc.response
    detail = (response.text or "").strip()
    if len(detail) > 500:
        detail = f"{detail[:500]}..."
    return f"{response.status_code} {response.reason_phrase}: {detail or response.url}"


def _extract_json(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        return cleaned[start : end + 1]
    return cleaned
