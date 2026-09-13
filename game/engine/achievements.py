# -*- coding: utf-8 -*-
"""成就系统：按状态判定成就是否解锁，解锁时写入档案并记日志。"""
from __future__ import annotations

from .config import ACHIEVEMENT_BY_ID
from .rating import total_assets
from .state import add_log


def _conditions(state: dict) -> dict[str, bool]:
    stats = state["stats"]
    return {
        "first_gold": stats.get("total_earned", 0) >= 300,
        "harvest_king": stats.get("harvested_count", 0) >= 60,
        "near_bankrupt": state["gold"] < 20,
        "scientist": stats.get("fertilize_count", 0) >= 20,
        "pest_hunter": stats.get("pest_cleared", 0) >= 3,
        "tycoon": total_assets(state) >= 2500,
    }


def check_achievements(state: dict) -> list[dict]:
    """返回本次新解锁的成就列表（同时写入 state）。"""
    unlocked = set(state.get("achievements") or [])
    newly: list[dict] = []
    for ach_id, passed in _conditions(state).items():
        if passed and ach_id not in unlocked:
            unlocked.add(ach_id)
            meta = ACHIEVEMENT_BY_ID.get(ach_id)
            if not meta:
                continue
            newly.append(meta)
            add_log(state, f"解锁成就「{meta['name']}」{meta['icon']} —— {meta['desc']}", "achievement")
    if newly:
        state["achievements"] = [a["id"] for a in _ordered(unlocked)]
    return newly


def _ordered(ids: set[str]) -> list[dict]:
    from .config import ACHIEVEMENTS

    return [a for a in ACHIEVEMENTS if a["id"] in ids]


def list_achievements(state: dict) -> list[dict]:
    """完整成就墙（含是否解锁）。"""
    from .config import ACHIEVEMENTS

    unlocked = set(state.get("achievements") or [])
    return [{**a, "unlocked": a["id"] in unlocked} for a in ACHIEVEMENTS]
