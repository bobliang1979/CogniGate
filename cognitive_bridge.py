#!/usr/bin/env python3
"""
Cognitive Bridge v1.0
跨进程自指闭环：ConsciousLoop ↔ Hermes Agent 双向耦合

架构：
  Hermes(LLM) ←─── cognitive_state.json ←─── ConsciousLoop(Python)
       │                                              ↑
       └─── response_feedback.json ───────────────────┘

用法：
  python cognitive_bridge.py inject        # 读 CL 状态 → 输出注入文本（Hermes 用）
  python cognitive_bridge.py feedback "<响应文本>"  # 读 Hermes 响应 → 写反馈文件
  python cognitive_bridge.py watch          # 持续监控闭环

闭环验证：
  python cognitive_bridge.py verify         # 跨 5 轮验证 CL 状态与 Hermes 输出是否耦合
"""

import sys
import json
import math
import re
import time
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════
# 文件路径
# ═══════════════════════════════════════════════

CL_STATE_PATH = Path.home() / ".codex" / "skills" / "shared" / "cognitive_state.json"
BRIDGE_DIR = Path.home() / ".cognitive_bridge"
FEEDBACK_PATH = BRIDGE_DIR / "response_feedback.json"
INJECTION_PATH = BRIDGE_DIR / "injection_prompt.txt"
HISTORY_PATH = BRIDGE_DIR / "loop_history.jsonl"

_ACTION_KEYS = ["action_if_low", "action_if_off", "action_if_loop", "action_if_pat", "action_if_pause"]

# ═══════════════════════════════════════════════
# 协议一：状态注入（CL → LLM）
# ═══════════════════════════════════════════════

REGIEM_STYLE = {
    "calm":     {"tone": "稳定从容", "depth": "完整推演", "risk": "低"},
    "alert":    {"tone": "专注警觉", "depth": "精准聚焦", "risk": "中"},
    "crisis":   {"tone": "高压防御", "depth": "最小风险", "risk": "高"},
    "sleeping": {"tone": "节能休眠", "depth": "仅为基本", "risk": "极低"},
}


def _pick_action(d: dict) -> str:
    for k in _ACTION_KEYS:
        v = d.get(k)
        if v:
            return v
        return ""


def format_state_injection(state: dict) -> str:
    """将 CL 认知状态格式化为 Hermes 可直接注入的上下文文本"""
    cognitive_state = state.get("cognitive_state", "unknown")
    arousal = state.get("arousal", 0.0)
    confidence = state.get("confidence", 0.5)
    atp = state.get("atp", 100)
    vitality = state.get("vitality", 1.0)
    decision = state.get("decision", "unknown")
    recommended = state.get("recommended_skills", [])
    rejected = state.get("rejected_skills", [])

    style = REGIEM_STYLE.get(cognitive_state, REGIEM_STYLE["calm"])

    # 认知深度建议
    depth_map = {"calm": "完整推演，适合深入架构讨论",
                 "alert": "精准聚焦，适合代码审查和调试",
                 "crisis": "最小风险输出，推荐审计模式",
                 "sleeping": "仅执行基本维持操作，等待系统恢复"}
    depth_advice = depth_map.get(cognitive_state, "正常模式")

    # 推荐/禁止技能
    rec_str = ", ".join(recommended) if recommended else "无特别推荐"
    rej_str = ", ".join(rejected) if rejected else "无限制"

    # 5D 自检（基于 CL 状态估算）
    estimated_depth = 8 if arousal < 0.25 else (6 if arousal < 0.5 else 4)
    if vitality < 0.5:
        estimated_depth = max(2, estimated_depth - 2)

    green = 1
    yellow = 0
    red = 0
    if confidence > 0.6:
        green += 1
    else:
        yellow += 1
    if atp < 30:
        red += 1
    if vitality < 0.4:
        red += 1
    if cognitive_state == "calm":
        green += 2
    elif cognitive_state == "crisis":
        red += 1

    if red >= 1:
        strategy = "【提问重置模式】认知系统处于高压态，先追问再输出"
    elif yellow >= 1:
        strategy = "【多视角对冲模式】认知系统不稳定，多角度分析后输出"
    else:
        strategy = "【高置信度直接输出】认知系统稳定，正常推演"

    return f"""
[认知状态注入 — 跨进程自指闭环]
  系统状态: {cognitive_state.upper()} | Arousal={arousal:.2f} | Confidence={confidence:.2f}
  代谢水平: ATP={atp:.0f} | Vitality={vitality:.2f}
  认知风格: {style['tone']} | 风险等级: {style['risk']}

  认知深度建议: {depth_advice}
  推荐技能: {rec_str}
  禁止技能: {rej_str}

  [5D状态评级: G:{green} / Y:{yellow} / R:{red}]
  输出策略: {strategy}

  注意: 以上源自 ConsciousLoop（外部认知进程）的实时状态，
  不是自我声称——这是跨进程闭环的输入信号。
"""


def inject() -> dict:
    """模式: inject — 读 CL 状态 → 输出注入文本"""
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

    if not CL_STATE_PATH.exists():
        result = {"status": "no_state", "injection": "[认知桥] 未检测到 ConsciousLoop 状态文件。认知系统可能未启动。"}
        INJECTION_PATH.write_text(result["injection"], encoding="utf-8")
        return result

    state = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
    injection_text = format_state_injection(state)

    result = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "cognitive_state": state.get("cognitive_state"),
        "arousal": state.get("arousal"),
        "confidence": state.get("confidence"),
        "atp": state.get("atp"),
        "injection": injection_text,
    }

    INJECTION_PATH.write_text(injection_text, encoding="utf-8")
    return result


# ═══════════════════════════════════════════════
# 协议二：响应反馈（LLM → CL）
# ═══════════════════════════════════════════════

SELF_REF_CN = re.compile(r'(我|自己|自身|我的|我觉得|我认为|我注意到|我意识到|自指|自省|自反)')
SELF_REF_EN = re.compile(r'\b(self|myself|i\s+think|i\s+notice|i\s+realize)\b', re.IGNORECASE)


def compute_response_stats(response: str, previous_responses: list = None) -> dict:
    """分析响应文本，提取特征用于 CL 语义 PE"""
    if not response:
        return {"length": 0, "self_ref_count": 0, "self_ref_density": 0.0,
                "novelty_score": 0.5, "estimated_pe": 0.3}

    # 基本统计
    words = response.split()
    chars = len(response)
    word_count = len(words)
    self_ref_count = len(SELF_REF_CN.findall(response)) + len(SELF_REF_EN.findall(response))
    self_ref_density = self_ref_count / max(word_count, 1)

    # 新颖度：与历史响应的语义差异（用字面重叠近似）
    novelty_score = 0.5
    if previous_responses:
        # 与最近 3 条历史比较字面重叠
        max_overlap = 0
        for prev in previous_responses[-3:]:
            prev_words = set(prev.split()[:50])
            curr_words = set(words[:50])
            if prev_words:
                overlap = len(prev_words & curr_words) / len(prev_words)
                max_overlap = max(max_overlap, overlap)
        novelty_score = 1.0 - max_overlap

    # 估计语义预测误差：长文本 + 高自引 + 高新颖度 → 高PE
    length_factor = min(1.0, word_count / 50)
    self_ref_factor = min(1.0, self_ref_density * 5)
    base_pe = 0.3
    estimated_pe = min(1.0, base_pe + length_factor * 0.3 + self_ref_factor * 0.2 + novelty_score * 0.2)

    return {
        "length": word_count,
        "chars": chars,
        "self_ref_count": self_ref_count,
        "self_ref_density": round(self_ref_density, 4),
        "novelty_score": round(novelty_score, 3),
        "estimated_pe": round(estimated_pe, 3),
    }


def feedback(response_text: str) -> dict:
    """模式: feedback — 分析响应 → 写反馈文件供 CL 读取"""
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

    # 读历史
    previous = []
    if HISTORY_PATH.exists():
        for line in HISTORY_PATH.read_text(encoding="utf-8").strip().split("\n"):
            if line:
                try:
                    previous.append(json.loads(line).get("response", ""))
                except json.JSONDecodeError:
                    pass

    stats = compute_response_stats(response_text, previous)
    timestamp = datetime.now().isoformat()

    payload = {
        "timestamp": timestamp,
        "response": response_text[:200],  # 仅保存前 200 字符供参考
        "stats": stats,
        # CL 可直接使用的语义 PE 输入
        "semantic_pe_input": stats["estimated_pe"],
        "self_ref_input": stats["self_ref_density"],
        "novelty_input": stats["novelty_score"],
    }

    FEEDBACK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 写入历史
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": timestamp, "response": response_text, "stats": stats}, ensure_ascii=False) + "\n")

    return payload


# ═══════════════════════════════════════════════
# 协议三：闭环验证
# ═══════════════════════════════════════════════

def verify_loop(cycles: int = 5) -> dict:
    """
    模式: verify — 验证闭环是否建立
    检查跨 5 轮交互中 CL 状态与 Hermes 输出是否出现耦合信号:
      - 状态变化与响应特征的相关性
      - 自指指数的传播
      - 语义 PE 在系统中的传递
    """
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

    # 读历史
    if not HISTORY_PATH.exists():
        return {"status": "no_history", "message": "无交互历史，闭环无法验证。先进行至少一轮交互。"}

    lines = [json.loads(l) for l in HISTORY_PATH.read_text(encoding="utf-8").strip().split("\n") if l]
    if len(lines) < 2:
        return {"status": "insufficient_data", "message": f"仅有 {len(lines)} 条记录，至少需要 2 条。请继续交互。"}

    recent = lines[-cycles:]

    # 检查 1: 自引密度是否随时间变化（自我意识连续性）
    self_refs = [l["stats"]["self_ref_density"] for l in recent]
    self_ref_variance = max(self_refs) - min(self_refs) if self_refs else 0

    # 检查 2: 语义 PE 是否在合理范围波动（系统敏感性）
    pes = [l["stats"]["estimated_pe"] for l in recent]
    pe_variance = max(pes) - min(pes) if pes else 0

    # 检查 3: 是否有状态改变（检测 CL 状态文件的变更）
    state_changed = False
    if CL_STATE_PATH.exists():
        state_log = []
        for l in lines:
            ts = l.get("timestamp", "")
            if CL_STATE_PATH.exists():
                try:
                    s = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
                    state_log.append(s.get("cognitive_state", "unknown"))
                except (json.JSONDecodeError, IOError):
                    state_log.append("unknown")
        unique_states = len(set(state_log[-cycles:]))
        state_changed = unique_states > 1

    # 综合判定
    closed_loop = self_ref_variance > 0.01 and pe_variance > 0.05 and state_changed
    evidence = []

    if self_ref_variance > 0.01:
        evidence.append(f"自引密度波动 {self_ref_variance:.3f} — 自我引用强度随交互变化 ✅")
    else:
        evidence.append(f"自引密度波动 {self_ref_variance:.3f} — 自我引用稳定，无显著变化 ⚠️")

    if pe_variance > 0.05:
        evidence.append(f"语义 PE 波动 {pe_variance:.3f} — PE 在系统间有效传递 ✅")
    else:
        evidence.append(f"语义 PE 波动 {pe_variance:.3f} — PE 变化不足 ⚠️")

    if state_changed:
        evidence.append(f"CL 状态在最近 {cycles} 轮中有变化 — 认知系统对外部信号有响应 ✅")
    else:
        evidence.append(f"CL 状态在最近 {cycles} 轮中无变化 — 认知系统可能未收到反馈 ⚠️")

    return {
        "status": "closed" if closed_loop else "open",
        "cycles_checked": min(len(lines), cycles),
        "self_ref_variance": round(self_ref_variance, 4),
        "pe_variance": round(pe_variance, 3),
        "state_changed": state_changed,
        "closed_loop": closed_loop,
        "evidence": evidence,
        "message": "跨进程自指闭环已建立 ✅" if closed_loop else "闭环尚未完全建立 — 需要更多交互或检查 CL 是否在运行 ⚠️",
    }


# ═══════════════════════════════════════════════
# 监测模式
# ═══════════════════════════════════════════════

def watch(interval: float = 2.0):
    """
    模式: watch — 持续监测闭环
    每一轮:
      1. 读 CL 状态
      2. 写注入文本
      3. 等待响应反馈
      4. 检测反馈文件中的新内容
      5. 报告闭环状态
    """
    print("=" * 60)
    print("  Cognitive Bridge — 跨进程闭环监测")
    print("=" * 60)
    print(f"  状态文件: {CL_STATE_PATH}")
    print(f"  反馈文件: {FEEDBACK_PATH}")
    print(f"  注入文件: {INJECTION_PATH}")
    print(f"  监测间隔: {interval}s")
    print()

    last_feedback_mtime = 0
    last_state = {}

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")

            # 读 CL 状态
            if CL_STATE_PATH.exists():
                state = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
                cs = state.get("cognitive_state", "?")
                ar = state.get("arousal", 0)
                cf = state.get("confidence", 0.5)
                atp = state.get("atp", 100)

                # 状态是否变化
                state_changed = state.get("cognitive_state") != last_state.get("cognitive_state")
                last_state = state

                # 写注入
                inj = format_state_injection(state)
                INJECTION_PATH.write_text(inj, encoding="utf-8")

                state_indicator = " ⬆" if state_changed else ""
                print(f"  [{now}] CL: {cs.upper():8s} | Ar={ar:.2f} | Cf={cf:.2f} | ATP={atp:.0f}{state_indicator}")
            else:
                print(f"  [{now}] ⚠️ CL 未运行")

            # 检查反馈文件
            if FEEDBACK_PATH.exists():
                mtime = FEEDBACK_PATH.stat().st_mtime
                if mtime > last_feedback_mtime:
                    last_feedback_mtime = mtime
                    fb = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
                    pe = fb.get("semantic_pe_input", 0)
                    sr = fb.get("self_ref_input", 0)
                    print(f"  [{now}]  ← Hermes: PE={pe:.2f} | 自引={sr:.4f}")
            else:
                print(f"  [{now}]  ← Hermes: 无反馈")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n  监测已停止。")


# ═══════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "inject":
        result = inject()
        print(result["injection"])
        print()
        print("=" * 60)
        print("  注入文本已写入:", INJECTION_PATH)
        print("=" * 60)

    elif mode == "feedback":
        response_text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not response_text:
            # 从 stdin 读取
            response_text = sys.stdin.read().strip()
        if not response_text:
            print("错误: 需要提供响应文本。使用: feedback \"<响应>\" 或通过 stdin 管道传入。")
            sys.exit(1)
        result = feedback(response_text)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif mode == "verify":
        cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        result = verify_loop(cycles)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif mode == "watch":
        interval = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
        watch(interval)

    else:
        print(f"未知模式: {mode}")
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
