"""Business Policy Engine — 「AI商业宪法」

核心作用:
  定义并强制执行商业规则，防止 AI 乱决策。

规则类型:
  - hard: 硬性规则，违反即阻止（不可绕过）
  - soft: 软性规则，违反出警告但可执行

规则分类:
  - market_entry: 市场进入限制
  - minimum_margin: 最低利润率
  - pricing: 定价/折扣约束
  - product: 产品策略约束
"""
import logging

logger = logging.getLogger("business_policy")

POLICY_RULES = [
    {
        "id": "POLICY_001",
        "category": "market_entry",
        "rule": "不得超出已知目标市场范围",
        "severity": "hard",
        "check_type": "country_allowed",
        "allowed_countries": [
            "US", "CA", "GB", "DE", "FR", "IT", "ES", "NL",
            "AE", "SA", "QA", "KW", "OM", "BH",
            "AU", "SG", "JP", "MY",
        ],
    },
    {
        "id": "POLICY_002",
        "category": "minimum_margin",
        "rule": "所有成交订单利润率不得低于25%",
        "severity": "hard",
        "check_type": "minimum_margin",
        "min_margin": 0.25,
    },
    {
        "id": "POLICY_003",
        "category": "pricing",
        "rule": "最高折扣不得超过25%",
        "severity": "hard",
        "check_type": "max_discount",
        "max_discount": 0.25,
    },
    {
        "id": "POLICY_004",
        "category": "pricing",
        "rule": "低价值客户折扣上限5%，中等10%，高价值15%",
        "severity": "soft",
        "check_type": "tier_discount",
        "tier_limits": {"LOW": 0.05, "MEDIUM": 0.10, "HIGH_VALUE": 0.15},
    },
    {
        "id": "POLICY_005",
        "category": "product",
        "rule": "停售产品不得推荐",
        "severity": "hard",
        "check_type": "product_status",
        "allowed_statuses": ["active"],
    },
    {
        "id": "POLICY_006",
        "category": "market_entry",
        "rule": "新市场进入前必须有至少3个成功询盘记录",
        "severity": "soft",
        "check_type": "market_readiness",
        "min_inquiries": 3,
    },
    {
        "id": "POLICY_007",
        "category": "pricing",
        "rule": "同一客户30天内不得降价超过一次",
        "severity": "soft",
        "check_type": "price_change_frequency",
        "cooldown_days": 30,
    },
]


class BusinessPolicy:
    """商业策略引擎 — 评估策略合规性"""

    @staticmethod
    def load_all():
        """加载所有策略规则"""
        return POLICY_RULES

    @staticmethod
    def get_by_category(category):
        """按分类获取规则"""
        return [r for r in POLICY_RULES if r["category"] == category]

    @staticmethod
    def get_by_severity(severity):
        """按严重级别获取规则"""
        return [r for r in POLICY_RULES if r["severity"] == severity]

    @staticmethod
    def evaluate_strategy(strategy_report):
        """对策略报告执行完整合规评估

        参数:
            strategy_report: StrategyEngine.run_full_analysis() 的输出

        返回:
            dict: { overall_compliant, hard_violations, soft_violations,
                    total_hard, total_soft, compliant }
        """
        violations_hard = []
        violations_soft = []
        report = strategy_report or {}

        for rule in POLICY_RULES:
            check_type = rule["check_type"]
            violation = None

            if check_type == "country_allowed":
                violation = BusinessPolicy._check_country(report, rule)
            elif check_type == "minimum_margin":
                violation = BusinessPolicy._check_min_margin(report, rule)
            elif check_type == "max_discount":
                violation = BusinessPolicy._check_max_discount(report, rule)
            elif check_type == "tier_discount":
                violation = BusinessPolicy._check_tier_discount(report, rule)
            elif check_type == "product_status":
                violation = BusinessPolicy._check_product_status(report, rule)

            if violation:
                if rule["severity"] == "hard":
                    violations_hard.append(violation)
                else:
                    violations_soft.append(violation)

        return {
            "overall_compliant": len(violations_hard) == 0,
            "hard_violations": violations_hard,
            "soft_violations": violations_soft,
            "total_hard": len(violations_hard),
            "total_soft": len(violations_soft),
            "compliant": len(violations_hard) == 0,
        }

    @staticmethod
    def _check_country(report, rule):
        """检查建议市场是否在许可范围内"""
        market_strategy = report.get("market_strategy", {})
        markets = market_strategy.get("scored_markets", [])
        allowed = set(rule["allowed_countries"])
        for m in markets:
            code = m.get("country_code", "")
            if code and code not in allowed:
                return {
                    "policy_id": rule["id"],
                    "rule": rule["rule"],
                    "detail": f"市场 {code} 不在许可范围",
                    "severity": rule["severity"],
                }
        return None

    @staticmethod
    def _check_min_margin(report, rule):
        """检查建议利润率是否低于最低要求"""
        pricing_strategy = report.get("pricing_strategy", {})
        strategies = pricing_strategy.get("strategies", [])
        for s in strategies:
            margin = s.get("target_margin", 1)
            if margin < rule["min_margin"]:
                return {
                    "policy_id": rule["id"],
                    "rule": rule["rule"],
                    "detail": f"建议利润率 {margin:.0%} 低于最低 {rule['min_margin']:.0%}",
                    "severity": rule["severity"],
                }
        return None

    @staticmethod
    def _check_max_discount(report, rule):
        """检查建议折扣是否超过上限"""
        pricing_strategy = report.get("pricing_strategy", {})
        policies = pricing_strategy.get("discount_policies", [])
        for p in policies:
            discount = p.get("max_discount_pct", 0)
            if discount > rule["max_discount"]:
                return {
                    "policy_id": rule["id"],
                    "rule": rule["rule"],
                    "detail": f"建议折扣 {discount:.0%} 超过上限 {rule['max_discount']:.0%}",
                    "severity": rule["severity"],
                }
        return None

    @staticmethod
    def _check_tier_discount(report, rule):
        """检查各客户等级的折扣是否在限制内"""
        pricing_strategy = report.get("pricing_strategy", {})
        policies = pricing_strategy.get("discount_policies", [])
        limits = rule["tier_limits"]
        for p in policies:
            tier = p.get("customer_tier", "LOW")
            discount = p.get("max_discount_pct", 0)
            limit = limits.get(tier, 0.05)
            if discount > limit:
                return {
                    "policy_id": rule["id"],
                    "rule": rule["rule"],
                    "detail": f"{tier} 客户折扣 {discount:.0%} 超过限制 {limit:.0%}",
                    "severity": rule["severity"],
                    "suggestion": f"建议降至 {limit:.0%}",
                }
        return None

    @staticmethod
    def _check_product_status(report, rule):
        """检查推荐产品是否均为活跃状态"""
        product_strategy = report.get("product_strategy", {})
        products = product_strategy.get("scored_products", [])
        for p in products:
            status = p.get("status", "active")
            if status not in rule["allowed_statuses"]:
                return {
                    "policy_id": rule["id"],
                    "rule": rule["rule"],
                    "detail": f"产品 {p.get('product_name', '?')} 状态为 {status}",
                    "severity": rule["severity"],
                }
        return None

    # ── 消息级验证（V0-SAFETY: AI Governance Gateway）──

    @staticmethod
    def validate_message_content(message_text, customer_context=None):
        """对单条出站消息执行策略规则检查

        参数:
            message_text: AI生成的回复内容
            customer_context: dict，可含 tier, country, product 等

        返回:
            list of dict: 触发的规则列表，空表示合规
        """
        violations = []
        text_lower = message_text.lower()

        # POLICY_003: 折扣上限 25%
        import re
        discount_matches = re.findall(r"(\d+)\s*%", text_lower)
        for pct_str in discount_matches:
            try:
                pct = int(pct_str)
                if pct > 25:
                    violations.append({
                        "policy_id": "POLICY_003",
                        "rule": "最高折扣不得超过25%",
                        "detail": f"消息含 {pct}% 折扣超过上限 25%",
                        "severity": "hard",
                        "suggestion": "将折扣降至 25% 以下",
                    })
            except ValueError:
                pass

        # POLICY_004: 客户等级折扣
        if customer_context:
            tier = customer_context.get("tier", "LOW")
            tier_limits = {"LOW": 5, "MEDIUM": 10, "HIGH_VALUE": 15}
            limit = tier_limits.get(tier, 5)
            for pct_str in discount_matches:
                try:
                    pct = int(pct_str)
                    if pct > limit:
                        violations.append({
                            "policy_id": "POLICY_004",
                            "rule": f"{tier} 客户折扣上限 {limit}%",
                            "detail": f"{tier} 客户折扣 {pct}% 超过上限 {limit}%",
                            "severity": "soft",
                            "suggestion": f"降至 {limit}% 以下",
                        })
                except ValueError:
                    pass

        return violations

    @staticmethod
    def suggest_mitigations(violations):
        """为违例建议修正方案"""
        mitigations = []
        for v in violations:
            suggestion = v.get("suggestion")
            if not suggestion:
                pid = v["policy_id"]
                if pid == "POLICY_001":
                    suggestion = "移除不在许可列表中的市场"
                elif pid == "POLICY_002":
                    suggestion = "调高定价或降低成本以达到最低利润率"
                elif pid == "POLICY_003":
                    suggestion = "降低折扣比例"
                else:
                    suggestion = "调整策略参数以符合规则"
            mitigations.append({
                "policy_id": v["policy_id"],
                "violation": v["detail"],
                "suggested_fix": suggestion,
            })
        return mitigations
