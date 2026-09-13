# AI 种田经营游戏
**用户经营一块农田，安排播种/浇水/买卖/应对天气，AI 每天生成随机事件与市场波动，后端规则引擎结算收成和金币，30 天结算农场评级，Docker 一键运行。**

> 本目录是应用代码本体。仓库根目录的 `README.md` 为作品说明与快速开始入口。
> 下方的「玩法 / 功能清单 / 提示词 / API」是最初的设想，已全部实现；文末补充了实际落地的数值表与运行方式。

## 玩法
1. 玩家查看状态：天数、天气、金币、体力、土地、库存、市场价格。
2. 玩家行动：播种、浇水、施肥、买卖、应对天气、休息。
3. AI 生成随机事件：虫害、干旱、集市涨价、商人收购、邻居求助。
4. 后端结算：生长、产量、金币、体力、市场价格。
5. 成就系统：第一桶金、丰收之王、破产边缘

## 功能清单
- 农田网格：6~9 块地（实际实现为 **3×3 = 9 块**）
- 作物：萝卜、小麦、玉米、南瓜，各有成本、生长天数、售价、天气偏好
- 天气：晴、雨、干旱、暴风雨、寒潮
- 行动：播种、浇水、施肥、收获、买卖、休息
- AI 事件：每天 1 个随机事件，带 2~3 个选项
- 结算：产量 = 基础产量 × 天气系数 × 照料系数 × 事件系数
- 结局：30 天总资产评级：破产农夫 / 小康农场 / 农业大亨
- Docker：监听 `0.0.0.0:8686`，一键运行

## 提示词
```txt
你是农场随机事件生成器。根据当前状态和玩家行动，生成一个事件。
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
数值范围：gold -200~200，growth_bonus -0.5~0.5。
```
### 示例
```json
state = {
    "day": 1,
    "weather": "晴",
    "gold": 500,
    "energy": 10,
    "land": [
        {"crop": "小麦", "stage": 2, "water": 60, "fertilized": False}
    ],
    "inventory": {"小麦种子": 3, "小麦": 0},
    "market": {"小麦": 20, "玉米": 35},
    "log": []
}
```
实际实现中提示词位于 `ai/prompts.py`，会在上述模板后追加**当前状态摘要 + 玩家上一步行动 + 最近日志**，并要求以流式返回严格 JSON。

## API
- POST /api/new-game 新游戏
- GET /api/state 获取状态
- POST /api/action 执行行动
- POST /api/next-day 进入下一天
- GET /api/rating 结算评级
- POST /api/event/choose 选择事件选项
- GET /api/achievements 成就墙
- GET /api/meta 静态配置表（作物/天气/事件类型/成就/评级）
- GET /api/health 探活

统一响应：成功 `{ok:true, state, messages, new_achievements}`；失败 `{ok:false, error:{code, message}}`。

---

# 实现说明（落地后的实际数值）

## 运行方式

```bash
# Docker（推荐）—— 注意：本地 docker run 不会继承宿主 CNB_* 变量，需显式透传
cd .. && docker build -t ai-farm-tycoon .
docker run --rm -p 8080:8686 \
  -e CNB_API_ENDPOINT -e CNB_REPO_SLUG -e CNB_TOKEN \
  ai-farm-tycoon

# 本地
pip install -r requirements.txt
PORT=8080 python app.py        # 本地调试端口；容器内固定 8686
```

> 云开发环境中宿主 `8686` 可能被 IDE 占用，本地预览请用 `-p 8080:8686`。
> 云原生环境里 `CNB_*` 由平台自动注入，用「🌾 开始游戏」按钮启动时无需配置。

## 数值表

### 开局条件
| 项 | 值 |
| --- | --- |
| 天数 | 30 天 |
| 农田 | 3×3 = 9 块 |
| 初始金币 | 500 |
| 体力上限 / 初始 | 10 / 10 |
| 初始种子 | 萝卜 ×3 |
| 每日体力恢复 | +6 |

### 行动消耗
| 行动 | 体力 | 金币 |
| --- | --- | --- |
| 播种 | 1 | — |
| 浇水（水分 +45） | 1 | — |
| 施肥（产量系数 ×1.25） | 2 | 12 |
| 收获 | 1 | — |
| 休息 | — | — （体力 +4） |

### 作物
| 作物 | 种子成本 | 生长天数 | 基础产量 | 基准售价 | 天气偏好 |
| --- | --- | --- | --- | --- | --- |
| 🥕 萝卜 | 12 | 3 | 3 | 11 | 雨 1.30 / 晴 1.15 / 干旱 0.70 |
| 🌾 小麦 | 30 | 5 | 4 | 17 | 晴 1.25 / 雨 1.05 / 干旱 0.60 |
| 🌽 玉米 | 55 | 7 | 5 | 25 | 晴 1.30 / 雨 1.15 / 干旱 0.55 |
| 🎃 南瓜 | 85 | 9 | 7 | 30 | 寒潮 1.15 / 晴 1.10 / 干旱 0.70 |

### 天气
| 天气 | 每日水分变化 | 受灾概率 | 出现权重 |
| --- | --- | --- | --- |
| ☀️ 晴 | −10 | — | 34 |
| 🌧️ 雨 | +35 | — | 26 |
| 🔥 干旱 | −24 | 4% | 15 |
| ⛈️ 暴风雨 | +45 | 10% | 13 |
| ❄️ 寒潮 | −6 | 8% | 12 |

### 市场与结算
- 价格在基准价的 **0.6 ~ 1.7 倍**之间波动，每日随机波动 ±10%，向基准价回归速度 0.22
- 产量 = 基础产量 × 天气系数 × 照料系数 × 事件系数
  - 照料系数 = 水分系数 × 施肥系数 × 虫害系数
  - 水分系数：≥60 → 1.00；30~59 → 0.85；<30 → 0.60
  - 施肥系数：施过肥 → 1.25
  - 虫害系数：有虫害 → 0.55
  - 事件系数：来自事件的 `growth_bonus`，区间 `[0.5, 2.0]`
- 连续 **3 天**缺水（水分 < 30）作物枯死

### 事件契约夹取
| 字段 | 范围 |
| --- | --- |
| `effects.gold` | −200 ~ 200 |
| `effects.energy` | −5 ~ 3 |
| `effects.growth_bonus` | −0.5 ~ 0.5 |
| `effects.market_modifier` | 0.5 ~ 2.0 |
| `choices` 数量 | 2 ~ 3 |

`effect` 取值：`none` / `heal_pest`（别名 `remove_pest`）/ `crop_damage` / `lose_crop` / `free_water` / `market_boom` / `market_crash` / `gift_seed` / `extra_energy`。

### 成就
| 成就 | 条件 |
| --- | --- |
| 💰 第一桶金 | 累计卖货收入达 300 金币 |
| 👑 丰收之王 | 累计收获 60 份作物 |
| 🕳️ 破产边缘 | 金币一度跌到 20 以下 |
| 🧪 科学种田 | 累计施肥 20 次 |
| 🐛 灭虫专家 | 累计消除 3 次虫害 |
| 🏆 农业大亨 | 总资产突破 2500 金币 |

### 评级（第 30 天总资产 = 金币 + 库存收成估值 + 在地作物估值 + 种子估值）
| 评级 | 门槛 |
| --- | --- |
| 🏆 农业大亨 | ≥ 3000 |
| 🌾 小康农场 | ≥ 1200 |
| 💸 破产农夫 | < 1200 |

## 模块结构

```
game/
├── app.py                     # Flask 入口：静态托管 + 全部 API + 统一错误处理 + 全局状态锁
├── requirements.txt           # 唯一依赖：Flask
├── engine/                    # 规则引擎（纯标准库，与 AI 完全解耦）
│   ├── config.py              # 数值配置表（本文件即数值表的唯一来源）
│   ├── state.py               # GameState 定义、初始化、序列化、会话锁
│   ├── weather.py             # 天气生成、预报与影响
│   ├── actions.py             # 播种/浇水/施肥/收获/买卖/休息
│   ├── settlement.py          # 每日结算、产量公式、事件效果落地
│   ├── achievements.py        # 成就判定
│   └── rating.py              # 总资产与评级
├── ai/                        # AI 事件层（失败即降级，不影响可玩性）
│   ├── prompts.py             # 提示词模板 + 状态摘要
│   ├── llm_client.py          # OpenAI 兼容客户端（urllib，兼容 SSE）
│   ├── event_generator.py     # 生成 → 契约校验 → 降级 主流程
│   └── fallback_events.py     # 24 条内置事件库（5 类均衡）
├── tools/simulate.py          # 无头 30 天模拟器，用于数值回归
├── templates/index.html       # 单页骨架
└── static/css|js              # 深色数据面板风样式与交互
```

## LLM 接入

零密钥接入 CNB 大模型，环境变量优先级：

| 变量 | 说明 |
| --- | --- |
| `BASE_URL` / `LLM_BASE_URL` / `OPENAI_BASE_URL` | 接口地址，未设置时用 `CNB_API_ENDPOINT` + `CNB_REPO_SLUG` 推导 |
| `API_KEY` / `LLM_API_KEY` / `OPENAI_API_KEY` / `CNB_TOKEN` | Bearer 凭证 |
| `MODEL_ID` / `LLM_MODEL` / `OPENAI_MODEL` | 模型名，未设置时用内置默认值 `deepseek-v3` |
| `LLM_TIMEOUT` | 超时秒数，默认 8（实测单次事件生成约 3.5s） |

两个实测踩到的坑：

1. **`model` 必填**，不传会 400 `model [] service info not found`，故内置 `DEFAULT_MODEL = "deepseek-v3"`。
2. 推导地址只用 `CNB_API_ENDPOINT`（`api.cnb.cool`）；`CNB_WEB_ENDPOINT`（`cnb.cool`）会 400，不能当候选。

任一环节异常（无配置 / 超时 / 非 200 / JSON 解析失败 / 契约校验失败）都会降级到 `ai/fallback_events.py`，
事件与日志上的 `source` 字段标注 `llm` 或 `fallback`，前端以徽标形式展示。

排查用：`llm_client.diagnose()`（暴露在 `/api/meta` 的 `meta.llm`）返回地址来源、模型来源与缺失项，
不包含任何密钥内容。

## 数值回归

改动 `engine/config.py` 后必须重跑：

```bash
python tools/simulate.py                                  # 三种策略各 200 局，输出评级分布
python tools/simulate.py --strategy smart --seed 42 -v     # 固定种子单局逐日日志
```

当前基线：精明型 ≈3680（农业大亨 79.5%）、保守型 ≈1990（小康农场 99.5%）、摆烂型 ≈940（破产农夫 73.5%），三档覆盖正常。
