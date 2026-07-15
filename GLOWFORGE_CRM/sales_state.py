"""Sales State Engine v2 — 销售阶段状态机 + 成交引擎

核心升级:
  v1: state → 分类输出
  v2: state + price_tier + deal_probability → 可执行的成交行为

不调用外部 AI API，纯规则引擎。
可直接被 analyze_customer_message() 调用，也可独立使用。

状态流转:
  NEW → NEEDS_ANALYSIS → BUDGET → OBJECTION → FINAL
  (任何阶段都可能回退到前序状态)
"""
import re

# ==================== 状态定义 ====================

STATES = {
    "NEW": {
        "label": "新客户",
        "description": "未报价客户，需要了解需求",
        "default_next_action": "ask",
    },
    "NEEDS_ANALYSIS": {
        "label": "需求分析",
        "description": "客户在询问价格或产品信息",
        "default_next_action": "present_options",
    },
    "BUDGET": {
        "label": "预算阶段",
        "description": "客户提到具体预算数字或价格期望",
        "default_next_action": "anchor_price",
    },
    "OBJECTION": {
        "label": "异议处理",
        "description": "客户在比价、质疑价格或质量",
        "default_next_action": "handle_objection",
    },
    "FINAL": {
        "label": "成交阶段",
        "description": "客户明确要下单或确认",
        "default_next_action": "close",
    },
}

# ==================== 成交概率基数（per state） ====================
# 根据销售经验预设的成交概率
_DEAL_PROBABILITY_BASE = {
    "NEW": 0.10,
    "NEEDS_ANALYSIS": 0.30,
    "BUDGET": 0.60,
    "OBJECTION": 0.40,
    "FINAL": 0.85,
}

# ==================== 价格档位定义 ====================

_TIER_CONFIG = {
    "LOW": {"range": "$120-200", "label": "入门档", "weight": 0},
    "MID": {"range": "$200-350", "label": "主流档", "weight": 1},
    "HIGH": {"range": "$350+", "label": "高端档", "weight": 2},
    "UNKNOWN": {"range": "待确认", "label": "未知", "weight": -1},
}

# 定性关键词 → 价格档位映射
_TIER_QUALITATIVE = {
    "LOW": ["cheap", "affordable", "low cost", "budget friendly", "economy",
            "inexpensive", "便宜的", "低端"],
    "MID": ["standard", "mid-range", "medium", "regular", "normal",
            "中等", "标准"],
    "HIGH": ["premium", "luxury", "high-end", "top quality", "best",
             "高端", "顶级", "豪华", "最好的"],
}

# 数字提取模式（用于更精确的档位判断）
_PRICE_RANGE_PATTERN = re.compile(
    r'\$\s*(\d+[\d,]*\.?\d*)'          # $100, $1,500
    r'|(\d+)\s*(?:usd|cny|eur|gbp)'    # 100 usd
    r'|usd\s*(\d+)'                     # usd 100
    r'|(?:around|about|roughly|approx|approximately)\s*\$?\s*(\d+)'
)

# 报价类型推荐规则
_QUOTE_TYPE_RULES = {
    "LOW": "simple",
    "MID": "ai",
    "HIGH": "formal",
    "UNKNOWN": "simple",
}
# state 对 quote_type 的修正
_QUOTE_TYPE_STATE_OVERRIDE = {
    "NEW": "simple",
    "FINAL": "ai",
}

# ==================== 关键词规则 ====================

_NEW_KEYWORDS = [
    "hi", "hello", "hey", "good morning", "good afternoon",
    "interested in", "looking for", "i need", "i want",
    "can you", "do you", "are you", "tell me about",
    "你好", "在吗", "请问", "我想",
]

_NEEDS_ANALYSIS_KEYWORDS = [
    "how much", "price", "cost", "quote", "quotation",
    "pricing", "rate", "how much is", "what is the price",
    "price list", "price sheet", "catalog", "brochure",
    "多少钱", "报价", "价格", "怎么算", "价位",
    "difference between", "recommend", "suggest", "what is",
    "which one", "how about", "tell me", "can you make",
    "do you have", "what material", "what kind",
    "sample", "samples", "free sample", "free samples",
]

_BUDGET_KEYWORDS = [
    "budget", "my budget", "we have", "roughly",
    "预算", "大概", "左右", "以内",
]

_OBJECTION_KEYWORDS = [
    "cheaper", "cheap", "expensive", "too high", "too much",
    "competitor", "other supplier", "other company",
    "compare", "comparable", "similar", "better price",
    "overpriced", "pricey", "costly",
    "别家", "比价", "太贵", "更便宜", "别处", "贵了",
    "quality issue", "not reliable", "bad review",
]

_FINAL_KEYWORDS = [
    "place order", "place the order", "i want to order",
    "let's proceed", "proceed", "confirm order", "confirm",
    "send invoice", "invoice me", "buy now", "purchase",
    "下单", "订购", "确认", "成交", "签合同",
    "i'll take", "i will take", "go ahead",
]

# 数字模式（用于 BUDGET 检测）
_PRICE_PATTERN = re.compile(
    r'\$\s*\d+[\d,]*\.?\d*'        # $100, $1,500, $123.45
    r'|\d+\s*(?:usd|cny|eur|gbp)'   # 100 usd, 200 cny
    r'|usd\s*\d+'                   # usd 100
    r'|(?:around|about|roughly|approx|approximately)\s*\d+'  # around 500
)

# 否定词（降低 confidence）
_NEGATION_WORDS = [
    "no", "not", "don't", "dont", "won't", "wont", "can't", "cant",
    "不", "不是", "不要", "没有",
]


def _has_price_signal(text):
    """检测消息中是否包含具体数字/价格信号"""
    return bool(_PRICE_PATTERN.search(text))


def _count_matches(text, keywords):
    """统计文本中命中关键词的数量（词级别匹配）"""
    t = text.lower()
    count = 0
    for kw in keywords:
        if kw in t:
            count += 1
    return count


def _has_negation(text):
    """检查是否包含否定意图（词边界匹配，避免"now"误匹配"no"）"""
    t = text.lower()
    # 先检查中文否定词（不用边界）
    cn_neg = [w for w in _NEGATION_WORDS if ord(w[0]) > 127]
    if any(w in t for w in cn_neg):
        return True
    # 英文否定词用词边界匹配
    en_neg = [w for w in _NEGATION_WORDS if ord(w[0]) < 128]
    for w in en_neg:
        if re.search(r'\b' + re.escape(w) + r'\b', t):
            return True
    return False


def _detect_price_tier(message):
    """检测客户价格档位

    策略:
      1. 提取消息中的具体金额数字
      2. 按价格区间归类 LOW(<$200) / MID($200-350) / HIGH(>$350)
      3. 若无具体金额，用定性关键词判断
      4. 仍然未知则返回 UNKNOWN
    """
    t = message.lower()

    # === 策略1: 定性关键词 ===
    for tier, keywords in _TIER_QUALITATIVE.items():
        for kw in keywords:
            if kw in t:
                return tier

    # === 策略2: 提取具体金额 ===
    amounts = []
    for match in _PRICE_RANGE_PATTERN.finditer(t):
        for group in match.groups():
            if group:
                try:
                    amounts.append(float(group.replace(",", "")))
                except ValueError:
                    pass

    if amounts:
        max_amount = max(amounts)
        if max_amount < 200:
            return "LOW"
        elif max_amount <= 350:
            return "MID"
        else:
            return "HIGH"

    # === 策略3: 已有 _PRICE_PATTERN 的匹配结果 ===
    if _has_price_signal(t):
        # 有价格信号但无法提取具体数值 → 默认 MID
        return "MID"

    return "UNKNOWN"


def _get_deal_probability(state, price_tier="UNKNOWN", has_negation=False):
    """计算成交概率

    基数来自 state:
      NEW=0.10  NEEDS_ANALYSIS=0.30  BUDGET=0.60
      OBJECTION=0.40  FINAL=0.85

    修正因子:
      - UNKNOWN price_tier: -0.05
      - HIGH price_tier: +0.10
      - has_negation: -0.15
      - FINAL + negation: -0.40 (客户反悔)
    """
    prob = _DEAL_PROBABILITY_BASE.get(state, 0.10)

    # price_tier 修正
    if price_tier == "UNKNOWN":
        prob -= 0.05
    elif price_tier == "HIGH":
        prob += 0.10
    elif price_tier == "LOW":
        prob -= 0.03

    # 否定词修正
    if has_negation:
        if state == "FINAL":
            prob -= 0.40  # 客户反悔
        else:
            prob -= 0.15

    return max(0.0, min(1.0, round(prob, 2)))


def _get_next_action(state, price_tier="UNKNOWN"):
    """销售级 next_action（比 v1 更精细）

    NEW            → ask                   收集需求，不报价
    NEEDS_ANALYSIS → present_options       给 A/B/C 三档选择
    BUDGET         → anchor_price          给价格锚 + 锁定区间
    OBJECTION      → handle_objection      风险压制，不降价
    FINAL          → close                 逼单 + 稀缺性
    """
    action_map = {
        "NEW": "ask",
        "NEEDS_ANALYSIS": "present_options",
        "BUDGET": "anchor_price",
        "OBJECTION": "handle_objection",
        "FINAL": "close",
    }
    action = action_map.get(state, "ask")

    # 特殊修正
    if state == "BUDGET" and price_tier == "HIGH":
        action = "anchor_price"  # 高端客户先锚定再报价
    if state == "OBJECTION" and price_tier == "LOW":
        action = "present_options"  # 低端客户异议 → 重新给更低价档选项

    return action


def _get_recommended_quote_type(state, price_tier="UNKNOWN"):
    """推荐报价类型

    simple: 只给价格区间（LOW/UNKNOWN 客户，NEW 阶段）
    ai:     AI 润色报价（MID 客户，NEEDS_ANALYSIS/BUDGET）
    formal: 正式 PDF 报价（HIGH 客户，FINAL 阶段）
    """
    base = _QUOTE_TYPE_RULES.get(price_tier, "simple")
    override = _QUOTE_TYPE_STATE_OVERRIDE.get(state)
    if override:
        return override
    return base


def detect_sales_state(message="", intent="", price_signal=""):
    """核心函数：判断销售阶段

    Args:
        message: 客户原始消息文本
        intent: 已检测的意图（可选，来自 _detect_knowledge_intent）
        price_signal: 价格信号（可选，外部传入）

    Returns:
        dict: {
            "state": str,
            "confidence": float (0-1),
            "next_action": str,
            "matched_keywords": list,
            "reason": str,
        }
    """
    text = message or ""
    t = text.lower()

    matched_keywords = []
    reasons = []

    # ========== 权重计算 ==========
    # 每个状态的得分（0-100）。NEW 不计分，仅作为兜底
    scores = {
        "NEW": 0,
        "NEEDS_ANALYSIS": _count_matches(t, _NEEDS_ANALYSIS_KEYWORDS) * 20,
        "BUDGET": 0,
        "OBJECTION": 0,
        "FINAL": 0,
    }

    # intent 映射
    if intent == "询价":
        scores["NEEDS_ANALYSIS"] += 40
    elif intent == "问工艺":
        scores["NEEDS_ANALYSIS"] += 20
    elif intent == "比价":
        scores["OBJECTION"] += 50
    elif intent == "要样品":
        scores["NEEDS_ANALYSIS"] += 20
    elif intent == "要目录":
        scores["NEEDS_ANALYSIS"] += 15
    elif intent == "问交期":
        scores["NEEDS_ANALYSIS"] += 10
    elif intent == "下单":
        scores["FINAL"] += 60
    elif intent == "售后":
        scores["OBJECTION"] += 30

    # 异议关键词（先检测，后面 budget 需要引用）
    objection_count = _count_matches(t, _OBJECTION_KEYWORDS)
    has_objection = objection_count > 0
    if has_objection:
        scores["OBJECTION"] += objection_count * 30
        matched_keywords.append("objection_keyword")

    # 价格信号 → BUDGET
    if _has_price_signal(t):
        scores["BUDGET"] += 30
        matched_keywords.append("price_number")

    # price_signal 参数
    if price_signal and price_signal.lower() in t:
        scores["BUDGET"] += 25
        matched_keywords.append(f"price_signal:{price_signal}")

    # 具体预算关键词
    budget_count = _count_matches(t, _BUDGET_KEYWORDS)
    if budget_count > 0:
        # 如果同时有异议关键词，降低预算权重（"budget"在异议语境中不是预算信号）
        budget_weight = 15 if has_objection else 30
        scores["BUDGET"] += budget_count * budget_weight
        matched_keywords.append("budget_keyword")

    # 成交关键词
    final_count = _count_matches(t, _FINAL_KEYWORDS)
    if final_count > 0:
        scores["FINAL"] += final_count * 35
        matched_keywords.append("final_keyword")

    # ========== 否定词处理 ==========
    # 如果有否定词，降低 FINAL 和 BUDGET 的分数
    if _has_negation(t):
        scores["FINAL"] = int(scores["FINAL"] * 0.3)
        scores["BUDGET"] = int(scores["BUDGET"] * 0.5)

    # ========== 状态选择 ==========
    # 按优先级排序：FINAL > OBJECTION > BUDGET > NEEDS_ANALYSIS > NEW
    priority_order = ["FINAL", "OBJECTION", "BUDGET", "NEEDS_ANALYSIS", "NEW"]

    best_state = "NEW"
    best_score = 0

    for state in priority_order:
        score = scores.get(state, 0)
        # 需要超过阈值
        threshold = {
            "FINAL": 35,
            "OBJECTION": 25,
            "BUDGET": 35,
            "NEEDS_ANALYSIS": 15,
            "NEW": 0,
        }.get(state, 0)

        if score >= threshold and score > best_score:
            best_state = state
            best_score = score

    # ========== confidence 计算 ==========
    max_possible = 100
    confidence = min(1.0, best_score / max_possible)

    # 简单消息（只有几个词）降低 confidence
    word_count = len(t.split())
    if word_count <= 3:
        confidence = max(0.2, confidence - 0.2)

    # ========== v2: price_tier ==========
    price_tier = _detect_price_tier(t)

    # ========== v2: deal_probability ==========
    has_neg = _has_negation(t)
    deal_probability = _get_deal_probability(best_state, price_tier, has_neg)

    # ========== v2: next_action（销售级） ==========
    next_action = _get_next_action(best_state, price_tier)

    # ========== v2: recommended_quote_type ==========
    recommended_quote_type = _get_recommended_quote_type(best_state, price_tier)

    # ========== reason ==========
    if matched_keywords:
        reasons.append(f"matched:{','.join(matched_keywords)}")
    if intent:
        reasons.append(f"intent:{intent}")
    reasons.append(f"score:{best_state}={best_score}")
    reasons.append(f"tier:{price_tier}")
    reason_str = "; ".join(reasons)

    # ========== 记录关键词匹配细节 ==========
    detail = {}
    for state_name in STATES:
        key = f"{state_name}_matches"
        if state_name == "NEW":
            detail[key] = _count_matches(t, _NEW_KEYWORDS)
        elif state_name == "NEEDS_ANALYSIS":
            detail[key] = _count_matches(t, _NEEDS_ANALYSIS_KEYWORDS)
        elif state_name == "BUDGET":
            detail[key] = budget_count + (1 if _has_price_signal(t) else 0)
        elif state_name == "OBJECTION":
            detail[key] = _count_matches(t, _OBJECTION_KEYWORDS)
        elif state_name == "FINAL":
            detail[key] = _count_matches(t, _FINAL_KEYWORDS)

    # v2 详细信息
    detail["price_tier"] = price_tier
    detail["deal_probability"] = deal_probability
    detail["negation_detected"] = has_neg

    return {
        "state": best_state,
        "confidence": round(confidence, 2),
        # ====== v2 新增字段 ======
        "deal_probability": deal_probability,
        "price_tier": price_tier,
        "next_action": next_action,
        "recommended_quote_type": recommended_quote_type,
        # ==========================
        "matched_keywords": list(set(matched_keywords)),
        "reason": reason_str,
        "details": detail,
    }


# ==================== 兼容 analyze_customer_message() ====================

def inject_sales_state(result_dict, message="", intent="", price_signal=""):
    """将状态机结果注入 analyze_customer_message() 的输出字典

    用法:
        result = analyze_customer_message(...)
        inject_sales_state(result, text, intent)
        # result 中会增加 sales_state 字段
    """
    state_info = detect_sales_state(
        message=message,
        intent=intent,
        price_signal=price_signal,
    )
    if isinstance(result_dict, dict):
        result_dict["sales_state"] = state_info
    return result_dict
