# -*- coding: utf-8 -*-
"""无头 30 天自动模拟：数值平衡回归工具。

用法::

    python tools/simulate.py                     # 三种策略各跑 200 局，输出评级分布
    python tools/simulate.py --strategy smart -v --runs 1   # 逐日打印一局
    python tools/simulate.py --seed 42           # 固定随机种子复现

回归标准：三种玩家策略应分别落在三个评级档位附近，
且任何策略都不该出现「必定破产」或「必定大亨」的单调结果。
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import event_generator  # noqa: E402
from engine import actions, achievements, rating, settlement  # noqa: E402
from engine import config as cfg  # noqa: E402
from engine import state as state_mod  # noqa: E402

STRATEGIES = {
    "smart": "精明型：择优种植、施肥、择机出售",
    "safe": "保守型：只种萝卜小麦、稳健灌溉、见好就收",
    "lazy": "摆烂型：只种白送的种子、基本不浇水不施肥",
}


def profit_per_day(crop: str) -> float:
    c = cfg.CROPS[crop]
    return (c["base_yield"] * c["base_price"] - c["seed_cost"]) / c["grow_days"]


# --------------------------------------------------------------------------
# 策略
# --------------------------------------------------------------------------
def pick_crop_smart(state: dict) -> str | None:
    """单位时间收益最高、且来得及成熟、且买得起的作物。"""
    days_left = state["max_day"] - state["day"] + 1
    best: tuple[float, str] | None = None
    for name in cfg.CROP_NAMES:
        c = cfg.CROPS[name]
        if c["grow_days"] > days_left:
            continue
        if state["seeds"][name] <= 0 and state["gold"] < c["seed_cost"]:
            continue
        key = (profit_per_day(name), name)
        if best is None or key > best:
            best = key
    return best[1] if best else None


def pick_crop_safe(state: dict) -> str | None:
    """只种萝卜和小麦。"""
    for name in ("萝卜", "小麦"):
        c = cfg.CROPS[name]
        if c["grow_days"] > state["max_day"] - state["day"] + 1:
            continue
        if state["seeds"][name] > 0 or state["gold"] >= c["seed_cost"]:
            return name
    return None


def pick_crop_lazy(state: dict) -> str | None:
    """只用白送的种子。"""
    for name in cfg.CROP_NAMES:
        if state["seeds"][name] > 0:
            return name
    return None


PICKERS = {"smart": pick_crop_smart, "safe": pick_crop_safe, "lazy": pick_crop_lazy}


def resolve_event(state: dict, rng: random.Random, strategy: str) -> None:
    """事件决策：优先规避伤作物的选项，且付得起。"""
    event = state.get("pending_event")
    if not event:
        return
    choices = event.get("choices") or []
    if not choices:
        state["pending_event"] = None
        return

    scored = []
    for idx, choice in enumerate(choices):
        cost = int(choice.get("cost") or 0)
        if cost > state["gold"]:
            continue
        op = choice.get("effect") or "none"
        score = {"crop_damage": -3, "lose_crop": -5, "none": 0}.get(op, 2)
        score += float((choice.get("effects") or {}).get("growth_bonus", 0)) * 10
        score -= cost / 200
        if strategy == "lazy":
            score -= cost / 50          # 摆烂型极度厌恶花钱
        scored.append((score, idx))
    if not scored:
        state["pending_event"] = None
        return
    scored.sort(reverse=True)
    settlement.resolve_event(state, scored[0][1], rng)


def play_day(state: dict, rng: random.Random, strategy: str) -> None:
    picker = PICKERS[strategy]
    lazy = strategy == "lazy"
    water_threshold = 10 if lazy else (45 if strategy == "smart" else 50)

    # 1) 收获成熟作物
    for plot in state["land"]:
        crop = plot["crop"]
        if crop and plot["progress"] >= cfg.CROPS[crop]["grow_days"]:
            actions.do_action(state, {"type": "harvest", "plot": plot["id"]}, rng)

    # 2) 浇水：优先最渴的地块
    for plot in sorted(
        [p for p in state["land"] if p["crop"] and p["water"] < water_threshold],
        key=lambda p: p["water"],
    ):
        if not actions.do_action(state, {"type": "water", "plot": plot["id"]}, rng)["ok"]:
            break

    # 3) 补种空地
    for plot in state["land"]:
        if plot["crop"] or state["energy"] < 2:
            continue
        crop = picker(state)
        if not crop:
            break
        if not actions.do_action(state, {"type": "plant", "plot": plot["id"], "crop": crop}, rng)["ok"]:
            break

    # 4) 施肥
    fertilize_budget = 0 if lazy else (cfg.FERTILIZER_COST * 4 if strategy == "smart" else cfg.FERTILIZER_COST * 2)
    if state["gold"] > fertilize_budget and fertilize_budget > 0:
        targets = sorted(
            [p for p in state["land"] if p["crop"] and not p["fertilized"]],
            key=lambda p: profit_per_day(p["crop"]),
            reverse=True,
        )[: 2 if strategy == "smart" else 1]
        for plot in targets:
            if not actions.do_action(state, {"type": "fertilize", "plot": plot["id"]}, rng)["ok"]:
                break

    # 5) 卖货
    for crop in cfg.CROP_NAMES:
        item = state["market"][crop]
        if not state["harvest"][crop]:
            continue
        if lazy and item["price"] < item["base"] * 1.1:
            continue
        if strategy == "safe" and item["price"] < item["base"] * 0.95:
            continue
        if item["price"] >= item["base"]:
            actions.do_action(state, {"type": "sell", "crop": crop}, rng)

    # 6) 体力见底就休息
    if state["energy"] <= 1:
        actions.do_action(state, {"type": "rest"}, rng)


# --------------------------------------------------------------------------
# 单局
# --------------------------------------------------------------------------
def run_one(seed: int | None, strategy: str = "smart", verbose: bool = False) -> dict:
    rng = random.Random(seed)
    state = state_mod.new_state(rng)
    event_generator.generate_event(state, "开局", rng, use_llm=False)

    while not state["finished"]:
        if verbose:
            print(f"--- 第 {state['day']} 天 | {state['weather']} | 金币 {state['gold']} "
                  f"| 体力 {state['energy']} ---")
        resolve_event(state, rng, strategy)
        play_day(state, rng, strategy)
        achievements.check_achievements(state)

        result = settlement.advance_day(state, rng)
        if not result.get("ok") or result.get("finished"):
            break
        event_generator.generate_event(state, state.get("last_action"), rng, use_llm=False)
        achievements.check_achievements(state)

    achievements.check_achievements(state)
    report = rating.evaluate(state)
    if verbose:
        print(f"\n最终：{report['name']} {report['icon']} 总资产 {report['assets']}")
        print(f"统计：{state['stats']}")
        print(f"成就：{state['achievements']}")
        print("最后 15 条日志：")
        for entry in state["log"][-15:]:
            print(f"  [{entry['day']}] {entry['text']}")
    return {
        "assets": report["assets"],
        "rating": report["name"],
        "stats": state["stats"],
        "achievements": list(state["achievements"]),
    }


def report(name: str, results: list[dict]) -> None:
    assets = [r["assets"] for r in results]
    dist: dict[str, int] = {}
    for r in results:
        dist[r["rating"]] = dist.get(r["rating"], 0) + 1
    runs = len(results)
    print(f"\n【{name}】{STRATEGIES[name]}  共 {runs} 局")
    print(f"  总资产  min={min(assets)}  max={max(assets)}  "
          f"中位数={int(statistics.median(assets))}  均值={int(statistics.mean(assets))}")
    for tier in cfg.RATING_TIERS:
        count = dist.get(tier["name"], 0)
        print(f"  {tier['name']:<6} {count:>4} 局 {'█' * round(count / max(1, runs) * 36)}")
    ach: dict[str, int] = {}
    for r in results:
        for a in r["achievements"]:
            ach[a] = ach.get(a, 0) + 1
    print("  成就达成率：" + "，".join(
        f"{cfg.ACHIEVEMENT_BY_ID[k]['name']} {v}/{runs}" for k, v in ach.items()
    ) or "  无")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 种田经营游戏 - 无头数值模拟")
    parser.add_argument("--runs", type=int, default=200, help="每种策略模拟局数")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--strategy", choices=list(STRATEGIES), default=None, help="只跑某一策略")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印逐日详情（单局）")
    args = parser.parse_args()

    names = [args.strategy] if args.strategy else list(STRATEGIES)
    for name in names:
        runs = 1 if args.verbose else args.runs
        results = []
        for i in range(runs):
            seed = None if args.seed is None else args.seed + i
            results.append(run_one(seed, strategy=name, verbose=args.verbose))
        report(name, results)


if __name__ == "__main__":
    main()
