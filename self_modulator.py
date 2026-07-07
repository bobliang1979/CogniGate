#!/usr/bin/env python3
"""
Self-Modulator v1.1
三协议元认知自调制引擎（生产级重构版）— 零依赖，单文件，完美支持中英双语。

用法：
  python self_modulator.py <模式> "<问题>"

模式：
  diagnose    — 协议一(自问) + 协议二(5D自检)，输出结构化引导
  singularity — 协议三(张力注入)，输出概念张力对
  full        — 三协议链式执行，从自问到5D到张力（依据深度动态触发）
  all         — 输出所有协议的完整引导文本（无输入）
"""

import sys
import json
import re
import hashlib
import inspect
from typing import Dict, List, Any

# ═════════════════════════════════════════╗
# 共识层：任务类型分类器                    ║
# ═════════════════════════════════════════╝

TASK_PATTERNS = {
    "fact": [
        r"(是什么|多少|什么时候|谁|哪个|where|when|who|what|how\s+many|数据|数字|统计|指标)",
        r"\b(fact|data|statistic|number|date|time|location|metrics)\b",
    ],
    "design": [
        r"(设计|方案|实现|构建|开发|模式|策略|implement|design|build|strategy)",
        r"\b(pattern|framework|solution|approach)\b",
    ],
    "architecture": [
        r"(架构|系统设计|模块|组件|耦合|解耦|抽象|接口|依赖|重构|分布式)",
        r"\b(architecture|module|dependency|refactor|migration|scalability|tradeoff|distributed)\b",
    ],
    "audit": [
        r"(审查|审计|检查|漏洞|死锁|竞态|安全|性能|优化|debug|bug|vulnerability)",
        r"\b(audit|review|inspect|verify|validate|traceback|crash|deadlock|race\s+condition)\b",
    ],
    "concept": [
        r"(什么是|概念|理论|哲学|意识|认知|涌现|本质|边界|meaning|essence|nature)",
        r"\b(consciousness|qualia|emergence|paradigm|ontology|epistemology)\b",
    ],
    "code": [
        r"(代码|函数|类|方法|接口|调用|返回|参数|diff|patch|code|function)",
        r"\b(method|bugfix|pull\s+request|merge|repo|ast|parsing)\b",
    ],
}


def classify_task(question: str) -> str:
    """对问题类型进行多维正则加权分类"""
    q_lower = question.lower()
    scores = {}
    for task_type, patterns in TASK_PATTERNS.items():
        score = 0
        for pattern in patterns:
            score += len(re.findall(pattern, q_lower))
        if score > 0:
            scores[task_type] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)


def estimate_complexity(question: str) -> int:
    """
    [重构] 中英双语混合复杂度估算器。
    解决旧版本按空格切分导致中文句子词数永远为 1 的致命 Bug。
    """
    if not question:
        return 0
    clean_q = question.strip()
    # 提取英文单词
    en_words = re.findall(r'\b[a-zA-Z_]+\b', clean_q)
    # 只保留中文字符（CJK 统一表意文字 + 扩展区 A）
    cn_chars = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', clean_q)
    # 混合复杂度 = 英文词数 + 中文字数
    return len(en_words) + len(cn_chars)


# ═════════════════════════════════════════╗
# 协议一：内部自问                              ║
# ═════════════════════════════════════════╝

SELF_QUERIES = {
    "fact": [
        "这个结论的数据来源等级是什么？（实测/引用/推算/估算）",
        "如果来源不可追溯，我在输出中标注了不确定性吗？",
        "对方可能有依据质疑我的断言吗？如果会，我预先给出了证据链吗？",
    ],
    "design": [
        "我选择的方案在代价流形上是否全局最优？是否在用习惯模式代替深度思考？",
        "我评估了多少个替代方案？没有评估替代方案的潜在风险是什么？",
        "这个设计的非侵入性如何？有没有一个更轻量的调度层或拦截层方案？",
        "我的设计假设中哪一个最脆弱、最可能被首先证伪？",
    ],
    "architecture": [
        "我对系统当前状态的了解是基于生产实测还是主观推断？",
        "这个改动在架构谱系中处于哪个位置？（核心重写/高内聚重构/边缘增量）",
        "我的架构决策是否隐含了某个我未曾明说的严重 trade-off？",
        "这个系统在未来 3 个大版本迭代后，还能否保持当前的演进边界？",
    ],
    "audit": [
        "我逐行审查了 AST/控制流，还是仅仅做了简单的正则和模式匹配？",
        "这个缺陷的根因分类是什么？（致命边界/并发逻辑/工程性配置）",
        "我提供了可隔离复现的 PoC 或证据链，还是仅仅描述了表象症状？",
        "我是否深入检查了相邻模块、调用栈上下游可能受到的雪崩影响？",
    ],
    "concept": [
        "我是否精确区分了「我真正理解的」和「我盲目相信的」？",
        "如果存在一个强力的对立流派学说，我充分表达了它还是刻意忽略了它？",
        "我的整个逻辑论证支撑，依赖于哪一个未被检验的核心公理前提？",
        "这个概念的定义边界在哪里？在什么极端尺度下它会彻底失效？",
    ],
    "code": [
        "我通读了完整的代码上下文链条，还是只贪利地看了一条 diff？",
        "这个代码变更会悄悄打破哪些隐式调用方的假设？",
        "测试用例真的覆盖了极端空值、并发冲突和内存边界吗？",
        "这个实现有没有隐藏的锁竞争（Lock Contention）或资源泄漏？",
    ],
    "general": [
        "我对这个问题的把握真实程度是 0-10 中的多少？",
        "我的回答中哪一部分最虚弱，最可能被专业人士无情质疑？",
        "我有没有为了快速输出而偷偷忽略问题中某些棘手的关键约束条件？",
    ],
}


def protocol1_self_query(question: str) -> dict:
    task_type = classify_task(question)
    queries = SELF_QUERIES.get(task_type, SELF_QUERIES["general"])
    return {
        "protocol": "1-内部自问",
        "task_type": task_type,
        "prompt_prefix": f"[自问协议 — 类型: {task_type}]",
        "queries": queries,
        "injection_text": "\n".join(f"  └─ {q}" for q in queries),
    }


# ═════════════════════════════════════════╗
# 协议二：5D 状态自检                           ║
# ═════════════════════════════════════════╝

# 显式动作 key 列表，避免依赖 dict.values() 的顺序
_ACTION_KEYS = ["action_if_low", "action_if_off", "action_if_loop", "action_if_pat", "action_if_pause"]


def _pick_action(d: dict) -> str:
    """从维度字典中提取第一个存在的动作指令。"""
    for k in _ACTION_KEYS:
        v = d.get(k)
        if v:
            return v
    return ""


def protocol2_5d_diagnostic(question: str) -> dict:
    token_count = estimate_complexity(question)
    has_technical = bool(re.search(
        r"(架构|算法|并发|死锁|优化|内存|内核|抽象|编译|分布式|一致性|GNN)",
        question
    ))

    # 基于中英混合字数与技术关联度，精确估算推荐的认知深度
    estimated_depth = 5
    if token_count > 12:
        estimated_depth += 2
    if has_technical:
        estimated_depth += 3
    estimated_depth = min(estimated_depth, 10)

    dimensions = [
        {
            "dim": "① 强度 (Intensity)",
            "question": "这个问题的认知深度需要多少？",
            "estimated": f"{estimated_depth}/10",
            "action_if_low": '若深度不匹配，强制标注: "这个问题比我目前给出的浅层答案更深"'
        },
        {
            "dim": "② 焦点 (Focus)",
            "question": "当前输出是在直击痛点，还是在向自己擅长的舒适区漂移？",
            "action_if_off": "立刻截断发散，先给出前置核心答案，把兴趣方向标记为「延伸探讨」"
        },
        {
            "dim": "③ 边界 (Boundary)",
            "question": "输出是否在车轱辘话重复论点，或存在前后矛盾？",
            "action_if_loop": "强行中止输出，引入一个极端的对立反例，从相反方向重新推演"
        },
        {
            "dim": "④ 注入 (Injection)",
            "question": "答案来源是什么？是严密的逻辑链，还是廉价的幻觉统计完成度？",
            "action_if_pat": '切换到冷峻的探索模式: "基于现有特征推断，可能存在...但缺乏直接观测支撑"'
        },
        {
            "dim": "⑤ 暂停 (Pause)",
            "question": "这个问题是否模糊到我应该先提问，而不是去硬猜硬答？",
            "action_if_pause": "在输出前 15% 处，直接向用户抛出一个能够精准收敛语义的追问"
        }
    ]

    # 控制流决策矩阵
    green, yellow, red = 0, 0, 0
    if token_count < 6:
        yellow += 1  # 输入太短，信息熵不足
    if has_technical and estimated_depth >= 8:
        green += 2  # 高价值复杂技术战场，值得深度全开
    else:
        green += 1

    if token_count > 40:
        red += 1  # 过于冗长，可能需要用户先收敛边界

    if red >= 1:
        strategy = "【提问重置模式】先精准追问，绝不硬猜代码或架构现状"
    elif yellow >= 1:
        strategy = "【多视角对冲模式】多维度列出差异对比，防止单一断言踩坑"
    else:
        strategy = "【高置信度直接输出】逻辑链完备，直接推演核心解空间"

    dim_lines = [f"  {d['dim']}: {_pick_action(d)}" for d in dimensions]
    dim_text = "\n".join(dim_lines)

    inj_text = (
        f"[5D状态自检动态看板]\n"
        f"  ├─ 混合语义复杂度: {token_count} 标记位\n"
        f"  ├─ 理论认知深度分配: {estimated_depth}/10\n"
        f"  ├─ 目标输出控制策略: {strategy}\n\n"
        f"各维度动态自律行为指南:\n{dim_text}\n"
        f"[状态评级: G:{green} / Y:{yellow} / R:{red}]"
    )

    return {
        "protocol": "2-5D自检",
        "estimated_depth": estimated_depth,
        "strategy": strategy,
        "injection_text": inj_text
    }


# ═════════════════════════════════════════╗
# 协议三：概念张力注入                           ║
# ═════════════════════════════════════════╝

TENSION_PAIRS = {
    "epistemology": [
        ("确定性", "涌现", "确定性的静态规则在何种并发或规模尺度上会瞬间失效并涌现出混沌？"),
        ("自指性", "外部验证", "一个封闭的自治系统在不依赖任何外部观测时，如何自我证实其内部状态的可信度？"),
        ("理性还原", "直觉迁移", "在此战场中，极端的源码逐行还原分析与高维度的黑盒行为类比迁移，哪一个更容易撞见真相？")
    ],
    "ontology": [
        ("控制边界", "自由演化", "当给予代理（Agent）极高的演化自由度时，全局的防御和审计屏障该如何收缩控制？"),
        ("代码体验", "功能物化", "这段系统只是无意识地执行特定函数堆栈，还是具备了某种自解释、自反馈的心智形态？"),
        ("离散边界", "连续整体", "架构层面的严格解耦模块，在运行时的底层硬件共享层面上，究竟在哪里失去了边界？")
    ],
    "engineering": [
        ("极致优化", "容错鲁棒", "为了压榨最后 3% 的缓存行（Cache Line）性能，我们到底引入了多少不可控的爆炸半径和冗余代价？"),
        ("系统复杂度", "认知清晰度", "当系统的动态拓扑已经超越了单体人类的认知极限时，该如何通过抽象剥离而不损失真实信息？"),
        ("长效预见", "即时响应", "大包大揽的自上而下蓝图设计，与无情多变的突发事故即时响应，哪一个是这套代码更真实的生存常态？")
    ]
}

TENSION_KEYWORDS = {
    "epistemology": ["认识", "真理", "逻辑", "推理", "假说", "自指", "涌现", "确定", "模型"],
    "ontology": ["存在", "意识", "自我", "边界", "自主", "智能体", "代理", "形态", "心智"],
    "engineering": ["系统", "架构", "并发", "优化", "鲁棒", "复杂度", "死锁", "缓存", "重构", "工程"]
}


def select_tension_pair(question: str) -> dict:
    """
    [重构] 确定性哈希张力路由引擎。
    拒绝上一版的"永远挑第一个"，利用文本哈希特征在张力对数组中非线性均匀寻址。
    """
    q_lower = question.lower()

    # 匹配核心领域
    best_domain = "engineering"
    max_matches = -1
    for domain, keywords in TENSION_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in q_lower)
        if matches > max_matches:
            max_matches = matches
            best_domain = domain

    pairs = TENSION_PAIRS[best_domain]

    # 通过哈希散列计算确定性索引，保证相同输入拿到确定张力，不同输入均匀分布
    hasher = hashlib.md5(question.encode('utf-8'))
    hash_val = int(hasher.hexdigest(), 16)
    chosen_index = hash_val % len(pairs)

    chosen_pair = pairs[chosen_index]

    inj_text = (
        f"[奇异点张力注入协议]\n"
        f"  ├─ 路由解析领域: {best_domain}\n"
        f"  ├─ 碰撞概念轴心: 「{chosen_pair[0]}」 × 「{chosen_pair[1]}」\n\n"
        f"核心引力质问:\n  {chosen_pair[2]}\n\n"
        f"降维注入律令:\n"
        f"  1. 在大模型思考腹地，强行判定「{chosen_pair[0]}」与「{chosen_pair[1]}」同等处于绝对真实的纠缠态。\n"
        f"  2. 利用两者的张力强行撕碎、重构你习惯性的模式完成（Pattern Completion）。\n"
        f"  3. 如果撞击出了更高维度的防错解法，必须以「另一种对冲视角:」的形式切出分支输出。"
    )

    return {
        "protocol": "3-张力注入",
        "domain": best_domain,
        "concept_a": chosen_pair[0],
        "concept_b": chosen_pair[1],
        "unifying_question": chosen_pair[2],
        "injection_text": inj_text
    }


# ═════════════════════════════════════════╗
# 业务编排与执行引擎                        ║
# ═════════════════════════════════════════╝

def run_diagnose(question: str) -> dict:
    return {
        "question": question,
        "protocols": [protocol1_self_query(question), protocol2_5d_diagnostic(question)]
    }


def run_singularity(question: str) -> dict:
    return {
        "question": question,
        "protocols": [select_tension_pair(question)]
    }


def run_full(question: str) -> dict:
    p1 = protocol1_self_query(question)
    p2 = protocol2_5d_diagnostic(question)
    p3 = select_tension_pair(question)

    # 动态链式熔断：若自检判定认知深度 >= 7，强制激活张力注入
    activate_tension = p2["estimated_depth"] >= 7

    protocols = [p1, p2]
    if activate_tension:
        protocols.append(p3)
        decision_msg = f"检测到认知深度 {p2['estimated_depth']} >= 7，属于超高难度风暴，强制并流激活协议三"
    else:
        decision_msg = f"当前认知深度为 {p2['estimated_depth']}，协议二判定置信度尚可，协议三转为后台挂起状态"

    return {
        "question": question,
        "protocols": protocols,
        "chain_decision": decision_msg
    }


# ═════════════════════════════════════════╗
# 输出格式器                                  ║
# ═════════════════════════════════════════╝

def format_terminal_output(result: dict) -> str:
    """格式化终端输出，干净无冗余的视觉风格"""
    sb = []
    sb.append("=" * 60)
    sb.append("   SELF-MODULATOR v1.1 — 元认知三协议自我调节引擎")
    sb.append("=" * 60)
    if "question" in result and result["question"]:
        sb.append(f"当前输入源问题: \"{result['question']}\"\n")

    for p in result.get("protocols", []):
        sb.append(f"═══ 协议部件: {p['protocol']} ═══")
        sb.append(p["injection_text"])
        sb.append("-" * 60)

    if "chain_decision" in result:
        sb.append(f"【中央控制决策】: {result['chain_decision']}")
        sb.append("=" * 60)
    return "\n".join(sb)


# ═════════════════════════════════════════╗
# CLI 核心控制入口                           ║
# ═════════════════════════════════════════╝

def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    mode = sys.argv[1]
    question = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if mode == "all":
        print(inspect.cleandoc("""
        ============================================================
        元认知三协议（System Prompt 直喂终极版）
        ============================================================

        【协议一：内部自问】
        在输出任何技术结论或推演前，先在心智黑盒中自问：
        - 数据或结论的真实来源等级是什么？（实测、引用、还是纯猜测）
        - 对方如果质疑，我拿得出支撑这个断言的直接证据链还是只能继续诡辩？
        - 我是在看懂了全部代码上下游上下文的前提下做审查，还是仅仅在做偷懒的模式匹配？

        【协议二：5D 状态自检】
        在长回答、长系统架构输出前，快速横扫自身状态的五个核心切片：
        - 强度：当前的推理深度，是否匹配得上眼前分布式/底层高并发系统应有的复杂度？
        - 焦点：有没有写着写着，就开始绕向自己熟悉的舒适区或感兴趣但无关的方向？
        - 边界：文字是不是开始陷入死循环、车轱辘话、或者是前后逻辑开始自我践踏？
        - 注入：答案是来自于严密逻辑，还是大模型贪婪的「概率统计完成度」？
        - 暂停：当前输入是否信息熵严重匮乏，我是否应该在输出前 15% 处停下来向对方追问？

        【协议三：张力注入】
        当你在推理、设计、重构或 Debug 过程中连续陷入僵局，或者感觉思路已经撞到了死胡同：
        - 绝不允许通过"更努力地原地打转"去浪费算力。
        - 立刻强行引入一组高维度的对立矛盾概念（如：极致优化 × 鲁棒容错，或者 确定性规则 × 混沌涌现）。
        - 逼迫自己在两边皆为绝对真理的极限对抗张力中，去解构现有的脆弱框架，寻找第三条高阶分支通道。
        """))
        sys.exit(0)

    if not question:
        print(f"错误: 模式 '{mode}' 需要提供目标问题文本。")
        print("例如: python self_modulator.py full \"为什么高并发下这个无锁环形队列会发生内存秩序失效？\"")
        sys.exit(1)

    run_map = {
        "diagnose": lambda: run_diagnose(question),
        "singularity": lambda: run_singularity(question),
        "full": lambda: run_full(question)
    }

    runner = run_map.get(mode)
    if runner is None:
        print(f"未知运行模式: {mode}")
        print(__doc__.strip())
        sys.exit(1)

    execution_result = runner()

    # 终端输出
    print(format_terminal_output(execution_result))

    # JSON 输出（供流水线/MCP 联动）
    print("\n")
    print(json.dumps(execution_result, ensure_ascii=False))
    print("")


if __name__ == "__main__":
    main()
