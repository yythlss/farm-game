# -*- coding: utf-8 -*-
"""总资产计算与 30 天结局评级。

总资产 = 金币 + 库存收成估值 + 在地作物估值
"""
from __future__ import annotations

from .config import CROPS, RATING_TIERS


def crop_unit_price(state: dict, crop: str) -> int:
    item = state["market"].get(crop)
    if not item:
        return int(CROPS.get(crop, {}).get("base_price", 0))
    return int(item["price"])


def inventory_value(state: dict) -> int:
    return sum(
        count * crop_unit_price(state, crop)
        for crop, count in state["harvest"].items()
        if count
    )


def standing_crop_value(state: dict) -> int:
    """在地作物按生长进度折算的估值。"""
    total = 0.0
    for plot in state["land"]:
        crop = plot["crop"]
        if not crop:
            continue
        cfg = CROPS[crop]
        grow_days = cfg["grow_days"] or 1
        ratio = min(1.0, plot["progress"] / grow_days)
        total += cfg["base_yield"] * crop_unit_price(state, crop) * ratio
    return int(round(total))


def seed_value(state: dict) -> int:
    return sum(
        count * CROPS[crop]["seed_cost"]
        for crop, count in state["seeds"].items()
        if count
    )


def breakdown(state: dict) -> dict:
    gold = int(state["gold"])
    inventory = inventory_value(state)
    standing = standing_crop_value(state)
    seeds = seed_value(state)
    return {
        "gold": gold,
        "inventory": inventory,
        "standing": standing,
        "seeds": seeds,
        "total": gold + inventory + standing + seeds,
    }


def total_assets(state: dict) -> int:
    return int(breakdown(state)["total"])


def evaluate(state: dict) -> dict:
    """根据当前总资产给出评级档位。"""
    assets = total_assets(state)
    for tier in RATING_TIERS:
        if assets >= tier["min"]:
            return {
                "name": tier["name"],
                "icon": tier["icon"],
                "desc": tier["desc"],
                "assets": assets,
            }
    last = RATING_TIERS[-1]
    return {"name": last["name"], "icon": last["icon"], "desc": last["desc"], "assets": assets}
