"""CRM Bridge — 系统隔离层

只做三件事:
  1. get_customer()   — 只读查询客户
  2. get_products()   — 只读查询产品
  3. call_crm_api()   — 通过 API 写入(报价/消息/订单)

原则:
  ❌ 禁止直接写 CRM 数据库
  ✔ 读操作走只读数据库连接
  ✔ 写操作走 CRM 现有 HTTP API
"""
import sqlite3
import json
import os
import requests as http_requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
CRM_BASE = "http://127.0.0.1:5789"  # CRM 内部地址

# ── 只读数据库连接 ──────────────────────────────────────

def _read_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")  # 强制只读
    return conn


# ── 客户查询 ────────────────────────────────────────────

def get_customer(identifier):
    """按 ID、名称或 WhatsApp ID 查找客户"""
    conn = _read_db()
    row = None
    if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
        row = conn.execute("SELECT * FROM customers WHERE id=?", (int(identifier),)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM customers WHERE name=? COLLATE NOCASE", (str(identifier),)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM customers WHERE whatsapp=? COLLATE NOCASE", (str(identifier),)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        # 解析 JSON 字段
        for field in ("tags", "products_interest", "history_summary"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
    return None


def get_customer_messages(customer_id, limit=20):
    """获取客户聊天记录（只读）"""
    conn = _read_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_customers(keyword, limit=10):
    """搜索客户"""
    conn = _read_db()
    rows = conn.execute(
        "SELECT id, name, country, lead_status, lead_score, created_at "
        "FROM customers WHERE name LIKE ? OR whatsapp LIKE ? OR company LIKE ? "
        "ORDER BY lead_score DESC LIMIT ?",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── 产品查询 ────────────────────────────────────────────

def get_products(category=None, keyword=None, limit=20):
    """查询产品库"""
    conn = _read_db()
    sql = "SELECT * FROM products WHERE status='active'"
    params = []
    if category:
        sql += " AND category=?"
        params.append(category)
    if keyword:
        sql += " AND (name LIKE ? OR description LIKE ? OR material LIKE ?)"
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        # 解析价格阶层
        if "price_tiers" in d and isinstance(d["price_tiers"], str):
            try:
                d["price_tiers"] = json.loads(d["price_tiers"])
            except (json.JSONDecodeError, TypeError):
                d["price_tiers"] = []
        results.append(d)
    return results


def get_product_categories():
    """获取产品分类列表"""
    conn = _read_db()
    rows = conn.execute(
        "SELECT DISTINCT category FROM products WHERE status='active' AND category IS NOT NULL AND category!='' "
        "ORDER BY category"
    ).fetchall()
    conn.close()
    return [r["category"] for r in rows]


def search_knowledge(query, limit=5):
    """搜索知识库（从 .txt 文件搜索）"""
    knowledge_dir = os.path.join(BASE_DIR, "knowledge")
    if not os.path.isdir(knowledge_dir):
        return []
    q = query.lower()
    results = []
    import glob
    for fp in sorted(glob.glob(os.path.join(knowledge_dir, "*.txt")))[:30]:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            if q in content.lower():
                results.append({
                    "title": os.path.splitext(os.path.basename(fp))[0],
                    "content": content[:500],
                })
                if len(results) >= limit:
                    break
        except Exception:
            continue
    return results


# ── 通过 CRM API 写入 ──────────────────────────────────

CRM_SESSION = None


def _ensure_session():
    global CRM_SESSION
    if CRM_SESSION is None:
        CRM_SESSION = http_requests.Session()
        # 用 admin 身份登录以获取 session cookie
        try:
            CRM_SESSION.post(f"{CRM_BASE}/api/login", json={
                "username": "admin", "password": "admin123"
            }, timeout=5)
        except Exception:
            pass
    return CRM_SESSION


def call_crm_api(endpoint, method="POST", data=None):
    """调用 CRM 现有 API

    支持的 endpoint:
      /api/calc/save-quote    — 保存报价
      /api/customers          — 添加客户
      /api/messages           — 添加消息
      /api/whatsapp-send      — 发送 WhatsApp
    """
    sess = _ensure_session()
    url = f"{CRM_BASE}{endpoint}"
    try:
        if method == "GET":
            resp = sess.get(url, params=data, timeout=10)
        else:
            resp = sess.post(url, json=data or {}, timeout=15)
        if resp.status_code < 400:
            return resp.json()
        return {"ok": False, "error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def save_quote(quote_data):
    """通过 API 保存报价"""
    return call_crm_api("/api/calc/save-quote", data=quote_data)


def add_customer(name, source="whatsapp", country=""):
    """通过 API 添加客户"""
    return call_crm_api("/api/customers", data={
        "name": name, "source": source, "country": country, "status": "new"
    })


def send_whatsapp(text, contact_name):
    """通过 CRM 发送 WhatsApp 消息"""
    return call_crm_api("/api/whatsapp-send", data={
        "text": text, "contact_name": contact_name
    })


def get_lead_state(customer_id):
    """获取客户销售阶段状态"""
    conn = _read_db()
    row = conn.execute(
        "SELECT lead_state, lead_status, lead_score FROM customers WHERE id=?",
        (customer_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {"lead_state": "NEW", "lead_status": "new", "lead_score": 0}


# ── 健康检查 ────────────────────────────────────────────

def health():
    """检查桥接层连通性"""
    try:
        conn = _read_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    try:
        api_ok = call_crm_api("/api/health", method="GET").get("status") == "ok"
    except Exception:
        api_ok = False
    return {"db": db_ok, "api": api_ok}
