"""V3 Price Optimizer — 价格优化引擎

追踪每个价格点的成交率，自动推荐最优 A/B/C 结构，并动态更新
sales_executor._PRICE_ANCHORS。

算法:
  - 每个档位（LOW/MID/HIGH）内计算各价格区间的成交率
  - 使用贝叶斯平滑（+2 伪成交 / +4 伪试验）避免小样本过拟合
  - 选出每档位最优价格区间
  - 通过 JSON 文件持久化，启动时自动加载
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import get_db
from conversion_tracker import ConversionTracker

# JSON 持久化路径
_V3_PRICE_ANCHORS_PATH = os.path.join(BASE_DIR, "v3_price_anchors.json")

# 默认价格锚配置（与 sales_executor._PRICE_ANCHORS 一致）
_DEFAULT_PRICE_ANCHORS = {
    "LOW": {
        "range": "$120-200",
        "anchor": "$200",
        "abc": [
            {"label": "A — 入门款", "price": "$120-150", "desc": "基本功能，适合预算有限"},
            {"label": "B — 标准款", "price": "$150-180", "desc": "更高亮度，性价比之选"},
            {"label": "C — 升级款", "price": "$180-200", "desc": "全功能，效果最佳"},
        ],
        "risk_framing": "低价方案可能在户外6个月后开始褪色，更换成本更高。",
    },
    "MID": {
        "range": "$200-350",
        "anchor": "$280",
        "abc": [
            {"label": "A — 实用款", "price": "$200-250", "desc": "可靠耐用，适合大多数场景"},
            {"label": "B — 热销款", "price": "$250-300", "desc": "夜间高可见度，最受客户欢迎"},
            {"label": "C — 旗舰款", "price": "$300-350", "desc": "高端质感，使用寿命最长"},
        ],
        "risk_framing": "选择低价方案意味着 LED 可能在12个月后亮度衰减 30%，影响品牌形象。",
    },
    "HIGH": {
        "range": "$350+",
        "anchor": "$400",
        "abc": [
            {"label": "A — 标准高端", "price": "$350-400", "desc": "进口LED + 304不锈钢 + IP67防水"},
            {"label": "B — 奢华款", "price": "$400-500", "desc": "炫彩效果 + 双通道LED + 10年质保"},
            {"label": "C — 定制旗舰", "price": "$500+", "desc": "完全定制设计 + 安装服务 + 终身技术支持"},
        ],
        "risk_framing": "高端项目使用低端材料会导致 2-3 年后返工，总成本反超 3 倍。",
    },
    "UNKNOWN": {
        "range": "待确认",
        "anchor": "$250",
        "abc": [
            {"label": "A — 入门款", "price": "$120-200", "desc": "适合预算有限"},
            {"label": "B — 标准款", "price": "$200-300", "desc": "适合大多数需求"},
            {"label": "C — 高端款", "price": "$300+", "desc": "追求最佳品质和效果"},
        ],
        "risk_framing": "选择更可靠的品质意味着更低的长期维护成本。",
    },
}


def _midpoint(price_str):
    """从价格字符串 "$120-150" 中提取中点值 135"""
    import re
    nums = re.findall(r'\d+', price_str.replace(",", ""))
    if not nums:
        return 0
    nums = [float(n) for n in nums]
    return sum(nums) / len(nums)


class PriceOptimizer:
    """价格优化引擎"""

    def __init__(self):
        self._tracker = ConversionTracker()
        self._anchors = self.load_persisted_anchors()

    # ==================== 分析 ====================

    def analyze_price_performance(self, days=90):
        """分析各价格点成交性能"""
        raw = self._tracker.get_price_performance(days=days)
        by_tier = {}
        for row in raw:
            t = row["price_tier"]
            if t not in by_tier:
                by_tier[t] = []
            by_tier[t].append(row)
        return by_tier

    def compute_optimal_prices(self, min_samples=15):
        """核心算法：计算最优价格区间

        对每个档位，对 A/B/C 选项使用贝叶斯平滑估算成交率，
        选出最优选项。

        Returns:
            dict: 每个档位的推荐结构
        """
        raw = self._tracker.get_price_performance(days=90, price_tier=None)
        recommendations = {}

        # 按档位分组
        by_tier = {}
        for row in raw:
            t = row["price_tier"]
            if t not in by_tier:
                by_tier[t] = []
            by_tier[t].append(row)

        for tier in ["LOW", "MID", "HIGH", "UNKNOWN"]:
            data = by_tier.get(tier, [])
            default = _DEFAULT_PRICE_ANCHORS.get(tier, _DEFAULT_PRICE_ANCHORS["UNKNOWN"])

            if not data:
                recommendations[tier] = {"status": "no_data", "recommended": default}
                continue

            # 贝叶斯平滑：对每个价格点计算 smoothed_rate
            smoothed = []
            for d in data:
                trials = d["total_trials"]
                won = d["won_count"]
                # Beta(1,1) prior → +2 pseudo-wins, +4 pseudo-trials
                smoothed_rate = (won + 2) / (trials + 4) if trials > 0 else 0.5
                smoothed.append({
                    "price_range": d["price_range"],
                    "trials": trials,
                    "won": won,
                    "raw_rate": d["conversion_rate"],
                    "smoothed_rate": round(smoothed_rate, 4),
                })

            # 找出最优平滑率的价格点
            best = max(smoothed, key=lambda x: x["smoothed_rate"]) if smoothed else None

            if best and best["trials"] >= min_samples:
                # 找到对应档位的 ABC 中哪个选项匹配此价格
                best_abc_idx = 1  # default to B
                for i, abc in enumerate(default["abc"]):
                    mp = _midpoint(abc["price"])
                    if _midpoint(best["price_range"]) > 0 and abs(_midpoint(best["price_range"]) - mp) < 50:
                        best_abc_idx = i
                        break

                # 构建推荐：将该选项设为最优
                recommended_abc = list(default["abc"])
                # 把最优选项放到 B 位置（中间），重新排序
                best_item = recommended_abc.pop(best_abc_idx)
                recommended_abc.insert(1, best_item)  # B position

                recommendations[tier] = {
                    "status": "optimized",
                    "recommended": {
                        "range": default["range"],
                        "anchor": best["price_range"].split("-")[0].strip("$") if "-" in best["price_range"] else default["anchor"],
                        "abc": recommended_abc,
                        "risk_framing": default["risk_framing"],
                    },
                    "best_price": best["price_range"],
                    "smoothed_rate": best["smoothed_rate"],
                    "samples": best["trials"],
                }
            else:
                recommendations[tier] = {
                    "status": "insufficient_data" if best and best["trials"] < min_samples else "no_data",
                    "recommended": default,
                    "samples": best["trials"] if best else 0,
                }

        return recommendations

    # ==================== 应用 ====================

    def update_price_anchors(self, recommendations=None):
        """将优化后的价格写入 _PRICE_ANCHORS（通过 JSON 文件）"""
        if recommendations is None:
            recommendations = self.compute_optimal_prices()

        new_anchors = {}
        changes_made = 0
        for tier in ["LOW", "MID", "HIGH", "UNKNOWN"]:
            rec = recommendations.get(tier, {})
            if rec.get("status") == "optimized":
                new_anchors[tier] = rec["recommended"]
                changes_made += 1
            else:
                new_anchors[tier] = _DEFAULT_PRICE_ANCHORS.get(tier, _DEFAULT_PRICE_ANCHORS["UNKNOWN"])

        # 写入 JSON 文件
        self._anchors = new_anchors
        self.persist_anchors()

        # 尝试动态更新 sales_executor._PRICE_ANCHORS
        try:
            import sales_executor
            sales_executor._PRICE_ANCHORS.update(new_anchors)
        except Exception:
            pass

        # 审计日志
        conn = get_db()
        for tier, cfg in new_anchors.items():
            old = _DEFAULT_PRICE_ANCHORS.get(tier, {})
            conn.execute(
                "INSERT INTO v3_weight_history (weight_type, weight_key, old_value, new_value, reason, triggered_by) VALUES (?,?,?,?,?,?)",
                ("price_anchor", tier, json.dumps(old, ensure_ascii=False),
                 json.dumps(cfg, ensure_ascii=False), "auto_optimize", "system")
            )
        conn.commit()
        conn.close()

        return {
            "changes_made": changes_made,
            "new_anchors": new_anchors,
        }

    # ==================== 持久化 ====================

    def persist_anchors(self):
        """保存当前价格锚到 JSON 文件"""
        with open(_V3_PRICE_ANCHORS_PATH, "w", encoding="utf-8") as f:
            json.dump(self._anchors, f, ensure_ascii=False, indent=2)

    def load_persisted_anchors(self):
        """从 JSON 文件加载价格锚"""
        if os.path.exists(_V3_PRICE_ANCHORS_PATH):
            try:
                with open(_V3_PRICE_ANCHORS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data
            except Exception:
                pass
        return dict(_DEFAULT_PRICE_ANCHORS)

    def reset_to_defaults(self):
        """重置为默认价格"""
        self._anchors = dict(_DEFAULT_PRICE_ANCHORS)
        self.persist_anchors()
        try:
            import sales_executor
            sales_executor._PRICE_ANCHORS.update(self._anchors)
        except Exception:
            pass

    # ==================== 查询 ====================

    def get_current_anchors(self):
        """获取当前价格锚"""
        return self._anchors

    def get_recommended_quote(self, price_tier="UNKNOWN"):
        """获取当前推荐的报价结构"""
        return self._anchors.get(price_tier, self._anchors.get("UNKNOWN", _DEFAULT_PRICE_ANCHORS["UNKNOWN"]))


# ==================== 快捷入口 ====================

optimizer = PriceOptimizer()


def load_persisted_price_anchors():
    """启动时调用，加载优化后的价格到 sales_executor"""
    try:
        import sales_executor
        anchors = optimizer.load_persisted_anchors()
        sales_executor._PRICE_ANCHORS.update(anchors)
        return True
    except Exception:
        return False
