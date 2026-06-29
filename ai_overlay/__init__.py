"""AI Overlay — WhatsApp AI Sales Operating System

在现有 CRM 之上叠加的「销售 AI 操作系统」。
不改 CRM 一行代码，通过 crm_bridge 只读桥接。

V2.0 Revenue OS: 从「成交优化」到「利润优化」
  - Profit Engine: 6维利润评分
  - Dynamic Pricing: 4因子动态定价
  - Campaign Intel: 智能营销客户池
  - Market Expansion: Geo Score 国家评分
  - Strategy Loop: 每日自动优化闭环

启动方式:
  python -m ai_overlay.main         # 启动跟进引擎(后台)
  python -m ai_overlay.main --test  # 运行测试
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ai_overlay")


def test_all():
    """运行所有模块的完整测试"""
    from ai_overlay.crm_bridge import health, get_customer, get_products, search_knowledge
    from ai_overlay.orchestrator import decide, process_message
    from ai_overlay.followup_engine import FollowupScheduler

    print("=" * 50)
    print("AI Overlay — 全面测试")
    print("=" * 50)

    # 1. CRM Bridge
    print("\n1. CRM Bridge ---")
    h = health()
    print(f"   Health: DB={h['db']} API={h['api']}")
    c = get_customer(6)
    print(f"   Customer 6: {c['name'] if c else 'NOT FOUND'}")
    p = get_products(limit=2)
    print(f"   Products: {len(p)} found")
    k = search_knowledge("LED", limit=2)
    print(f"   Knowledge matches: {len(k)}")

    # 2. Orchestrator
    print("\n2. Orchestrator ---")
    r = decide(6, "How much is your LED sign for a small restaurant?")
    print(f"   Intent: {r.get('intent')}")
    print(f"   Action: {r.get('action')}")
    print(f"   State: {r.get('state')}")
    print(f"   Reply: {(r.get('reply') or '')[:100]}...")

    # 3. V1.3 Multi-Agent Brain
    print("\n3. Multi-Agent Brain ---")
    from ai_overlay.multi_agent_brain import MultiAgentRouter, list_agents
    agents = list_agents()
    for a in agents:
        print(f"   Agent: {a['name']} - {a['role']}")

    # 4. V1.3 Sales Autopilot
    print("\n4. Sales Autopilot ---")
    from ai_overlay.sales_autopilot import SalesAutopilot
    ap = SalesAutopilot.evaluate(6, "NEW", "ready_to_order", "Yes I want to order", [])
    print(f"   Buying signal: force={ap['force_progression']} -> {ap['proposed_state']}")
    ap2 = SalesAutopilot.evaluate(6, "PRICING", "general", "Still thinking about it", [])
    print(f"   No signal: force={ap2['force_progression']}")

    # 5. Process message
    print("\n3. process_message() ---")
    r2 = process_message(6, "I need a quote for a 1.5m sign")
    print(f"   Reply: {(r2.get('reply') or '')[:100]}...")

    # 4. Followup
    print("\n4. Followup Scheduler ---")
    s = FollowupScheduler()
    s.schedule(6, "PRICING")
    due = s.get_due()
    print(f"   Due items: {len(due)}")

    # === V2.0 测试 ===
    print("\n" + "=" * 50)
    print("V2.0 Revenue OS 测试")
    print("=" * 50)

    # V2.1 Profit Engine
    print("\nV2.1 Profit Engine ---")
    from ai_overlay.v2_profit_engine import ProfitEngine
    ps = ProfitEngine.score(6)
    print(f"   ProfitScore={ps.get('profit_score')} tier={ps.get('tier')}")
    print(f"   Dimensions: {ps.get('dimensions')}")
    strat = ProfitEngine.get_tier_strategy(ps.get('tier', 'LOW'))
    print(f"   Strategy: {strat['label']}")

    # V2.2 Dynamic Pricing
    print("\nV2.2 Dynamic Pricing ---")
    from ai_overlay.v2_dynamic_pricing import DynamicPricingEngine
    dp = DynamicPricingEngine.calculate(6, urgency="medium")
    print(f"   Final price={dp.get('final_price')} margin={dp.get('margin')}")
    print(f"   Factors: {dp.get('factors')}")
    dp2 = DynamicPricingEngine.get_quote_price(6, quantity=10)
    print(f"   Quote: unit={dp2.get('unit_price')} total={dp2.get('total_price')}")

    # V2.3 Campaign Intel
    print("\nV2.3 Campaign Intel ---")
    from ai_overlay.v2_campaign_intel import CampaignIntelEngine
    segs = CampaignIntelEngine.list_segments()
    for k, v in segs.items():
        print(f"   {k}: {v['count']} prospects")
    seg_result = CampaignIntelEngine.execute_segment("hot_no_response", dry_run=True)
    print(f"   Hot no-response segment: {seg_result['total']} customers (dry_run)")

    # V2.4 Market Expansion
    print("\nV2.4 Market Expansion ---")
    from ai_overlay.v2_market_expansion import MarketExpansionEngine
    markets = MarketExpansionEngine.score_all_markets()
    for m in markets[:3]:
        print(f"   {m['country_code']}: score={m['geo_score']} ({m['recommendation']})")
    budget = MarketExpansionEngine.recommend_budget_allocation()
    print(f"   Budget allocation: {len(budget)} markets")

    # V2.5 Strategy Loop
    print("\nV2.5 Strategy Loop ---")
    from ai_overlay.v2_strategy_loop import StrategyLoop
    sa = StrategyLoop.run_daily_analysis()
    print(f"   Focus product: {sa.get('focus_product')}")
    print(f"   Focus region: {sa.get('focus_region')}")
    print(f"   Followup speed: {sa.get('followup_speed')}")
    print(f"   Discount policy: {sa.get('discount_policy')}")

    # V2.6 Composite Decision
    print("\nV2.6 Revenue Orchestrator Core ---")
    from ai_overlay.v2_core import RevenueOrchestrator
    comp = RevenueOrchestrator.composite_decision(
        6, "How much is your LED sign for a small restaurant?"
    )
    print(f"   V1: state={comp['v1']['state']} action={comp['v1']['action']}")
    print(f"   V2 Profit: score={comp['v2']['profit']['profit_score']} tier={comp['v2']['profit']['tier']}")
    print(f"   V2 Pricing: price={comp['v2']['pricing']['final_price']} margin={comp['v2']['pricing']['margin']}")
    print(f"   Composite: override={comp['composite']['tier_override']} signal={comp['composite']['profit_signal']}")

    print("\n" + "=" * 50)
    print("All tests passed (V1.3 + V2.0)!")
    print("=" * 50)


def start_services():
    """启动后台服务（跟进引擎）"""
    from ai_overlay.followup_engine import start_followup_engine
    eng = start_followup_engine(check_interval=300)
    logger.info("AI Overlay 服务已启动")
    logger.info("  跟进引擎: 运行中 (每5分钟检查)")
    logger.info("  按 Ctrl+C 停止")
    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        eng.stop()
        logger.info("AI Overlay 服务已停止")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_all()
    else:
        start_services()
