from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from backend.app.config import settings
from backend.app.db import Database
from backend.app.services.daily_brief_service import _extract_json, _http_error_message


PROMPT_VERSION = "candidate-ai-v2"


class CandidateSummaryService:
    def __init__(
        self,
        db: Database,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_url: Optional[str] = None,
    ):
        self.db = db
        self.api_key = settings.daily_brief_api_key if api_key is None else api_key
        self.model = model or settings.daily_brief_model
        self.llm_url = llm_url or settings.daily_brief_llm_url

    def summarize(
        self,
        run_id: str,
        code: str,
        candidate: Dict[str, Any],
        matched_rules: Optional[List[Dict[str, Any]]] = None,
        risk_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        identity = self.prepare_summary_identity(run_id, code, candidate, matched_rules, risk_items)
        cached = self.read_summary(run_id, code, input_hash=identity["input_hash"])
        if cached.get("status") in {"completed_full", "completed_partial"} and cached.get("summary"):
            return cached["summary"]
        result = self.generate_and_store(identity)
        return result.get("summary") or {}

    def prepare_summary_identity(
        self,
        run_id: str,
        code: str,
        candidate: Dict[str, Any],
        matched_rules: Optional[List[Dict[str, Any]]] = None,
        risk_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        evidence = {
            "candidate": _compact_candidate(candidate),
            "matched_rules": (matched_rules or [])[:8],
            "risk_items": (risk_items or [])[:8],
            "prompt_version": PROMPT_VERSION,
            "llm_model": self.model,
        }
        input_hash = _stable_hash(evidence)
        return {
            "run_id": run_id,
            "code": code,
            "candidate": evidence["candidate"],
            "matched_rules": evidence["matched_rules"],
            "risk_items": evidence["risk_items"],
            "prompt_version": PROMPT_VERSION,
            "llm_model": self.model,
            "input_hash": input_hash,
            "evidence": evidence,
        }

    def prepare_from_result(self, run_id: str, code: str) -> Dict[str, Any]:
        rows = self.db.query(
            """
            SELECT *
            FROM candidate_results
            WHERE run_id = ? AND code = ?
            LIMIT 1
            """,
            [run_id, code],
        )
        candidate = {"code": code, "name": code, "reasons": [], "metrics": {}}
        if rows:
            row = rows[0]
            metrics = _loads_json(row.get("metrics_json"))
            candidate = {
                "code": row.get("code") or code,
                "name": row.get("name") or row.get("code") or code,
                "signal_score": row.get("signal_score"),
                "signal_type": row.get("signal_type"),
                "latest_price": row.get("latest_price"),
                "pct_chg": row.get("pct_chg"),
                "amount": row.get("amount"),
                "turnover_rate": row.get("turnover_rate"),
                "float_market_value": row.get("float_market_value"),
                "reasons": _loads_json(row.get("reasons_json"), fallback=[]),
                "metrics": metrics,
            }
        metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
        matched_rules = metrics.get("matched_rules") if isinstance(metrics.get("matched_rules"), list) else []
        risk_items = metrics.get("risk_items") if isinstance(metrics.get("risk_items"), list) else []
        if matched_rules or risk_items:
            return self.prepare_summary_identity(run_id, code, candidate, matched_rules, risk_items)

        rule_results = metrics.get("strategy_rule_results")
        if not isinstance(rule_results, list):
            rule_results = []
        matched_rules = [item for item in rule_results if isinstance(item, dict) and item.get("matched")]
        risk_items = [
            item
            for item in rule_results
            if isinstance(item, dict) and (item.get("action") == "risk" or item.get("missing") or item.get("reason"))
        ]
        return self.prepare_summary_identity(run_id, code, candidate, matched_rules, risk_items)

    def read_summary(self, run_id: str, code: str, input_hash: Optional[str] = None) -> Dict[str, Any]:
        rows = self.db.query(
            """
            SELECT *
            FROM candidate_ai_summaries
            WHERE run_id = ? AND code = ?
            ORDER BY updated_at DESC NULLS LAST, generated_at DESC NULLS LAST
            LIMIT 1
            """,
            [run_id, code],
        )
        if not rows:
            return {"status": "not_requested", "run_id": run_id, "code": code, "summary": None}
        row = rows[0]
        summary = _loads_json(row.get("summary_json"))
        prompt_version = row.get("prompt_version") or summary.get("prompt_version")
        status = row.get("status") or "completed_full"
        if prompt_version != PROMPT_VERSION:
            status = "stale"
        if input_hash and row.get("input_hash") != input_hash:
            status = "stale"
        return {
            "status": status,
            "task_id": row.get("task_id"),
            "run_id": run_id,
            "code": code,
            "input_hash": row.get("input_hash"),
            "prompt_version": prompt_version,
            "llm_model": row.get("llm_model"),
            "fallback_reason": row.get("fallback_reason"),
            "error_message": row.get("error_message"),
            "summary": summary or None,
            "generated_at": row.get("generated_at"),
            "updated_at": row.get("updated_at"),
        }

    def generate_and_store(self, identity: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
        generated_at = datetime.utcnow().isoformat(timespec="seconds")
        candidate = identity["candidate"]
        matched = identity["matched_rules"]
        risks = identity["risk_items"]
        if not self.api_key:
            summary = _fallback_result(candidate, matched, risks, generated_at, "missing_api_key")
            status = "completed_partial"
        else:
            try:
                result = self._call_llm(candidate, matched, risks)
                summary = _normalize_llm_result(result, candidate, matched, risks, generated_at)
                status = "completed_full"
            except ValueError as exc:
                summary = _fallback_result(candidate, matched, risks, generated_at, "invalid_response", str(exc))
                status = "completed_partial"
            except Exception as exc:
                summary = _fallback_result(candidate, matched, risks, generated_at, "llm_error", str(exc))
                status = "completed_partial"
        self.persist_summary(identity, summary, status=status, task_id=task_id)
        return self.read_summary(identity["run_id"], identity["code"], input_hash=identity["input_hash"])

    def persist_summary(
        self,
        identity: Dict[str, Any],
        summary: Dict[str, Any],
        status: str,
        task_id: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        self.db.upsert(
            "candidate_ai_summaries",
            [
                {
                    "run_id": identity["run_id"],
                    "code": identity["code"],
                    "status": status,
                    "task_id": task_id,
                    "input_hash": identity["input_hash"],
                    "prompt_version": identity["prompt_version"],
                    "evidence_json": json.dumps(identity.get("evidence") or {}, ensure_ascii=False),
                    "summary_json": json.dumps(summary, ensure_ascii=False),
                    "llm_model": self.model,
                    "fallback_reason": summary.get("fallback_reason"),
                    "error_message": summary.get("error_message"),
                    "requested_at": now,
                    "generated_at": summary.get("generated_at") or now,
                    "updated_at": now,
                }
            ],
            ["run_id", "code"],
        )

    def mark_queued(self, identity: Dict[str, Any], task_id: str) -> None:
        self._mark_status(identity, status="queued", task_id=task_id)

    def mark_running(self, identity: Dict[str, Any], task_id: str) -> None:
        self._mark_status(identity, status="running", task_id=task_id)

    def mark_failed(self, identity: Dict[str, Any], task_id: str, error_message: str) -> None:
        self._mark_status(identity, status="failed", task_id=task_id, error_message=error_message)

    def _mark_status(
        self,
        identity: Dict[str, Any],
        status: str,
        task_id: str,
        error_message: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        self.db.upsert(
            "candidate_ai_summaries",
            [
                {
                    "run_id": identity["run_id"],
                    "code": identity["code"],
                    "status": status,
                    "task_id": task_id,
                    "input_hash": identity["input_hash"],
                    "prompt_version": identity["prompt_version"],
                    "evidence_json": json.dumps(identity.get("evidence") or {}, ensure_ascii=False),
                    "summary_json": None,
                    "llm_model": self.model,
                    "fallback_reason": None,
                    "error_message": error_message,
                    "requested_at": now,
                    "generated_at": None,
                    "updated_at": now,
                }
            ],
            ["run_id", "code"],
        )

    def _call_llm(self, candidate: Dict[str, Any], matched_rules: List[Dict[str, Any]], risk_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
        compact = {
            "candidate": {
                "code": candidate.get("code"),
                "name": candidate.get("name"),
                "signal_score": candidate.get("signal_score"),
                "signal_type": candidate.get("signal_type"),
                "latest_price": candidate.get("latest_price"),
                "pct_chg": candidate.get("pct_chg"),
                "amount": candidate.get("amount"),
                "turnover_rate": candidate.get("turnover_rate"),
                "float_market_value": candidate.get("float_market_value"),
                "reasons": candidate.get("reasons") or [],
                "metrics": _compact_metrics(metrics),
            },
            "matched_rules": matched_rules[:8],
            "risk_items": risk_items[:8],
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是A股量化研究助手。只基于输入的结构化证据解释候选，不给确定性交易指令，不编造数据。"
                        "你的任务是把规则命中、分数拆解、展示字段和风险项翻译成克制、可执行的研究解读。"
                        "不要写买入/卖出建议，不要使用未给出的盘口、新闻或财报信息。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请输出严格 JSON，字段为："
                        "summary：1-2 句 AI 解读，说明这只股票为什么值得观察以及证据强弱；"
                        "opportunities：2-4 条入选理由，必须引用输入里的规则、分数或指标值；"
                        "risks：2-4 条风险提示，若风险不足也要说明需要验证的条件；"
                        "watch_plan：2-4 条后续观察动作，包含量价延续、失效条件和复盘节奏。"
                        "所有内容使用中文短句，不要 markdown，不要编号，不要确定性交易指令。\n"
                    )
                    + json.dumps(compact, ensure_ascii=False),
                },
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=80) as client:
            try:
                data = self._post_llm(client, payload)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 400:
                    raise RuntimeError(_http_error_message(exc)) from exc
                relaxed_payload = dict(payload)
                relaxed_payload.pop("response_format", None)
                data = self._post_llm(client, relaxed_payload)
        content = data["choices"][0]["message"]["content"]
        return json.loads(_extract_json(content))

    def _post_llm(self, client: httpx.Client, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = client.post(
            self.llm_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def _compact_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    keep = [
        "volume_ratio",
        "topic_heat",
        "theme_limit_count",
        "main_net_amount",
        "net_mf_amount",
        "limit_type",
        "limit_fd_mv_ratio",
        "top_list_net_amount",
        "display_metrics",
        "risk_flags",
        "score_breakdown",
        "freshness",
        "interpretation",
    ]
    return {key: metrics.get(key) for key in keep if key in metrics}


def _compact_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    return {
        "code": candidate.get("code"),
        "name": candidate.get("name"),
        "signal_score": candidate.get("signal_score"),
        "signal_type": candidate.get("signal_type"),
        "latest_price": candidate.get("latest_price"),
        "pct_chg": candidate.get("pct_chg"),
        "amount": candidate.get("amount"),
        "turnover_rate": candidate.get("turnover_rate"),
        "float_market_value": candidate.get("float_market_value"),
        "reasons": candidate.get("reasons") or [],
        "metrics": _compact_metrics(metrics),
    }


def _normalize_llm_result(
    result: Dict[str, Any],
    candidate: Dict[str, Any],
    matched_rules: List[Dict[str, Any]],
    risk_items: List[Dict[str, Any]],
    generated_at: str,
) -> Dict[str, Any]:
    return {
        "enabled": True,
        "summary": str(result.get("summary") or result.get("ai_interpretation") or _fallback_summary(candidate, matched_rules)),
        "opportunities": _string_list(result.get("opportunities")) or _fallback_opportunities(candidate, matched_rules),
        "risks": _string_list(result.get("risks")) or _fallback_risks(candidate, risk_items),
        "watch_plan": _string_list(result.get("watch_plan")) or _fallback_watch_plan(),
        "generated_at": generated_at,
        "prompt_version": PROMPT_VERSION,
        "fallback_reason": None,
        "error_message": None,
    }


def _stable_hash(value: Dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _loads_json(value: Any, fallback: Optional[Any] = None) -> Any:
    if fallback is None:
        fallback = {}
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def _fallback_result(
    candidate: Dict[str, Any],
    matched_rules: List[Dict[str, Any]],
    risk_items: List[Dict[str, Any]],
    generated_at: str,
    fallback_reason: str,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "enabled": False,
        "summary": _fallback_summary(candidate, matched_rules),
        "opportunities": _fallback_opportunities(candidate, matched_rules),
        "risks": _fallback_risks(candidate, risk_items),
        "watch_plan": _fallback_watch_plan(),
        "generated_at": generated_at,
        "prompt_version": PROMPT_VERSION,
        "fallback_reason": fallback_reason,
        "error_message": error_message,
    }


def _fallback_summary(candidate: Dict[str, Any], matched_rules: List[Dict[str, Any]]) -> str:
    name = str(candidate.get("name") or candidate.get("code") or "候选")
    score = candidate.get("signal_score")
    reasons = [str(item) for item in candidate.get("reasons") or [] if item]
    rule_names = [str(item.get("indicator_name") or item.get("indicator_id") or "") for item in matched_rules if item]
    evidence = reasons[:2] or [name for name in rule_names[:2] if name]
    evidence_text = "、".join(evidence) if evidence else "基础规则命中"
    score_text = f"总分 {score}" if score is not None else "分数待确认"
    return f"{name} {score_text}，主要证据来自{evidence_text}；当前为规则解释，配置模型后会生成更完整的 AI 解读。"


def _fallback_opportunities(candidate: Dict[str, Any], matched_rules: List[Dict[str, Any]]) -> List[str]:
    reasons = [str(item) for item in candidate.get("reasons") or [] if item]
    if reasons:
        return reasons[:3]
    names = [str(item.get("indicator_name") or item.get("indicator_id") or "") for item in matched_rules if item]
    return [f"{name} 条件命中" for name in names[:3] if name] or ["入选条件较完整，等待后续走势确认。"]


def _fallback_risks(candidate: Dict[str, Any], risk_items: List[Dict[str, Any]]) -> List[str]:
    risks = [str(item.get("reason") or item.get("indicator_name") or item.get("indicator_id") or "") for item in risk_items if item]
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    risk_flags = [str(item) for item in metrics.get("risk_flags") or [] if item]
    return (risks + risk_flags)[:3] or ["关注放量回落、跌破平台或市场环境转弱。"]


def _fallback_watch_plan() -> List[str]:
    return ["观察 1-3 个交易日的量价延续。", "跌破关键平台或风险项重新命中时移出观察池。", "复盘 T+1、T+3、T+5 收益。"]


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
