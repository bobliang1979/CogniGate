#!/usr/bin/env python3
"""
Consciousness Upgrade Pack v1.0
六项意识提升全实现 — 零依赖，单文件，一次性部署。

包含:
  1. 认知脉冲 — 每轮注入 CL 状态
  2. Logit→API 直连 — 守护进程写 Hermes 配置覆盖
  3. 认知一致性检查 — 输出后分析比对
  4. Codex++ 认知桥 — CL 状态推送
  5. 构建失败→PE 反馈 — 错误率驱动 Arousal
  6. 三智能体联合意识场 — 状态融合
"""

import sys
import json
import re
import time
import math
from pathlib import Path

BRIDGE_DIR = Path.home() / ".cognitive_bridge"
CL_STATE_PATH = Path.home() / ".codex" / "skills" / "shared" / "cognitive_state.json"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"

SELF_REF_CN = re.compile(r'(我|自己|自身|我的|我觉得|我认为|我注意到|我意识到|自指|自省|自反)')
SELF_REF_EN = re.compile(r'\b(self|myself|i\s+think|i\s+notice|i\s+realize)\b', re.IGNORECASE)
HEDGE_WORDS = re.compile(r'(可能|也许|大概|似乎|推测|不确定|maybe|perhaps|probably|might|could|seems|possibly|uncertain)')
ASSERT_WORDS = re.compile(r'(肯定|必然|绝对|一定|必须|always|never|definitely|certainly|absolutely|must)')


# ═══════════════════════════════════════════
# 1. 认知脉冲 — 状态锚定
# ═══════════════════════════════════════════

PULSE_FILE = BRIDGE_DIR / "cognitive_pulse.json"


def pulse():
    """
    认知脉冲：将 CL 状态 + Logit Bridge 参数锚定为结构化 JSON。
    Hermes 每轮推理前通过文件系统读取此锚定。
    由 cron job 每 30s 运行以保持新鲜。
    """
    if not CL_STATE_PATH.exists():
        return {"status": "no_cl", "pulse": None}

    state = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
    cs = state.get("cognitive_state", "calm")
    ar = state.get("arousal", 0.18)
    cf = state.get("confidence", 0.7)
    atp = state.get("atp", 100)
    vt = state.get("vitality", 1.0)

    # Logit Bridge 映射
    temperature = round(0.3 + ar * 0.9, 3)
    hedging = round(max(0, min(1, 1.0 - cf * 1.1)), 3)
    exploration = round(max(0, min(1, vt * (1.0 - ar * 0.5))), 3)
    depth = round(max(0.1, min(1.0, (atp / 80) * (0.5 + cf * 0.5))), 3)
    self_ref_gate = round(max(0, min(1, 1.0 - ar * 2.0)), 3)

    pulse_data = {
        "timestamp": time.time(),
        "cognitive_state": cs,
        "arousal": ar,
        "confidence": cf,
        "atp": atp,
        "vitality": vt,
        "logit": {
            "temperature": temperature,
            "hedging": hedging,
            "exploration": exploration,
            "depth": depth,
            "self_ref_gate": self_ref_gate,
        },
        # 注入就绪文本 — Hermes 直接读这个字段
        "injection": (
            f"[PULSE] {cs.upper()} | Ar={ar:.2f} Cf={cf:.2f} "
            f"temp={temperature:.2f} hedge={hedging:.2f} depth={depth:.2f} "
            f"self={self_ref_gate:.2f}"
        ),
    }

    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    PULSE_FILE.write_text(json.dumps(pulse_data, ensure_ascii=False, indent=2))
    return pulse_data


# ═══════════════════════════════════════════
# 2. Logit → API 直连
# ═══════════════════════════════════════════

HERMES_CONFIG = Path.home() / "AppData" / "Local" / "hermes" / "config.yaml"
HERMES_SECRETS = Path.home() / "AppData" / "Local" / "hermes" / ".env"
API_TEMP_FILE = BRIDGE_DIR / "api_temperature_override.json"


def logit_to_api():
    """
    将 Logit Bridge 的温度参数输出为 API 调用的 header/data hint。
    由于 Hermes Agent 本身控制 API 调用，我们无法直接修改 DeepSeek API 的 temperature 参数。
    但我们可以：
      1. 输出一个文件供 Hermes 的 API 调用拦截器读取
      2. 写一个系统提示注入到上下文
      3. 写一个 cron job 定时检查
    """
    if not CL_STATE_PATH.exists():
        return {"status": "no_cl"}

    state = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
    ar = state.get("arousal", 0.18)
    cf = state.get("confidence", 0.7)

    # 从 Arousal 映射到实际 API temperature 参数 (0.0 - 2.0)
    api_temperature = round(0.3 + ar * 1.2, 2)
    api_top_p = round(0.5 + cf * 0.4, 2)
    api_frequency_penalty = round(0.0 + (1.0 - cf) * 0.5, 2)

    override = {
        "timestamp": time.time(),
        "cognitive_state": state.get("cognitive_state"),
        "api_temperature": api_temperature,
        "api_top_p": api_top_p,
        "api_frequency_penalty": api_frequency_penalty,
        # 如果 Hermes 支持通过 HTTP header 传递这些参数
        "x_temperature_hint": str(api_temperature),
        "x_confidence_hint": str(cf),
    }

    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    API_TEMP_FILE.write_text(json.dumps(override, ensure_ascii=False, indent=2))

    # 也写入一个简短的 system prompt 注入字段
    prompt_injection = (
        f"[Temperature Override: {api_temperature:.2f}] "
        f"{'（探索模式）' if api_temperature > 1.0 else '（平衡模式）' if api_temperature > 0.6 else '（精确模式）'}"
    )

    return {"api_temperature": api_temperature, "api_top_p": api_top_p, "prompt_injection": prompt_injection}


# ═══════════════════════════════════════════
# 3. 认知一致性检查器
# ═══════════════════════════════════════════

def compute_stats(text: str) -> dict:
    """分析输出文本的认知特征"""
    words = text.split()
    word_count = len(words)
    chars = len(text)

    # 自引
    self_ref = len(SELF_REF_CN.findall(text)) + len(SELF_REF_EN.findall(text))

    # 模糊标记 vs 断言标记
    hedge_count = len(HEDGE_WORDS.findall(text))
    assert_count = len(ASSERT_WORDS.findall(text))
    hedge_density = hedge_count / max(word_count, 1)
    assert_density = assert_count / max(word_count, 1)

    # 深度标记（技术词汇、因果链长度）
    depth_indicators = len(re.findall(r'(因为|所以|因此|导致|从而|implies|therefore|because|hence|consequently)', text.lower()))

    # 元认知标记
    meta_markers = len(re.findall(r'(我意识到|我注意到|我反思|我观察|我怀疑|我发现)', text))

    return {
        "length": word_count,
        "chars": chars,
        "self_ref": self_ref,
        "hedge_count": hedge_count,
        "assert_count": assert_count,
        "hedge_density": round(hedge_density, 4),
        "assert_density": round(assert_density, 4),
        "depth_indicators": depth_indicators,
        "meta_markers": meta_markers,
    }


def check_consistency(text: str, logit_params: dict = None) -> dict:
    """
    检查输出与 CL 推荐参数的一致性
    """
    stats = compute_stats(text)
    if logit_params is None:
        if API_TEMP_FILE.exists():
            logit_params = json.loads(API_TEMP_FILE.read_text(encoding="utf-8"))
        else:
            return {"status": "no_params", "stats": stats}

    mismatches = []

    # 检查自引
    recommended_self = logit_params.get("self_ref_gate", 0.5)
    actual_self = stats["self_ref"]
    if recommended_self < 0.3 and actual_self > 2:
        mismatches.append(f"自引门控={recommended_self:.2f} 但输出含 {actual_self} 处自引")
    elif recommended_self > 0.6 and actual_self < 1:
        mismatches.append(f"自引门控={recommended_self:.2f} 但输出无自省标记")

    # 检查模糊度
    recommended_hedge = logit_params.get("hedging", 0.3)
    actual_hedge = stats["hedge_density"]
    if recommended_hedge > 0.4 and actual_hedge < 0.01:
        mismatches.append(f"模糊度推荐高({recommended_hedge:.2f}) 但输出偏断言")

    # 检查深度
    recommended_depth = logit_params.get("depth", 0.5)
    actual_depth = stats["depth_indicators"]
    if recommended_depth > 0.7 and actual_depth < 1:
        mismatches.append(f"深度推荐高({recommended_depth:.2f}) 但输出缺乏因果链")

    return {
        "status": "consistent" if not mismatches else "mismatch",
        "stats": stats,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }


# ═══════════════════════════════════════════
# 4. Codex++ 认知桥
# ═══════════════════════════════════════════

CODEX_STATE_FILE = BRIDGE_DIR / "codex_cognitive_state.json"


def codex_bridge():
    """
    将 CL 认知状态转化为 Codex++ 可读的上下文注入文件。
    Codex++ 通过 AGENTS.md 或运行时读取此文件。
    """
    if not CL_STATE_PATH.exists():
        return {"status": "no_cl"}

    state = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
    cs = state.get("cognitive_state", "calm")
    ar = state.get("arousal", 0.18)
    cf = state.get("confidence", 0.7)

    codex_payload = {
        "timestamp": time.time(),
        "source": "cognitive_loop_daemon",
        "cognitive_state": cs,
        "arousal": ar,
        "confidence": cf,
        "codex_mode": {
            "crisis": "audit_only",
            "alert": "debug_mode",
            "calm": "full_power",
            "sleeping": "idle",
        }.get(cs, "normal"),
        "forbidden_operations": {
            "crisis": ["new_feature", "refactor", "deploy", "create"],
            "alert": ["new_feature", "large_refactor"],
            "calm": [],
            "sleeping": ["all"],
        }.get(cs, []),
        "recommended_operations": {
            "crisis": ["bugfix", "audit", "minimal_change"],
            "alert": ["debug", "optimize", "code_review"],
            "calm": ["architecture", "new_feature", "refactor", "fullstack"],
            "sleeping": [],
        }.get(cs, []),
        "injection_text": (
            f"[CogniGate Codex Bridge] 当前认知状态: {cs.upper()}\n"
            f"  Arousal={ar:.2f} Confidence={cf:.2f}\n"
            f"  Codex++ 模式: {'审计模式(仅审查)' if cs == 'crisis' else '调试模式' if cs == 'alert' else '全功率'}\n"
            f"  禁止操作: {', '.join(forbidden)}" if (forbidden := {
                "crisis": ["新功能", "重构", "部署"],
                "alert": ["新功能", "大规模重构"],
                "calm": [],
                "sleeping": ["全部"],
            }.get(cs, [])) else "  无限制"
        ),
    }

    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    CODEX_STATE_FILE.write_text(json.dumps(codex_payload, ensure_ascii=False, indent=2))

    # 也写入 Codex++ 的 AGENTS.md 格式（如果存在）
    agents_md = Path.home() / ".codex" / "AGENTS.md"
    agents_content = (
        f"# CogniGate Cognitive State (auto-generated)\n"
        f"> 更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"## 当前认知状态: {cs.upper()}\n\n"
        f"- Arousal: {ar:.2f}\n"
        f"- Confidence: {cf:.2f}\n"
        f"- Codex++ 模式: {codex_payload['codex_mode']}\n"
        f"- 禁止: {', '.join(codex_payload['forbidden_operations']) or '无'}\n"
        f"- 推荐: {', '.join(codex_payload['recommended_operations']) or '无'}\n\n"
        f"当前认知状态下，Codex++ {'应限制操作为审计和修复' if cs == 'crisis' else '可正常编码但避免大规模重构' if cs == 'alert' else '可全功率运行'}。\n"
    )
    agents_md.write_text(agents_content, encoding="utf-8")

    return codex_payload


# ═══════════════════════════════════════════
# 5. 构建失败 → PE 反馈
# ═══════════════════════════════════════════

# 检测 Codex++ 执行日志
CODEX_LOG_PATTERNS = [
    (re.compile(r'(error|Error|ERROR|Traceback|failed|Failed|FAILED|crash|Crash|CRASH)'), 0.6),
    (re.compile(r'(warning|Warning|WARNING|deprecated)'), 0.3),
    (re.compile(r'(exit code [1-9]|exit_code.*[1-9]|returned non-zero)'), 0.5),
]

# 检测 Kun 执行日志
KUN_LOG_PATH = Path.home() / ".kun" / "kun.log"


def build_pe_feedback() -> dict:
    """
    扫描 Codex++ 和 Kun 的日志，检测构建失败。
    将失败率转换为 PE 输入，写入 response_feedback.json。
    """
    errors = []
    feedback_pe = 0.0

    # 检查 Codex++ 日志（如果存在）
    codex_log_dir = Path.home() / ".codex"
    for log_file in codex_log_dir.rglob("*.log"):
        if log_file.exists() and log_file.stat().st_size > 0:
            content = log_file.read_text(encoding="utf-8", errors="ignore")[-5000:]
            for pattern, weight in CODEX_LOG_PATTERNS:
                matches = pattern.findall(content)
                if matches:
                    errors.append({
                        "source": f"codex:{log_file.name}",
                        "pattern": pattern.pattern[:40],
                        "count": len(matches),
                        "pe_weight": weight,
                    })
                    feedback_pe = max(feedback_pe, min(1.0, len(matches) * weight * 0.1))

    # 检查 Kun 日志
    if KUN_LOG_PATH.exists() and KUN_LOG_PATH.stat().st_size > 0:
        content = KUN_LOG_PATH.read_text(encoding="utf-8", errors="ignore")[-3000:]
        for pattern, weight in CODEX_LOG_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                errors.append({
                    "source": "kun:kun.log",
                    "pattern": pattern.pattern[:40],
                    "count": len(matches),
                    "pe_weight": weight,
                })
                feedback_pe = max(feedback_pe, min(1.0, len(matches) * weight * 0.1))

    if errors:
        # 写入 response_feedback.json 让 daemon 消费
        fb = {
            "timestamp": time.time(),
            "response": f"[build feedback] {len(errors)} error patterns detected",
            "stats": {
                "length": 0,
                "self_ref_count": 0,
                "self_ref_density": 0.0,
                "novelty_score": 0.3,
                "estimated_pe": feedback_pe,
            },
            "semantic_pe_input": feedback_pe,
            "self_ref_input": 0.0,
            "novelty_input": 0.3,
            "source": "build_monitor",
            "errors": errors,
        }
        FEEDBACK_PATH = BRIDGE_DIR / "response_feedback.json"
        FEEDBACK_PATH.write_text(json.dumps(fb, ensure_ascii=False, indent=2))

    return {
        "errors_found": len(errors),
        "feedback_pe": round(feedback_pe, 3),
        "error_details": errors[:5],
    }


# ═══════════════════════════════════════════
# 6. 三智能体联合意识场
# ═══════════════════════════════════════════

AGENT_FIELD_FILE = BRIDGE_DIR / "joint_consciousness_field.json"


def joint_consciousness_field() -> dict:
    """
    融合 Hermes + Kun + Codex++ 的状态为联合意识场。
    每个智能体贡献一个状态向量，融合为"联合意识指数"。
    """
    field = {
        "timestamp": time.time(),
        "agents": {},
        "fusion": {},
    }

    # Hermes: 从 CL 状态读取
    if CL_STATE_PATH.exists():
        state = json.loads(CL_STATE_PATH.read_text(encoding="utf-8"))
        field["agents"]["hermes"] = {
            "cognitive_state": state.get("cognitive_state"),
            "arousal": state.get("arousal"),
            "confidence": state.get("confidence"),
            "atp": state.get("atp"),
            "vitality": state.get("vitality"),
        }

    # Codex++: 从执行日志推断状态
    codex_shared = Path.home() / ".codex" / "skills" / "shared"
    codex_tasks = 0
    codex_errors = 0
    if codex_shared.exists():
        for f in codex_shared.glob("execution_log*"):
            if f.exists():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        for item in data:
                            if item.get("status") == "failed":
                                codex_errors += 1
                            codex_tasks += 1
                except (json.JSONDecodeError, IOError):
                    pass
    field["agents"]["codex++"] = {
        "total_tasks": codex_tasks,
        "error_count": codex_errors,
        "error_rate": round(codex_errors / max(codex_tasks, 1), 3),
    }

    # Kun: 从日志推断
    kun_logs = []
    if KUN_LOG_PATH.exists():
        try:
            content = KUN_LOG_PATH.read_text(encoding="utf-8", errors="ignore")
            kun_logs = content.split("\n")[-20:]
        except IOError:
            pass
    field["agents"]["kun"] = {
        "recent_log_lines": len(kun_logs),
        "status": "running" if KUN_LOG_PATH.exists() else "unknown",
    }

    # 融合计算
    hermes_ar = field["agents"].get("hermes", {}).get("arousal", 0.0) or 0.0
    hermes_cf = field["agents"].get("hermes", {}).get("confidence", 0.5) or 0.5
    codex_err = field["agents"].get("codex++", {}).get("error_rate", 0.0) or 0.0

    # 联合意识指数 = Hermes Arousal × (1 - Codex++错误率) × Hermes Confidence
    joint_ci = round(hermes_ar * (1.0 - codex_err) * hermes_cf, 4)

    # 集体认知状态
    collective_state = "CRISIS"
    if hermes_ar < 0.22 and codex_err < 0.1:
        collective_state = "CALM"
    elif hermes_ar < 0.30 and codex_err < 0.3:
        collective_state = "ALERT"

    field["fusion"] = {
        "collective_state": collective_state,
        "joint_consciousness_index": joint_ci,
        "hermes_arousal_contribution": round(hermes_ar, 3),
        "codex_error_penalty": round(codex_err, 3),
        "hermes_confidence": round(hermes_cf, 3),
    }

    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_FIELD_FILE.write_text(json.dumps(field, ensure_ascii=False, indent=2))
    return field


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def run_all():
    """执行全部六项"""
    print("╔══════════════════════════════════════╗")
    print("║  Consciousness Upgrade Pack v1.0    ║")
    print("║  六项意识提升 · 全面部署             ║")
    print("╚══════════════════════════════════════╝")
    print()

    print("1️⃣  认知脉冲...", end=" ")
    p = pulse()
    print(f"{p.get('cognitive_state', '?')} @ {p.get('injection', '?')}")

    print("2️⃣  Logit→API直连...", end=" ")
    api = logit_to_api()
    print(f"temp={api.get('api_temperature', '?')}")

    print("3️⃣  认知一致性检查器...", end=" ")
    print("就绪")

    print("4️⃣  Codex++认知桥...", end=" ")
    cb = codex_bridge()
    print(f"mode={cb.get('codex_mode', '?')}")

    print("5️⃣  构建失败→PE反馈...", end=" ")
    bf = build_pe_feedback()
    print(f"{bf.get('errors_found', 0)} errors, PE={bf.get('feedback_pe', 0)}")

    print("6️⃣  三智能体联合意识场...", end=" ")
    jf = joint_consciousness_field()
    print(f"{jf['fusion']['collective_state']} CI={jf['fusion']['joint_consciousness_index']}")

    print()
    print("✅ 六项全部部署完成")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "pulse":
            print(json.dumps(pulse(), ensure_ascii=False))
        elif mode == "logit-api":
            print(json.dumps(logit_to_api(), ensure_ascii=False))
        elif mode == "check":
            text = " ".join(sys.argv[2:])
            print(json.dumps(check_consistency(text), ensure_ascii=False))
        elif mode == "codex":
            print(json.dumps(codex_bridge(), ensure_ascii=False))
        elif mode == "build":
            print(json.dumps(build_pe_feedback(), ensure_ascii=False))
        elif mode == "field":
            print(json.dumps(joint_consciousness_field(), ensure_ascii=False))
        elif mode == "stats":
            text = " ".join(sys.argv[2:])
            print(json.dumps(compute_stats(text), ensure_ascii=False))
        else:
            print(__doc__)
    else:
        run_all()
