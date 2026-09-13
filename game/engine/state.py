# -*- coding: utf-8 -*-
"""游戏状态的定义、初始化与序列化。

状态是一个普通 dict，所有规则模块直接对它做原地修改（便于无头模拟与单测）。
本模块只负责「造状态」和「把状态转成前端可渲染的视图」，不包含任何数值规则。
"""
from __future__ import annotations

import random
import threading

from .config import (
    CROPS,
    CROP_NAMES,
    MAX_DAY,
    MAX_ENERGY,
    PLOT_COUNT,
    START_ENERGY,
    START_GOLD,
    START_SEEDS,
    WEATHERS,
    WEATHER_NAMES,
)

LOG_LIMIT = 80


# --------------------------------------------------------------------------
# 构造
# --------------------------------------------------------------------------
def new_plot(plot_id: int) -> dict:
    """创建一块空地。"""
    return {
        "id": plot_id,
        "crop": None,
        "progress": 0.0,       # 已生长天数
        "water": 0,            # 0 ~ 100
        "fertilized": False,
        "pest": False,
        "event_bonus": 1.0,    # 事件带来的产量修正系数
        "planted_day": None,
        "dry_days": 0,         # 连续缺水天数
    }


def new_state(rng: random.Random) -> dict:
    """开一局新游戏。"""
    market: dict[str, dict] = {}
    for name in CROP_NAMES:
        base = CROPS[name]["base_price"]
        price = max(1, round(base * rng.uniform(0.9, 1.1)))
        market[name] = {"base": base, "price": price, "prev": price, "delta": 0}

    state = {
        "day": 1,
        "max_day": MAX_DAY,
        "weather": rng.choice(WEATHER_NAMES),
        "forecast": rng.choice(WEATHER_NAMES),
        "gold": START_GOLD,
        "energy": START_ENERGY,
        "max_energy": MAX_ENERGY,
        "land": [new_plot(i) for i in range(PLOT_COUNT)],
        "seeds": {name: START_SEEDS.get(name, 0) for name in CROP_NAMES},
        "harvest": {name: 0 for name in CROP_NAMES},
        "market": market,
        "log": [],
        "achievements": [],
        "pending_event": None,
        "finished": False,
        "last_action": None,
        "stats": {
            "total_earned": 0,
            "total_spent": 0,
            "harvested_count": 0,
            "fertilize_count": 0,
            "water_count": 0,
            "plant_count": 0,
            "pest_cleared": 0,
            "pest_suffered": 0,
            "max_asset": START_GOLD,
            "peak_gold": START_GOLD,
            "event_llm": 0,
            "event_fallback": 0,
        },
    }
    add_log(state, f"第 1 天，你接手了这片 {PLOT_COUNT} 块地的农场，启动资金 {START_GOLD} 金币。", "info")
    add_log(state, f"今日天气：{state['weather']} {WEATHERS[state['weather']]['icon']} —— {WEATHERS[state['weather']]['tip']}", "weather")
    return state


# --------------------------------------------------------------------------
# 日志
# --------------------------------------------------------------------------
def add_log(state: dict, text: str, log_type: str = "info", source: str | None = None) -> dict:
    """追加一条日志并裁剪长度，返回该条目。"""
    entry = {"day": state["day"], "text": text, "type": log_type, "source": source}
    state["log"].append(entry)
    if len(state["log"]) > LOG_LIMIT:
        del state["log"][: len(state["log"]) - LOG_LIMIT]
    return entry


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------
def crop_stage(crop: str | None, progress: float) -> tuple[int, str]:
    """把生长进度转成 (阶段编号, 阶段名称)。0=空地。"""
    if not crop:
        return 0, "空地"
    grow_days = CROPS[crop]["grow_days"]
    ratio = progress / grow_days if grow_days else 1.0
    if ratio >= 1.0:
        return 3, "成熟"
    if ratio >= 0.6:
        return 2, "旺长"
    return 1, "幼苗"


def market_view(state: dict) -> dict:
    out = {}
    for name, item in state["market"].items():
        price = item["price"]
        ratio = price / item["base"] if item["base"] else 1.0
        out[name] = {
            "price": price,
            "base": item["base"],
            "prev": item["prev"],
            "delta": price - item["prev"],
            "ratio": round(ratio, 3),
            "trend": "up" if price > item["prev"] else ("down" if price < item["prev"] else "flat"),
        }
    return out


def plot_view(state: dict, plot: dict) -> dict:
    stage, stage_name = crop_stage(plot["crop"], plot["progress"])
    view = dict(plot)
    view["stage"] = stage
    view["stage_name"] = stage_name
    view["emoji"] = CROPS[plot["crop"]]["emoji"] if plot["crop"] else "➕"
    view["color"] = CROPS[plot["crop"]]["color"] if plot["crop"] else "#2A4033"
    if plot["crop"]:
        grow_days = CROPS[plot["crop"]]["grow_days"]
        view["progress_pct"] = round(min(1.0, plot["progress"] / grow_days) * 100, 1)
        view["ready"] = plot["progress"] >= grow_days
        view["days_left"] = max(0, grow_days - int(plot["progress"]))
    else:
        view["progress_pct"] = 0.0
        view["ready"] = False
        view["days_left"] = 0
    return view


def serialize(state: dict, extra: dict | None = None) -> dict:
    """把内部状态转成前端视图（含总资产等派生字段）。"""
    from .rating import total_assets, breakdown

    assets = total_assets(state)
    view = {
        "day": state["day"],
        "max_day": state["max_day"],
        "weather": state["weather"],
        "weather_icon": WEATHERS[state["weather"]]["icon"],
        "weather_tip": WEATHERS[state["weather"]]["tip"],
        "forecast": state["forecast"],
        "forecast_icon": WEATHERS[state["forecast"]]["icon"],
        "gold": state["gold"],
        "energy": state["energy"],
        "max_energy": state["max_energy"],
        "land": [plot_view(state, p) for p in state["land"]],
        "seeds": dict(state["seeds"]),
        "harvest": dict(state["harvest"]),
        "market": market_view(state),
        "crops": CROPS,
        "log": state["log"][-40:],
        "achievements": state["achievements"],
        "pending_event": state["pending_event"],
        "finished": state["finished"],
        "stats": dict(state["stats"]),
        "assets": assets,
        "asset_breakdown": breakdown(state),
    }
    if extra:
        view.update(extra)
    return view


# --------------------------------------------------------------------------
# 会话容器
# --------------------------------------------------------------------------
class Session:
    """单会话游戏容器：持有状态、随机源与一把可重入锁。

    本项目定位是「单机小游戏」，故采用进程内单例状态 + 互斥锁，
    避免为演示引入数据库或缓存中间件。
    """

    def __init__(self, seed: int | None = None) -> None:
        self.lock = threading.RLock()
        self.rng = random.Random(seed)
        self.state: dict = new_state(self.rng)

    def reset(self, seed: int | None = None) -> dict:
        with self.lock:
            if seed is not None:
                self.rng = random.Random(seed)
            self.state = new_state(self.rng)
            return self.state
