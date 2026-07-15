"""Growth Experiment Engine — 增长实验引擎

系统自动生成「可测试增长策略」。
组合维度: 市场 × 产品 × 广告角度 × 定价策略

每个实验 = 一个可执行的增长假设:
  "在 US 市场用 Luxury 角度推 Cabinet 产品 + high_margin 定价"
"""
import logging
from itertools import product
from datetime import datetime

logger = logging.getLogger("growth.experiment_engine")

# ── 实验默认配置 ──
MAX_EXPERIMENTS_PER_RUN = 12       # 每轮最大实验数
MIN_EXPERIMENT_SCORE = 0.3          # 实验最低分
EXPERIMENT_TTL_DAYS = 14            # 实验有效期
NEW_EXPERIMENT_RATIO = 0.3          # 每轮新实验比例


class GrowthExperimentEngine:
    """增长实验引擎 — 自动生成可测试增长策略"""

    @staticmethod
    def generate_experiments(
        market_data=None,
        product_data=None,
        pricing_data=None,
        angle_data=None,
        growth_state=None,
        dry_run=True,
    ):
        """生成增长实验组合

        将 市场 × 产品 × 角度 × 定价 交叉组合，
        过滤无效组合，按预期 ROI 排序。

        参数:
            market_data: market_scoring.score_markets() 输出
            product_data: product_scoring.score_products() 输出
            pricing_data: pricing_strategy.develop_strategy() 输出
            angle_data: angle_generator.generate_angles() 输出
            growth_state: 可选的 growth_state.json 历史数据
            dry_run: 预览模式

        返回:
            dict: { experiments, summary, generated_at }
        """
        # ── 1. 收集输入 ──
        markets = GrowthExperimentEngine._get_markets(market_data)
        products = GrowthExperimentEngine._get_products(product_data)
        pricing_tiers = GrowthExperimentEngine._get_pricing_tiers(pricing_data)
        angles = angle_data.get("angles", []) if angle_data else []

        logger.info(
            f"Experiment inputs: {len(markets)} markets × {len(products)} products "
            f"× {len(angles)} angles × {len(pricing_tiers)} pricing"
        )

        if not markets or not products or not angles:
            logger.warning("Insufficient dimensions for experiment generation")
            return {
                "experiments": [],
                "summary": {
                    "total_raw_combinations": 0,
                    "experiments_generated": 0,
                    "filtered_by_policy": 0,
                    "reason": "missing dimensions",
                },
                "generated_at": datetime.now().isoformat(),
            }

        # ── 2. 交叉组合 ──
        raw_combinations = list(product(markets, products, angles, pricing_tiers))
        total_raw = len(raw_combinations)
        logger.info(f"Raw combinations: {total_raw}")

        # ── 3. 评分 & 过滤 ──
        scored = []
        for mkt, prod, ang, price in raw_combinations:
            exp = GrowthExperimentEngine._score_experiment(
                market=mkt, product=prod, angle=ang, pricing=price,
                market_data=market_data, product_data=product_data,
                growth_state=growth_state,
            )
            if exp and exp["score"] >= MIN_EXPERIMENT_SCORE:
                scored.append(exp)

        scored.sort(key=lambda x: x["score"], reverse=True)

        # ── 4. 多样性选择 — 避免全部集中在同一市场/产品 ──
        selected = GrowthExperimentEngine._diversify_selection(
            scored, max_count=MAX_EXPERIMENTS_PER_RUN,
            growth_state=growth_state,
        )

        # ── 5. 注入新实验（探索） ──
        if growth_state:
            selected = GrowthExperimentEngine._inject_new_experiments(
                selected, scored, growth_state,
            )

        # 标记实验 ID
        for i, exp in enumerate(selected):
            exp["experiment_id"] = f"EXP-{datetime.now().strftime('%Y%m%d')}-{i+1:03d}"

        return {
            "experiments": selected,
            "summary": {
                "total_raw_combinations": total_raw,
                "experiments_generated": len(selected),
                "filtered_by_policy": total_raw - len(scored),
                "top_score": round(selected[0]["score"], 3) if selected else 0,
            },
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _get_markets(market_data):
        """从 market_scoring 提取市场列表"""
        if not market_data:
            return []
        scored = market_data.get("scored_markets") or market_data.get("market_strategy", {}).get("scored_markets", [])
        # 取前 10 个市场（支持 country_code / country / market 字段）
        result = []
        for m in scored[:10]:
            code = m.get("country_code") or m.get("country") or m.get("market")
            if code:
                result.append(code)
        return result

    @staticmethod
    def _get_products(product_data):
        """从 product_scoring 提取产品列表"""
        if not product_data:
            return []
        scored = product_data.get("scored_products") or product_data.get("product_strategy", {}).get("scored_products", [])
        result = []
        for p in scored[:8]:
            name = p.get("product_name") or p.get("name") or p.get("product_id") or p.get("id")
            if name:
                result.append(str(name))
        return result

    @staticmethod
    def _get_pricing_tiers(pricing_data):
        """从 pricing_strategy 提取定价层级"""
        if not pricing_data:
            return ["medium"]
        tiers = pricing_data.get("pricing_strategy", {}).get("tiers", [])
        if not tiers:
            tiers = pricing_data.get("tiers", [])
        return [t.get("tier") or t.get("name", "medium") for t in tiers] or ["medium"]

    @staticmethod
    def _score_experiment(market, product, angle, pricing,
                          market_data=None, product_data=None, growth_state=None):
        """给单个实验组合打分

        分数 = 市场分(0.25) + 产品分(0.25) + 角度分(0.20)
             + 定价匹配(0.15) + 历史修正(0.15)
        """
        score = 0.0
        reasons = []

        # 市场分 (0-1)
        market_score = GrowthExperimentEngine._lookup_score(
            market_data, market, "market_score"
        )
        score += 0.25 * market_score

        # 产品分 (0-1)
        product_score = GrowthExperimentEngine._lookup_score(
            product_data, product, "product_score"
        )
        score += 0.25 * product_score

        # 角度分 (0-1)
        angle_score = angle.get("score", 0.5)
        score += 0.20 * min(angle_score / 2.0, 1.0)

        # 定价匹配 (0-1)
        pricing_fit = GrowthExperimentEngine._pricing_market_fit(
            pricing, market
        )
        score += 0.15 * pricing_fit

        # 历史修正 — 过去表现好的组合加分
        hist_score = 0.5
        if growth_state:
            hist = growth_state.get("experiment_history", {}).get(
                f"{market}|{product}|{angle['id']}|{pricing}", {}
            )
            if hist.get("avg_roi", 0) > 0:
                hist_score = min(hist["avg_roi"] / 5.0, 1.5)
                reasons.append(f"hist_roi={hist['avg_roi']}")
        score += 0.15 * hist_score

        # 政策过滤（硬约束）
        policy_ok = GrowthExperimentEngine._policy_check(market, product, pricing)
        if not policy_ok:
            return None

        return {
            "market": market,
            "product": product,
            "angle_id": angle.get("id", "unknown"),
            "angle_name": angle.get("name", "Unknown"),
            "angle_hook": angle.get("hook", ""),
            "pricing_tier": pricing,
            "score": round(score, 3),
            "components": {
                "market_score": round(market_score, 3),
                "product_score": round(product_score, 3),
                "angle_score": round(angle_score, 3),
                "pricing_fit": round(pricing_fit, 3),
                "historical_boost": round(hist_score if growth_state else 0.5, 3),
            },
            "expected_roi": round(score * 5.0, 2),  # 映射到 ROI 预估
            "status": "active",
        }

    @staticmethod
    def _lookup_score(data, key, score_field):
        """从 scored 列表里查找单项分数"""
        if not data:
            return 0.5
        scored = (data.get("scored_markets") or data.get("scored_products") or
                  data.get("market_strategy", {}).get("scored_markets", []) or
                  data.get("product_strategy", {}).get("scored_products", []) or [])
        for item in scored:
            name = item.get("country") or item.get("market") or item.get("product_name") or item.get("product_id") or ""
            if name == key:
                raw = item.get(score_field, 0)
                return min(raw / 100.0, 1.0) if raw > 0 else 0.5
        return 0.5

    @staticmethod
    def _pricing_market_fit(pricing_tier, market):
        """定价与市场的匹配度

        高利润市场 → high_margin 更合适
        价格敏感市场 → discount 更合适
        """
        premium_markets = {"US", "AE", "JP", "GB", "CA", "AU", "QA", "KW", "SA", "CH", "NO"}
        price_sensitive = {"IN", "PK", "BD", "VN", "PH", "EG"}

        if pricing_tier in ("high_margin", "high", "premium"):
            return 1.0 if market in premium_markets else 0.5
        elif pricing_tier in ("discount", "low", "economy"):
            return 1.0 if market in price_sensitive else 0.3
        else:
            return 0.7  # medium / maintain

    @staticmethod
    def _policy_check(market, product, pricing):
        """政策过滤"""
        restricted_markets = {"IR", "KP", "SY", "CU", "RU"}  # 受限制市场
        if market in restricted_markets:
            return False
        return True

    @staticmethod
    def _diversify_selection(scored, max_count=12, growth_state=None):
        """多样性选择 — 避免集中在同一市场/产品"""
        if len(scored) <= max_count:
            return scored

        selected = []
        seen_markets = {}
        seen_products = {}

        for exp in scored:
            if len(selected) >= max_count:
                break

            mkt = exp["market"]
            prod = exp["product"]

            # 同一市场最多 4 个实验
            if seen_markets.get(mkt, 0) >= 4:
                continue
            # 同一产品最多 3 个实验
            if seen_products.get(prod, 0) >= 3:
                continue

            selected.append(exp)
            seen_markets[mkt] = seen_markets.get(mkt, 0) + 1
            seen_products[prod] = seen_products.get(prod, 0) + 1

        return selected

    @staticmethod
    def _inject_new_experiments(selected, all_scored, growth_state):
        """注入新实验（探索）"""
        history = growth_state.get("experiment_history", {})

        # 找出从未尝试过的组合
        new_ones = []
        tried_keys = set(history.keys())
        for exp in all_scored:
            key = f"{exp['market']}|{exp['product']}|{exp['angle_id']}|{exp['pricing_tier']}"
            if key not in tried_keys:
                new_ones.append(exp)

        if not new_ones:
            return selected

        # 替换部分实验为新组合
        replace_count = max(1, int(len(selected) * NEW_EXPERIMENT_RATIO))
        new_ones.sort(key=lambda x: x["score"], reverse=True)

        # 替换得分最低的旧实验
        selected = selected[:-replace_count] + new_ones[:replace_count]
        selected.sort(key=lambda x: x["score"], reverse=True)

        logger.info(f"Injected {min(replace_count, len(new_ones))} new experiments")

        return selected

    @staticmethod
    def get_experiment_summary(experiments):
        """实验摘要统计"""
        markets = set()
        products = set()
        angles = set()
        tiers = set()

        for exp in experiments:
            markets.add(exp["market"])
            products.add(exp["product"])
            angles.add(exp["angle_id"])
            tiers.add(exp["pricing_tier"])

        return {
            "total_experiments": len(experiments),
            "unique_markets": len(markets),
            "unique_products": len(products),
            "unique_angles": len(angles),
            "unique_pricing_tiers": len(tiers),
            "avg_score": round(
                sum(e["score"] for e in experiments) / len(experiments), 3
            ) if experiments else 0,
        }
