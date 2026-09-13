# -*- coding: utf-8 -*-
"""天气系统：随机生成、次日预报与天气影响查询。"""
from __future__ import annotations

import random

from .config import WEATHERS, WEATHER_NAMES


def roll_weather(rng: random.Random, exclude: str | None = None) -> str:
    """按权重随机一种天气，``exclude`` 用于避免连续两天完全相同。"""
    names = [n for n in WEATHER_NAMES if n != exclude] or WEATHER_NAMES
    weights = [WEATHERS[n]["weight"] for n in names]
    return rng.choices(names, weights=weights, k=1)[0]


def roll_forecast(rng: random.Random, current: str) -> str:
    """生成次日预报（有 70% 概率与最终天气一致）。"""
    if rng.random() < 0.7:
        return roll_weather(rng, exclude=current)
    return roll_weather(rng)


def advance(state: dict, rng: random.Random) -> str:
    """把预报变成今天的天气，并生成新的预报。返回今天的新天气。"""
    nxt = state.get("forecast")
    if nxt not in WEATHERS:
        nxt = roll_weather(rng, exclude=state.get("weather"))
    state["weather"] = nxt
    state["forecast"] = roll_forecast(rng, nxt)
    return nxt


def water_delta(weather: str) -> int:
    """该天气下每日水分变化。"""
    return int(WEATHERS.get(weather, {}).get("water_delta", 0))


def damage_risk(weather: str) -> float:
    """该天气下作物受灾（进度倒退）的概率。"""
    return float(WEATHERS.get(weather, {}).get("damage", 0.0))
