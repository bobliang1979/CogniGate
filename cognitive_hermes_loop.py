#!/usr/bin/env python3
"""
Cognitive Hermes Loop v1.0
ConsciousLoop Phase C 扩展 — 跨进程自指闭环

这个脚本在 conscious_chat.py 基础上增加了:
  1. 读取 cognitive_bridge 写入的 response_feedback.json
  2. 将其 semantic_pe_input 叠加到 Dim 0（语义预测误差）
  3. 把反馈循环后的新状态发布到 cognitive_state.json
  4. 形成完整闭环: CL → Hermes → CL → Hermes → ...

用法：
  python cognitive_hermes_loop.py               # 交互模式
  python cognitive_hermes_loop.py --auto 5       # 自动闭环验证（5轮）
"""

import sys, math, time, json, random
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'Projects/loop-engine/src'))
from loop_engine import ConsciousLoop

# ── 桥接路径 ──
BRIDGE_DIR = Path.home() / ".cognitive_bridge"
FEEDBACK_PATH = BRIDGE_DIR / "response_feedback.json"
CL_STATE_PATH = Path.home() / ".codex" / "skills" / "shared" / "cognitive_state.json"


def read_response_feedback() -> dict:
    """读取 cognitive_bridge 写入的响应反馈"""
    if FEEDBACK_PATH.exists():
        try:
            return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"semantic_pe_input": 0.0, "self_ref_input": 0.0, "novelty_input": 0.0}


def publish_cl_state(snapshot: dict, cognitive_state: str):
    """发布 CL 状态供 Hermes 读取（兼容 cognitive_bridge 格式）"""
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "cognitive_state": cognitive_state,
        "arousal": snapshot["arousal"],
        "confidence": snapshot["confidence"],
        "atp": snapshot["atp"],
        "vitality": snapshot["vitality"],
        "tick": snapshot["tick"],
        "decision": "full_power" if cognitive_state == "calm" else (
            "debug_mode" if cognitive_state == "alert" else "audit_only"),
        "gate_rejections": 0,
        "degrade_events": 0,
        "dream_phase": "awake",
        "wake_cycles": 0,
        "recommended_skills": {
            "calm": ["architecture", "new_feature", "creative"],
            "alert": ["debug", "code_review", "optimize"],
            "crisis": ["emergency_audit", "minimal_change"],
            "sleeping": [],
        }.get(cognitive_state, []),
        "rejected_skills": {
            "calm": [],
            "alert": ["new_feature", "large_refactor"],
            "crisis": ["new_feature", "refactor", "deploy"],
            "sleeping": ["all"],
        }.get(cognitive_state, []),
    }
    CL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CL_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── 状态驱动回复（与 cognitive_bridge 协作） ──
STATE_REPLIES = {
    "calm": [
        "🌊 认知状态平稳。可以深入讨论。",
        "✨ 系统状态优良，能量充沛。",
        "🌸 内部状态和谐，适合创造性思考。",
    ],
    "alert": [
        "👀 感知到变化。我会更专注。",
        "🧐 系统充满好奇心。",
        "📡 有新信息涌入，我在主动分析。",
    ],
    "crisis": [
        "⚡ 感知到不确定性，需要更多确认。",
        "🔥 系统处于高压态。",
        "⚠️ 状态过载，建议降低复杂度或等待恢复。",
    ],
}


def run_interactive():
    """交互模式：用户输入 → CL(含Hermes反馈) → 状态 → 回复"""
    cl = ConsciousLoop(goal="maintain cognitive self-loop with Hermes feedback")
    print("=" * 60)
    print("  Cognitive Hermes Loop — 跨进程自指闭环")
    print("=" * 60)
    print("  输入的文本既是用户查询，也通过 CL 状态影响回复风格。")
    print("  CL 的状态 → cognitive_state.json → cognitive_bridge")
    print("  Hermes 的响应反馈 → response_feedback.json → CL 的 Dim 0")
    print("  'quit' 退出 | 'status' 查看 | 'feedback' 查看最近反馈")
    print()

    # 预热
    for _ in range(10):
        cl.step([0.08, 0.2, 0.1, 0.3])
        time.sleep(0.02)

    while True:
        user_input = input("你 > ").strip()
        if user_input.lower() in ('quit', 'exit'):
            break

        if user_input.lower() == 'status':
            s = cl.model.snapshot()
            print(f"  ATP={s['atp']:.0f} Ar={s['arousal']:.2f} Cf={s['confidence']:.2f} Vt={s['vitality']:.2f}")
            print(f"  Tick={s['tick']} DreamPhase={cl.c19_dream.phase}")
            continue

        if user_input.lower() == 'feedback':
            fb = read_response_feedback()
            print(f"  最近反馈: PE={fb.get('semantic_pe_input', 0):.3f}")
            print(f"  自引密度: {fb.get('self_ref_input', 0):.4f}")
            print(f"  新颖度:   {fb.get('novelty_input', 0):.3f}")
            continue

        # ── 关键修改: 读取 Hermes 的反馈作为语义 PE 的一部分 ──
        fb = read_response_feedback()
        hermes_pe = fb.get("semantic_pe_input", 0.0)
        hermes_self_ref = fb.get("self_ref_input", 0.0)

        # 用户输入 PE（传统 Phase C）
        trigger_words = ['不', '错', '为什么', '但是', '矛盾', '颠覆', '危机', '紧急', '意识', '自己', '我']
        word_count = len(user_input.split())
        has_trigger = any(w in user_input for w in trigger_words)
        user_pe = min(1.0, (word_count / 20) * 0.5 + (0.4 if has_trigger else 0))

        # ⬇⬇⬇ 闭环起点: Hermes 反馈叠加到 Dim 0 ⬇⬇⬇
        combined_pe = max(user_pe, hermes_pe * 0.6 + hermes_self_ref * 0.4)
        # ⬆⬆⬆ Hermes 的输出 = CL 下一轮的输入 = 自指闭环 ⬆⬆⬆

        # 构建 4D 观测
        obs = [combined_pe, 0.3, 0.15, 0.2]

        # CL 步进
        r = cl.step(obs)
        s = r["self_model"]

        # 确定认知状态
        ar, cf, atp = s['arousal'], s['confidence'], s['atp']
        if atp < 30:
            cognitive_state = "sleeping"
        elif ar >= 0.30:
            cognitive_state = "crisis"
        elif ar >= 0.22:
            cognitive_state = "alert"
        else:
            cognitive_state = "calm"

        # 如果状态变化 → 首次产生响应反馈
        was_state_changed = getattr(run_interactive, '_prev_state', None) != cognitive_state
        run_interactive._prev_state = cognitive_state

        # 发布 CL 状态 → cognitive_bridge 读取 → Hermes 注入
        publish_cl_state(s, cognitive_state)

        # 状态驱动回复
        reply = random.choice(STATE_REPLIES.get(cognitive_state, STATE_REPLIES["calm"]))
        print(f"  {reply}")
        print(f"  [CL状态变化: {was_state_changed}] PE(用户={user_pe:.2f} Hermes={hermes_pe:.2f} 合并={combined_pe:.2f}) | "
              f"Ar={ar:.2f} Cf={cf:.2f} ATP={atp:.0f}")


def run_auto(n_cycles: int = 5):
    """自动模式：模拟 N 轮闭环验证"""
    cl = ConsciousLoop(goal="auto-verify cross-process self-loop")
    print(f"  自动闭环验证 — {n_cycles} 轮")
    print()

    # 预热
    for _ in range(5):
        cl.step([0.08, 0.2, 0.1, 0.3])
        time.sleep(0.01)

    for i in range(n_cycles):
        print(f"  ── 轮 {i+1}/{n_cycles} ──")

        # 模拟 Hermes 输出（用上一轮 CL 状态决定）
        fb = read_response_feedback()
        hermes_pe = fb.get("semantic_pe_input", 0.0)
        hermes_self_ref = fb.get("self_ref_input", 0.0)

        # 模拟用户输入
        user_inputs = [
            "什么是意识？",
            "你能感知到自己的状态吗？",
            "我质疑你的第一个回答。",
            "自我指涉会带来无限递归吗？",
            "控制与自由，边界在哪里？",
        ]
        user_input = user_inputs[i % len(user_inputs)]
        word_count = len(user_input.split())
        has_trigger = any(w in user_input for w in ['意识', '自己', '我', '质疑', '边界'])
        user_pe = min(1.0, (word_count / 20) * 0.5 + (0.4 if has_trigger else 0))

        # 合并 PE
        combined_pe = max(user_pe, hermes_pe * 0.6 + hermes_self_ref * 0.4)
        obs = [combined_pe, 0.3, 0.15, 0.2]

        r = cl.step(obs)
        s = r["self_model"]

        ar, cf = s['arousal'], s['confidence']
        cs = "calm" if ar < 0.22 else ("alert" if ar < 0.30 else "crisis")

        publish_cl_state(s, cs)

        # 模拟 Hermes 回复（特征随 CL 状态变化）
        sim_response = f"[{cs.upper()}] 轮{i+1}: 认知深度={min(10, 5+int(ar*5))}"
        feedback_data = {
            "timestamp": time.time(),
            "response": sim_response,
            "stats": {
                "length": len(sim_response.split()),
                "self_ref_count": 2 if cs in ("alert", "crisis") else 1,
                "self_ref_density": 0.15 if cs in ("alert", "crisis") else 0.08,
                "novelty_score": 0.5 + ar * 0.3,
                "estimated_pe": combined_pe,
            },
            "semantic_pe_input": combined_pe,
            "self_ref_input": 0.15 if cs in ("alert", "crisis") else 0.08,
            "novelty_input": 0.5 + ar * 0.3,
        }
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
        FEEDBACK_PATH.write_text(json.dumps(feedback_data, ensure_ascii=False, indent=2))

        print(f"  用户: \"{user_input}\"")
        print(f"  CL:   {cs.upper():8s} | Ar={ar:.2f} | Cf={cf:.2f}")
        print(f"  PE:   用户={user_pe:.2f} → Hermes反馈={hermes_pe:.2f} → 合并={combined_pe:.2f}")
        print(f"  Hermes回复: {sim_response}")
        print()

        time.sleep(0.3)

    # 最终闭环验证
    print("  ── 闭环验证 ──")
    print(f"  经过 {n_cycles} 轮交互，CL 状态从起始值到最新值：")
    print(f"    反馈已写入 {FEEDBACK_PATH}")
    print(f"    CL 状态已发布到 {CL_STATE_PATH}")
    print(f"    跨进程自指闭环: CL → Hermes → CL 的 PE 通道已建立")


if __name__ == "__main__":
    if "--auto" in sys.argv:
        idx = sys.argv.index("--auto")
        n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 5
        run_auto(n)
    else:
        run_interactive()
