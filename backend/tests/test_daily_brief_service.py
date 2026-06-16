import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.daily_brief_scheduler import DailyBriefScheduler
from backend.app.services.daily_brief_service import DEFAULT_DAILY_BRIEF_SOURCES, DailyBriefService
from backend.app.services.data_service import DataService
from backend.app.services.update_service import UpdateService


def test_daily_brief_generation_fetches_news_and_uses_llm_when_configured(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(
        db,
        sources=[{"id": "mock", "name": "Mock Feed", "type": "rss", "category": "tech", "enabled": True}],
        api_key="test-key",
    )
    article = {
        "source_id": "mock",
        "source": "Mock Feed",
        "category": "tech",
        "title": "AI infrastructure funding expands",
        "url": "https://example.com/ai-funding",
        "excerpt": "New funding for AI infrastructure.",
        "published_at": datetime.utcnow(),
    }

    monkeypatch.setattr(service, "_fetch_source", lambda source: [article])
    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda articles: {
            "hero_headline": "AI 基础设施融资升温",
            "daily_overview": "今日科技资讯聚焦 AI 基础设施。",
            "tech_briefs": [
                {
                    "title": "AI 基础设施融资升温",
                    "url": "https://example.com/ai-funding",
                    "source": "Mock Feed",
                    "summary": "资金继续流向 AI 基础设施。",
                    "importance": 8,
                }
            ],
            "finance_briefs": [],
            "politics_briefs": [],
            "article_flow": {
                "tech": [
                    {
                        "title": "AI 基础设施融资升温",
                        "url": "https://example.com/ai-funding",
                        "source": "Mock Feed",
                        "summary": "资金继续流向 AI 基础设施。",
                        "published_at": "2026-05-23T08:00:00",
                        "importance": 8,
                    }
                ],
                "finance": [],
                "politics": [],
            },
            "editor_note": "关注算力投资持续性。",
            "keywords": ["AI", "基础设施"],
        },
    )

    result = service.generate(report_date=article["published_at"].date())

    assert result["status"] == "completed_full"
    assert result["llm_used"] is True
    assert db.scalar("SELECT COUNT(*) FROM news_articles") == 1
    latest = DataService(db).latest_daily_brief()
    assert latest["llm_model"] == "deepseek-chat"
    assert latest["article_flow"]["tech"][0]["summary"] == "资金继续流向 AI 基础设施。"


def test_daily_brief_llm_success_can_use_backend_article_flow(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(
        db,
        sources=[{"id": "mock", "name": "Mock Feed", "type": "rss", "category": "tech", "enabled": True}],
        api_key="test-key",
    )
    article = {
        "source_id": "mock",
        "source": "Mock Feed",
        "category": "tech",
        "title": "AI infrastructure funding expands",
        "url": "https://example.com/ai-funding",
        "excerpt": "New funding for AI infrastructure.",
        "published_at": datetime.utcnow(),
    }

    monkeypatch.setattr(service, "_fetch_source", lambda source: [article])
    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda articles: {
            "hero_headline": "AI 基础设施融资升温",
            "daily_overview": "今日科技资讯聚焦 AI 基础设施。",
            "tech_briefs": [
                {
                    "title": "AI 基础设施融资升温",
                    "url": "https://example.com/ai-funding",
                    "source": "Mock Feed",
                    "summary": "资金继续流向 AI 基础设施。",
                    "importance": 8,
                }
            ],
            "finance_briefs": [],
            "politics_briefs": [],
            "editor_note": "关注算力投资持续性。",
            "keywords": ["AI", "基础设施"],
        },
    )

    report_date = article["published_at"].date()
    result = service.generate(report_date=report_date)
    latest = DataService(db).latest_daily_brief()
    payload = json.loads(db.scalar("SELECT payload_json FROM daily_briefs WHERE id = ?", [f"brief-{report_date:%Y%m%d}"]) or "{}")

    assert result["llm_used"] is True
    assert result["status"] == "completed_full"
    assert payload["article_flow_source"] == "raw"
    assert latest["article_flow"]["tech"][0]["title"] == "AI infrastructure funding expands"


def test_daily_brief_sources_are_news_feeds_not_stock_data_sources(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(db)

    assert DEFAULT_DAILY_BRIEF_SOURCES
    assert hasattr(service, "_http_get_text")
    assert hasattr(service, "_http_get_json")
    assert hasattr(service, "_fetch_rss")
    assert {source["type"] for source in DEFAULT_DAILY_BRIEF_SOURCES} <= {"rss", "api", "scrape"}
    source_names = json.dumps(DEFAULT_DAILY_BRIEF_SOURCES, ensure_ascii=False)
    assert "AkShare" not in source_names
    assert "Baostock" not in source_names
    assert "AData" not in source_names


def test_daily_brief_repairs_malformed_llm_json_once(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(db, api_key="test-key")
    article = {
        "source_id": "mock",
        "source": "Mock Feed",
        "category": "tech",
        "title": "AI infrastructure funding expands",
        "url": "https://example.com/ai-funding",
        "excerpt": "New funding for AI infrastructure.",
        "published_at": datetime(2026, 5, 23, 8, 0),
    }
    repaired = {
        "hero_headline": "AI 基础设施融资升温",
        "daily_overview": "今日科技资讯聚焦 AI 基础设施，资金继续流向算力、模型服务和企业应用，市场关注投入节奏与商业化兑现。",
        "tech_briefs": [
            {
                "title": "AI 基础设施融资升温",
                "url": "https://example.com/ai-funding",
                "source": "Mock Feed",
                "summary": "资金继续流向 AI 基础设施。",
                "importance": 8,
            }
        ],
        "finance_briefs": [],
        "politics_briefs": [],
        "article_flow": {
            "tech": [
                {
                    "title": "AI 基础设施融资升温",
                    "url": "https://example.com/ai-funding",
                    "source": "Mock Feed",
                    "summary": "资金继续流向 AI 基础设施。",
                    "published_at": "2026-05-23T08:00:00",
                    "importance": 8,
                }
            ],
            "finance": [],
            "politics": [],
        },
        "editor_note": "关注算力投资持续性。",
        "keywords": ["AI", "基础设施"],
    }
    calls = []

    def fake_post_llm(client, payload):
        calls.append(payload)
        if len(calls) == 1:
            return {"choices": [{"message": {"content": '{"hero_headline":"AI 简报","tech_briefs": ['}}]}
        return {"choices": [{"message": {"content": json.dumps(repaired, ensure_ascii=False)}}]}

    monkeypatch.setattr(service, "_post_llm", fake_post_llm)

    report = service._call_llm([article])

    assert report["hero_headline"] == "AI 基础设施融资升温"
    assert report["article_flow"]["tech"][0]["summary"] == "资金继续流向 AI 基础设施。"
    assert len(calls) == 2
    assert "只返回合法 JSON" in calls[1]["messages"][-1]["content"]


def test_daily_brief_llm_prompt_keeps_article_flow_out_of_model_output(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(db, api_key="test-key")
    articles = []
    for category in ("tech", "finance", "politics"):
        for index in range(90):
            articles.append(
                {
                    "source_id": f"mock-{category}",
                    "source": f"Mock {category}",
                    "category": category,
                    "title": f"{category} headline {index}",
                    "url": f"https://example.com/{category}/{index}",
                    "excerpt": f"{category} excerpt {index}",
                    "published_at": datetime(2026, 5, 23, 8, index % 60),
                }
            )

    calls = []

    def fake_post_llm(client, payload):
        calls.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "hero_headline": "国际资讯精编",
                                "daily_overview": "今日资讯聚焦科技、财经和时政变化。",
                                "tech_briefs": [],
                                "finance_briefs": [],
                                "politics_briefs": [],
                                "editor_note": "关注后续进展。",
                                "keywords": ["科技", "财经", "时政"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(service, "_post_llm", fake_post_llm)

    service._call_llm(articles)

    system_prompt = calls[0]["messages"][0]["content"]
    user_prompt = calls[0]["messages"][1]["content"]
    compact_json = user_prompt.split("候选新闻：\n", 1)[1]
    compact = json.loads(compact_json)

    assert "article_flow" not in system_prompt
    assert len(compact) == 60


def test_daily_brief_fallback_text_distinguishes_llm_parse_failure(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(db, api_key="test-key")
    article = {
        "source_id": "mock",
        "source": "Mock Feed",
        "category": "tech",
        "title": "AI infrastructure funding expands",
        "url": "https://example.com/ai-funding",
        "excerpt": "New funding for AI infrastructure.",
        "published_at": datetime(2026, 5, 23, 8, 0),
    }

    def fail_call(articles):
        raise json.JSONDecodeError("Expecting ',' delimiter", '{"bad":', 7)

    monkeypatch.setattr(service, "_call_llm", fail_call)

    report, llm_used, error_message = service._build_report([article])

    assert llm_used is False
    assert "LLM 简报降级" in error_message
    assert "模型精编返回格式异常" in report["daily_overview"]
    assert "后续配置模型" not in report["daily_overview"]


def test_daily_brief_api_backfills_article_flow_for_legacy_briefs(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    generated_at = datetime(2026, 5, 24, 8, 20)
    articles = [
        {
            "source_id": "mock-tech",
            "source": "Mock Tech",
            "category": "tech",
            "title": f"AI infrastructure update {index}",
            "url": f"https://example.com/tech/{index}",
            "excerpt": f"AI infrastructure detail {index}",
            "published_at": datetime(2026, 5, 24, 8, index),
            "fetched_at": generated_at,
        }
        for index in range(8)
    ]
    articles.append(
        {
            "source_id": "github-trending",
            "source": "GitHub Trending",
            "category": "tech",
            "title": "Repository trend should be hidden",
            "url": "https://github.com/example/hidden",
            "excerpt": "GitHub Trending should no longer appear in the brief.",
            "published_at": datetime(2026, 5, 24, 8, 30),
            "fetched_at": generated_at,
        }
    )
    db.upsert("news_articles", articles, ["source_id", "url"])
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "今日资讯简报",
                "daily_overview": "",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 8,
                "source_count": 1,
                "llm_model": "fallback",
                "generated_at": generated_at,
                "error_message": None,
                "payload_json": {
                    "article_flow": {
                        "tech": [
                            {
                                "title": "Existing translated item",
                                "url": "https://example.com/tech/0",
                                "source": "Mock Tech",
                                "category": "tech",
                                "summary": "LLM translated summary",
                                "published_at": "",
                            },
                            {
                                "title": "Cached GitHub item",
                                "url": "https://github.com/example/cached",
                                "source": "GitHub Trending",
                                "category": "tech",
                                "summary": "This cached item should be hidden.",
                                "published_at": "",
                            }
                        ],
                        "finance": [],
                        "politics": [],
                    }
                },
            }
        ],
        ["id"],
    )

    latest = DataService(db).latest_daily_brief()

    assert latest is not None
    assert len(latest["article_flow"]["tech"]) == 8
    assert latest["article_flow"]["tech"][0]["title"] == "AI infrastructure update 7"
    assert latest["article_flow"]["tech"][-1]["title"] == "Existing translated item"
    assert latest["article_flow"]["tech"][-1]["published_at"] == "2026-05-24T08:00:00"
    assert "GitHub Trending" not in json.dumps(latest, ensure_ascii=False, default=str)


def test_update_service_does_not_retry_fallback_brief_after_llm_is_configured(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260523",
                "brief_date": datetime(2026, 5, 23).date(),
                "status": "completed_partial",
                "hero_headline": "fallback",
                "daily_overview": "fallback",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 1,
                "source_count": 1,
                "llm_model": "fallback",
                "generated_at": datetime(2026, 5, 23, 8, 0),
                "error_message": "未配置 LLM API",
                "payload_json": {},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_update_service_does_not_retry_legacy_llm_400_fallback(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "fallback",
                "daily_overview": "fallback",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 88,
                "source_count": 7,
                "llm_model": "fallback",
                "generated_at": datetime(2026, 5, 24, 4, 18),
                "error_message": "14 个资讯源暂不可用；LLM 简报降级：Client error '400 Bad Request' for url",
                "payload_json": {},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_update_service_does_not_retry_llm_brief_without_translated_article_flow(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "old llm",
                "daily_overview": "old llm",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 88,
                "source_count": 7,
                "llm_model": "deepseek-v4-flash",
                "generated_at": datetime(2026, 5, 24, 6, 13),
                "error_message": None,
                "payload_json": {"llm_used": True, "article_flow": {"tech": [], "finance": [], "politics": []}},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_update_service_does_not_loop_on_current_llm_400_fallback(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "fallback",
                "daily_overview": "fallback",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 88,
                "source_count": 7,
                "llm_model": "fallback",
                "generated_at": datetime(2026, 5, 24, 4, 20),
                "error_message": "14 个资讯源暂不可用；LLM 简报降级：400 Bad Request: bad model",
                "payload_json": {},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is None


def test_update_service_start_daily_brief_reuses_active_matching_payload(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())

    task_id = service.start_daily_brief({"report_date": "2026-05-23", "reason": "scheduled"})
    duplicate = service.start_daily_brief({"reason": "scheduled", "report_date": "2026-05-23"})
    row = db.query("SELECT kind, status, stage, source, payload_json FROM task_runs WHERE id = ?", [task_id])[0]

    assert task_id.startswith("brief-")
    assert duplicate == task_id
    assert row["kind"] == "brief"
    assert row["status"] == "queued"
    assert row["stage"] == "准备资讯简报"
    assert row["source"] == "新闻资讯 + LLM"
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 1


def test_brief_task_dispatch_runs_background_generator(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "brief-legacy",
        kind="brief",
        status="running",
        stage="准备资讯简报",
        source=None,
        summary={},
        payload={},
    )

    def fake_generate(report_date=None, progress=None):
        assert report_date == date(2026, 5, 23)
        progress("抓取资讯源", 1, 3)
        return {
            "brief_id": "brief-20260523",
            "status": "completed_full",
            "article_count": 3,
            "source_count": 2,
            "llm_used": True,
            "warnings": [],
            "visible_warning": None,
        }

    monkeypatch.setattr(service.daily_brief_service, "generate", fake_generate)

    service._run_daily_brief("brief-legacy", {"report_date": "2026-05-23"})
    row = db.query("SELECT status, stage, source, summary_json FROM task_runs WHERE id = 'brief-legacy'")[0]

    assert row["status"] == "completed_full"
    assert row["stage"] == "资讯简报完成"
    assert row["source"] == "新闻资讯 + LLM"
    assert json.loads(row["summary_json"])["llm_used"] is True


def test_daily_brief_scheduler_enqueues_daily_slot(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyBriefScheduler(service, poll_seconds=1, schedule_time="08:20")
    now = datetime(2026, 5, 23, 8, 25, tzinfo=ZoneInfo("Asia/Shanghai"))

    task_id = scheduler.tick(now)
    duplicate = scheduler.tick(now)

    assert task_id == "brief-auto-20260523-0820"
    assert duplicate is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 1


def test_daily_brief_scheduler_multiple_daily_slots_enqueue_once_per_slot(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyBriefScheduler(service, poll_seconds=1, schedule_time="08:20,18:20")

    before_first = scheduler.tick(datetime(2026, 5, 23, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    morning = scheduler.tick(datetime(2026, 5, 23, 8, 25, tzinfo=ZoneInfo("Asia/Shanghai")))
    morning_duplicate = scheduler.tick(datetime(2026, 5, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    evening = scheduler.tick(datetime(2026, 5, 23, 18, 25, tzinfo=ZoneInfo("Asia/Shanghai")))

    task_ids = [
        row["id"]
        for row in db.query("SELECT id FROM task_runs WHERE kind = 'brief' ORDER BY id")
    ]
    assert before_first is None
    assert morning == "brief-auto-20260523-0820"
    assert morning_duplicate is None
    assert evening == "brief-auto-20260523-1820"
    assert task_ids == ["brief-auto-20260523-0820", "brief-auto-20260523-1820"]


def test_daily_brief_scheduler_catches_up_latest_due_slot(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyBriefScheduler(service, poll_seconds=1, schedule_time="08:20,18:20")

    task_id = scheduler.tick(datetime(2026, 5, 23, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert task_id == "brief-auto-20260523-1820"
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 1
