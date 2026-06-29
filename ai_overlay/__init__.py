"""AI Overlay — WhatsApp AI Sales Operating System

在现有 CRM 之上叠加的「销售 AI 操作系统」。
不改 CRM 一行代码，通过 crm_bridge 只读桥接。

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

    # 3. Process message
    print("\n3. process_message() ---")
    r2 = process_message(6, "I need a quote for a 1.5m sign")
    print(f"   Reply: {(r2.get('reply') or '')[:100]}...")

    # 4. Followup
    print("\n4. Followup Scheduler ---")
    s = FollowupScheduler()
    s.schedule(6, "PRICING")
    due = s.get_due()
    print(f"   Due items: {len(due)}")

    print("\n" + "=" * 50)
    print("All tests passed!")
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
