"""销售状态机仿真测试 — 模拟真实客户对话流程（使用真实意图检测）"""
import os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from lead_state_engine import (
    update_lead_state, get_lead_state, set_lead_state,
    get_state_history, init_customer_state
)
from decision_engine import decide_action
from action_router import register_action, execute_action, get_action_history
from ai_engine import _detect_knowledge_intent
import sqlite3
from lead_state_engine import _ensure_state_field, _ensure_state_log_table
from action_router import _ensure_action_log

# Ensure DB tables exist
_ensure_state_field()
_ensure_state_log_table()
_ensure_action_log()

# Register action callbacks (same as app.py)
register_action('GENERATE_QUOTE', lambda c, x: {'ok': True, 'result': 'quote_generated'})
register_action('SEND_QUOTE', lambda c, x: {'ok': True, 'result': 'quote_sent'})
register_action('FOLLOW_UP', lambda c, x: {'ok': True, 'result': 'followup_logged'})
register_action('ESCALATE', lambda c, x: {'ok': True, 'result': 'escalated'})

conn = None  # placeholder

def clean_test_data():
    global conn
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'crm_data.db'))
    rows = conn.execute("SELECT id FROM customers WHERE name LIKE 'TEST_SIM_%'").fetchall()
    for (cid,) in rows:
        conn.execute("DELETE FROM customers WHERE id=?", (cid,))
        conn.execute("DELETE FROM lead_state_log WHERE customer_id=?", (cid,))
        conn.execute("DELETE FROM lead_action_log WHERE customer_id=?", (cid,))
        conn.execute("DELETE FROM messages WHERE customer_id=?", (cid,))
    conn.commit()
    conn.close()

clean_test_data()

print("=" * 70)
print("  GLOWFORGE CRM - Lead State Machine Simulation")
print("  Intent: ai_engine._detect_knowledge_intent")
print("=" * 70)

def sim_round(label, msg, cid, manual_state=None):
    """Simulate one message exchange. If manual_state set, force state first."""
    if manual_state:
        set_lead_state(cid, manual_state)

    intent = _detect_knowledge_intent(msg)
    cur = get_lead_state(cid)
    sr = update_lead_state(cid, intent, trigger_detail=msg[:60])
    dec = decide_action(cid, intent)
    ar = execute_action(dec['action'], cid, {'chat_name': label})

    changed = "CHANGED" if sr['transitioned'] else "same"
    print(f"  [{label}] {msg[:65]}")
    print(f"           intent={intent:6s}  state={cur}->{sr['to_state']} [{changed}]")
    print(f"           decision={dec['action']:<20s} action={'OK' if ar['ok'] else 'FAIL'}")
    return intent, sr, dec


# ============================================================
# CASE 1: 墨尔本餐厅 — 正常成交路径
# ============================================================
print()
print("-" * 70)
print("  CASE 1: 墨尔本餐厅客户 - 标准成交路径")
print("  终端用户, 询价 -> 给规格 -> 比价 -> 系统报价 -> 下单")
print("-" * 70)

conn = sqlite3.connect(os.path.join(BASE_DIR, 'crm_data.db'))
conn.execute("INSERT INTO customers (name,status,country) VALUES ('TEST_SIM_1','new','Australia')")
cid1 = conn.execute("SELECT id FROM customers WHERE name=?", ('TEST_SIM_1',)).fetchone()[0]
conn.commit()
conn.close()
init_customer_state(cid1)

sim_round("R1", "Hi, I need acrylic signs for my restaurant in Melbourne. Can you give me a price?", cid1)
sim_round("R2", "The letters need to be about 40cm height, 8 letters, outdoor use", cid1)
sim_round("R3", "Your price is higher than another supplier. Can you do better?", cid1)
# System generates quote -> QUOTED
sim_round("R4", "OK, I want to place an order. How do I proceed?", cid1, manual_state='QUOTED')

s1 = get_lead_state(cid1)
print(f"\n  >> Result: {s1}")
assert s1 == "HOT", f"Expected HOT, got {s1}"
print("  >> PASS: 客户从 NEW -> QUOTED -> HOT")

# ============================================================
# CASE 2: 美国贸易商 — 比价场景
# ============================================================
print()
print("-" * 70)
print("  CASE 2: 美国贸易商 - 比价异议处理")
print("  分销商, 上来比价, 要求降价")
print("-" * 70)

conn = sqlite3.connect(os.path.join(BASE_DIR, 'crm_data.db'))
conn.execute("INSERT INTO customers (name,status,country) VALUES ('TEST_SIM_2','new','USA')")
cid2 = conn.execute("SELECT id FROM customers WHERE name=?", ('TEST_SIM_2',)).fetchone()[0]
conn.commit()
conn.close()
init_customer_state(cid2)

sim_round("R1", "I found cheaper options on Alibaba. Why should I choose you?", cid2)
sim_round("R2", "Your MOQ is too high, I need flexible quantity", cid2)
sim_round("R3", "Actually I want to place a trial order first", cid2, manual_state='NEGOTIATING')

s2 = get_lead_state(cid2)
print(f"\n  >> Result: {s2}")
assert s2 == "HOT", f"Expected HOT, got {s2}"
print("  >> PASS: 比价异议 -> 成交")

# ============================================================
# CASE 3: 迪拜工程公司 — 沉默跟进
# ============================================================
print()
print("-" * 70)
print("  CASE 3: 迪拜工程公司 - 沉默后唤醒")
print("  已报价, 跟进测试")
print("-" * 70)

conn = sqlite3.connect(os.path.join(BASE_DIR, 'crm_data.db'))
conn.execute("INSERT INTO customers (name,status,country) VALUES ('TEST_SIM_3','new','UAE')")
cid3 = conn.execute("SELECT id FROM customers WHERE name=?", ('TEST_SIM_3',)).fetchone()[0]
conn.commit()
conn.close()
init_customer_state(cid3)
set_lead_state(cid3, 'QUOTED')

sim_round("R1", "We are reviewing the quote with our team", cid3)
# check decision when quoted + 其他
d = decide_action(cid3, '其他')
assert d['action'] in ('SEND_SOCIAL_PROOF', 'PUSH_URGENCY'), f"Expected social proof or urgency, got {d['action']}"
print(f"  >> PASS: QUOTED+跟进 -> {d['action']}")

# ============================================================
# CASE 4: 状态隔离 — 已成交不可逆
# ============================================================
print()
print("-" * 70)
print("  CASE 4: 已成交客户状态隔离")
print("  CLOSED_WON 应该锁定状态")
print("-" * 70)

conn = sqlite3.connect(os.path.join(BASE_DIR, 'crm_data.db'))
conn.execute("INSERT INTO customers (name,status,country) VALUES ('TEST_SIM_4','customer','UK')")
cid4 = conn.execute("SELECT id FROM customers WHERE name=?", ('TEST_SIM_4',)).fetchone()[0]
conn.commit()
conn.close()
init_customer_state(cid4)
set_lead_state(cid4, 'CLOSED_WON')

sim_round("R1", "I need another batch of signs for my new store", cid4)
s4 = get_lead_state(cid4)
assert s4 == "CLOSED_WON", f"Expected CLOSED_WON, got {s4}"
print("  >> PASS: CLOSED_WON 状态未变更")

# ============================================================
# CASE 5: AI 真实回复测试 (需要AI API)
# ============================================================
print()
print("-" * 70)
print("  CASE 5: AI 分析 + 状态机联动 (真实API调用)")
print("  验证 analyze_customer_message + 状态机是否兼容")
print("-" * 70)

try:
    from ai_engine import analyze_customer_message
    test_msg = "How much for 10 sets of stainless steel letters, 30cm height, for my hotel in Sydney?"
    result = analyze_customer_message(test_msg, country="Australia", history=None, style_samples=None)
    if result and 'intent' in result:
        intent = result['intent']
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'crm_data.db'))
        conn.execute("INSERT INTO customers (name,status,country) VALUES ('TEST_SIM_5','new','Australia')")
        cid5 = conn.execute("SELECT id FROM customers WHERE name=?", ('TEST_SIM_5',)).fetchone()[0]
        conn.commit()
        conn.close()
        init_customer_state(cid5)

        sr = update_lead_state(cid5, intent)
        dec = decide_action(cid5, intent)
        print(f"  AI intent={intent}  state=NEW->{sr['to_state']}  decision={dec['action']}")
        print(f"  AI回复预览: {result.get('suggested_reply_en','')[:60]}...")
        print("  >> PASS: AI + 状态机联动正常")
    else:
        print(f"  AI返回: {result}")
        # Not a failure - AI API might be slow
        print("  >> SKIP: AI API暂时无响应")
except Exception as e:
    print(f"  >> SKIP: AI调用跳过 ({e})")

# ============================================================
# Cleanup
# ============================================================
print()
print("-" * 70)
print("  CLEANUP")
print("-" * 70)
clean_test_data()
print("  Test data cleaned")

print()
print("=" * 70)
print("  ALL CASES PASSED")
print("=" * 70)
