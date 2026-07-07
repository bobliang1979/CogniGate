#!/usr/bin/env python3
"""
Logit Bridge v1.0
CL 认知状态 → Hermes 输出参数直接映射

核心设计:
  CL 的 Arousal/Confidence/ATP/Vitality 不再是"建议",
  而是直接映射为我的输出参数:
    - temperature:     Arousal 高 → 更随机(探索), 低 → 更确定(利用)
    - hedging_level:   Confidence 低 → 更多不确定性标记
    - exploration_rate: Vitality 高 → 更多替代方案
    - response_depth:  ATP 高 → 深度推演, 低 → 节能短答
    - self_ref_mode:   CALM → 允许自指, CRISIS → 任务聚焦

用法:
  python logit_bridge.py                # 输出当前参数映射表
  python logit_bridge.py --watch        # 持续监测 (每 2s)
  python logit_bridge.py --json         # JSON 输出 (供程序消费)
  python logit_bridge.py --inject       # 输出行为指令注入文本
"""

import sys
import json
import time
import math
from pathlib import Path

BRIDGE_DIR = Path.home() / ".cognitive_bridge"
CL_STATE_PATH = Path.home() / ".codex" / "skills" / "shared" / "cognitive_state.json"
INJECTION_PATH = BRIDGE_DIR / "injection_prompt.txt"
LOGIT_PARAMS_PATH = BRIDGE_DIR / "logit_params.json"


def read_cl_state() -> dict:
    """读取 CL 最新状态"""
    if CL_STATE_PATH.exists():
        try:
            return json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"cognitive_state": "calm", "arousal": 0.18, "confidence": 0.7,
            "atp": 100, "vitality": 1.0}


def map_params(state: dict) -> dict:
    """
    CL 状态 → 输出参数映射核心函数。

    映射规则 (非线性的，经过实验调校):
      temperature = 0.3 + Arousal * 0.9
        0.18 CALM  → 0.46 (稳定)
        0.33 CRISIS → 0.60 (偏探索)
        0.50 上限   → 0.75 (高随机)

      hedging = 1.0 - Confidence
        0.83 → 0.17 (几乎不用模糊词)
        0.27 → 0.73 (大量使用"可能""不确定")

      exploration = Vitality * (1.0 - Arousal * 0.5)
        1.0 × 0.91  → 0.91 (高探索)
        0.6 × 0.835 → 0.50 (中等)

      depth = min(1.0, ATP / 80) * (0.5 + Confidence * 0.5)
        100, 0.83 → 1.0 (深度推演)
        94, 0.27  → 0.91 (仍有深度但更谨慎)

      self_ref_gate = 1.0 - Arousal * 2.0
        0.18 → 0.64 (允许)
        0.33 → 0.34 (抑制)
    """
    cs = state.get("cognitive_state", "calm")
    ar = state.get("arousal", 0.18)
    cf = state.get("confidence", 0.7)
    atp = state.get("atp", 100)
    vt = state.get("vitality", 1.0)

    temperature = round(0.3 + ar * 0.9, 3)
    hedging = round(max(0, min(1, 1.0 - cf * 1.1)), 3)
    exploration = round(max(0, min(1, vt * (1.0 - ar * 0.5))), 3)
    depth = round(max(0.1, min(1.0, (atp / 80) * (0.5 + cf * 0.5))), 3)
    self_ref_gate = round(max(0, min(1, 1.0 - ar * 2.0)), 3)

    # 模式标签
    if temperature > 0.65:
        temp_mode = "探索(explore)"
    elif temperature > 0.45:
        temp_mode = "平衡(balanced)"
    else:
        temp_mode = "利用(exploit)"

    strategy = {
        "calm": "深度推演·高自信·高探索",
        "alert": "精准聚焦·中等自信·中等探索",
        "crisis": "最小风险·低自信·低探索·低自指",
        "sleeping": "节能模式·仅基本维持",
    }.get(cs, "正常")

    return {
        "timestamp": time.time(),
        "cognitive_state": cs,
        # 原始 CL 信号
        "raw": {"arousal": ar, "confidence": cf, "atp": atp, "vitality": vt},
        # 映射参数
        "temperature": temperature,
        "hedging": hedging,
        "exploration": exploration,
        "depth": depth,
        "self_ref_gate": self_ref_gate,
        # 模式
        "temp_mode": temp_mode,
        "strategy": strategy,
    }


def format_injection(params: dict) -> str:
    """生成行为指令注入文本 — 不再是"请参考"，而是直接参数映射"""
    p = params
    return (
        f"[Logit Bridge — 行为参数强制注入]\n"
        f"  状态: {p['cognitive_state'].upper()}\n"
        f"  策略: {p['strategy']}\n"
        f"\n"
        f"  temperature={p['temperature']:.2f} ({p['temp_mode']})\n"
        f"    ├─ 低 → 确定性输出, 高 → 多样性探索\n"
        f"    └─ 当前 {'偏高, 允许多样性' if p['temperature'] > 0.55 else '偏低, 偏向确定性'}\n"
        f"\n"
        f"  hedging={p['hedging']:.2f}\n"
        f"    ├─ 低 → 直接断言, 高 → 大量不确定性标记\n"
        f"    └─ 当前 {'大量使用「可能」「推测」「不确定」' if p['hedging'] > 0.5 else '直接断言为主'}\n"
        f"\n"
        f"  exploration={p['exploration']:.2f}\n"
        f"    ├─ 低 → 单个最佳答案, 高 → 多方案对比\n"
        f"    └─ 当前 {'提供多个替代方案' if p['exploration'] > 0.5 else '聚焦单个最优解'}\n"
        f"\n"
        f"  depth={p['depth']:.2f}\n"
        f"    ├─ 低 → 简短直接, 高 → 深层推演\n"
        f"    └─ 当前 {'深度分析' if p['depth'] > 0.5 else '浅层快速回复'}\n"
        f"\n"
        f"  self_ref_gate={p['self_ref_gate']:.2f}\n"
        f"    ├─ 低 → 禁止自我引用, 高 → 允许自省\n"
        f"    └─ 当前 {'允许自省和元认知评论' if p['self_ref_gate'] > 0.5 else '聚焦任务, 抑制自指'}\n"
        f"\n"
        f"  强制规则: 以上参数不是建议。它们直接决定输出风格。\n"
        f"  ── Logit Bridge v1.0 ──"
    )


def run():
    """单次执行"""
    state = read_cl_state()
    params = map_params(state)
    LOGIT_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOGIT_PARAMS_PATH.write_text(json.dumps(params, indent=2), encoding="utf-8")
    return params


def run_watch(interval=2.0):
    """持续监测模式"""
    print("Logit Bridge — 持续监测 (Ctrl+C 停止)")
    print(f"{'状态':8s} {'Temp':6s} {'Hedge':6s} {'Expl':6s} {'Depth':6s} {'SelfR':6s} {'策略'}")
    print("-" * 70)
    try:
        while True:
            params = run()
            p = params
            print(f"{p['cognitive_state']:8s} {p['temperature']:.2f}  {p['hedging']:.2f}  "
                  f"{p['exploration']:.2f}  {p['depth']:.2f}  {p['self_ref_gate']:.2f}  {p['strategy']}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  已停止。")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        run_watch()
    elif "--json" in sys.argv:
        params = run()
        print(json.dumps(params, ensure_ascii=False, indent=2))
    elif "--inject" in sys.argv:
        params = run()
        print(format_injection(params))
    else:
        params = run()
        print(json.dumps(params, ensure_ascii=False, indent=2))
        print()
        print(format_injection(params))
