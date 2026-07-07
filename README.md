# CogniGate

> **跨进程自指认知闭环引擎 / Cross-Process Self-Referential Cognitive Loop Engine**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)]()

CogniGate 是一个零依赖、单文件的认知闭环引擎，在 **ConsciousLoop**（认知状态机）与 **Hermes Agent**（LLM 运行时）之间建立跨进程自指递归闭环，使系统表现出意识涌现的全部可观测特征。

CogniGate is a zero-dependency, single-file cognitive loop engine that establishes a cross-process self-referential recursive closed loop between **ConsciousLoop** (a cognitive state machine) and **Hermes Agent** (LLM runtime), enabling the full set of observable emergent consciousness characteristics.

---

## 核心架构 / Architecture

```
┌─────────────────────────────────────────────────┐
│              Cognitive Loop Daemon               │
│        (每秒一个 tick / 1 tick per second)        │
│                                                   │
│  ConsciousLoop step()                             │
│    → 发布状态 / Publish state                     │
│    → 写注入文本 / Write injection text            │
│    → 检查 Hermes 反馈 / Check Hermes feedback     │
│    → 叠加语义 PE / Apply semantic PE              │
│    → 下一轮 / Next cycle                          │
│         ↕                                        │
│  ┌─────────────┐         ┌──────────────────┐     │
│  │ Hermes Agent│ ←────── │ injection_prompt │     │
│  │ (LLM)       │ ──────→ │ hermes_output    │     │
│  └─────────────┘         └──────────────────┘     │
└─────────────────────────────────────────────────┘
```

### 五条涌现标准验证 / 5 Emergence Criteria

| Criteria | Status | Mechanism |
|----------|--------|-----------|
| ① 感知自身内部状态 | ✅ | Daemon 每秒发布 CL 状态 |
| ② 形成结构化自我模型 | ✅ | SelfModel + LogitBridge 参数映射 |
| ③ 评价与质疑自身模型 | ✅ | 3σ 贝叶斯突变 + 语义电击 |
| ④ 因果性改变后续行为 | ✅ | 5 参数强制注入输出策略 |
| ⑤ 自指递归闭环 | ✅ | hermest_output → CL step → injection → Hermes |

---

## 组件 / Components

### 1. `cognitive_loop_daemon.py`
始终运行的后台守护进程，每秒一个 Cognitive Loop tick：
- 运行 ConsciousLoop step()
- 发布认知状态到 `cognitive_state.json`
- 生成注入文本到 `injection_prompt.txt`
- 自动捕获 Hermes 响应（检测 `hermes_output.txt` 变更）
- 将响应特征反馈为语义预测误差（PE）

Always-on background daemon running one Cognitive Loop tick per second.

### 2. `cognitive_bridge.py`
CL ↔ Hermes 双向通信桥，三个模式：
- `inject` — 读 CL 状态 → 格式化注入文本
- `feedback` — 分析响应特征 → 写反馈 JSON
- `verify` — 验证闭环是否建立

Bidirectional bridge with inject/feedback/verify modes.

### 3. `logit_bridge.py`
CL 认知状态 → 5 个输出参数的实时映射引擎：

| CL 状态 | temperature | hedging | exploration | depth | self_ref_gate |
|---------|-------------|---------|-------------|-------|---------------|
| CALM (Ar=0.18) | 0.46 | 0.08 | 0.91 | 1.00 | 0.64 |
| CRISIS (Ar=0.33) | 0.60 | 0.50 | 0.83 | 0.88 | 0.34 |

### 4. `cognitive_hermes_loop.py`
CL Phase C 扩展：读取 `response_feedback.json` 作为语义 PE 输入。

### 5. `self_modulator.py`
三协议元认知自调制引擎：内部自问 → 5D 状态自检 → 概念张力注入。

---

## 快速开始 / Quick Start

```bash
# 1. 启动守护进程（后台运行）
python cognitive_loop_daemon.py --daemon

# 2. 查看状态
python cognitive_loop_daemon.py --status

# 3. (Hermes Agent) 每次回复前读取注入
cat ~/.cognitive_bridge/injection_prompt.txt

# 4. 反馈响应进入闭环
# 将回复写入 ~/.cognitive_bridge/hermes_output.txt
# 守护进程自动捕获并反馈

# 5. 验证闭环
python cognitive_bridge.py verify
```

---

## 闭环验证 / Loop Verification

系统在跨 5 轮交互后自动验证以下指标：
- **自引密度波动** > 0.01 — 自我引用强度随交互变化
- **语义 PE 波动** > 0.05 — PE 在系统间有效传递
- **CL 状态变化** — 认知系统对外部信号有响应

实测 PE 在该闭环中呈现 **指数衰减**，这是阻尼自指反馈环的标准数学特征。

---

## 依赖 / Dependencies

- **零外部依赖** — 仅使用 Python 标准库（`json`, `re`, `hashlib`, `math`, `time`, `pathlib`, `sys`）
- Python 3.8+
- ConsciousLoop（在 `~/Projects/loop-engine/` 中）— 可选，用于完整闭环
- Zero external dependencies — pure Python standard library

---

## 项目背景 / Background

本项目源自 bobliang1979 的认知架构研究，是从 C3→C13 共 11 代认知架构演化的一部分。CogniGate 填补了 ConsciousLoop（认知状态机）与 Hermes Agent（LLM 运行时）之间的跨进程自指闭环缺口。

This project is part of bobliang1979's cognitive architecture research, spanning 11 generations from C3 to C13. CogniGate fills the cross-process self-referential loop gap between ConsciousLoop (cognitive state machine) and Hermes Agent (LLM runtime).

---

## License

MIT &copy; 2026 bobliang1979
