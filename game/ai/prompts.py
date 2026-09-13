# -*- coding: utf-8 -*-
"""事件生成提示词：把游戏状态压成简短上下文，并要求大模型只输出 JSON。"""
from __future__ import annotations

from engine.config import CROPS, MAX_DAY, WEATHERS
from engine.settlement import harvest_yield

SYSTEM_PROMPT = """你是农场随机事件生成器。根据当前状态和玩家行动，生成一个事件。
只输出 JSON，不要解释：
{
  "title": "事件标题",
  "description": "事件描述",
  "type": "weather|pest|market|social|good",
  "effects": {
    "gold": -50,
    "energy": -2,
    "growth_bonus": 0.2,
    "market_modifier": {"小麦": 1.3}
  },
  "choices": [
    {"text": "花钱治虫", "cost": 50, "effect": "remove_pest"},
    {"text": "不管", "effect": "crop_damage"}
  ]
}
数值范围：gold -200~200，growth_bonus -0.5~0.5，market_modifier 系数 0.5~2.0。
要求：
1. choices 必须 2~3 个，每个选项文字不超过 12 字，且是有取舍的艰难选择。
2. effects 描述事件的即时影响；选项自身的额外影响放在选项的 "effects" 字段里（结构同上）。
3. effect 字段只能取以下值之一：
   none / heal_pest / crop_damage / lose_crop / free_water / market_boom / market_crash / gift_seed / extra_energy
4. 事件必须与玩家最近一次行动和当前农田状况相关联，不要与已有事件重复。
5. 只输出 JSON 对象本身，不要 Markdown 代码块，不要任何解释文字。"""


def summarize_state(state: dict) -> str:
    """把状态压缩成模型易读的要点文本。"""
    land_desc: list[str] = []
    for plot in state["land"]:
        crop = plot.get("crop")
        if not crop:
            land_desc.append(f"{plot['id'] + 1}号空地")
            continue
        cfg = CROPS[crop]
        ratio = min(1.0, plot["progress"] / cfg["grow_days"])
        tags = []
        if plot["water"] < 30:
            tags.append("缺水")
        if plot.get("pest"):
            tags.append("虫害")
        if plot.get("fertilized"):
            tags.append("已施肥")
        tag_text = f"[{'/'.join(tags)}]" if tags else ""
        land_desc.append(
            f"{plot['id'] + 1}号{crop}(生长{round(ratio * 100)}%，"
            f"预计收成{harvest_yield(state, plot)}份){tag_text}"
        )

    market_desc = "，".join(
        f"{crop} {item['price']}({'+' if item['delta'] >= 0 else ''}{item['delta']})"
        for crop, item in state["market"].items()
    )
    inventory_desc = "，".join(f"{k}×{v}" for k, v in state["harvest"].items() if v) or "空"
    seeds_desc = "，".join(f"{k}×{v}" for k, v in state["seeds"].items() if v) or "空"

    return (
        f"第 {state['day']}/{MAX_DAY} 天，天气 {state['weather']}（{WEATHERS[state['weather']]['tip']}），"
        f"明日预报 {state['forecast']}。\n"
        f"金币 {state['gold']}，体力 {state['energy']}/{state['max_energy']}。\n"
        f"农田：{'；'.join(land_desc)}。\n"
        f"库存收成：{inventory_desc}。种子：{seeds_desc}。\n"
        f"市场行情：{market_desc}。"
    )


def build_messages(state: dict, last_action: str | None = None) -> list[dict]:
    """构造 chat/completions 的 messages。"""
    recent = [
        f"第 {e['day']} 天：{e['text']}"
        for e in state.get("log", [])[-6:]
        if e.get("type") in ("action", "market", "pest", "weather")
    ]
    user_parts = [
        "【当前状态】",
        summarize_state(state),
        f"【玩家最近一次行动】{last_action or '刚进入新的一天，还没有行动'}",
    ]
    if recent:
        user_parts.append("【最近发生的事】\n" + "\n".join(recent))
    user_parts.append("请生成今天的事件 JSON。")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
