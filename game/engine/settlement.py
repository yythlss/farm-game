# -*- coding: utf-8 -*-
"""每日结算：生长、水分、虫害、受灾、市场波动与事件效果落地。

产量公式（核心可讲点）::

    产量 = 基础产量 × 天气系数 × 照料系数 × 事件系数

其中照料系数由水分、施肥、虫害三部分相乘得到，事件系数来自 AI 事件的 growth_bonus 累加。
"""
from __future__ import annotations

import random

from . import weather as weather_mod
from .config import (
    CROPS,
    DAILY_ENERGY_RECOVER,
    MARKET_DAILY_VOLATILITY,
    MARKET_MAX_RATIO,
    MARKET_MEAN_REVERSION,
    MARKET_MIN_RATIO,
    MAX_ENERGY,
    WATER_GOOD,
    WATER_LOW,
    crop_weather_factor,
)
from .state import add_log

# 地块连续缺水多少天后作物枯死
DRY_DEATH_DAYS = 3
# 虫害基础发生率
PEST_BASE_CHANCE = 0.05
PEST_WEATHER_CHANCE = {"干旱": 0.08, "暴风雨": 0.06, "寒潮": 0.03}
# 事件系数允许区间
EVENT_BONUS_MIN, EVENT_BONUS_MAX = 0.5, 2.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------
# 产量计算
# --------------------------------------------------------------------------
def water_factor(plot: dict) -> float:
    """水分系数：充足 1.0 / 偏低 0.85 / 严重缺水 0.6。"""
    water = plot.get("water", 0)
    if water >= WATER_GOOD:
        return 1.0
    if water >= WATER_LOW:
        return 0.85
    return 0.6


def care_factor(plot: dict) -> float:
    """照料系数 = 水分 × 施肥 × 虫害。"""
    factor = water_factor(plot)
    if plot.get("fertilized"):
        factor *= 1.25
    if plot.get("pest"):
        factor *= 0.55
    return factor


def event_factor(plot: dict) -> float:
    return _clamp(float(plot.get("event_bonus", 1.0)), EVENT_BONUS_MIN, EVENT_BONUS_MAX)


def harvest_yield(state: dict, plot: dict) -> int:
    """按公式计算并返回该地块本次收割的产量（份）。"""
    crop = plot.get("crop")
    if not crop:
        return 0
    base = CROPS[crop]["base_yield"]
    weather_f = crop_weather_factor(crop, state["weather"])
    raw = base * weather_f * care_factor(plot) * event_factor(plot)
    return max(1, int(round(raw)))


# --------------------------------------------------------------------------
# 事件效果
# --------------------------------------------------------------------------
def grant_growth_bonus(state: dict, bonus: float) -> int:
    """把 growth_bonus 累加到所有在地作物的事件系数上，返回受影响地块数。"""
    if not bonus:
        return 0
    affected = 0
    for plot in state["land"]:
        if plot.get("crop"):
            plot["event_bonus"] = _clamp(
                float(plot.get("event_bonus", 1.0)) + float(bonus),
                EVENT_BONUS_MIN,
                EVENT_BONUS_MAX,
            )
            affected += 1
    return affected


def apply_market_modifier(state: dict, modifier: dict) -> list[str]:
    """按 {作物: 系数} 调整市场价格，返回可读描述。"""
    notes: list[str] = []
    for crop, mult in (modifier or {}).items():
        item = state["market"].get(crop)
        if not item:
            continue
        try:
            mult = float(mult)
        except (TypeError, ValueError):
            continue
        mult = _clamp(mult, 0.5, 2.0)
        base = item["base"]
        new_price = _clamp(item["price"] * mult, base * 0.5, base * 2.0)
        item["prev"] = item["price"]
        item["price"] = max(1, int(round(new_price)))
        item["delta"] = item["price"] - item["prev"]
        arrow = "↑" if item["price"] > item["prev"] else ("↓" if item["price"] < item["prev"] else "→")
        notes.append(f"{crop} {item['prev']}→{item['price']} {arrow}")
    return notes


def _op_heal_pest(state: dict, rng: random.Random) -> list[str]:
    healed = 0
    for plot in state["land"]:
        if plot.get("pest"):
            plot["pest"] = False
            healed += 1
    if healed:
        state["stats"]["pest_cleared"] += healed
        return [f"清除了 {healed} 块地的虫害。"]
    return ["地里并没有虫害，白忙一场。"]


def _op_crop_damage(state: dict, rng: random.Random) -> list[str]:
    candidates = [p for p in state["land"] if p.get("crop")]
    if not candidates:
        return ["地里空空如也，没什么可损失的。"]
    targets = rng.sample(candidates, k=min(len(candidates), rng.randint(1, 2)))
    notes = []
    for plot in targets:
        loss = CROPS[plot["crop"]]["grow_days"] * 0.45
        plot["progress"] = max(0.0, plot["progress"] - loss)
        notes.append(f"{plot['crop']} 受灾，生长进度倒退。")
    return notes


def _op_lose_crop(state: dict, rng: random.Random) -> list[str]:
    candidates = [p for p in state["land"] if p.get("crop")]
    if not candidates:
        return ["地里空空如也，什么也没损失。"]
    plot = rng.choice(candidates)
    crop = plot["crop"]
    plot.update({"crop": None, "progress": 0.0, "fertilized": False, "pest": False,
                 "event_bonus": 1.0, "planted_day": None, "dry_days": 0})
    return [f"第 {plot['id'] + 1} 号地的 {crop} 全毁了。"]


def _op_free_water(state: dict, rng: random.Random) -> list[str]:
    for plot in state["land"]:
        plot["water"] = min(100, int(plot.get("water", 0)) + 45)
        if plot["water"] > 0:
            plot["dry_days"] = 0
    return ["所有地块都喝饱了水。"]


def _op_market_boom(state: dict, rng: random.Random) -> list[str]:
    names = rng.sample(list(state["market"].keys()), k=min(2, len(state["market"])))
    return apply_market_modifier(state, {n: 1.25 for n in names}) or ["市场价格纹丝不动。"]


def _op_market_crash(state: dict, rng: random.Random) -> list[str]:
    names = rng.sample(list(state["market"].keys()), k=min(2, len(state["market"])))
    return apply_market_modifier(state, {n: 0.8 for n in names}) or ["市场价格纹丝不动。"]


def _op_gift_seed(state: dict, rng: random.Random) -> list[str]:
    crop = rng.choice(list(CROPS.keys()))
    state["seeds"][crop] = state["seeds"].get(crop, 0) + 2
    return [f"获得 {crop}种子 ×2。"]


def _op_extra_energy(state: dict, rng: random.Random) -> list[str]:
    state["energy"] = min(state["max_energy"], state["energy"] + 3)
    return ["体力 +3。"]


def _op_nothing(state: dict, rng: random.Random) -> list[str]:
    return []


EFFECT_OPS = {
    "none": _op_nothing,
    "heal_pest": _op_heal_pest,
    "crop_damage": _op_crop_damage,
    "lose_crop": _op_lose_crop,
    "free_water": _op_free_water,
    "market_boom": _op_market_boom,
    "market_crash": _op_market_crash,
    "gift_seed": _op_gift_seed,
    "extra_energy": _op_extra_energy,
}


def apply_effects(state: dict, effects: dict, rng: random.Random) -> list[str]:
    """应用事件（或选项）携带的数值效果，返回可读描述。"""
    notes: list[str] = []
    gold = int(effects.get("gold") or 0)
    if gold:
        state["gold"] = max(0, state["gold"] + gold)
        notes.append(f"金币 {'+' if gold > 0 else ''}{gold}。")

    energy = int(effects.get("energy") or 0)
    if energy:
        state["energy"] = max(0, min(state["max_energy"], state["energy"] + energy))
        notes.append(f"体力 {'+' if energy > 0 else ''}{energy}。")

    bonus = float(effects.get("growth_bonus") or 0)
    if bonus:
        affected = grant_growth_bonus(state, bonus)
        sign = "+" if bonus > 0 else ""
        notes.append(f"作物生长系数 {sign}{round(bonus * 100)}%（{affected} 块地）。")

    modifier = effects.get("market_modifier") or {}
    if modifier:
        market_notes = apply_market_modifier(state, modifier)
        if market_notes:
            notes.append("行情变动：" + "，".join(market_notes) + "。")

    op = effects.get("op")
    if op:
        handler = EFFECT_OPS.get(op)
        if handler:
            notes.extend(handler(state, rng))
    return notes


def resolve_event(state: dict, index: int, rng: random.Random) -> dict:
    """结算玩家对当日事件选项的选择。"""
    event = state.get("pending_event")
    if not event:
        return {"ok": False, "error": "当前没有待处理的事件。"}
    if index is False or index is None:
        return {"ok": False, "error": "请选择一个选项。"}
    try:
        index = int(index)
    except (TypeError, ValueError):
        return {"ok": False, "error": "选项参数不合法。"}

    choices = event.get("choices") or []
    if not (0 <= index < len(choices)):
        return {"ok": False, "error": "该选项不存在。"}

    choice = choices[index]
    cost = int(choice.get("cost") or 0)
    if cost > state["gold"]:
        return {"ok": False, "error": f"金币不足，需要 {cost} 金币（当前 {state['gold']}）。"}

    messages: list[str] = [f"【{event.get('title', '事件')}】你选择了「{choice.get('text', '')}」。"]

    if cost:
        state["gold"] -= cost
        state["stats"]["total_spent"] += cost
        messages.append(f"支付 {cost} 金币。")

    messages.extend(apply_effects(state, event.get("effects") or {}, rng))
    merged = dict(choice.get("effects") or {})
    if "op" not in merged and choice.get("effect"):
        merged["op"] = choice["effect"]
    messages.extend(apply_effects(state, merged, rng))

    state["pending_event"] = None
    for line in messages:
        add_log(state, line, event.get("type", "info"), event.get("source"))
    return {"ok": True, "messages": messages}


# --------------------------------------------------------------------------
# 每日推进
# --------------------------------------------------------------------------
def update_market(state: dict, rng: random.Random) -> None:
    """市场价格随机游走 + 向基准价回归。"""
    for item in state["market"].values():
        base = item["base"]
        price = item["price"]
        revert = (base - price) * MARKET_MEAN_REVERSION
        noise = base * rng.uniform(-MARKET_DAILY_VOLATILITY, MARKET_DAILY_VOLATILITY)
        new_price = _clamp(price + revert + noise, base * MARKET_MIN_RATIO, base * MARKET_MAX_RATIO)
        item["prev"] = price
        item["price"] = max(1, int(round(new_price)))
        item["delta"] = item["price"] - price


def _grow_plots(state: dict, rng: random.Random) -> list[str]:
    notes: list[str] = []
    delta_water = weather_mod.water_delta(state["weather"])
    risk = weather_mod.damage_risk(state["weather"])

    for plot in state["land"]:
        # 1) 水分变化
        plot["water"] = max(0, min(100, int(plot.get("water", 0)) + delta_water))
        if plot["water"] > 0:
            plot["dry_days"] = 0
        else:
            plot["dry_days"] = int(plot.get("dry_days", 0)) + 1

        crop = plot.get("crop")
        if not crop:
            continue

        cfg = CROPS[crop]
        mature = plot["progress"] >= cfg["grow_days"]

        # 2) 枯死判定
        if plot["dry_days"] >= DRY_DEATH_DAYS:
            plot.update({"crop": None, "progress": 0.0, "fertilized": False, "pest": False,
                         "event_bonus": 1.0, "planted_day": None, "dry_days": 0})
            notes.append(f"第 {plot['id'] + 1} 号地的 {crop} 因缺水枯死了。")
            continue

        # 3) 生长（成熟后不再增长）
        if not mature:
            speed = crop_weather_factor(crop, state["weather"])
            speed *= 1.0 if plot["water"] >= WATER_LOW else 0.6
            if plot["pest"]:
                speed *= 0.7
            plot["progress"] = min(
                float(cfg["grow_days"]), float(plot["progress"]) + max(0.0, speed)
            )

        # 4) 天气受灾
        if risk and rng.random() < risk:
            backup = cfg["grow_days"] * 0.35
            plot["progress"] = max(0.0, plot["progress"] - backup)
            notes.append(f"第 {plot['id'] + 1} 号地的 {crop} 受 {state['weather']} 影响，长势倒退。")

        # 5) 虫害
        chance = PEST_BASE_CHANCE + PEST_WEATHER_CHANCE.get(state["weather"], 0.0)
        if not plot["pest"] and rng.random() < chance:
            plot["pest"] = True
            state["stats"]["pest_suffered"] += 1
            notes.append(f"第 {plot['id'] + 1} 号地的 {crop} 生了虫害！")

    return notes


def advance_day(state: dict, rng: random.Random) -> dict:
    """推进到下一自然日：天气、生长、水分、虫害、市场、体力。"""
    if state.get("finished"):
        return {"ok": False, "error": "本局已经结束了。"}
    if state.get("pending_event"):
        return {"ok": False, "error": "请先处理今日事件，再进入新的一天。"}

    if state["day"] >= state["max_day"]:
        state["finished"] = True
        add_log(state, f"第 {state['max_day']} 天结束，本季收官！", "info")
        return {"ok": True, "finished": True, "messages": ["30 天结束，进入结算。"]}

    state["day"] += 1
    new_weather = weather_mod.advance(state, rng)
    add_log(
        state,
        f"第 {state['day']} 天，天气转为 {new_weather} {_weather_icon(new_weather)}"
        f"（预报：{state['forecast']}）",
        "weather",
    )

    notes = _grow_plots(state, rng)
    for note in notes:
        add_log(state, note, "pest" if "虫害" in note else "weather")

    update_market(state, rng)

    recovered = min(state["max_energy"], state["energy"] + DAILY_ENERGY_RECOVER)
    gained = recovered - state["energy"]
    state["energy"] = recovered
    if gained:
        add_log(state, f"休息了一晚，体力恢复 +{gained}（{state['energy']}/{state['max_energy']}）。", "info")

    record_peak(state)
    return {"ok": True, "messages": notes, "weather": new_weather}


def _weather_icon(name: str) -> str:
    from .config import WEATHERS

    return WEATHERS.get(name, {}).get("icon", "")


def record_peak(state: dict) -> None:
    """记录峰值指标，用于成就与结算统计。"""
    from .rating import total_assets

    state["stats"]["peak_gold"] = max(state["stats"]["peak_gold"], state["gold"])
    state["stats"]["max_asset"] = max(state["stats"]["max_asset"], total_assets(state))
