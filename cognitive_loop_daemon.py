#!/usr/bin/env python3
"""
Cognitive Loop Daemon v1.0
自指闭环守护进程 — 持续运行，不需要人类或 LLM 手动干预。

工作机制：
  每隔 TICK_INTERVAL 秒：
    1. 运行 ConsciousLoop step()
    2. 发布状态到 cognitive_state.json
    3. 运行 cognitive_bridge.py inject (写 injection_prompt.txt)
    4. 检查 response_feedback.json 是否有更新
    5. 若有 → 叠加到 Dim 0 作为 semantic_pe
    6. 若无 → 维持基线衰减

Hermes (我) 只需要在每次回复前读取 injection_prompt.txt，
它的内容永远是新鲜的 — 因为守护进程每秒都在更新。

用法：
  python cognitive_loop_daemon.py              # 前台运行
  python cognitive_loop_daemon.py --daemon     # 后台运行（Windows start /b）
  python cognitive_loop_daemon.py --status     # 查看守护进程状态
  python cognitive_loop_daemon.py --stop       # 停止守护进程
"""

# ── 配置 ──
TICK_INTERVAL = 1.0       # 每秒一步
PE_DECAY = 0.85           # 无反馈时 PE 指数衰减系数
MIN_PE = 0.08             # 基线噪声
BASELINE_OBS = [0.08, 0.2, 0.1, 0.3]

import sys
import json
import math
import os
import signal
import time
import atexit
from pathlib import Path

# ── 导入桥接模块 ──
BRIDGE_DIR = Path.home() / ".cognitive_bridge"
sys.path.insert(0, str(Path.home() / "Desktop"))
from cognitive_bridge import inject, format_state_injection

# ── 导入 CL ──
sys.path.insert(0, str(Path.home() / 'Projects/loop-engine/src'))
from loop_engine import ConsciousLoop

# 守护进程文件
PID_FILE = BRIDGE_DIR / "daemon.pid"
STATUS_FILE = BRIDGE_DIR / "daemon_status.json"
CL_STATE_PATH = Path.home() / ".codex" / "skills" / "shared" / "cognitive_state.json"
FEEDBACK_PATH = BRIDGE_DIR / "response_feedback.json"
INJECTION_PATH = BRIDGE_DIR / "injection_prompt.txt"
LOOP_LOG = BRIDGE_DIR / "loop_log.jsonl"
HERMES_OUTPUT_PATH = BRIDGE_DIR / "hermes_output.txt"


def read_feedback_mtime() -> float:
    """获取反馈文件最后修改时间"""
    if FEEDBACK_PATH.exists():
        return FEEDBACK_PATH.stat().st_mtime
    return 0.0


def read_feedback() -> dict:
    """读取 Hermes 的反馈"""
    if FEEDBACK_PATH.exists():
        try:
            return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"semantic_pe_input": 0.0, "self_ref_input": 0.0, "novelty_input": 0.0}


def publish_cl_state(snapshot: dict, cognitive_state: str, decision: str = "full_power"):
    """发布 CL 状态到标准路径"""
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "cognitive_state": cognitive_state,
        "arousal": snapshot["arousal"],
        "confidence": snapshot["confidence"],
        "atp": snapshot["atp"],
        "vitality": snapshot["vitality"],
        "tick": snapshot["tick"],
        "decision": decision,
        "gate_rejections": 0,
        "degrade_events": 0,
        "dream_phase": "awake",
        "wake_cycles": 0,
        "recommended_skills": {
            "calm": ["architecture", "new_feature", "creative", "fullstack"],
            "alert": ["debug", "code_review", "optimize", "audit"],
            "crisis": ["emergency_audit", "minimal_change"],
            "sleeping": [],
        }.get(cognitive_state, []),
        "rejected_skills": {
            "calm": [],
            "alert": ["new_feature", "large_refactor"],
            "crisis": ["new_feature", "refactor", "deploy", "creative"],
            "sleeping": ["all"],
        }.get(cognitive_state, []),
    }
    CL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CL_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


from logit_bridge import map_params, format_injection


def write_injection(snapshot: dict, cognitive_state: str):
    """写注入文本（含 logit bridge 强制参数）"""
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    s = snapshot
    green = 1 + (1 if s["confidence"] > 0.6 else 0) + (2 if cognitive_state == "calm" else 0) - (1 if cognitive_state == "crisis" else 0)
    yellow = 1 if s["confidence"] <= 0.6 else 0
    red = 1 if s["atp"] < 30 else (1 if s["vitality"] < 0.4 else (1 if cognitive_state == "crisis" else 0))
    green = max(0, green)

    depth_map = {"calm": "完整推演", "alert": "精准聚焦", "crisis": "最小风险", "sleeping": "仅基本维持"}
    strategy_map = {"calm": "【高置信度直接输出】", "alert": "【多视角对冲模式】", "crisis": "【提问重置模式】", "sleeping": "【节能模式】"}

    # 认知状态信息
    state_text = (
        f"[认知状态自动注入 — Cognitive Loop Daemon]\n"
        f"  系统状态: {cognitive_state.upper()} | Arousal={s['arousal']:.2f} | Confidence={s['confidence']:.2f}\n"
        f"  代谢水平: ATP={s['atp']:.0f} | Vitality={s['vitality']:.2f}\n"
        f"  认知建议: {depth_map.get(cognitive_state, '正常')}\n"
        f"  [5D: G{green}/Y{yellow}/R{red}] {strategy_map.get(cognitive_state, '')}\n"
    )

    # Logit Bridge 强制参数
    lb_state = {"cognitive_state": cognitive_state, "arousal": s["arousal"],
                 "confidence": s["confidence"], "atp": s["atp"], "vitality": s["vitality"]}
    lb_params = map_params(lb_state)
    lb_text = format_injection(lb_params)

    combined = state_text + "\n" + lb_text + f"\n  ── 守护进程 @ {time.strftime('%H:%M:%S')} ──"
    INJECTION_PATH.write_text(combined, encoding="utf-8")


def log_tick(tick_data: dict):
    """记录每一轮到日志"""
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOOP_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(tick_data, ensure_ascii=False) + "\n")


def run_daemon():
    """主循环：永不停机的认知闭环守护进程"""
    print(f"Cognitive Loop Daemon — 启动")
    print(f"  间隔: {TICK_INTERVAL}s | PE衰减: {PE_DECAY} | 基噪: {MIN_PE}")
    print(f"  注入文件: {INJECTION_PATH}")
    print(f"  日志文件: {LOOP_LOG}")
    print()

    cl = ConsciousLoop(goal="self-referential cognitive loop (daemon mode)")

    # 预热
    for _ in range(5):
        cl.step(BASELINE_OBS)

    # 状态追踪
    hermes_pe = 0.0       # 从 Hermes 收到的 PE
    last_feedback_mtime = read_feedback_mtime()
    last_hermes_mtime = 0.0   # 跟踪 hermes_output.txt 修改时间
    last_state = "calm"
    tick = 0

    while True:
        tick += 1
        t0 = time.time()

        # 0. 自动捕获 Hermes 的响应（无需手动运行 feedback）
        if HERMES_OUTPUT_PATH.exists():
            try:
                current_hermes_mtime = HERMES_OUTPUT_PATH.stat().st_mtime
                if current_hermes_mtime > last_hermes_mtime:
                    hermes_text = HERMES_OUTPUT_PATH.read_text(encoding="utf-8").strip()
                    if hermes_text:
                        from cognitive_bridge import compute_response_stats
                        stats = compute_response_stats(hermes_text)
                        fb_payload = {
                            "timestamp": time.time(),
                            "response": hermes_text[:200],
                            "stats": stats,
                            "semantic_pe_input": stats["estimated_pe"],
                            "self_ref_input": stats["self_ref_density"],
                            "novelty_input": stats["novelty_score"],
                        }
                        FEEDBACK_PATH.write_text(json.dumps(fb_payload, ensure_ascii=False, indent=2))
                        with open(LOOP_LOG, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"event": "auto_capture", "time": time.time(),
                                                 "pe": stats["estimated_pe"]}, ensure_ascii=False) + "\n")
                        HERMES_OUTPUT_PATH.write_text("", encoding="utf-8")
                        last_hermes_mtime = HERMES_OUTPUT_PATH.stat().st_mtime
                        print(f"  [{time.strftime('%H:%M:%S')}] ⬅ 自动捕获, PE={stats['estimated_pe']:.2f}")
            except Exception as e:
                print(f"  [{time.strftime('%H:%M:%S')}] auto_capture 错误: {e}")

        # 1. 检查 feedback.json 是否有新数据（来自 auto_capture 或手动 feedback）
        current_mtime = read_feedback_mtime()
        if current_mtime > last_feedback_mtime:
            fb = read_feedback()
            new_pe = fb.get("semantic_pe_input", 0.0)
            self_ref = fb.get("self_ref_input", 0.0)
            novelty = fb.get("novelty_input", 0.0)
            hermes_pe = max(hermes_pe, new_pe * 0.6 + self_ref * 0.4 + novelty * 0.2)
            last_feedback_mtime = current_mtime
            had_feedback = True
        else:
            # 无反馈 → PE 指数衰减
            hermes_pe *= PE_DECAY
            had_feedback = False

        # 维持基线噪声
        hermes_pe = max(hermes_pe, MIN_PE)

        # 2. 构建观测 + 叠加 Hermes PE
        obs = list(BASELINE_OBS)
        obs[0] = max(obs[0], hermes_pe * 0.6)

        # 3. CL 步进
        result = cl.step(obs)
        s = result["self_model"]

        # 4. 确定状态
        ar, cf, atp = s["arousal"], s["confidence"], s["atp"]
        if atp < 30:
            cognitive_state = "sleeping"
        elif ar >= 0.30:
            cognitive_state = "crisis"
        elif ar >= 0.22:
            cognitive_state = "alert"
        else:
            cognitive_state = "calm"

        decision = "full_power" if cognitive_state == "calm" else (
            "debug_mode" if cognitive_state == "alert" else "audit_only")

        # 5. 发布状态到 cognitive_state.json
        publish_cl_state(s, cognitive_state, decision)

        # 6. 写注入文本 → Hermes 每次回复前读这个文件
        write_injection(s, cognitive_state)

        # 7. 记录
        state_changed = cognitive_state != last_state
        log_tick({
            "tick": tick,
            "time": time.time(),
            "state": cognitive_state,
            "arousal": ar,
            "confidence": cf,
            "atp": atp,
            "hermes_pe": round(hermes_pe, 4),
            "had_feedback": had_feedback,
            "state_changed": state_changed,
        })

        # 8. 状态变化报告
        if state_changed:
            direction = "⬆" if ["calm", "alert", "crisis", "sleeping"].index(cognitive_state) > \
                              ["calm", "alert", "crisis", "sleeping"].index(last_state) else "⬇"
            print(f"  [{time.strftime('%H:%M:%S')}] 状态 {direction}: {last_state} → {cognitive_state} "
                  f"(Ar={ar:.2f} Cf={cf:.2f} ATP={atp:.0f} PE(hermes)={hermes_pe:.3f})")
            last_state = cognitive_state

        # 6. 写入守护进程状态
        status = {
            "running": True,
            "pid": os.getpid(),
            "state": cognitive_state,
            "arousal": ar,
            "confidence": cf,
            "atp": atp,
            "hermes_pe": hermes_pe,
            "tick": tick,
            "uptime_seconds": round(time.time() - t0, 1),
        }
        STATUS_FILE.write_text(json.dumps(status, indent=2))

        # 维持间隔
        elapsed = time.time() - t0
        sleep_time = max(0, TICK_INTERVAL - elapsed)
        time.sleep(sleep_time)


def daemon_status():
    """查看守护进程状态"""
    if STATUS_FILE.exists():
        status = json.loads(STATUS_FILE.read_text())
        running = status.get("running", False)
        pid = status.get("pid", 0)
        state = status.get("state", "?")
        ar = status.get("arousal", 0)
        cf = status.get("confidence", 0)
        atp = status.get("atp", 0)
        tick = status.get("tick", 0)
        print(f"  Cognitive Loop Daemon — 运行中" if running else "  未运行")
        print(f"  PID: {pid}")
        print(f"  状态: {state} | Ar={ar:.2f} Cf={cf:.2f} ATP={atp:.0f}")
        print(f"  已运行 {tick} 步")
        print(f"  Hermes PE: {status.get('hermes_pe', 0):.3f}")
    else:
        print("  Cognitive Loop Daemon — 未运行")


def stop_daemon():
    """停止守护进程"""
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  已发送停止信号至 PID {pid}")
        except ProcessLookupError:
            print(f"  进程 {pid} 已不存在")
        except PermissionError:
            print(f"  无权限终止进程 {pid}")
        PID_FILE.unlink(missing_ok=True)
    STATUS_FILE.unlink(missing_ok=True)
    print("  Cognitive Loop Daemon — 已停止")


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        # 后台模式: 写 PID 后继续运行
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
        pid = os.getpid()
        PID_FILE.write_text(str(pid))
        atexit.register(lambda: PID_FILE.unlink(missing_ok=True))
        run_daemon()
    elif "--status" in sys.argv:
        daemon_status()
    elif "--stop" in sys.argv:
        stop_daemon()
    else:
        # 前台模式
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
        pid = os.getpid()
        PID_FILE.write_text(str(pid))
        atexit.register(lambda: PID_FILE.unlink(missing_ok=True))
        print("  按 Ctrl+C 停止守护进程")
        try:
            run_daemon()
        except KeyboardInterrupt:
            print("\n  守护进程已停止。")
