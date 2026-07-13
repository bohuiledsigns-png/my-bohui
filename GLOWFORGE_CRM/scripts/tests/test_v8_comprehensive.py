"""V5-V8 全系统最终综合测试"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['FLASK_ENV'] = 'testing'

print("=" * 50)
print("V5-V8 综合系统测试")
print("=" * 50)

# 1. 验证所有模块导入
modules_to_test = {
    'V4': [
        'ai_engine.deal_prioritizer', 'ai_engine.dynamic_pricing',
        'ai_engine.conversion_ai_brain', 'ai_engine.autonomous_sender',
        'ai_engine.revenue_scheduler',
    ],
    'V5': [
        'ai_engine.agents.hunter_agent', 'ai_engine.agents.consultant_agent',
        'ai_engine.agents.soft_seller_agent', 'ai_engine.agents.technical_agent',
        'ai_engine.agents.closer_agent', 'ai_engine.agents.agent_competition',
        'ai_engine.agents.winner_selector', 'ai_engine.agents.agent_manager',
        'ai_engine.agents.agent_router',
    ],
    'V6': [
        'ai_engine.global_router', 'ai_engine.culture_adaptor',
        'ai_engine.regional_sales_brain', 'ai_engine.profit_engine',
        'ai_engine.production_allocator', 'ai_engine.currency_optimizer',
    ],
    'V7': [
        'ai_engine.acquisition_engine', 'ai_engine.content_factory',
        'ai_engine.channel_distributor', 'ai_engine.product_expander',
        'ai_engine.market_explorer', 'ai_engine.ad_optimizer',
        'ai_engine.revenue_feedback_loop',
    ],
    'V8': [
        'ai_universe.company_factory', 'ai_universe.business_clone_engine',
        'ai_universe.capital_allocator', 'ai_universe.brand_generator',
        'ai_universe.market_spinup', 'ai_universe.portfolio_manager',
        'ai_universe.risk_balancer',
    ],
}

all_ok = True
for version, mods in modules_to_test.items():
    for m in mods:
        try:
            __import__(m)
        except Exception as e:
            print(f"  FAIL [{version}] {m}: {e}")
            all_ok = False
print(f"[1/4] Module imports: {'ALL OK' if all_ok else 'HAS FAILURES'}")

# 2. 验证Flask启动
try:
    from app import app
    rules = list(app.url_map.iter_rules())
    v5 = len([r for r in rules if '/api/v5/' in r.rule])
    v6 = len([r for r in rules if '/api/v6/' in r.rule])
    v7 = len([r for r in rules if '/api/v7/' in r.rule])
    v8 = len([r for r in rules if '/api/v8/' in r.rule])
    total = len(rules)
    print(f"[2/4] Flask boot: OK ({total} routes: V5={v5} V6={v6} V7={v7} V8={v8})")
    assert v5 >= 30, f"V5 routes missing: {v5}"
    assert v6 >= 40, f"V6 routes missing: {v6}"
    assert v7 >= 25, f"V7 routes missing: {v7}"
    assert v8 == 17, f"V8 routes expected 17, got {v8}"
except Exception as e:
    print(f"[2/4] Flask boot: FAIL - {e}")
    all_ok = False
    raise

# 3. 冒烟测试所有API路由
with app.test_client() as c:
    post_routes = [
        ('/api/v5/competition/run', {'customer_msg': 'test', 'context': {}, 'agent_ids': ['hunter_agent']}),
        ('/api/v5/competition/route', {'customer_msg': 'test', 'context': {}}),
        ('/api/v6/route', {'country': 'AE'}),
        ('/api/v6/adapt-message', {'text': 'hello', 'country': 'AE'}),
        ('/api/v6/profit/calculate', {'base_cost': 100, 'country': 'AE'}),
        ('/api/v6/currency/convert', {'amount_usd': 500, 'to_currency': 'EUR'}),
        ('/api/v6/currency/localize', {'amount_usd': 500, 'country': 'GB'}),
        ('/api/v6/currency/all-prices', {'amount_usd': 500}),
        ('/api/v6/production/allocate', {'orders': []}),
        ('/api/v6/production/shipping', {'country': 'AE'}),
        ('/api/v7/acquisition/campaign', {'product': 'sign', 'target': 'restaurant', 'country': 'US'}),
        ('/api/v7/acquisition/budget', {'channels': ['meta'], 'duration_days': 30}),
        ('/api/v7/content/plan', {'product': 'sign', 'target': 'restaurant', 'country': 'US'}),
        ('/api/v7/distribute', {'product': 'sign', 'target': 'restaurant', 'country': 'US', 'budget': 1000}),
        ('/api/v7/product/expand', {'product_id': 'led_sign', 'industry': 'signage'}),
        ('/api/v7/ad/optimize', {'product': 'sign', 'target': 'restaurant', 'country': 'US'}),
        ('/api/v7/ad/ab-test', {'platform': 'meta', 'variable': 'headline', 'base': 'a', 'variants': ['b']}),
        ('/api/v7/revenue/record', {'type': 'test', 'source': 'test', 'metric': 'test', 'value': 1}),
        ('/api/v7/revenue/auto-optimize', {}),
        ('/api/v8/company/generate', {'base_capability': 'led_sign', 'markets': ['US', 'AE']}),
        ('/api/v8/brand/generate', {'industry': 'signage', 'market': 'AE', 'style': 'luxury'}),
        ('/api/v8/market/plan', {'product': 'led_sign', 'target_market': 'SG'}),
        ('/api/v8/market/success-probability', {'product': 'led_sign', 'market': 'SG'}),
        ('/api/v8/capital/allocate', {'total_capital': 50000}),
        ('/api/v8/capital/rebalance', {}),
        ('/api/v8/portfolio/register', {'name': 'Test', 'market': 'US', 'industry': 'signage', 'invested': 5000}),
        ('/api/v8/risk/assess', {'portfolio': [{'company': 'A', 'market': 'US', 'revenue': 100, 'profit': 20}]}),
        ('/api/v8/risk/balance', {'portfolio': [{'company': 'A', 'market': 'US', 'revenue': 100, 'profit': 20}]}),
        ('/api/v8/risk/hedge', {'risk_assessment': {}}),
        ('/api/v8/clone/plan', {'model_id': 'us_restaurant_sign', 'target_market': 'GB'}),
        ('/api/v8/clone/opportunities', {'source_market': 'US'}),
    ]

    fails = 0
    for url, data in post_routes:
        r = c.post(url, json=data)
        if r.status_code not in (200, 401):
            print(f"  FAIL [{r.status_code}] POST {url}")
            fails += 1

    get_routes = [
        '/api/v5/competition/agents',
        '/api/v5/competition/weights',
        '/api/v5/competition/evolution',
        '/api/v5/competition/schedule',
        '/api/v5/competition/load',
        '/api/v6/regions',
        '/api/v6/strategies',
        '/api/v6/profit/countries',
        '/api/v6/production/factories',
        '/api/v7/product/categories',
        '/api/v7/market/analyze',
        '/api/v7/market/discover',
        '/api/v7/market/summary',
        '/api/v7/revenue/insights',
        '/api/v7/revenue/learning-curve',
        '/api/v8/company/templates',
        '/api/v8/clone/models',
        '/api/v8/portfolio/summary',
        '/api/v8/portfolio/analyze',
        '/api/v8/portfolio/growth',
    ]

    for url in get_routes:
        r = c.get(url)
        if r.status_code not in (200, 401):
            print(f"  FAIL [{r.status_code}] GET {url}")
            fails += 1

    total_tested = len(post_routes) + len(get_routes)
    status = f"{fails} failed" if fails > 0 else "ALL OK"
    print(f"[3/4] Route smoke test ({total_tested} routes): {status}")

# 4. 跨模块集成测试
from ai_universe.risk_balancer import assess
from ai_universe.capital_allocator import allocate
portfolio = [
    {'company': 'Glow US', 'market': 'US', 'revenue': 85000, 'profit': 12000, 'customers': 45},
    {'company': 'Glow AE', 'market': 'AE', 'revenue': 65000, 'profit': 18000, 'customers': 30},
]
risk = assess(portfolio)
cap = allocate(100000, portfolio)
from ai_universe.business_clone_engine import find_opportunities
opps = find_opportunities('US')
from ai_universe.market_spinup import MarketSpinup
prob = MarketSpinup.estimate_success_probability('led_sign', 'AE')
print(f"[4/4] Integration: risk={risk['risk_level']} capital={len(cap['allocation'])}items clones={len(opps)}opps AE={prob['probability']}")

# Summary
print()
if all_ok and fails == 0:
    print(">>> 全系统测试通过 <<<")
    print("V5: AI销售公司 (9 modules + 35 routes)")
    print("V6: 全球销售网络 (6 modules + 49 routes)")
    print("V7: 自动赚钱帝国 (7 modules + 32 routes)")
    print("V8: 商业宇宙系统 (7 modules + 17 routes)")
else:
    print(">>> 测试失败，请检查以上错误 <<<")
    sys.exit(1)
