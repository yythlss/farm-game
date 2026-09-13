# -*- coding: utf-8 -*-
"""全局数值配置表：作物、天气、经济、成就与评级阈值。

所有可调参数集中在此文件，便于路演前快速调参。
修改数值后请运行 ``python tools/simulate.py`` 做 30 天回归，确认三种评级均可达成。
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# 局内基础参数
# --------------------------------------------------------------------------
MAX_DAY = 30
PLOT_COUNT = 9

START_GOLD = 500
MAX_ENERGY = 10
START_ENERGY = 10

# 开局赠送的种子，让玩家不必第一步就花钱
START_SEEDS: dict[str, int] = {"萝卜": 3}

# 行动体力消耗
ENERGY_COST: dict[str, int] = {
    "plant": 1,
    "water": 1,
    "fertilize": 2,
    "harvest": 1,
    "rest": 0,
}
FERTILIZER_COST = 12         # 每次施肥的金币成本
REST_ENERGY = 4              # 休息恢复的体力
DAILY_ENERGY_RECOVER = 6     # 每日自然恢复体力
WATER_PER_ACTION = 45        # 单次浇水补充的水分

# 地块水分阈值 -> 生长/收成系数
WATER_GOOD = 60
WATER_LOW = 30

# 市场价格的浮动边界（相对基准价的倍数）
MARKET_MIN_RATIO = 0.6
MARKET_MAX_RATIO = 1.7
MARKET_DAILY_VOLATILITY = 0.10   # 每日随机波动幅度
MARKET_MEAN_REVERSION = 0.22     # 向基准价回归的速度

# --------------------------------------------------------------------------
# 作物
# --------------------------------------------------------------------------
# weather: 该天气下作物的生长/收成系数（同时作用于生长速度与最终产量）
CROPS: dict[str, dict] = {
    "萝卜": {
        "emoji": "🥕",
        "color": "#F4A261",
        "seed_cost": 12,
        "grow_days": 3,
        "base_yield": 3,
        "base_price": 11,
        "weather": {"晴": 1.15, "雨": 1.30, "干旱": 0.70, "暴风雨": 0.90, "寒潮": 0.95},
        "desc": "生长最快的开荒作物，回本快但单产低。",
    },
    "小麦": {
        "emoji": "🌾",
        "color": "#E9C46A",
        "seed_cost": 30,
        "grow_days": 5,
        "base_yield": 4,
        "base_price": 17,
        "weather": {"晴": 1.25, "雨": 1.05, "干旱": 0.60, "暴风雨": 0.80, "寒潮": 0.75},
        "desc": "喜晴天，稳产的主力口粮。",
    },
    "玉米": {
        "emoji": "🌽",
        "color": "#F6C445",
        "seed_cost": 55,
        "grow_days": 7,
        "base_yield": 5,
        "base_price": 25,
        "weather": {"晴": 1.30, "雨": 1.15, "干旱": 0.55, "暴风雨": 0.70, "寒潮": 0.65},
        "desc": "中周期高收益，怕旱怕冻。",
    },
    "南瓜": {
        "emoji": "🎃",
        "color": "#E76F51",
        "seed_cost": 85,
        "grow_days": 9,
        "base_yield": 7,
        "base_price": 30,
        "weather": {"晴": 1.10, "雨": 1.00, "干旱": 0.70, "暴风雨": 0.85, "寒潮": 1.15},
        "desc": "周期最长、单产最高，且耐受寒潮。",
    },
}
CROP_NAMES: list[str] = list(CROPS.keys())

# --------------------------------------------------------------------------
# 天气
# --------------------------------------------------------------------------
# water_delta: 每日水分变化（正数为补充）
# weight:     随机出现权重
# damage:     作物受灾（进度倒退）概率
WEATHERS: dict[str, dict] = {
    "晴": {"icon": "☀️", "water_delta": -10, "weight": 34, "damage": 0.00, "tip": "光照充足，生长加快，水分蒸发较快。"},
    "雨": {"icon": "🌧️", "water_delta": 35, "weight": 26, "damage": 0.00, "tip": "天然灌溉，水分自动补满。"},
    "干旱": {"icon": "🔥", "water_delta": -24, "weight": 15, "damage": 0.04, "tip": "土地干裂，水分飞速流失，务必浇水。"},
    "暴风雨": {"icon": "⛈️", "water_delta": 45, "weight": 13, "damage": 0.10, "tip": "狂风骤雨，水分充足但有作物受损风险。"},
    "寒潮": {"icon": "❄️", "water_delta": -6, "weight": 12, "damage": 0.08, "tip": "气温骤降，多数作物生长放缓。"},
}
WEATHER_NAMES: list[str] = list(WEATHERS.keys())

# --------------------------------------------------------------------------
# 事件
# --------------------------------------------------------------------------
EVENT_TYPES: dict[str, dict] = {
    "weather": {"label": "天气", "icon": "🌦️", "color": "#29B6F6"},
    "pest": {"label": "虫害", "icon": "🐛", "color": "#8D6E63"},
    "market": {"label": "市场", "icon": "📈", "color": "#F9A825"},
    "social": {"label": "社交", "icon": "🤝", "color": "#AB47BC"},
    "good": {"label": "好事", "icon": "✨", "color": "#4CAF50"},
}

# 事件数值夹取范围（防止大模型输出越界数值）
EVENT_GOLD_RANGE = (-200, 200)
EVENT_ENERGY_RANGE = (-5, 3)
EVENT_GROWTH_RANGE = (-0.5, 0.5)
EVENT_MARKET_RANGE = (0.5, 2.0)
EVENT_CHOICE_MIN, EVENT_CHOICE_MAX = 2, 3

# --------------------------------------------------------------------------
# 成就
# --------------------------------------------------------------------------
ACHIEVEMENTS: list[dict] = [
    {"id": "first_gold", "name": "第一桶金", "icon": "💰", "desc": "累计卖货收入达到 300 金币"},
    {"id": "harvest_king", "name": "丰收之王", "icon": "👑", "desc": "累计收获 60 份作物"},
    {"id": "near_bankrupt", "name": "破产边缘", "icon": "🕳️", "desc": "金币一度跌到 20 以下"},
    {"id": "scientist", "name": "科学种田", "icon": "🧪", "desc": "累计施肥 20 次"},
    {"id": "pest_hunter", "name": "灭虫专家", "icon": "🐛", "desc": "累计消除 3 次虫害"},
    {"id": "tycoon", "name": "农业大亨", "icon": "🏆", "desc": "总资产突破 2500 金币"},
]
ACHIEVEMENT_BY_ID: dict[str, dict] = {a["id"]: a for a in ACHIEVEMENTS}

# --------------------------------------------------------------------------
# 结局评级（按第 30 天总资产）
# --------------------------------------------------------------------------
RATING_TIERS: list[dict] = [
    {"min": 3000, "name": "农业大亨", "icon": "🏆", "desc": "你把一块薄田经营成了产业，村民都来取经。"},
    {"min": 1200, "name": "小康农场", "icon": "🌾", "desc": "仓廪实、钱袋鼓，日子过得踏实。"},
    {"min": -10**9, "name": "破产农夫", "icon": "💸", "desc": "账本见底，只能等下一年重头再来。"},
]


def crop_weather_factor(crop: str, weather: str) -> float:
    """作物在指定天气下的生长/收成系数。"""
    profile = CROPS.get(crop, {}).get("weather", {})
    return float(profile.get(weather, 1.0))
