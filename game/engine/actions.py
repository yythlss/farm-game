# -*- coding: utf-8 -*-
"""玩家行动：播种、浇水、施肥、收获、买卖、休息。

每个行动都会做完整的前置校验（体力 / 金币 / 地块状态 / 库存），
校验不通过时返回 ``{"ok": False, "error": ...}``，绝不产生半截副作用。
"""
from __future__ import annotations

import random

from .config import (
    CROPS,
    ENERGY_COST,
    FERTILIZER_COST,
    REST_ENERGY,
    WATER_PER_ACTION,
)
from .rating import crop_unit_price
from .settlement import harvest_yield, record_peak
from .state import add_log

ACTION_LABELS = {
    "plant": "播种",
    "water": "浇水",
    "fertilize": "施肥",
    "harvest": "收获",
    "buy": "买入",
    "sell": "卖出",
    "rest": "休息",
}


def _need_energy(state: dict, action: str) -> str | None:
    cost = ENERGY_COST.get(action, 0)
    if state["energy"] < cost:
        return f"体力不足（需要 {cost}，当前 {state['energy']}），先休息一下。"
    return None


def _spend_energy(state: dict, action: str) -> None:
    state["energy"] = max(0, state["energy"] - ENERGY_COST.get(action, 0))


def _get_plot(state: dict, index) -> tuple[dict | None, str | None]:
    try:
        index = int(index)
    except (TypeError, ValueError):
        return None, "地块编号不合法。"
    if not (0 <= index < len(state["land"])):
        return None, "地块编号超出范围。"
    return state["land"][index], None


def _get_crop(payload) -> tuple[str | None, str | None]:
    crop = payload.get("crop")
    if crop not in CROPS:
        return None, "作物不存在。"
    return crop, None


# --------------------------------------------------------------------------
# 各行动实现
# --------------------------------------------------------------------------
def _plant(state: dict, payload: dict, rng: random.Random) -> dict:
    plot, err = _get_plot(state, payload.get("plot"))
    if err:
        return {"ok": False, "error": err}
    crop, err = _get_crop(payload)
    if err:
        return {"ok": False, "error": err}
    if plot.get("crop"):
        return {"ok": False, "error": "这块地已经种了作物。"}
    if err := _need_energy(state, "plant"):
        return {"ok": False, "error": err}

    messages: list[str] = []
    cost = CROPS[crop]["seed_cost"]
    if state["seeds"].get(crop, 0) > 0:
        state["seeds"][crop] -= 1
    elif state["gold"] >= cost:
        state["gold"] -= cost
        state["stats"]["total_spent"] += cost
        messages.append(f"种子库存不足，现场花 {cost} 金币买了 1 包 {crop}种子。")
    else:
        return {"ok": False, "error": f"没有 {crop}种子，且金币不足以购买（需 {cost}）。"}

    _spend_energy(state, "plant")
    plot.update({
        "crop": crop,
        "progress": 0.0,
        "fertilized": False,
        "pest": False,
        "event_bonus": 1.0,
        "planted_day": state["day"],
        "dry_days": 0,
    })
    state["stats"]["plant_count"] += 1
    messages.append(f"在第 {plot['id'] + 1} 号地种下了 {crop} {CROPS[crop]['emoji']}，预计 {CROPS[crop]['grow_days']} 天成熟。")
    add_log(state, messages[-1], "action")
    return {"ok": True, "messages": messages}


def _water(state: dict, payload: dict, rng: random.Random) -> dict:
    plot, err = _get_plot(state, payload.get("plot"))
    if err:
        return {"ok": False, "error": err}
    if not plot.get("crop"):
        return {"ok": False, "error": "空地不需要浇水。"}
    if plot["water"] >= 100:
        return {"ok": False, "error": "这块地水分已满。"}
    if err := _need_energy(state, "water"):
        return {"ok": False, "error": err}

    _spend_energy(state, "water")
    plot["water"] = min(100, int(plot["water"]) + WATER_PER_ACTION)
    plot["dry_days"] = 0
    state["stats"]["water_count"] += 1
    text = f"给第 {plot['id'] + 1} 号地浇水，水分 {plot['water']}%。"
    add_log(state, text, "action")
    return {"ok": True, "messages": [text]}


def _fertilize(state: dict, payload: dict, rng: random.Random) -> dict:
    plot, err = _get_plot(state, payload.get("plot"))
    if err:
        return {"ok": False, "error": err}
    if not plot.get("crop"):
        return {"ok": False, "error": "空地不需要施肥。"}
    if plot.get("fertilized"):
        return {"ok": False, "error": "这块地已经施过肥了。"}
    if state["gold"] < FERTILIZER_COST:
        return {"ok": False, "error": f"金币不足，肥料需要 {FERTILIZER_COST} 金币。"}
    if err := _need_energy(state, "fertilize"):
        return {"ok": False, "error": err}

    _spend_energy(state, "fertilize")
    state["gold"] -= FERTILIZER_COST
    state["stats"]["total_spent"] += FERTILIZER_COST
    state["stats"]["fertilize_count"] += 1
    plot["fertilized"] = True
    text = f"给第 {plot['id'] + 1} 号地的 {plot['crop']} 施了肥（-{FERTILIZER_COST} 金币），产量系数 +25%。"
    add_log(state, text, "action")
    return {"ok": True, "messages": [text]}


def _harvest(state: dict, payload: dict, rng: random.Random) -> dict:
    plot, err = _get_plot(state, payload.get("plot"))
    if err:
        return {"ok": False, "error": err}
    crop = plot.get("crop")
    if not crop:
        return {"ok": False, "error": "这块地没有作物。"}
    if plot["progress"] < CROPS[crop]["grow_days"]:
        left = CROPS[crop]["grow_days"] - int(plot["progress"])
        return {"ok": False, "error": f"{crop}还没成熟，大约还需 {max(1, left)} 天。"}
    if err := _need_energy(state, "harvest"):
        return {"ok": False, "error": err}

    _spend_energy(state, "harvest")
    amount = harvest_yield(state, plot)
    state["harvest"][crop] = state["harvest"].get(crop, 0) + amount
    state["stats"]["harvested_count"] += amount
    pest = plot.get("pest", False)
    plot.update({
        "crop": None,
        "progress": 0.0,
        "fertilized": False,
        "pest": False,
        "event_bonus": 1.0,
        "planted_day": None,
        "dry_days": 0,
    })
    text = f"收获 {crop} ×{amount}（第 {plot['id'] + 1} 号地）。"
    if pest:
        text += " 虫害让产量打了折扣。"
    add_log(state, text, "action")
    return {"ok": True, "messages": [text], "harvested": {crop: amount}}


def _buy(state: dict, payload: dict, rng: random.Random) -> dict:
    crop, err = _get_crop(payload)
    if err:
        return {"ok": False, "error": err}
    amount = int(payload.get("amount") or 1)
    if amount <= 0:
        return {"ok": False, "error": "购买数量必须大于 0。"}
    cost = CROPS[crop]["seed_cost"] * amount
    if state["gold"] < cost:
        return {"ok": False, "error": f"金币不足，{amount} 包 {crop}种子需要 {cost} 金币。"}

    state["gold"] -= cost
    state["stats"]["total_spent"] += cost
    state["seeds"][crop] = state["seeds"].get(crop, 0) + amount
    text = f"买入 {crop}种子 ×{amount}，花费 {cost} 金币。"
    add_log(state, text, "market")
    return {"ok": True, "messages": [text]}


def _sell(state: dict, payload: dict, rng: random.Random) -> dict:
    crop, err = _get_crop(payload)
    if err:
        return {"ok": False, "error": err}
    stock = state["harvest"].get(crop, 0)
    if stock <= 0:
        return {"ok": False, "error": f"仓库里没有 {crop} 可卖。"}
    raw_amount = payload.get("amount")
    amount = stock if raw_amount in (None, "", "all") else int(raw_amount)
    if amount <= 0:
        return {"ok": False, "error": "出售数量必须大于 0。"}
    if amount > stock:
        return {"ok": False, "error": f"{crop} 库存只有 {stock} 份。"}

    price = crop_unit_price(state, crop)
    income = price * amount
    state["harvest"][crop] = stock - amount
    state["gold"] += income
    state["stats"]["total_earned"] += income
    text = f"卖出 {crop} ×{amount}，单价 {price}，收入 {income} 金币。"
    add_log(state, text, "market")
    return {"ok": True, "messages": [text], "income": income}


def _rest(state: dict, payload: dict, rng: random.Random) -> dict:
    before = state["energy"]
    state["energy"] = min(state["max_energy"], before + REST_ENERGY)
    gained = state["energy"] - before
    text = f"你靠在谷仓边打了个盹，体力 +{gained}（{state['energy']}/{state['max_energy']}）。"
    add_log(state, text, "info")
    return {"ok": True, "messages": [text]}


HANDLERS = {
    "plant": _plant,
    "water": _water,
    "fertilize": _fertilize,
    "harvest": _harvest,
    "buy": _buy,
    "sell": _sell,
    "rest": _rest,
}


def do_action(state: dict, payload: dict, rng: random.Random) -> dict:
    """行动总入口。"""
    if state.get("finished"):
        return {"ok": False, "error": "本局已经结束，请开新游戏。"}
    if state.get("pending_event"):
        return {"ok": False, "error": "请先处理今日事件。"}

    action = (payload or {}).get("type")
    handler = HANDLERS.get(action)
    if not handler:
        return {"ok": False, "error": f"未知行动：{action}"}

    result = handler(state, payload or {}, rng)
    if result.get("ok"):
        record_peak(state)
    return result
