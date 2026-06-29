"""销售决策引擎 — 根据客户状态+意图，决定下一步动作"""

from lead_state_engine import get_lead_state, get_state_history

# ======================== 动作定义 ========================
ACTIONS = {
    "ASK_DETAILS": "追问项目细节（尺寸/图纸/安装环境/数量）",
    "RECOMMEND_MATERIAL": "推荐材质和工艺方案",
    "GENERATE_QUOTE": "生成报价（计算器→AI润色→PDF）",
    "SEND_QUOTE": "发送报价单给客户",
    "SEND_SOCIAL_PROOF": "发送匹配案例/社会证明",
    "PUSH_URGENCY": "用工厂排期制造紧迫感",
    "HANDLE_OBJECTION": "处理比价/异议（列差异化点）",
    "ATTEMPT_CLOSE": "推进成交（确认规格→收定金）",
    "FOLLOW_UP": "跟进沉默客户",
    "ESCALATE": "升级到人工处理",
    "ROUTINE_REPLY": "常规回复，无需额外动作",
}

# 动作执行后的等待策略（秒）
ACTION_WAIT_STRATEGY = {
    "GENERATE_QUOTE": 120,     # 报价后等2分钟再发？
    "SEND_QUOTE": 3600,        # 报价后自然跟进
    "PUSH_URGENCY": 86400,     # 紧迫感后等1天
    "FOLLOW_UP": 86400 * 3,    # 跟进后等3天
}

# ======================== 决策规则 ========================

def decide_action(customer_id, intent, extra_context=None):
    """核心决策函数

    参数:
        customer_id: 客户ID
        intent: 从analyze_customer_message()返回的意图
        extra_context: 额外信息（如urgency等级, 历史等）, dict

    返回:
        dict: {
            "action": 动作名称,
            "priority": "high"/"medium"/"low",
            "reason": 决策原因,
            "suggested_reply_style": "push"/"normal"/"soft"
        }
    """
    state = get_lead_state(customer_id)
    extra = extra_context or {}

    # ===== 决策树：先按状态，再按意图 =====

    # --- NEW: 新客户 ---
    if state == "NEW":
        if intent == "询价":
            return _make("ASK_DETAILS", "high", "新客户问价，先问规格再报价", "normal")
        if intent in ("问工艺", "要目录", "合作"):
            return _make("RECOMMEND_MATERIAL", "high", "新客户了解产品，主动推荐+引导", "normal")
        if intent == "比价":
            return _make("ASK_DETAILS", "high", "新客户上来比价，先了解需求再差异化", "normal")
        return _make("ASK_DETAILS", "medium", "新客户常规询问，引导需求", "normal")

    # --- INTERESTED: 有兴趣 ---
    if state == "INTERESTED":
        if intent == "询价":
            return _make("GENERATE_QUOTE", "high", "客户已有兴趣+问价，立刻报价", "push")
        if intent == "比价":
            return _make("HANDLE_OBJECTION", "high", "客户已被报价但还在比价", "push")
        if intent == "问工艺":
            return _make("RECOMMEND_MATERIAL", "medium", "客户深入了解工艺，专业引导", "normal")
        return _make("ROUTINE_REPLY", "low", "常规兴趣阶段回复", "normal")

    # --- REQUESTED_PRICE: 已问价 ---
    if state == "REQUESTED_PRICE":
        if intent == "询价":
            return _make("GENERATE_QUOTE", "high", "客户再次确认价格，生成报价", "push")
        if intent == "比价":
            return _make("HANDLE_OBJECTION", "high", "报价后客户比价，准备差异化话术", "push")
        if intent == "售后":
            return _make("ROUTINE_REPLY", "medium", "已有客户售后", "normal")
        return _make("GENERATE_QUOTE", "high", "客户已问价，推进到出报价", "push")

    # --- QUOTED: 已报价 ---
    if state == "QUOTED":
        if intent == "询价":
            return _make("SEND_QUOTE", "high", "已报价客户又询价，提醒已有报价", "push")
        if intent == "比价":
            return _make("HANDLE_OBJECTION", "high", "报价后被比价，捍卫价值", "push")
        if intent == "售后":
            return _make("ROUTINE_REPLY", "medium", "已有客户售后处理", "normal")
        if intent in ("跟进", "其他"):
            has_social_proof = extra.get("has_social_proof", False)
            if has_social_proof:
                return _make("SEND_SOCIAL_PROOF", "medium", "报价后跟进，补案例增加信任", "normal")
            return _make("PUSH_URGENCY", "medium", "报价后跟进，用排期推动", "normal")
        return _make("ROUTINE_REPLY", "low", "常规报价阶段回复", "normal")

    # --- NEGOTIATING: 谈判中 ---
    if state == "NEGOTIATING":
        if intent == "比价":
            return _make("HANDLE_OBJECTION", "high", "谈判中比价，必须守住价格底线", "push")
        if intent == "询价":
            return _make("GENERATE_QUOTE", "high", "谈判中重新询价，可能需要调整方案", "push")
        if intent == "下单":
            return _make("ATTEMPT_CLOSE", "high", "谈判后客户要下单，立刻推进成交", "push")
        return _make("PUSH_URGENCY", "medium", "谈判胶着，用排期推一把", "push")

    # --- HOT: 强购买信号 ---
    if state == "HOT":
        if intent == "下单":
            return _make("ATTEMPT_CLOSE", "high", "客户要下单，立刻推进成交", "push")
        if intent == "比价":
            return _make("HANDLE_OBJECTION", "high", "临门一脚还在比价，全力捍卫", "push")
        return _make("ATTEMPT_CLOSE", "high", "HOT状态，主动推进", "push")

    # --- COLD: 沉默 ---
    if state == "COLD":
        return _make("FOLLOW_UP", "medium", "沉默客户需要跟进唤醒", "soft")

    # --- CLOSED_WON / CLOSED_LOST ---
    if state in ("CLOSED_WON", "CLOSED_LOST"):
        return _make("ROUTINE_REPLY", "low", f"客户已{state}，常规回复", "normal")

    # --- 默认 ---
    return _make("ROUTINE_REPLY", "low", "默认常规回复", "normal")


def _make(action, priority, reason, reply_style):
    return {
        "action": action,
        "priority": priority,
        "reason": reason,
        "suggested_reply_style": reply_style,
        "action_description": ACTIONS.get(action, ""),
    }


# ======================== 批量决策（用于调度器/看板） ========================

def decide_batch_action(customer_id):
    """不看意图，仅根据状态+时间做决策（用于定时调度）"""
    state = get_lead_state(customer_id)
    history = get_state_history(customer_id, limit=5)

    if state == "NEW" and _is_older_than(customer_id, hours=24):
        return _make("FOLLOW_UP", "medium", "新客户24小时未回复，主动跟进", "soft")

    if state == "QUOTED" and _is_older_than(customer_id, hours=72):
        return _make("FOLLOW_UP", "high", "报价3天未回复，必须跟进", "push")

    if state == "COLD" and _is_older_than(customer_id, days=3):
        last_action = None
        for h in history:
            if h["trigger_source"] in ("action", "manual"):
                last_action = h["to_state"]
                break
        if last_action != "FOLLOW_UP":
            return _make("FOLLOW_UP", "medium", "沉默客户周期性跟进", "soft")

    return _make("ROUTINE_REPLY", "low", "无需特殊动作", "normal")


def _is_older_than(customer_id, hours=0, days=0):
    """检查客户最后一条消息是否超过指定时间"""
    import sqlite3
    from datetime import datetime, timedelta
    from lead_state_engine import DB_PATH

    delta = timedelta(hours=hours, days=days)
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT created_at FROM messages WHERE customer_id=? ORDER BY created_at DESC LIMIT 1",
            (customer_id,)
        ).fetchone()
        conn.close()
        if not row:
            return True  # 无消息记录也算"旧"
        last = datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
        return datetime.now() - last > delta
    except:
        return False
