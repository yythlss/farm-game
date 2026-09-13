# -*- coding: utf-8 -*-
"""事件生成主流程：优先调用大模型，失败则无缝降级到内置事件库。

「AI 优先 + 本地兜底」是本项目的核心工程取舍：
既能让大模型成为真正的玩法核心，又能保证现场 Demo 绝不因为网络或限流翻车。
"""
from __future__ import annotations

import random
import time
from typing import Any

from engine.config import (
    CROPS,
    EVENT_CHOICE_MAX,
    EVENT_CHOICE_MIN,
    EVENT_ENERGY_RANGE,
    EVENT_GOLD_RANGE,
    EVENT_GROWTH_RANGE,
    EVENT_MARKET_RANGE,
    EVENT_TYPES,
)
from engine.settlement import EFFECT_OPS
from engine.state import add_log

from . import fallback_events, llm_client, prompts

# 兼容提示词示例里出现的旧写法
OP_ALIASES = {"remove_pest": "heal_pest", "crop_damage_all": "crop_damage", "none": "none"}
MAX_COST = 500
MAX_TEXT_LEN = 60


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_effects(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {}
    effects: dict = {}

    gold = _as_int(raw.get("gold"))
    if gold:
        effects["gold"] = int(_clamp(gold, *EVENT_GOLD_RANGE))

    energy = _as_int(raw.get("energy"))
    if energy:
        effects["energy"] = int(_clamp(energy, *EVENT_ENERGY_RANGE))

    bonus = _as_float(raw.get("growth_bonus"))
    if bonus:
        effects["growth_bonus"] = round(_clamp(bonus, *EVENT_GROWTH_RANGE), 3)

    modifier = raw.get("market_modifier")
    if isinstance(modifier, dict):
        clean: dict[str, float] = {}
        for crop, mult in modifier.items():
            if crop not in CROPS:
                continue
            clean[crop] = round(_clamp(_as_float(mult), *EVENT_MARKET_RANGE), 3)
        if clean:
            effects["market_modifier"] = clean

    op = str(raw.get("op") or raw.get("effect") or "").strip()
    op = OP_ALIASES.get(op, op)
    if op in EFFECT_OPS and op != "none":
        effects["op"] = op

    return effects


def _normalize_choices(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    choices: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        text = text[:MAX_TEXT_LEN]
        op = str(item.get("effect") or item.get("op") or "none").strip()
        op = OP_ALIASES.get(op, op)
        if op not in EFFECT_OPS:
            op = "none"
        choice: dict = {
            "text": text,
            "cost": int(_clamp(_as_int(item.get("cost")), 0, MAX_COST)),
            "effect": op,
        }
        hint = str(item.get("hint") or "").strip()
        if hint:
            choice["hint"] = hint[:MAX_TEXT_LEN]
        extra = _normalize_effects(item.get("effects"))
        if extra:
            choice["effects"] = extra
        choices.append(choice)

    if len(choices) > EVENT_CHOICE_MAX:
        choices = choices[:EVENT_CHOICE_MAX]
    return choices


def normalize_event(raw: dict) -> dict | None:
    """校验并修正大模型返回的事件；结构不达标时返回 None（触发降级）。"""
    if not isinstance(raw, dict):
        return None

    title = str(raw.get("title") or "").strip()
    description = str(raw.get("description") or raw.get("desc") or "").strip()
    if not title or not description:
        return None

    event_type = str(raw.get("type") or "").strip().lower()
    if event_type not in EVENT_TYPES:
        event_type = "social"

    choices = _normalize_choices(raw.get("choices"))
    if len(choices) < EVENT_CHOICE_MIN:
        return None

    return {
        "title": title[:40],
        "description": description[:200],
        "type": event_type,
        "effects": _normalize_effects(raw.get("effects")),
        "choices": choices,
        "source": "llm",
    }


def generate_event(
    state: dict,
    last_action: str | None = None,
    rng: random.Random | None = None,
    use_llm: bool = True,
) -> dict:
    """生成当日事件并写入 ``state['pending_event']``。"""
    rng = rng or random.Random()
    started = time.time()
    event: dict | None = None
    reason = ""

    if use_llm and llm_client.is_configured():
        payload, error = llm_client.chat_json(prompts.build_messages(state, last_action))
        if payload:
            event = normalize_event(payload)
            if event is None:
                reason = "模型返回结构不合法，已降级"
        else:
            reason = error or "模型调用失败，已降级"
    elif use_llm:
        reason = "未配置大模型环境变量，使用内置事件库"
    else:
        reason = "已关闭在线生成，使用内置事件库"

    if event is None:
        event = fallback_events.pick_fallback(rng, state)
        event["source"] = "fallback"
        event["reason"] = reason
        state["stats"]["event_fallback"] += 1
    else:
        event["reason"] = ""
        state["stats"]["event_llm"] += 1

    event["latency"] = round(time.time() - started, 2)
    state["pending_event"] = event
    add_log(state, f"事件：{event['title']} —— {event['description']}", event["type"], event["source"])
    return event
