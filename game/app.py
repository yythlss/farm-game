# -*- coding: utf-8 -*-
"""AI 种田经营游戏 —— Flask 入口。

职责：
1. 托管单页前端（templates/ + static/）
2. 暴露全部游戏 API，统一错误响应格式
3. 把「规则引擎」与「AI 事件生成」编排到一起

设计要点：
- 全局单会话状态 + 可重入锁，写接口加锁；
- 所有 LLM 异常都在 ai 层被吞掉并降级，接口永不因大模型而 500；
- 端口从 ``PORT`` 读取（默认 8686），强制监听 ``0.0.0.0`` 以满足容器探活。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from ai import event_generator, llm_client  # noqa: E402
from engine import actions, achievements, rating, settlement  # noqa: E402
from engine import config as cfg  # noqa: E402
from engine import state as state_mod  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"),
            template_folder=os.path.join(BASE_DIR, "templates"))
app.config["JSON_AS_ASCII"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.json.ensure_ascii = False

_session = state_mod.Session(seed=int(os.environ["GAME_SEED"]) if os.environ.get("GAME_SEED") else None)


# --------------------------------------------------------------------------
# 统一响应
# --------------------------------------------------------------------------
def ok(state: dict, messages: list[str] | None = None, extra: dict | None = None):
    payload = {"ok": True, "state": state_mod.serialize(state), "messages": messages or []}
    if extra:
        payload.update(extra)
    return jsonify(payload)


def fail(message: str, code: str = "bad_request", status: int = 400):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def _body() -> dict:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    data = request.form.to_dict()
    return data or {}


def _unlock(state: dict) -> list[dict]:
    """检查成就并返回本次新解锁的列表。"""
    return achievements.check_achievements(state)


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "ai-farm-tycoon", "llm": llm_client.is_configured()})


@app.get("/api/meta")
def meta():
    """静态配置表：作物、天气、事件类型、成就、评级档位。"""
    return jsonify({
        "ok": True,
        "meta": {
            "crops": cfg.CROPS,
            "crop_names": cfg.CROP_NAMES,
            "weathers": cfg.WEATHERS,
            "event_types": cfg.EVENT_TYPES,
            "achievements": cfg.ACHIEVEMENTS,
            "rating_tiers": cfg.RATING_TIERS,
            "max_day": cfg.MAX_DAY,
            "plot_count": cfg.PLOT_COUNT,
            "energy_cost": cfg.ENERGY_COST,
            "fertilizer_cost": cfg.FERTILIZER_COST,
            "llm_enabled": llm_client.is_configured(),
            "llm": llm_client.diagnose(),
        },
    })


# --------------------------------------------------------------------------
# 游戏流程
# --------------------------------------------------------------------------
@app.post("/api/new-game")
def new_game():
    with _session.lock:
        state = _session.reset(seed=int(_body().get("seed")) if _body().get("seed") else None)
        _unlock(state)
        event_generator.generate_event(state, "开局，准备种地", _session.rng)
        return ok(state, ["新的一季开始了，共 30 天。"])


@app.get("/api/state")
def get_state():
    with _session.lock:
        return ok(_session.state)


@app.post("/api/action")
def do_action():
    payload = _body()
    with _session.lock:
        result = actions.do_action(_session.state, payload, _session.rng)
        if not result.get("ok"):
            return fail(result.get("error", "操作失败"))
        label = actions.ACTION_LABELS.get(payload.get("type"), "操作")
        _session.state["last_action"] = f"{label}：{'；'.join(result.get('messages', []))}"[:120]
        newly = _unlock(_session.state)
        return ok(_session.state, result.get("messages", []), {"new_achievements": newly})


@app.post("/api/event/choose")
def choose_event():
    index = _body().get("index")
    with _session.lock:
        result = settlement.resolve_event(_session.state, index, _session.rng)
        if not result.get("ok"):
            return fail(result.get("error", "事件处理失败"))
        newly = _unlock(_session.state)
        return ok(_session.state, result.get("messages", []), {"new_achievements": newly})


@app.post("/api/next-day")
def next_day():
    with _session.lock:
        state = _session.state
        result = settlement.advance_day(state, _session.rng)
        if not result.get("ok"):
            return fail(result.get("error", "无法进入下一天"))

        if result.get("finished"):
            newly = _unlock(state)
            return ok(state, result.get("messages", []),
                      {"finished": True, "rating": rating.evaluate(state), "new_achievements": newly})

        event = event_generator.generate_event(state, state.get("last_action"), _session.rng)
        newly = _unlock(state)
        return ok(state, result.get("messages", []), {"event": event, "new_achievements": newly})


@app.get("/api/rating")
def get_rating():
    state = _session.state
    return jsonify({
        "ok": True,
        "rating": rating.evaluate(state),
        "breakdown": rating.breakdown(state),
        "stats": state["stats"],
        "achievements": achievements.list_achievements(state),
        "day": state["day"],
        "finished": state["finished"],
    })


@app.get("/api/achievements")
def get_achievements():
    return jsonify({"ok": True, "achievements": achievements.list_achievements(_session.state)})


# --------------------------------------------------------------------------
# 兜底错误处理：任何未捕获异常都返回 JSON，不吐 HTML 堆栈
# --------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(_):
    return fail("接口或页面不存在", "not_found", 404)


@app.errorhandler(405)
def method_not_allowed(_):
    return fail("请求方法不被允许", "method_not_allowed", 405)


@app.errorhandler(Exception)
def server_error(exc):  # pragma: no cover - 兜底路径
    app.logger.exception("未捕获异常: %s", exc)
    return fail(f"服务器内部错误：{type(exc).__name__}", "internal_error", 500)


def main() -> None:
    port = int(os.environ.get("PORT", 8686))
    host = os.environ.get("HOST", "0.0.0.0")
    info = llm_client.diagnose()
    print("=" * 58)
    print("  🌾 AI 种田经营游戏已启动")
    print(f"  ▸ 访问地址 : http://{host}:{port}")
    if info["configured"]:
        print(f"  ▸ 大模型   : 已接入 {info['model']}（AI 实时生成事件）")
        print(f"  ▸ 接口地址 : {info['base_url']}  [{info['url_source']}]")
    else:
        print("  ▸ 大模型   : 未接入，当前使用内置事件库兜底")
        for item in info["missing"]:
            print(f"              缺失 {item}")
        print("               容器运行请透传：-e CNB_API_ENDPOINT -e CNB_REPO_SLUG -e CNB_TOKEN")
    print("=" * 58, flush=True)
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
