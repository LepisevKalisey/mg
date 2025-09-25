import os
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, time

import yaml

from .config import settings

# Simple in-memory structures; for production use, replace with Redis/DB.
_cluster_locks: dict[str, float] = {}
_clusters: dict[str, Dict[str, Any]] = {}


def _now_local() -> datetime:
    # Simple local time assumption; could use pytz/zoneinfo if needed
    return datetime.now()


def _parse_time(hhmm: str) -> Optional[time]:
    try:
        hh, mm = hhmm.split(":", 1)
        return time(int(hh), int(mm))
    except Exception:
        return None


def load_policy() -> Dict[str, Any]:
    if not os.path.exists(settings.POLICY_CONFIG_PATH):
        return {}
    try:
        with open(settings.POLICY_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_policy(cfg: Dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(settings.POLICY_CONFIG_PATH), exist_ok=True)
        with open(settings.POLICY_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def _classify(tags: List[str]) -> str:
    tset = set([t.lower() for t in tags or []])
    if tset & {"news", "other", "fact", "result"}:
        return "NEWS"
    if tset & {"expert", "analitics", "opinion", "story"}:
        return "EXPERT"
    return "NEWS" if "news" in tset else "EXPERT"


def _hard_drop(tags: List[str], hard_drop_tags: List[str]) -> bool:
    return bool(set(tags or []) & set(hard_drop_tags or []))


def _is_quiet_now(quiet_cfg: Dict[str, Any]) -> Tuple[bool, bool]:
    if not quiet_cfg or not quiet_cfg.get("enabled"):
        return False, False
    start = _parse_time(quiet_cfg.get("start", ""))
    end = _parse_time(quiet_cfg.get("end", ""))
    notify_silently = bool(quiet_cfg.get("notify_silently", True))
    now = _now_local().time()
    if start and end:
        if start <= end:
            in_window = (start <= now <= end)
        else:
            in_window = (now >= start or now <= end)
        return in_window, notify_silently
    return False, notify_silently


def _cluster_key(text: str) -> str:
    # Simplified cluster key; replace with shingles+embeddings in production.
    s = (text or "").strip().lower()
    return s[:128]


def _score(source: str, confidence: float, source_weights: Dict[str, float]) -> float:
    w = source_weights.get(source, source_weights.get("default", 1.0))
    recency_boost = 1.0
    return w * max(0.0, min(1.0, confidence or 0.0)) * recency_boost


def decide(post: Dict[str, Any]) -> Dict[str, Any]:
    policy = load_policy()
    p_policy = policy.get("policy", {})

    # 1) Hard-filter
    if _hard_drop(post.get("tags", []), p_policy.get("hard_drop_tags", [])):
        return {
            "post_id": post.get("id"),
            "cluster_id": None,
            "class": "REJECTED",
            "action": "REJECT",
            "editor_notify": {"send": False},
        }

    # 2) Cluster
    cluster_id = _cluster_key(post.get("text", ""))
    cl = _clusters.get(cluster_id)
    if not cl:
        cl = {"posts": [], "published": False, "merge_sources": []}
        _clusters[cluster_id] = cl
    cl["posts"].append(post)

    # 3) Classification
    klass = _classify(post.get("tags", []))

    # 4) Decision by class
    source_weights = p_policy.get("source_weights", {})
    quiet_cfg = (p_policy.get("news", {}) if klass == "NEWS" else p_policy.get("expert", {})).get("quiet_hours", {})
    in_quiet, silent = _is_quiet_now(quiet_cfg)

    decision: Dict[str, Any] = {
        "post_id": post.get("id"),
        "cluster_id": cluster_id,
        "class": klass,
        "editor_notify": {"send": False, "silent": bool(silent and in_quiet)},
    }

    if klass == "NEWS":
        news_cfg = p_policy.get("news", {})
        auto = bool(news_cfg.get("autoapprove", False))
        forward = bool(news_cfg.get("forward_to_editors", False))
        window = int(news_cfg.get("debounce_window_sec", 0) or 0)
        undo_window_sec = int(news_cfg.get("undo_window_sec", 0) or 0)

        if not auto and not forward:
            decision.update({
                "action": "SEND_TO_MOD",
                "editor_notify": {"send": False},
            })
            return decision
        if not auto and forward:
            decision.update({
                "action": "SEND_TO_MOD",
                "editor_notify": {"send": True, "silent": bool(silent and in_quiet), "card_status": "PENDING_REVIEW"},
            })
            return decision
        if auto and not forward:
            # Debounce and auto-publish
            if window <= 0:
                best = max(cl["posts"], key=lambda p: _score(p.get("source", ""), p.get("confidence", 0.0), source_weights))
                decision.update({
                    "action": "AUTO_PUBLISH",
                    "publish_plan": {"when": "now", "channel": post.get("source"), "merge_sources": [p.get("source") for p in cl["posts"] if p is not best]},
                })
                return decision
            else:
                decision.update({
                    "action": "DEBOUNCE",
                    "publish_plan": {"when": "ts"},
                })
                return decision
        if auto and forward:
            # Parallel editor card with undo window
            decision.update({
                "action": "DEBOUNCE",
                "editor_notify": {"send": True, "silent": bool(silent and in_quiet), "card_status": "AUTOAPPROVED", "undo_deadline_ts": None},
            })
            return decision

    else:  # EXPERT
        expert_cfg = p_policy.get("expert", {})
        auto = bool(expert_cfg.get("autoapprove", False))
        forward = bool(expert_cfg.get("forward_to_editors", False))
        topics = expert_cfg.get("topics", [])
        # naive mapping: pick first topic if any
        topic = topics[0] if topics else None
        undo_window_sec = int(expert_cfg.get("undo_window_sec", 0) or 0)

        if not auto and not forward:
            decision.update({"action": "SEND_TO_MOD", "editor_notify": {"send": False}})
            return decision
        if not auto and forward:
            decision.update({
                "action": "SEND_TO_MOD",
                "editor_notify": {"send": True, "silent": bool(silent and in_quiet), "card_status": "PENDING_REVIEW"},
            })
            return decision
        if auto and not forward:
            decision.update({
                "action": "QUEUE_DIGEST",
                "digest_plan": {"topic": topic, "slot_local": None},
                "editor_notify": {"send": False},
            })
            return decision
        if auto and forward:
            decision.update({
                "action": "QUEUE_DIGEST",
                "digest_plan": {"topic": topic, "slot_local": None},
                "editor_notify": {"send": True, "silent": bool(silent and in_quiet), "card_status": "AUTOQUEUED"},
            })
            return decision

    # Fallback
    decision.setdefault("action", "SEND_TO_MOD")
    return decision