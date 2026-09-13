# -*- coding: utf-8 -*-
"""AI 事件包：大模型优先、内置事件库兜底。"""
from . import event_generator, fallback_events, llm_client, prompts

__all__ = ["event_generator", "fallback_events", "llm_client", "prompts"]
