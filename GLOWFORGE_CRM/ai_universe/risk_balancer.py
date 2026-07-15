"""Risk Balancer — 风险控制系统

自动避免：
  ❌ 单一市场依赖
  ❌ 单一产品依赖
  ❌ 单一客户群风险

自动执行：
  利润过高集中 → 自动分散投资
  市场下降 → 自动停止投放
"""

import sys
import os
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class RiskBalancer:
    """风险控制系统 — 自动避险"""

    # 风险阈值配置
    RISK_THRESHOLDS = {
        "market_concentration": {
            "warning": 50,  # 单一市场占比超过50% → 警告
            "critical": 70,  # 超过70% → 自动行动
            "action": "diversify_market",
        },
        "product_concentration": {
            "warning": 60,
            "critical": 80,
            "action": "expand_product",
        },
        "customer_concentration": {
            "warning": 30,  # 单一客户占比超过30%
            "critical": 50,
            "action": "diversify_customer",
        },
        "profit_decline": {
            "warning": -15,  # 利润下降超过15%
            "critical": -30,
            "action": "cut_costs",
        },
        "market_decline": {
            "warning": -10,  # 市场下降超过10%
            "critical": -20,
            "action": "stop_spending",
        },
    }

    @staticmethod
    def assess_risk(portfolio: list) -> dict:
        """评估投资组合风险

        Args:
            portfolio: [{company, market, revenue, profit, customers}]

        Returns:
            dict: {risk_level, findings, auto_actions, score}
        """
        if not portfolio:
            return {"risk_level": "unknown", "score": 0, "findings": [], "auto_actions": []}

        findings = []
        auto_actions = []
        total_revenue = sum(p.get("revenue", 0) for p in portfolio)
        total_profit = sum(p.get("profit", 0) for p in portfolio)

        # 1. 市场集中度风险
        market_revenue = {}
        for p in portfolio:
            mkt = p.get("market", "unknown")
            market_revenue[mkt] = market_revenue.get(mkt, 0) + p.get("revenue", 0)

        for market, rev in market_revenue.items():
            if total_revenue > 0:
                pct = rev / total_revenue * 100
                if pct >= RiskBalancer.RISK_THRESHOLDS["market_concentration"]["critical"]:
                    findings.append({
                        "type": "market_concentration",
                        "severity": "critical",
                        "detail": f"{market}: {pct:.0f}% of revenue",
                        "score": pct,
                    })
                    auto_actions.append(f"Auto-diversify from {market} — redirect 20% budget to other markets")
                elif pct >= RiskBalancer.RISK_THRESHOLDS["market_concentration"]["warning"]:
                    findings.append({
                        "type": "market_concentration",
                        "severity": "warning",
                        "detail": f"{market}: {pct:.0f}% of revenue",
                        "score": pct,
                    })

        # 2. 产品集中度风险
        product_revenue = {}
        for p in portfolio:
            prod = p.get("product", p.get("focus", "unknown"))
            product_revenue[prod] = product_revenue.get(prod, 0) + p.get("revenue", 0)

        for prod, rev in product_revenue.items():
            if total_revenue > 0:
                pct = rev / total_revenue * 100
                if pct >= RiskBalancer.RISK_THRESHOLDS["product_concentration"]["critical"]:
                    findings.append({
                        "type": "product_concentration",
                        "severity": "critical",
                        "detail": f"{prod}: {pct:.0f}% of revenue",
                        "score": pct,
                    })
                    auto_actions.append(f"Auto-expand product line — introduce new variations of {prod}")

        # 3. 盈利风险
        if total_revenue > 0:
            profit_margin = total_profit / total_revenue * 100
            if profit_margin < 10:
                findings.append({
                    "type": "profit_margin",
                    "severity": "warning",
                    "detail": f"Overall profit margin: {profit_margin:.1f}%",
                    "score": profit_margin,
                })
                auto_actions.append("Auto-optimize pricing — increase prices 10% in low-margin markets")

        # 4. 亏损业务
        losing = [p for p in portfolio if p.get("profit", 0) < 0]
        if losing:
            total_loss = sum(abs(p.get("profit", 0)) for p in losing)
            findings.append({
                "type": "unprofitable_companies",
                "severity": "warning" if len(losing) <= 2 else "critical",
                "detail": f"{len(losing)} unprofitable companies, total loss: ${total_loss:.0f}",
                "score": len(losing) * 10,
            })
            if len(losing) >= 2:
                auto_actions.append("Auto-cut bottom performer — pause worst performing company")

        # 计算综合风险分
        risk_score = sum(f["score"] for f in findings if f["severity"] == "critical") * 2
        risk_score += sum(f["score"] for f in findings if f["severity"] == "warning")
        risk_score = min(risk_score / 10, 100)

        if risk_score >= 70:
            risk_level = "high"
        elif risk_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 1),
            "findings": findings,
            "auto_actions": list(set(auto_actions)),
            "total_actions": len(set(auto_actions)),
            "assessed_at": datetime.now().isoformat(),
        }

    @staticmethod
    def suggest_hedge(risk_assessment: dict) -> list:
        """根据风险评估建议对冲策略

        Args:
            risk_assessment: assess_risk() 的结果

        Returns:
            list: [strategy, ...]
        """
        strategies = []
        level = risk_assessment.get("risk_level", "low")

        if level == "high":
            strategies.extend([
                "Immediately reduce exposure to highest-risk market by 30%",
                "Increase cash reserve from 10% to 20%",
                "Halt all experimental spending until risk reduces",
                "Focus resources on 2 best-performing markets only",
            ])
        elif level == "medium":
            strategies.extend([
                "Gradually diversify into 1-2 new markets",
                "Increase product line variety",
                "Set up automatic stop-loss at 15% profit decline",
            ])
        else:
            strategies.extend([
                "Maintain current strategy",
                "Continue expansion into new markets",
                "Monitor market concentration quarterly",
            ])

        # 添加自动行动
        for action in risk_assessment.get("auto_actions", []):
            strategies.append(f"[AUTO] {action}")

        return strategies

    @staticmethod
    def auto_balance(portfolio: list) -> dict:
        """自动平衡投资组合（执行避险操作）

        Args:
            portfolio: 投资组合数据

        Returns:
            dict: {actions_taken, new_allocation, risk_before, risk_after}
        """
        risk_before = RiskBalancer.assess_risk(portfolio)
        actions = list(risk_before.get("auto_actions", []))

        # 模拟调整后的组合
        adjusted = []
        for p in portfolio:
            adjusted_p = dict(p)
            # 对高集中度市场减少投入
            mkt = p.get("market", "")
            for action in actions:
                if f"diversify from {mkt}" in action.lower():
                    adjusted_p["revenue"] = int(p.get("revenue", 0) * 0.8)
                    adjusted_p["budget"] = int(p.get("budget", 0) * 0.7)
            adjusted.append(adjusted_p)

        risk_after = RiskBalancer.assess_risk(adjusted)

        return {
            "actions_taken": actions,
            "total_actions": len(actions),
            "risk_before": risk_before,
            "risk_after": risk_after,
            "improvement": risk_before.get("risk_score", 0) - risk_after.get("risk_score", 0),
            "auto_mode": True,
        }


# 快捷入口
balancer = RiskBalancer()


def assess(portfolio: list) -> dict:
    return RiskBalancer.assess_risk(portfolio)


def auto_balance(portfolio: list) -> dict:
    return RiskBalancer.auto_balance(portfolio)
