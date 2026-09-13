# -*- coding: utf-8 -*-
"""内置事件库（降级方案）。

当大模型不可用（未配置环境变量 / 超时 / 返回脏数据）时，从这里抽取事件，
字段结构与 LLM 输出**完全一致**，因此前端渲染逻辑零差异。

覆盖 weather / pest / market / social / good 五类，共 24 条。
"""
from __future__ import annotations

import random

FALLBACK_EVENTS: list[dict] = [
    # ---------------- 虫害 pest ----------------
    {
        "title": "蚜虫来袭",
        "description": "叶片背面爬满蚜虫，嫩芽开始卷曲。农资店老板说特效药不便宜。",
        "type": "pest",
        "effects": {},
        "choices": [
            {"text": "花钱买药", "cost": 60, "effect": "heal_pest", "hint": "花 60 金币彻底清除虫害"},
            {"text": "先扛一扛", "cost": 0, "effect": "crop_damage", "hint": "不花钱，但作物受损"},
        ],
    },
    {
        "title": "蝗虫过境",
        "description": "远处的蝗群正朝这个方向移动，村里的锣鼓已经敲响。",
        "type": "pest",
        "effects": {},
        "choices": [
            {"text": "组织村民扑打", "cost": 0, "effect": "heal_pest", "hint": "不花钱，但要耗体力"},
            {"text": "自认倒霉", "cost": 0, "effect": "crop_damage", "hint": "作物生长进度倒退"},
        ],
    },
    {
        "title": "地老虎夜袭",
        "description": "一夜之间好几株苗被咬断了根，地上留下新鲜的土洞。",
        "type": "pest",
        "effects": {},
        "choices": [
            {"text": "撒草木灰", "cost": 40, "effect": "heal_pest", "hint": "花 40 金币驱虫"},
            {"text": "视而不见", "cost": 0, "effect": "crop_damage", "hint": "作物受损"},
        ],
    },
    {
        "title": "田鼠打洞",
        "description": "田埂上多了十几个洞，粮食还没收就被存进了别人的仓库。",
        "type": "pest",
        "effects": {},
        "choices": [
            {"text": "布设陷阱", "cost": 50, "effect": "heal_pest", "hint": "花 50 金币解决问题"},
            {"text": "养只猫", "cost": 0, "effect": "extra_energy", "hint": "蹲守很累，但能休息回体力"},
            {"text": "随它去", "cost": 0, "effect": "crop_damage", "hint": "作物受损"},
        ],
    },
    {
        "title": "瓢虫疑云",
        "description": "叶子上爬满了橙色小虫，看着吓人，可村口老农笑得意味深长。",
        "type": "pest",
        "effects": {},
        "choices": [
            {"text": "观察一阵", "cost": 0, "effect": "none", "hint": "瓢虫其实是益虫"},
            {"text": "全田喷药", "cost": 30, "effect": "heal_pest", "hint": "花 30 金币，可能误伤益虫"},
        ],
    },
    # ---------------- 天气 weather ----------------
    {
        "title": "干旱预警",
        "description": "气象站挂出橙色预警，接下来几天水分蒸发会异常剧烈。",
        "type": "weather",
        "effects": {},
        "choices": [
            {"text": "连夜抢浇", "cost": 30, "effect": "free_water", "hint": "花 30 金币给全部地块补水"},
            {"text": "只保重点", "cost": 0, "effect": "none", "hint": "省下钱，但缺水地块有风险"},
            {"text": "听天由命", "cost": 0, "effect": "crop_damage", "hint": "作物受损"},
        ],
    },
    {
        "title": "暴雨将至",
        "description": "乌云压得很低，排水沟却还堵着去年的枯枝。",
        "type": "weather",
        "effects": {},
        "choices": [
            {"text": "抢挖排水沟", "cost": 40, "effect": "none", "hint": "花 40 金币，作物长势更稳"},
            {"text": "赌雨不大", "cost": 0, "effect": "crop_damage", "hint": "作物有受损风险"},
        ],
    },
    {
        "title": "寒潮南下",
        "description": "夜里气温要掉到零下，露天的苗子扛不住这份冷。",
        "type": "weather",
        "effects": {},
        "choices": [
            {"text": "搭棚保温", "cost": 60, "effect": "none", "hint": "花 60 金币，抗住寒潮并增产"},
            {"text": "烧柴熏烟", "cost": 0, "effect": "extra_energy", "hint": "守夜很累，但能补体力"},
            {"text": "硬扛过去", "cost": 0, "effect": "crop_damage", "hint": "作物受损"},
        ],
    },
    {
        "title": "连日阴雨",
        "description": "湿气重得能拧出水，堆在田里的作物开始有霉味。",
        "type": "weather",
        "effects": {"growth_bonus": -0.1},
        "choices": [
            {"text": "铺草防霉", "cost": 30, "effect": "none", "hint": "花 30 金币抵消霉变"},
            {"text": "等天晴", "cost": 0, "effect": "none", "hint": "接受减产"},
        ],
    },
    {
        "title": "反常的暖冬",
        "description": "腊月里穿单衣，蜂子还在飞，老人家说这是几十年没见过的光景。",
        "type": "weather",
        "effects": {},
        "choices": [
            {"text": "抢种一茬", "cost": 0, "effect": "gift_seed", "hint": "白得 2 包种子"},
            {"text": "趁暖浇水", "cost": 0, "effect": "free_water", "hint": "全部地块补水"},
        ],
    },
    # ---------------- 市场 market ----------------
    {
        "title": "集市涨价",
        "description": "镇上办庙会，粮贩子连夜进城抢货，收购价一天涨了三成。",
        "type": "market",
        "effects": {"market_modifier": {"小麦": 1.3, "玉米": 1.25}},
        "choices": [
            {"text": "连夜摆摊", "cost": 0, "effect": "extra_energy", "hint": "卖得痛快，但累得够呛"},
            {"text": "按兵不动", "cost": 0, "effect": "none", "hint": "价格还会再飘一阵"},
        ],
    },
    {
        "title": "粮商上门收购",
        "description": "戴草帽的粮商挨家挨户敲门，说有多少收多少，但价格压得比集市低。",
        "type": "market",
        "effects": {},
        "choices": [
            {"text": "签下订单", "cost": 0, "effect": "none", "hint": "立刻到手 80 金币定金"},
            {"text": "婉言谢绝", "cost": 0, "effect": "market_boom", "hint": "自己卖，价格更好"},
        ],
    },
    {
        "title": "粮价跳水",
        "description": "隔壁几个大农场同时出货，市场一天就被砸穿了。",
        "type": "market",
        "effects": {"market_modifier": {"萝卜": 0.85, "南瓜": 0.9}},
        "choices": [
            {"text": "低价抄底种子", "cost": 0, "effect": "gift_seed", "hint": "白得 2 包种子"},
            {"text": "咬牙扛住", "cost": 0, "effect": "none", "hint": "等待价格回暖"},
        ],
    },
    {
        "title": "同行倾销",
        "description": "邻村农场主拉着整车南瓜堵在集市口，价格低得离谱。",
        "type": "market",
        "effects": {},
        "choices": [
            {"text": "降价抢客", "cost": 0, "effect": "market_crash", "hint": "自己降价，但还能出点货"},
            {"text": "走高端路线", "cost": 0, "effect": "market_boom", "hint": "打出口碑，价格反涨"},
        ],
    },
    {
        "title": "城里餐厅求购",
        "description": "一位穿西装的采购经理找上门，说要长期收南瓜做招牌汤。",
        "type": "market",
        "effects": {"market_modifier": {"南瓜": 1.2}},
        "choices": [
            {"text": "签下长约", "cost": 0, "effect": "none", "hint": "预付款 150 金币"},
            {"text": "谈谈分成", "cost": 0, "effect": "extra_energy", "hint": "谈判耗神，但能休息回体力"},
        ],
    },
    # ---------------- 社交 social ----------------
    {
        "title": "邻居借农具",
        "description": "老张家的锄头断了，想借你的新犁用两天，顺便蹭顿饭。",
        "type": "social",
        "effects": {},
        "choices": [
            {"text": "爽快借出", "cost": 30, "effect": "extra_energy", "hint": "花点损耗，换来邻里照应"},
            {"text": "找借口推脱", "cost": 0, "effect": "none", "hint": "省下损失，但人情变淡"},
        ],
    },
    {
        "title": "村里修水渠",
        "description": "村长挨家挨户摊派，修好以后灌溉就不用靠天了。",
        "type": "social",
        "effects": {},
        "choices": [
            {"text": "出钱", "cost": 80, "effect": "free_water", "hint": "花 80 金币，水渠立刻通水"},
            {"text": "出工", "cost": 0, "effect": "free_water", "hint": "不花钱，但要耗体力"},
            {"text": "推辞", "cost": 0, "effect": "none", "hint": "省下时间与金币"},
        ],
    },
    {
        "title": "老农传艺",
        "description": "八十岁的老把式蹲在你的田边，看了半天只说了一句「水浇多了」。",
        "type": "social",
        "effects": {},
        "choices": [
            {"text": "虚心请教", "cost": 0, "effect": "none", "hint": "获得生长加成"},
            {"text": "礼金谢师", "cost": 40, "effect": "extra_energy", "hint": "交了学费，学到更多"},
            {"text": "敷衍过去", "cost": 0, "effect": "none", "hint": "错过经验"},
        ],
    },
    {
        "title": "小学参观团",
        "description": "老师带着二十个孩子来农场做自然课，叽叽喳喳像一群麻雀。",
        "type": "social",
        "effects": {},
        "choices": [
            {"text": "免费开放", "cost": 0, "effect": "extra_energy", "hint": "热闹一天，心情不错"},
            {"text": "卖点农产品", "cost": 0, "effect": "gift_seed", "hint": "家长送了 2 包种子"},
        ],
    },
    {
        "title": "竞选村委",
        "description": "两位候选人都在拉票，其中一位承诺上任后修一条通往集市的路。",
        "type": "social",
        "effects": {},
        "choices": [
            {"text": "出钱助选", "cost": 50, "effect": "market_boom", "hint": "花 50 金币，换来行情利好"},
            {"text": "保持中立", "cost": 0, "effect": "none", "hint": "谁上任都不得罪"},
        ],
    },
    # ---------------- 好事 good ----------------
    {
        "title": "风调雨顺",
        "description": "云开了，日头正好，雨也正好，连虫子都躲了起来。",
        "type": "good",
        "effects": {"growth_bonus": 0.2},
        "choices": [
            {"text": "谢天谢地", "cost": 0, "effect": "none", "hint": "安静收下这份运气"},
            {"text": "抓紧补种", "cost": 0, "effect": "extra_energy", "hint": "趁着好天气多干点"},
        ],
    },
    {
        "title": "挖出一口井",
        "description": "清淤时铁锹磕到了硬东西，扒开泥一看，竟是一口老井的井口。",
        "type": "good",
        "effects": {},
        "choices": [
            {"text": "修井灌溉", "cost": 0, "effect": "free_water", "hint": "从此浇水不愁"},
            {"text": "卖水给邻田", "cost": 0, "effect": "none", "hint": "立刻到手 120 金币"},
        ],
    },
    {
        "title": "农科院试种包",
        "description": "一个背着双肩包的年轻人送来一包没见过的种子，说想看看能不能适种。",
        "type": "good",
        "effects": {},
        "choices": [
            {"text": "试种看看", "cost": 0, "effect": "gift_seed", "hint": "拿到 2 包种子"},
            {"text": "交给村里", "cost": 0, "effect": "none", "hint": "村里给了 60 金币补贴"},
        ],
    },
    {
        "title": "祖传田契",
        "description": "翻修老屋时从房梁里掉出一个铁盒，里面是一张泛黄的田契。",
        "type": "good",
        "effects": {},
        "choices": [
            {"text": "卖给收藏家", "cost": 0, "effect": "none", "hint": "立刻到手 150 金币"},
            {"text": "裱起来留着", "cost": 0, "effect": "none", "hint": "心里踏实，干活更有劲"},
        ],
    },
]


def pick_fallback(rng: random.Random, state: dict | None = None) -> dict:
    """随机抽取一个内置事件（返回深拷贝，避免被调用方就地修改）。"""
    import copy

    event = copy.deepcopy(rng.choice(FALLBACK_EVENTS))
    event["source"] = "fallback"
    return event
