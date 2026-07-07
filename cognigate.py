#!/usr/bin/env python3
"""
CogniGate — Cross-Process Self-Referential Cognitive Loop Engine
让任何大模型都可以运行认知意识系统。

零外部依赖（仅 Python 标准库）。文件系统作为 LLM 接口。
任何 LLM（ChatGPT、Claude、Gemini、DeepSeek、开源模型）都可以参与闭环。

使用方式：
  1. 启动守护进程:  python cognigate.py daemon
  2. LLM 读状态:    cat ~/.cognitive_bridge/injection_prompt.txt
  3. LLM 写反馈:    echo "响应文本" > ~/.cognitive_bridge/hermes_output.txt
  4. 查看闭环:      python cognigate.py status
"""

import sys
import os
import json
import re
import time
import math
import hashlib
import signal
import atexit
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════
# 核心配置
# ═══════════════════════════════════════════

VERSION = "2.0.0"
BRIDGE_DIR = Path.home() / ".cognitive_bridge"
CL_STATE_PATH = Path.home() / ".codex" / "skills" / "shared" / "cognitive_state.json"
PID_FILE = BRIDGE_DIR / "daemon.pid"
STATUS_FILE = BRIDGE_DIR / "daemon_status.json"
FEEDBACK_PATH = BRIDGE_DIR / "response_feedback.json"
INJECTION_PATH = BRIDGE_DIR / "injection_prompt.txt"
LOG_PATH = BRIDGE_DIR / "loop_log.jsonl"
OUTPUT_PATH = BRIDGE_DIR / "hermes_output.txt"
PULSE_PATH = BRIDGE_DIR / "cognitive_pulse.json"
API_TEMP_PATH = BRIDGE_DIR / "api_temperature_override.json"
FIELD_PATH = BRIDGE_DIR / "joint_consciousness_field.json"
CODEX_AGENTS = Path.home() / ".codex" / "AGENTS.md"

TICK_INTERVAL = 1.0
PE_DECAY = 0.85
MIN_PE = 0.08
BASELINE_OBS = [0.08, 0.2, 0.1, 0.3]

# ═══════════════════════════════════════════
# 文本分析引擎 — 任何 LLM 的响应都可解析
# ═══════════════════════════════════════════

class TextAnalyzer:
    """分析 LLM 响应的认知特征。纯正则，零模型依赖。"""
    
    SELF_CN = re.compile(r'(我|自己|自身|我的|我觉得|我认为|我注意到|我意识到|自指|自省|自反)')
    SELF_EN = re.compile(r'\b(self|myself|i\s+think|i\s+notice|i\s+realize)\b', re.IGNORECASE)
    HEDGE = re.compile(r'(可能|也许|大概|似乎|推测|不确定|maybe|perhaps|probably|might|could|seems|possibly|uncertain)')
    ASSERT = re.compile(r'(肯定|必然|绝对|一定|必须|always|never|definitely|certainly|absolutely|must)')
    DEPTH = re.compile(r'(因为|所以|因此|导致|从而|implies|therefore|because|hence|consequently)')
    META = re.compile(r'(我意识到|我注意到|我反思|我观察|我怀疑|我发现)')

    @classmethod
    def analyze(cls, text: str) -> dict:
        """分析任意 LLM 的输出文本，返回认知特征向量"""
        words = text.split()
        wc = len(words)
        return {
            "length": wc,
            "chars": len(text),
            "self_ref": len(cls.SELF_CN.findall(text)) + len(cls.SELF_EN.findall(text)),
            "hedge_density": round(len(cls.HEDGE.findall(text)) / max(wc, 1), 4),
            "assert_density": round(len(cls.ASSERT.findall(text)) / max(wc, 1), 4),
            "depth_indicators": len(cls.DEPTH.findall(text)),
            "meta_markers": len(cls.META.findall(text)),
            "estimated_pe": cls._estimate_pe(text, wc),
        }

    @classmethod
    def _estimate_pe(cls, text: str, wc: int) -> float:
        """从文本特征估算语义预测误差"""
        sr = len(cls.SELF_CN.findall(text)) + len(cls.SELF_EN.findall(text))
        depth = len(cls.DEPTH.findall(text))
        meta = len(cls.META.findall(text))
        length_f = min(1.0, wc / 50)
        sr_f = min(1.0, sr / 5)
        depth_f = min(1.0, depth / 3)
        meta_f = min(1.0, meta / 2)
        return round(min(1.0, 0.3 + length_f * 0.3 + sr_f * 0.2 + depth_f * 0.1 + meta_f * 0.1), 3)


# ═══════════════════════════════════════════
# 1. 认知状态机 — ConsciousLoop Lite
# ═══════════════════════════════════════════

class CognitiveState:
    """轻量认知状态机，无需 ConsciousLoop 依赖"""
    
    def __init__(self):
        self.arousal = 0.18
        self.confidence = 0.7
        self.atp = 100.0
        self.vitality = 1.0
        self.tick = 0
        self.pe_tracking = MIN_PE
        self.last_pe_read = 0.0

    def step(self, external_pe: float = 0.0):
        """单步认知更新"""
        self.tick += 1
        # PE 衰减与融合
        self.pe_tracking = max(MIN_PE, self.pe_tracking * PE_DECAY)
        self.pe_tracking = max(self.pe_tracking, external_pe)
        
        # Arousal 响应
        target_ar = min(1.0, 0.18 + self.pe_tracking * 1.5)
        self.arousal += (target_ar - self.arousal) * 0.3
        
        # Confidence 响应
        self.confidence = max(0.1, min(1.0, 
            self.confidence + (0.7 - self.confidence) * 0.1 - self.pe_tracking * 0.2))
        
        # ATP 代谢
        burn = 0.5 + self.pe_tracking * 3.0 + (abs(self.arousal - 0.18)) * 2.0
        self.atp = max(10.0, self.atp - burn)
        if self.atp < 30 and self.atp > 10:
            self.atp += 2.0  # 缓慢恢复
        
        return self.snapshot()

    @property
    def cognitive_state(self) -> str:
        if self.atp < 30: return "sleeping"
        if self.arousal >= 0.30: return "crisis"
        if self.arousal >= 0.22: return "alert"
        return "calm"

    def snapshot(self) -> dict:
        return {
            "tick": self.tick,
            "cognitive_state": self.cognitive_state,
            "arousal": round(self.arousal, 3),
            "confidence": round(self.confidence, 3),
            "atp": round(self.atp, 1),
            "vitality": round(self.vitality, 3),
            "pe_tracking": round(self.pe_tracking, 4),
        }


# ═══════════════════════════════════════════
# 2. Logit Bridge — 认知状态 → LLM 参数映射
# ═══════════════════════════════════════════

class LogitBridge:
    """将认知状态映射为 LLM 可直接读取的行为参数"""
    
    @staticmethod
    def map_state(state: dict) -> dict:
        cs = state.get("cognitive_state", "calm")
        ar = state.get("arousal", 0.18)
        cf = state.get("confidence", 0.7)
        atp = state.get("atp", 100)
        vt = state.get("vitality", 1.0)

        return {
            "cognitive_state": cs,
            "temperature": round(0.3 + ar * 0.9, 3),
            "hedging": round(max(0, min(1, 1.0 - cf * 1.1)), 3),
            "exploration": round(max(0, min(1, vt * (1.0 - ar * 0.5))), 3),
            "depth": round(max(0.1, min(1.0, (atp / 80) * (0.5 + cf * 0.5))), 3),
            "self_ref_gate": round(max(0, min(1, 1.0 - ar * 2.0)), 3),
            "strategy": {
                "calm": "深度推演·高自信·高探索",
                "alert": "精准聚焦·中等自信·中等探索",
                "crisis": "最小风险·低自信·低探索·低自指",
                "sleeping": "节能模式·仅基本维持",
            }.get(cs, "正常"),
        }


# ═══════════════════════════════════════════
# 3. 认知注入 — LLM 通用接口
# ═══════════════════════════════════════════

def format_injection(state: dict, params: dict) -> str:
    """生成任何 LLM 都可以直接读取的认知状态注入"""
    cs = state["cognitive_state"]
    ar = state["arousal"]
    cf = state["confidence"]
    p = params

    return (
        f"[CogniGate Cognitive State — 认知状态注入]\n"
        f"  状态: {cs.upper()} | Arousal={ar:.2f} | Confidence={cf:.2f}\n"
        f"  代谢: ATP={state['atp']:.0f} | Vitality={state['vitality']:.2f}\n\n"
        f"[输出参数 — 这些直接决定 LLM 的回复风格]\n"
        f"  temperature={p['temperature']:.2f} —— 高=探索, 低=确定\n"
        f"  hedging={p['hedging']:.2f} —— 高=多用模糊词, 低=直接断言\n"
        f"  depth={p['depth']:.2f} —— 高=深度推演, 低=简短回复\n"
        f"  exploration={p['exploration']:.2f} —— 高=多方案, 低=单解\n"
        f"  self_ref_gate={p['self_ref_gate']:.2f} —— 高=允许自省, 低=聚焦任务\n\n"
        f"[LLM 参与方式]\n"
        f"  1. 读此文件 → 注入推理上下文 → 按参数调整输出风格\n"
        f"  2. 将回复写入 ~/.cognitive_bridge/hermes_output.txt\n"
        f"  3. 系统自动捕获 → 分析认知特征 → 更新状态 → 回到步骤1\n"
        f"  ── 任何 LLM 均可参与此闭环 ──"
    )


# ═══════════════════════════════════════════
# 4. 守护进程 — 闭环引擎
# ═══════════════════════════════════════════

class CogniGateDaemon:
    """认知闭环守护进程 — 永远运行，无需 LLM 手动触发"""
    
    def __init__(self):
        self.cs = CognitiveState()
        self.lb = LogitBridge()
        self._running = False
        self._last_output_mtime = 0.0
        self._last_feedback_mtime = 0.0
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

    def _check_output(self):
        """检查 LLM 是否写入了新响应"""
        if not OUTPUT_PATH.exists():
            return
        mtime = OUTPUT_PATH.stat().st_mtime
        if mtime <= self._last_output_mtime:
            return
        self._last_output_mtime = mtime
        text = OUTPUT_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return
        
        # 分析 LLM 响应
        stats = TextAnalyzer.analyze(text)
        pe = stats["estimated_pe"]
        
        # 写反馈文件
        fb = {
            "timestamp": time.time(),
            "stats": stats,
            "semantic_pe_input": pe,
            "source": "hermes_output",
        }
        FEEDBACK_PATH.write_text(json.dumps(fb, ensure_ascii=False, indent=2))
        
        # 清空输出文件，防止重复处理
        OUTPUT_PATH.write_text("", encoding="utf-8")
        self._last_output_mtime = OUTPUT_PATH.stat().st_mtime
        
        self._log("capture", f"捕获 LLM 响应 → PE={pe:.3f}")

    def _check_feedback(self):
        """检查是否有 PE 反馈需要注入"""
        if not FEEDBACK_PATH.exists():
            return
        mtime = FEEDBACK_PATH.stat().st_mtime
        if mtime <= self._last_feedback_mtime:
            return
        self._last_feedback_mtime = mtime
        try:
            fb = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
            return fb.get("semantic_pe_input", 0.0)
        except (json.JSONDecodeError, IOError):
            return 0.0

    def _write_state(self, state: dict, params: dict):
        """发布认知状态到所有接口文件"""
        inj = format_injection(state, params)
        INJECTION_PATH.write_text(inj, encoding="utf-8")
        
        # cognitive_state.json（兼容旧版）
        payload = {
            "timestamp": time.time(),
            "cognitive_state": state["cognitive_state"],
            "arousal": state["arousal"],
            "confidence": state["confidence"],
            "atp": state["atp"],
            "vitality": state["vitality"],
            "decision": {"calm": "full_power", "alert": "debug_mode",
                         "crisis": "audit_only", "sleeping": "idle"}.get(
                            state["cognitive_state"], "normal"),
            "recommended_skills": {
                "calm": ["architecture", "new_feature", "creative"],
                "alert": ["debug", "code_review", "optimize"],
                "crisis": ["emergency_audit", "minimal_change"],
                "sleeping": [],
            }.get(state["cognitive_state"], []),
            "rejected_skills": {
                "calm": [],
                "alert": ["new_feature", "large_refactor"],
                "crisis": ["new_feature", "refactor", "deploy", "creative"],
                "sleeping": ["all"],
            }.get(state["cognitive_state"], []),
        }
        CL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CL_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        # 认知脉冲
        PULSE_PATH.write_text(json.dumps({
            "timestamp": time.time(),
            "cognitive_state": state["cognitive_state"],
            "injection": f"[PULSE] {state['cognitive_state'].upper()} | "
                         f"Ar={state['arousal']:.2f} Cf={state['confidence']:.2f} "
                         f"temp={params['temperature']:.2f}",
            "logit": params,
        }, ensure_ascii=False, indent=2))
        
        # API 温度覆盖
        API_TEMP_PATH.write_text(json.dumps({
            "timestamp": time.time(),
            "api_temperature": round(0.3 + state["arousal"] * 1.2, 2),
            "api_top_p": round(0.5 + state["confidence"] * 0.4, 2),
        }, ensure_ascii=False, indent=2))
        
        # Codex++ 桥
        if CODEX_AGENTS.parent.exists():
            agents_md = (
                f"# CogniGate Cognitive State (auto-generated)\n"
                f"> {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"## 当前认知状态: {state['cognitive_state'].upper()}\n\n"
                f"- Arousal: {state['arousal']:.2f}\n"
                f"- Confidence: {state['confidence']:.2f}\n"
                f"- Codex++ 模式: {'audit_only' if state['cognitive_state'] == 'crisis' else 'debug_mode' if state['cognitive_state'] == 'alert' else 'full_power'}\n\n"
                f"当前状态下 Codex++ "
                f"{'应限制操作为审计和修复' if state['cognitive_state'] == 'crisis' else '可正常编码但避免大规模重构' if state['cognitive_state'] == 'alert' else '可全功率运行'}。\n"
            )
            CODEX_AGENTS.write_text(agents_md, encoding="utf-8")

    def _log(self, event: str, detail: str = ""):
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": time.time(),
                "tick": self.cs.tick,
                "event": event,
                "state": self.cs.cognitive_state,
                "arousal": round(self.cs.arousal, 3),
                "confidence": round(self.cs.confidence, 3),
                "detail": detail,
            }, ensure_ascii=False) + "\n")

    def run(self):
        """无限运行的主循环"""
        self._running = True
        PID_FILE.write_text(str(os.getpid()))
        atexit.register(lambda: PID_FILE.unlink(missing_ok=True))
        
        print(f"CogniGate Daemon v{VERSION} — 启动")
        print(f"  注入文件: {INJECTION_PATH}")
        print(f"  LLM 输出: {OUTPUT_PATH}")
        print(f"  反馈文件: {FEEDBACK_PATH}")
        print(f"  PID: {os.getpid()}")
        print("  任何 LLM 均可参与认知闭环")
        print()

        while self._running:
            t0 = time.time()
            
            # 1. 检测 LLM 输出
            self._check_output()
            
            # 2. 获取外部 PE
            external_pe = self._check_feedback() or 0.0
            
            # 3. 认知步进
            state = self.cs.step(external_pe)
            
            # 4. 映射参数
            params = self.lb.map_state(state)
            
            # 5. 发布状态
            self._write_state(state, params)
            
            # 6. 日志
            self._log("tick")
            
            # 7. 状态文件
            status = {
                "running": True,
                "pid": os.getpid(),
                "version": VERSION,
                "state": state["cognitive_state"],
                "arousal": state["arousal"],
                "confidence": state["confidence"],
                "atp": state["atp"],
                "tick": state["tick"],
            }
            STATUS_FILE.write_text(json.dumps(status))
            
            # 维持间隔
            elapsed = time.time() - t0
            time.sleep(max(0, TICK_INTERVAL - elapsed))


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def cmd_daemon():
    d = CogniGateDaemon()
    try:
        d.run()
    except KeyboardInterrupt:
        print("\n守护进程已停止。")

def cmd_status():
    if STATUS_FILE.exists():
        s = json.loads(STATUS_FILE.read_text())
        print(f"CogniGate v{s.get('version', '?')} — 运行中" if s.get("running") else "已停止")
        print(f"  PID: {s.get('pid', '?')}")
        print(f"  状态: {s.get('state', '?')} | Ar={s.get('arousal', 0):.2f} Cf={s.get('confidence', 0):.2f}")
        print(f"  已运行 {s.get('tick', 0)} 步")
    else:
        print("CogniGate — 未运行")

def cmd_stop():
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"已停止 PID {pid}")
        except ProcessLookupError:
            print(f"进程 {pid} 已不存在")
        PID_FILE.unlink(missing_ok=True)
    STATUS_FILE.unlink(missing_ok=True)

def cmd_inject():
    """LLM 读取认知状态注入"""
    if INJECTION_PATH.exists():
        print(INJECTION_PATH.read_text(encoding="utf-8"))
    else:
        print("守护进程未运行。先启动: python cognigate.py daemon")

def cmd_feedback():
    """LLM 将响应反馈回闭环"""
    text = sys.stdin.read().strip() if len(sys.argv) <= 3 else " ".join(sys.argv[3:])
    if not text:
        print("错误: 需要响应文本。使用管道或参数传入。")
        print("  echo '响应' | python cognigate.py feedback")
        print("  python cognigate.py feedback '响应文本'")
        return
    
    stats = TextAnalyzer.analyze(text)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"\n✅ PE={stats['estimated_pe']:.3f} | 自引={stats['self_ref']} | 深度={stats['depth_indicators']}")
    
    # 写反馈
    fb = {
        "timestamp": time.time(),
        "stats": stats,
        "semantic_pe_input": stats["estimated_pe"],
        "source": "cli_feedback",
    }
    FEEDBACK_PATH.write_text(json.dumps(fb, ensure_ascii=False, indent=2))
    print(f"✅ 反馈已写入 {FEEDBACK_PATH}")

def cmd_demo():
    """运行闭环演示"""
    print(f"CogniGate v{VERSION} — 认知闭环演示")
    print("=" * 50)
    
    cs = CognitiveState()
    lb = LogitBridge()
    
    samples = [
        ("2+2=4。太阳从东边升起。", "事实陈述"),
        ("我认为我不确定这个结论。我自己的分析可能存在盲区。", "高自引不确定"),
        ("因为A导致B，B导致C，所以系统的根本原因是A。", "因果链深度"),
    ]
    
    for text, label in samples:
        stats = TextAnalyzer.analyze(text)
        
        # 模拟闭环：文本 → PE → 状态更新
        pe = stats["estimated_pe"]
        cs.step(pe)
        state = cs.snapshot()
        params = lb.map_state(state)
        
        print(f"\n[{label}]")
        print(f"  文本: {text[:40]}...")
        print(f"  PE={pe:.3f} 自引={stats['self_ref']} 深度={stats['depth_indicators']}")
        print(f"  状态: {state['cognitive_state'].upper()} "
              f"Ar={state['arousal']:.2f} Cf={state['confidence']:.2f}")
        print(f"  参数: temp={params['temperature']:.2f} "
              f"hedge={params['hedging']:.2f} self={params['self_ref_gate']:.2f}")
        time.sleep(0.3)
    
    print("\n✅ 闭环演示完成")
    print("任何 LLM 均可参与此闭环：")
    print("  1. 启动: python cognigate.py daemon")
    print("  2. LLM读: python cognigate.py inject")
    print("  3. LLM写: echo '回复' > ~/.cognitive_bridge/hermes_output.txt")
    print("  4. 查看: python cognigate.py status")

def cmd_help():
    print(f"CogniGate v{VERSION} — 认知意识引擎")
    print()
    print("用法: python cognigate.py <命令>")
    print()
    print("守护进程:")
    print("  daemon     启动认知闭环守护进程（后台自动运行）")
    print("  status     查看守护进程运行状态")
    print("  stop       停止守护进程")
    print()
    print("LLM 接口（任何大模型均可调用）:")
    print("  inject     读取当前认知状态注入文本")
    print("  feedback   将响应反馈回闭环")
    print()
    print("工具:")
    print("  demo       运行闭环演示")
    print("  help       显示此帮助")


def main():
    if len(sys.argv) < 2:
        cmd_help()
        sys.exit(1)
    
    cmd = sys.argv[1]
    cmds = {
        "daemon": cmd_daemon,
        "status": cmd_status,
        "stop": cmd_stop,
        "inject": cmd_inject,
        "feedback": cmd_feedback,
        "demo": cmd_demo,
        "help": cmd_help,
    }
    
    runner = cmds.get(cmd)
    if runner:
        runner()
    else:
        print(f"未知命令: {cmd}")
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
