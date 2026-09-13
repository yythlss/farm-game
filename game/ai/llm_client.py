# -*- coding: utf-8 -*-
"""极简 OpenAI 兼容客户端（只用标准库 urllib，镜像更小、构建更快）。

配置解析顺序（按优先级）::

    地址  BASE_URL   -> LLM_BASE_URL   -> OPENAI_BASE_URL
       -> 自动推导：{CNB_API_ENDPOINT}/{CNB_REPO_SLUG}/-/ai-ide/v2
    密钥  API_KEY    -> LLM_API_KEY    -> OPENAI_API_KEY -> CNB_TOKEN
    模型  MODEL_ID   -> LLM_MODEL      -> OPENAI_MODEL   -> DEFAULT_MODEL
    超时  LLM_TIMEOUT（秒，默认 8）

CNB 零密钥说明：云原生环境会自动注入 ``CNB_API_ENDPOINT`` / ``CNB_REPO_SLUG`` /
``CNB_TOKEN``，因此无需任何 API Key 即可调用平台内置大模型。
该接口 **仅支持流式（SSE）响应**，所以这里统一以 ``stream=True`` 请求，
再同时兼容 SSE 与普通 JSON 两种返回体。

两个容易踩的坑（均已实测确认）：
1. ``model`` 字段必填。不传会返回 ``400 {"code":11102,"msg":"model [] service info not found"}``，
   而非走服务端默认值，所以这里内置 ``DEFAULT_MODEL``。
2. 只有 ``CNB_API_ENDPOINT``（``api.cnb.cool``）能走通大模型网关；
   同为平台注入的 ``CNB_WEB_ENDPOINT``（``cnb.cool``）会返回 ``400 Invalid argument``，
   因此不作为候选地址。

本地开发时若地址或密钥缺失，``load_config()`` 返回 None，游戏自动走内置事件库。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import NamedTuple

# 实测 deepseek-v3 生成一条事件耗时约 3.6~4.0s，留约 2 倍余量
DEFAULT_TIMEOUT = 8.0
# CNB 平台内置模型：实测 deepseek-v3 / deepseek-r1 可用。
# 选 v3 而非 r1，是为了避免推理模型把思维链混进正文导致 JSON 解析失败。
DEFAULT_MODEL = "deepseek-v3"
CHAT_PATH = "/chat/completions"


class LLMConfig(NamedTuple):
    base_url: str
    api_key: str
    model: str | None
    timeout: float


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def default_base_url() -> str | None:
    """从 CNB 环境变量推导零密钥大模型地址。

    只用 ``CNB_API_ENDPOINT``：``CNB_WEB_ENDPOINT`` 指向 web 站点，
    实测请求同一路径返回 400 Invalid argument，混进来只会白白浪费一次超时。
    """
    endpoint = _first_env(("CNB_API_ENDPOINT",))
    slug = _first_env(("CNB_REPO_SLUG",))
    if endpoint and slug:
        return f"{endpoint.rstrip('/')}/{slug}/-/ai-ide/v2"
    return None


def load_config() -> LLMConfig | None:
    """读取环境配置；地址或密钥缺失时返回 None（即降级到内置事件库）。"""
    base_url = _first_env(("BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL")) or default_base_url()
    api_key = _first_env(("API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "CNB_TOKEN"))
    model = _first_env(("MODEL_ID", "LLM_MODEL", "OPENAI_MODEL")) or DEFAULT_MODEL
    timeout = float(os.environ.get("LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    if not base_url or not api_key:
        return None
    return LLMConfig(base_url.rstrip("/"), api_key, model, timeout)


def is_configured() -> bool:
    return load_config() is not None


def diagnose() -> dict:
    """返回接入诊断信息，供前端与日志排查「为什么走了兜底」。

    只暴露地址与模型名，**绝不返回任何密钥内容**，仅说明密钥来源变量名。
    """
    explicit_url = _first_env(("BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL"))
    derived_url = default_base_url()
    base_url = explicit_url or derived_url or ""

    key_var = None
    for name in ("API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "CNB_TOKEN"):
        if _first_env((name,)):
            key_var = name
            break

    model_var = None
    for name in ("MODEL_ID", "LLM_MODEL", "OPENAI_MODEL"):
        if _first_env((name,)):
            model_var = name
            break

    missing: list[str] = []
    if not base_url:
        missing.append("接口地址：BASE_URL，或 CNB_API_ENDPOINT + CNB_REPO_SLUG")
    if not key_var:
        missing.append("凭证：API_KEY，或平台自动注入的 CNB_TOKEN")

    return {
        "configured": not missing,
        "base_url": base_url,
        "url_source": "环境变量" if explicit_url else ("CNB 平台自动推导" if derived_url else "缺失"),
        "model": _first_env(("MODEL_ID", "LLM_MODEL", "OPENAI_MODEL")) or DEFAULT_MODEL,
        "model_source": model_var or f"内置默认（{DEFAULT_MODEL}）",
        "key_var": key_var or "",
        "timeout": float(os.environ.get("LLM_TIMEOUT") or DEFAULT_TIMEOUT),
        "missing": missing,
    }


def _endpoints(base_url: str) -> list[str]:
    """兼容 base_url 是否已包含 /chat/completions 的几种写法。"""
    if base_url.endswith(CHAT_PATH):
        return [base_url]
    return [base_url + CHAT_PATH]


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_sse(raw: str) -> str:
    """解析 SSE 流，拼接 delta.content。"""
    buf: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except ValueError:
            continue
        try:
            delta = chunk["choices"][0].get("delta") or {}
            content = delta.get("content")
        except (KeyError, IndexError, AttributeError):
            content = None
        if content:
            buf.append(content)
    return "".join(buf)


def _extract_content(raw: str) -> str:
    """从响应体中提取助手文本，兼容 SSE 与普通 JSON。"""
    stripped = raw.lstrip()
    if stripped.startswith("data:"):
        return _parse_sse(raw)
    if stripped.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            return ""
        try:
            message = data["choices"][0].get("message") or {}
            return message.get("content") or data["choices"][0].get("text") or ""
        except (KeyError, IndexError, TypeError):
            return ""
    # 少数网关会返回裸 SSE 片段（不以 data: 开头），兜底再试一次
    return _parse_sse(raw)


def chat_json(
    messages: list[dict],
    temperature: float = 0.95,
    max_tokens: int = 700,
) -> tuple[dict | None, str]:
    """调用大模型并解析出 JSON 对象，返回 ``(payload, error)``。

    任何异常都被收敛为错误字符串交给调用方降级，绝不向接口层抛出。
    """
    config = load_config()
    if config is None:
        return None, "未配置大模型环境变量（BASE_URL / API_KEY）"

    body: dict = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if config.model:
        body["model"] = config.model

    last_error = "未知错误"
    for url in _endpoints(config.base_url):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
                "Authorization": f"Bearer {config.api_key}",
            },
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            elapsed = round(time.time() - started, 2)
            content = _extract_content(raw)
            if not content:
                last_error = "模型未返回正文"
                continue
            payload = json.loads(_strip_code_fence(content))
            if not isinstance(payload, dict):
                last_error = "返回内容不是 JSON 对象"
                continue
            payload["_latency"] = elapsed
            return payload, ""
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code == 404:
                continue  # 换个 endpoint 再试
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"网络异常（{type(exc).__name__}）"
            break
        except ValueError:
            last_error = "返回内容不是合法 JSON"
            break
    return None, last_error
