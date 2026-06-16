"""GLOWFORGE CRM — Flask 主程序"""
import os
import sys
import json
import uuid
import threading
import time
import random
import signal
import atexit
import socket
import subprocess
import requests as http_requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from datetime import datetime
import io
import openpyxl

from database import init_db, get_stats, get_revenue_trend, get_chart_data, get_workbench, get_customers, get_customer, get_customer_detail, add_customer, update_customer, delete_customer, bulk_add_customers, add_activity_log, get_activity_logs, get_activity_logs_count
from database import get_messages, add_message, get_media, add_media, delete_media
from database import get_ai_generations, delete_ai_generation, add_ai_generation, get_ai_generation_stats
from database import get_email_settings, save_email_settings, add_email_log, get_email_log, get_all_email_log
from database import get_products, get_product, add_product, update_product, delete_product, get_product_categories
from database import get_cases, get_case, add_case, update_case, delete_case, get_case_categories
from database import get_quotes, get_quote, add_quote, update_quote, delete_quote
from database import get_users, get_user_by_username, add_user, update_user
from database import get_orders, get_order, add_order, update_order, delete_order
from database import add_timeline_entry, get_payment_dashboard, get_order_profit_stats, get_order_stats, get_commission_stats, get_production_schedule, get_production_tasks, save_production_tasks, update_production_task_status, get_production_task_defaults
from database import add_payment, get_ar_summary, get_ar_by_customer, get_payment_history, get_aging_analysis, migrate_payments_from_orders
from database import get_leads, get_lead_summary, get_lead_funnel, assign_lead, update_lead_status, update_lead_source
from database import get_leads_due_followup, get_today_followup_summary, update_last_contacted
from database import get_users, unassign_lead, claim_lead, reclaim_expired_leads, get_leads_with_pool_info
from database import add_notification, get_notifications, get_unread_count, mark_notification_read, mark_all_notifications_read, get_user_by_id, get_active_user_ids
from database import get_media_tags, add_media_tag, delete_media_tag, get_media_tags_for, update_media_tags, get_media_by_tag
from database import get_inventory_items, get_inventory_item, add_inventory_item, update_inventory_item, delete_inventory_item
from database import add_stock_movement, get_stock_movements, get_inventory_summary
from database import get_partners, get_partner, add_partner, update_partner, delete_partner
from database import get_purchase_orders, get_purchase_order, add_purchase_order, update_purchase_order, delete_purchase_order, add_po_timeline_entry
from ai_engine import translate, generate_image, generate_video, VIDEO_PRESETS, analyze_customer_message, summarize_chat, analyze_viral, rewrite_copy
from ai_engine import get_country_context, generate_customized_script, search_industry_knowledge, analyze_chat_history, parse_whatsapp_export, analyze_product_image
from ai_engine import generate_video_from_image, generate_image_volc, ask_ali, get_ai_greeting, get_ai_followup_message, clear_knowledge_base_cache
from catalog_generator import generate_catalog
from whatsapp_engine import send_text, send_image_clipboard, send_media_file, read_messages, start_monitor, stop_monitor, get_monitor_status, refresh_whatsapp_page, set_remote_server

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "glowforge-crm-2026-secret-key-change-in-production")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ========= AI 风格学习 =========
# 你手动发的消息会被保存下来，AI 学习你的语气
STYLE_FILE = os.path.join(BASE_DIR, ".communication_style.json")

def _save_style_sample(cn, en):
    import json
    samples = []
    if os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, "r", encoding="utf-8") as f:
            samples = json.load(f)
    samples.append({"cn": cn, "en": en, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    if len(samples) > 30:
        samples = samples[-30:]
    with open(STYLE_FILE, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)

def _get_style_samples(limit=5):
    import json
    if os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, "r", encoding="utf-8") as f:
            samples = json.load(f)
        return samples[-limit:]
    return []

# ========= 销售个人资料 =========
PROFILE_FILE = os.path.join(BASE_DIR, ".sales_profile.json")
_DEFAULT_PROFILE = {"name": "Philip", "title": "外贸销售", "company": "Bohui GLOWFORGE"}

def _get_profile():
    import json
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(_DEFAULT_PROFILE)

def _save_profile(data):
    import json
    profile = dict(_DEFAULT_PROFILE)
    profile.update(data)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return profile

# ========= 知识库 CRUD =========
KNOWLEDGE_DIR = os.path.join(BASE_DIR, 'knowledge')
SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts')
COUNTRIES_DIR = os.path.join(BASE_DIR, 'countries')

def _read_content_dir(directory):
    """列出目录中的txt文件"""
    files = []
    os.makedirs(directory, exist_ok=True)
    for f in sorted(os.listdir(directory)):
        if f.endswith(".txt"):
            path = os.path.join(directory, f)
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            lines = content.strip().split("\n")
            title = lines[0] if lines else f
            category = ""
            for line in lines:
                if "类别:" in line:
                    category = line.split("类别:")[-1].strip()
                    break
            files.append({"name": f, "title": title, "category": category, "size": os.path.getsize(path)})
    return files

def _read_file_or_404(directory, filename):
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _write_content_file(directory, name, content):
    if not name.endswith(".txt"):
        name += ".txt"
    path = os.path.join(directory, name)
    if os.path.exists(path):
        return None  # conflict
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True

def _update_content_file(directory, filename, content):
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True

def _delete_content_file(directory, filename):
    path = os.path.join(directory, filename)
    if os.path.exists(path):
        os.remove(path)
    return True

# 知识库
@app.route("/api/knowledge", endpoint="knowledge_list")
def api_knowledge_list():
    return jsonify(_read_content_dir(KNOWLEDGE_DIR))

@app.route("/api/knowledge/<path:filename>", endpoint="knowledge_get")
def api_knowledge_get(filename):
    content = _read_file_or_404(KNOWLEDGE_DIR, filename)
    if content is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"name": filename, "content": content})

@app.route("/api/knowledge", methods=["POST"], endpoint="knowledge_create")
def api_knowledge_create():
    data = request.json
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    if not name or not content:
        return jsonify({"error": "name and content required"}), 400
    result = _write_content_file(KNOWLEDGE_DIR, name, content)
    if result is None:
        return jsonify({"error": "已存在同名文件"}), 409
    return jsonify({"ok": True, "name": name})

@app.route("/api/knowledge/<path:filename>", methods=["PUT"], endpoint="knowledge_update")
def api_knowledge_update(filename):
    data = request.json
    if not _update_content_file(KNOWLEDGE_DIR, filename, data.get("content", "")):
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})

@app.route("/api/knowledge/<path:filename>", methods=["DELETE"], endpoint="knowledge_delete")
def api_knowledge_delete(filename):
    _delete_content_file(KNOWLEDGE_DIR, filename)
    return jsonify({"ok": True})

# 话术库
@app.route("/api/scripts", endpoint="scripts_list")
def api_scripts_list():
    return jsonify(_read_content_dir(SCRIPTS_DIR))

@app.route("/api/scripts/<path:filename>", endpoint="scripts_get")
def api_scripts_get(filename):
    content = _read_file_or_404(SCRIPTS_DIR, filename)
    if content is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"name": filename, "content": content})

@app.route("/api/scripts", methods=["POST"], endpoint="scripts_create")
def api_scripts_create():
    data = request.json
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    if not name or not content:
        return jsonify({"error": "name and content required"}), 400
    result = _write_content_file(SCRIPTS_DIR, name, content)
    if result is None:
        return jsonify({"error": "已存在同名文件"}), 409
    return jsonify({"ok": True, "name": name})

@app.route("/api/scripts/<path:filename>", methods=["PUT"], endpoint="scripts_update")
def api_scripts_update(filename):
    data = request.json
    if not _update_content_file(SCRIPTS_DIR, filename, data.get("content", "")):
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})

@app.route("/api/scripts/<path:filename>", methods=["DELETE"], endpoint="scripts_delete")
def api_scripts_delete(filename):
    _delete_content_file(SCRIPTS_DIR, filename)
    return jsonify({"ok": True})

# 国家档案
@app.route("/api/countries", endpoint="countries_list")
def api_countries_list():
    return jsonify(_read_content_dir(COUNTRIES_DIR))

@app.route("/api/countries/<path:filename>", endpoint="countries_get")
def api_countries_get(filename):
    content = _read_file_or_404(COUNTRIES_DIR, filename)
    if content is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"name": filename, "content": content})

@app.route("/api/countries", methods=["POST"], endpoint="countries_create")
def api_countries_create():
    data = request.json
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    if not name or not content:
        return jsonify({"error": "name and content required"}), 400
    result = _write_content_file(COUNTRIES_DIR, name, content)
    if result is None:
        return jsonify({"error": "已存在同名文件"}), 409
    return jsonify({"ok": True, "name": name})

@app.route("/api/countries/<path:filename>", methods=["PUT"], endpoint="countries_update")
def api_countries_update(filename):
    data = request.json
    if not _update_content_file(COUNTRIES_DIR, filename, data.get("content", "")):
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})

@app.route("/api/countries/<path:filename>", methods=["DELETE"], endpoint="countries_delete")
def api_countries_delete(filename):
    _delete_content_file(COUNTRIES_DIR, filename)
    return jsonify({"ok": True})

# 初始化数据库
init_db()


# ========= 页面 =========
@app.route("/")
def index():
    return render_template("index.html")


# ========= API: 提示词库 =========
PROMPT_DIR = os.path.join(BASE_DIR, "prompts")

def _list_prompt_files(ptype="image"):
    """列出指定类型的提示词文件"""
    d = os.path.join(PROMPT_DIR, ptype)
    os.makedirs(d, exist_ok=True)
    files = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".txt"):
            path = os.path.join(d, f)
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            # 提取标题（第一行）
            lines = content.strip().split("\n")
            title = lines[0] if lines else f
            # 提取类别标签
            category = ""
            for line in lines:
                if "类别:" in line:
                    category = line.split("类别:")[-1].strip()
                    break
            files.append({
                "name": f,
                "title": title,
                "category": category,
                "size": os.path.getsize(path)
            })
    return files

@app.route("/api/prompts")
def api_prompts():
    ptype = request.args.get("type", "image")
    return jsonify(_list_prompt_files(ptype))

@app.route("/api/prompts/<path:filename>")
def api_prompt_content(filename):
    ptype = request.args.get("type", "image")
    path = os.path.join(PROMPT_DIR, ptype, filename)
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"name": filename, "content": content})

@app.route("/api/prompts", methods=["POST"])
def api_create_prompt():
    data = request.json
    name = data.get("name", "").strip()
    ptype = data.get("type", "image")
    content = data.get("content", "").strip()
    if not name or not content:
        return jsonify({"error": "name and content required"}), 400
    if not name.endswith(".txt"):
        name += ".txt"
    path = os.path.join(PROMPT_DIR, ptype, name)
    if os.path.exists(path):
        return jsonify({"error": "已存在同名提示词"}), 409
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"ok": True, "name": name})

@app.route("/api/prompts/<path:filename>", methods=["PUT"])
def api_update_prompt(filename):
    ptype = request.args.get("type", "image")
    path = os.path.join(PROMPT_DIR, ptype, filename)
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    data = request.json
    content = data.get("content", "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"ok": True})

@app.route("/api/prompts/<path:filename>", methods=["DELETE"])
def api_delete_prompt(filename):
    ptype = request.args.get("type", "image")
    path = os.path.join(PROMPT_DIR, ptype, filename)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


# ========= API: 统计 =========
@app.route("/api/stats")
def api_stats():
    stats = get_stats()
    # 追加沉睡客户数量（最后一条消息是我们发的，且超过3天没动静）
    from database import get_db
    conn = get_db()
    dormant = conn.execute("""
        SELECT COUNT(*) FROM customers c
        WHERE (
            SELECT direction FROM messages m
            WHERE m.customer_id=c.id ORDER BY m.created_at DESC LIMIT 1
        ) = 'sent'
        AND CAST(julianday('now') - julianday(c.updated_at) AS INTEGER) >= 3
    """).fetchone()[0]
    conn.close()
    stats["dormant"] = dormant
    return jsonify(stats)

@app.route("/api/stale-customers")
def api_stale_customers():
    """沉睡客户：我们报价/发了消息后，客户超过3天没回复"""
    from database import get_db
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.company, c.status,
               CAST(julianday('now') - julianday(COALESCE(c.last_contacted_at, c.updated_at)) AS INTEGER) as days_since,
               (SELECT content_en FROM messages m WHERE m.customer_id=c.id ORDER BY m.created_at DESC LIMIT 1) as last_sent,
               (SELECT created_at FROM messages m WHERE m.customer_id=c.id ORDER BY m.created_at DESC LIMIT 1) as last_time
        FROM customers c
        WHERE (
            SELECT direction FROM messages m
            WHERE m.customer_id=c.id ORDER BY m.created_at DESC LIMIT 1
        ) = 'sent'
        AND CAST(julianday('now') - julianday(c.updated_at) AS INTEGER) >= 3
        ORDER BY days_since DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/follow-up/<int:cid>", methods=["POST"])
def api_follow_up(cid):
    """给沉睡客户发一条跟进消息"""
    from database import get_db
    conn = get_db()
    c = conn.execute("SELECT name, language FROM customers WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not c:
        return jsonify({"error": "客户不存在"}), 404

    contact_name = c["name"]
    lang = c.get("language", "English") or "English"

    # 根据天数选择不同的话术
    from database import get_messages
    msgs = get_messages(cid, limit=5)
    days = 0
    if msgs:
        from datetime import datetime
        last = msgs[-1].get("created_at", "")
        if last:
            try:
                dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                days = (datetime.now() - dt).days
            except:
                pass
    # AI生成跟进话术
    from ai_engine import ask_ali
    follow_prompt = f"""你叫Philip，是博汇Bohui GLOWFORGE工厂的销售。
你在跟进一个{lang}市场的客户「{contact_name}」，上次报价后对方没有回复。
目前已经{max(days, 3)}天没有联系了。

请用{lang}写一条简短的跟进消息，要求：
1. 语气友好自然，不要pushy
2. 简短2-3句，不要写小作文
3. 像是真人销售随手发的，不是模板
4. 不要用"I hope this message finds you well"等正式腔
5. 可以顺带提一下上次聊的内容（如果有）

直接输出跟进消息，不要解释："""
    reply = ask_ali(follow_prompt, f"最近聊天：{[(m.get('content_cn','') or m.get('content_en',''))[:80] for m in msgs[-3:]]}", max_tokens=500, timeout=30)
    if not reply:
        reply = f"Hi {contact_name}, just checking in — have you had a chance to review the quote? Happy to answer any questions."

    # 发送
    try:
        from whatsapp_engine import send_text
        send_text(reply, contact_name=contact_name)
        from database import add_message
        add_message(cid, "sent", f"[跟进] {reply[:60]}...", reply)
        _add_wa_activity("replied", cid, contact_name, f"已发送跟进消息")
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/workbench")
def api_workbench():
    return jsonify(get_workbench())


@app.route("/api/stats/revenue-trend")
def api_revenue_trend():
    months = request.args.get("months", 12, type=int)
    return jsonify(get_revenue_trend(months))


@app.route("/api/stats/chart-data")
def api_chart_data():
    return jsonify(get_chart_data())


# ========= API: 操作日志 =========
@app.route("/api/activity-logs")
def api_activity_logs():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    logs = get_activity_logs(limit, offset)
    total = get_activity_logs_count()
    return jsonify({"logs": logs, "total": total})


# ========= API: 客户 =========
@app.route("/api/customers")
def api_customers():
    return jsonify(get_customers())

@app.route("/api/customers/<int:cid>")
def api_customer(cid):
    c = get_customer(cid)
    return jsonify(c) if c else (jsonify({"error": "not found"}), 404)


@app.route("/api/customers/<int:cid>/detail")
def api_customer_detail(cid):
    """聚合客户详情"""
    detail = get_customer_detail(cid)
    if not detail:
        return jsonify({"error": "not found"}), 404
    return jsonify(detail)


@app.route("/api/customers", methods=["POST"])
def api_add_customer():
    data = request.json
    result = add_customer(
        name=data.get("name", ""),
        company=data.get("company", ""),
        whatsapp=data.get("whatsapp", ""),
        country=data.get("country", ""),
        language=data.get("language", "English"),
        status=data.get("status", "warm"),
        notes=data.get("notes", "")
    )
    uid = session.get("user_id")
    if uid and result.get("id"):
        add_activity_log(uid, "create", "customer", result["id"],
            f"创建了客户 {data.get('name','')} (ID:{result['id']})")
    return jsonify(result)

@app.route("/api/customers/<int:cid>", methods=["PUT"])
def api_update_customer(cid):
    old = get_customer(cid)
    update_customer(cid, **request.json)
    uid = session.get("user_id")
    if uid and old:
        add_activity_log(uid, "update", "customer", cid,
            f"修改了客户 {old.get('name','')} (ID:{cid})")
    return jsonify({"ok": True})

@app.route("/api/customers/<int:cid>", methods=["DELETE"])
def api_delete_customer(cid):
    old = get_customer(cid)
    delete_customer(cid)
    uid = session.get("user_id")
    if uid and old:
        add_activity_log(uid, "delete", "customer", cid,
            f"删除了客户 {old.get('name','')} (ID:{cid})")
    return jsonify({"ok": True})


# ========= API: 消息 =========
@app.route("/api/customers/<int:cid>/messages")
def api_messages(cid):
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_messages(cid, limit))

@app.route("/api/customers/<int:cid>/messages", methods=["POST"])
def api_send_message(cid):
    data = request.json
    content_cn = data.get("content_cn", "")
    content_en = data.get("content_en", "")
    direction = data.get("direction", "sent")

    add_message(cid, direction, content_cn, content_en)
    return jsonify({"ok": True})

# ==================== 订单 WhatsApp 通知 ====================
_ORDER_MSG_TEMPLATES = {
    "confirmed": {
        "en": "Dear {name}, your order {order_no} has been confirmed. We will start production soon. Thank you for your trust!",
        "zh": "亲爱的{name}，您的订单{order_no}已确认。我们将尽快安排生产。感谢您的信任！",
    },
    "in_production": {
        "en": "Dear {name}, your order {order_no} is now in production. We will keep you updated on progress.",
        "zh": "亲爱的{name}，您的订单{order_no}已进入生产阶段。我们会持续更新进度。",
    },
    "shipped": {
        "en": "Dear {name}, great news! Your order {order_no} has been shipped. We will share tracking information soon.",
        "zh": "亲爱的{name}，好消息！您的订单{order_no}已发货。物流信息将稍后提供。",
    },
    "delivered": {
        "en": "Dear {name}, your order {order_no} has been delivered. We hope you love it! Please let us know if you need anything.",
        "zh": "亲爱的{name}，您的订单{order_no}已完成交付。希望您满意！如有任何需要请随时联系我们。",
    },
    "payment_deposit": {
        "en": "Dear {name}, thank you! We have received your deposit of {currency}{amount} for order {order_no}.",
        "zh": "亲爱的{name}，感谢您！我们已收到您订单{order_no}的定金{currency}{amount}。",
    },
    "payment_balance": {
        "en": "Dear {name}, great news! We have received the final payment of {currency}{amount} for order {order_no}. Your order is now paid in full. Thank you!",
        "zh": "亲爱的{name}，好消息！我们已收到您订单{order_no}的尾款{currency}{amount}。您的订单已付清。感谢您的支持！",
    },
}

def _notify_order_status_change(order, customer, old_status, new_status):
    """Send WhatsApp notification to customer on order status change (run in bg thread)."""
    if not customer or not customer.get("whatsapp") or not customer.get("name"):
        return
    lang = (customer.get("language") or "English").lower()
    locale = "zh" if "zh" in lang or "chinese" in lang else "en"
    template = _ORDER_MSG_TEMPLATES.get(new_status, {}).get(locale)
    if not template:
        return
    text = template.format(name=customer["name"], order_no=order.get("order_no", ""), currency=order.get("currency", "USD"))
    try:
        send_text(text, contact_name=customer["name"])
        add_timeline_entry(order["id"], new_status, 0, f"[WhatsApp通知] 已通知客户订单状态变更: {old_status} → {new_status}")
    except Exception as e:
        print(f"[OrderNotify] WA send failed (oid={order['id']}, status={new_status}): {e}")

def _notify_payment_received(order, customer, ptype, amount):
    """Send WhatsApp notification to customer on payment received (run in bg thread)."""
    if not customer or not customer.get("whatsapp") or not customer.get("name"):
        return
    lang = (customer.get("language") or "English").lower()
    locale = "zh" if "zh" in lang or "chinese" in lang else "en"
    tkey = f"payment_{ptype}"
    template = _ORDER_MSG_TEMPLATES.get(tkey, {}).get(locale)
    if not template:
        return
    text = template.format(name=customer["name"], order_no=order.get("order_no", ""), amount=amount, currency=order.get("currency", "USD"))
    try:
        send_text(text, contact_name=customer["name"])
        label = "定金" if ptype == "deposit" else "尾款"
        add_timeline_entry(order["id"], "payment", 0, f"[WhatsApp通知] 已通知客户收到{label} {amount}")
    except Exception as e:
        print(f"[OrderNotify] WA send failed (oid={order['id']}, payment={ptype}): {e}")


@app.route("/api/customers/<int:cid>/send-whatsapp", methods=["POST"])
def api_send_whatsapp(cid):
    data = request.json
    text = data.get("text", "")
    content_cn = data.get("content_cn", "")
    content_en = data.get("content_en", "")

    # 查客户名用于切换聊天
    c = get_customer(cid)
    contact_name = c.get("name", "") if c else ""

    def job():
        try:
            send_text(text, contact_name=contact_name)
            add_message(cid, "sent", content_cn, content_en)
            # 手动发送的消息作为风格样本保存，AI会学习你的语气
            if content_cn and content_en:
                _save_style_sample(content_cn, content_en)
        except Exception as e:
            print(f"Send error: {e}")

    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True, "msg": "发送中"})


# ========= API: 翻译 =========
@app.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.json
    text = data.get("text", "")
    lang = data.get("language", "English")
    country = data.get("country", "")
    result = translate(text, target_language=lang, country=country)
    return jsonify({"result": result})


# ========= API: 话术生成 =========
@app.route("/api/generate-script", methods=["POST"])
def api_generate_script():
    """根据话术模板+国家上下文+客户上下文，AI生成个性化回复"""
    data = request.json
    scenario = data.get("scenario", "")
    country = data.get("country", "")
    customer_context = data.get("context", "")
    if not scenario:
        return jsonify({"error": "请选择话术场景"}), 400
    # 如果有客户ID，从数据库加载最近消息
    customer_id = data.get("customer_id")
    if customer_id and not customer_context:
        from database import get_messages
        msgs = get_messages(customer_id, limit=5)
        customer_context = "\n".join(
            f"{'【我】' if m['direction']=='sent' else '【客户】'}{m.get('content_en','') or m.get('content_cn','')}"
            for m in msgs[-5:]
        )
    result = generate_customized_script(scenario, country, customer_context)
    return jsonify(result)


# ========= API: 知识库搜索 =========
@app.route("/api/knowledge-search", methods=["POST"])
def api_knowledge_search():
    """搜索行业知识库，AI回答问题"""
    data = request.json
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "请输入问题"}), 400
    result = search_industry_knowledge(query)
    return jsonify({"result": result})


# ========= API: 生图 =========
@app.route("/api/generate-image", methods=["POST"])
def api_generate_image():
    data = request.json
    prompt = data.get("prompt", "")
    customer_id = data.get("customer_id")
    image_data = data.get("image_data", "")  # 图生图参考图(base64)

    # 图生图：提示词本身就是英文描述（客户发的图+修改要求）
    # 文生图：把中文翻译成英文
    if image_data:
        en_prompt = prompt
    else:
        en_prompt = translate(prompt) or prompt

    url, error = generate_image(en_prompt, image_data=image_data or None)
    if error:
        return jsonify({"error": error}), 500

    # 下载并保存
    try:
        import requests as req
        r = req.get(url, timeout=30)
        ext = ".png"
        filename = f"ai_{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(r.content)
        add_media(filename, filepath, "image", len(r.content), prompt, customer_id)
        add_ai_generation("image", prompt, url, filename, customer_id=customer_id,
                          metadata={"mode": "text_to_image" if not image_data else "image_to_image"})
        return jsonify({"url": url, "saved": filename, "filepath": filepath})
    except Exception as e:
        return jsonify({"url": url, "saved": None, "error": str(e)})


# ========= API: 视频生成 =========
_video_tasks = {}  # task_id -> {"status": "pending|running|done|error", "url": ..., "error": ...}
_video_task_lock = threading.Lock()

@app.route("/api/video-presets")
def api_video_presets():
    return jsonify({k: {
        "name": v["name"],
        "duration": v["duration"],
        "shot_type": v["shot_type"],
        "size": v["size"]
    } for k, v in VIDEO_PRESETS.items()})

@app.route("/api/generate-video", methods=["POST"])
def api_generate_video():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "请输入视频描述"}), 400

    size = data.get("size", "1280*720")
    duration = data.get("duration", 15)
    shot_type = data.get("shot_type", "multi")
    task_id = uuid.uuid4().hex[:12]

    with _video_task_lock:
        _video_tasks[task_id] = {"status": "pending", "url": None, "error": None}

    def _run():
        with _video_task_lock:
            _video_tasks[task_id]["status"] = "running"
        print(f"[Video] 任务{task_id}启动: {prompt[:60]}...")
        url, error = generate_video(prompt, size, duration, shot_type)
        with _video_task_lock:
            if error:
                _video_tasks[task_id]["status"] = "error"
                _video_tasks[task_id]["error"] = error
                print(f"[Video] 任务{task_id}失败: {error}")
            else:
                # 下载到本地
                try:
                    import requests as req
                    r = req.get(url, timeout=120)
                    filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
                    filepath = os.path.join(UPLOAD_DIR, filename)
                    with open(filepath, "wb") as f:
                        f.write(r.content)
                    add_media(filename, filepath, "video", len(r.content), prompt, data.get("customer_id"))
                    add_ai_generation("video", prompt, url, filename,
                                      customer_id=data.get("customer_id"),
                                      metadata={"size": size, "duration": duration, "shot_type": shot_type})
                    _video_tasks[task_id]["status"] = "done"
                    _video_tasks[task_id]["url"] = url
                    _video_tasks[task_id]["saved"] = filename
                    print(f"[Video] 任务{task_id}完成: {filename}")
                except Exception as e:
                    _video_tasks[task_id]["status"] = "error"
                    _video_tasks[task_id]["error"] = str(e)
                    _video_tasks[task_id]["url"] = url

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "task_id": task_id, "msg": "视频生成中（约1-5分钟）"})


# ========= API: 火山引擎 seedance 图生视频 =========
@app.route("/api/generate-video-from-image", methods=["POST"])
def api_generate_video_from_image():
    """上传产品图片 → seedance图生视频"""
    # 支持两种方式：上传文件 或 提供图片路径
    image_file = request.files.get("image")
    image_path = request.form.get("image_path", "")
    prompt = request.form.get("prompt", "")
    duration = int(request.form.get("duration", 5))
    customer_id = request.form.get("customer_id")

    # 保存上传的图片
    saved_path = None
    if image_file:
        import uuid
        ext = image_file.filename.rsplit(".", 1)[-1].lower() if "." in image_file.filename else "jpg"
        filename = f"seedance_{uuid.uuid4().hex[:8]}.{ext}"
        saved_path = os.path.join(UPLOAD_DIR, filename)
        image_file.save(saved_path)
    elif image_path:
        if os.path.exists(image_path):
            saved_path = image_path
        else:
            return jsonify({"error": f"图片路径不存在: {image_path}"}), 400
    else:
        return jsonify({"error": "请上传图片或提供图片路径"}), 400

    # 调用seedance
    url, error = generate_video_from_image(saved_path, prompt, duration)
    if error:
        return jsonify({"error": error}), 500

    # 下载视频到本地
    try:
        import requests as req
        r = req.get(url, timeout=120)
        vid = f"seedance_{uuid.uuid4().hex[:8]}.mp4"
        vpath = os.path.join(UPLOAD_DIR, vid)
        with open(vpath, "wb") as f:
            f.write(r.content)
        add_media(vid, vpath, "video", len(r.content),
                  f"Seedance图生视频: {prompt[:60] if prompt else '产品展示'}",
                  customer_id)
        add_ai_generation("video", f"[seedance] {prompt}", url, vid,
                          customer_id=customer_id,
                          metadata={"engine": "seedance", "source": os.path.basename(saved_path)})
        return jsonify({"ok": True, "url": url, "saved": vid, "filepath": vpath})
    except Exception as e:
        return jsonify({"ok": True, "url": url, "saved": None, "error": str(e)})


# ========= API: 火山引擎 seedream 文生图（备选） =========
@app.route("/api/generate-image-volc", methods=["POST"])
def api_generate_image_volc():
    """火山引擎seedream文生图，可作为阿里通义万相的备选"""
    data = request.json
    prompt = data.get("prompt", "")
    size = data.get("size", "2K")
    customer_id = data.get("customer_id")
    if not prompt:
        return jsonify({"error": "请输入描述"}), 400

    url, error = generate_image_volc(prompt, size)
    if error:
        return jsonify({"error": error}), 500

    # 保存
    try:
        import requests as req
        r = req.get(url, timeout=60)
        fn = f"seedream_{uuid.uuid4().hex[:8]}.png"
        fp = os.path.join(UPLOAD_DIR, fn)
        with open(fp, "wb") as f:
            f.write(r.content)
        add_media(fn, fp, "image", len(r.content), prompt, customer_id)
        add_ai_generation("image", f"[seedream] {prompt}", url, fn,
                          customer_id=customer_id,
                          metadata={"engine": "seedream"})
        return jsonify({"url": url, "saved": fn, "filepath": fp})
    except Exception as e:
        return jsonify({"url": url, "saved": None, "error": str(e)})

@app.route("/api/video-status/<task_id>")
def api_video_status(task_id):
    with _video_task_lock:
        task = _video_tasks.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404
    return jsonify(task)


# ========= API: 导入聊天记录 =========
@app.route("/api/customers/<int:cid>/import-chat", methods=["POST"])
def api_import_chat_history(cid):
    """上传WhatsApp导出的.txt聊天记录，AI分析后存入系统"""
    if "file" not in request.files:
        return jsonify({"error": "请上传文件"}), 400
    file = request.files["file"]
    if not file.filename.endswith(".txt"):
        return jsonify({"error": "仅支持.txt文件（WhatsApp导出的聊天记录）"}), 400
    try:
        raw_text = file.read().decode("utf-8", errors="replace")
    except:
        return jsonify({"error": "文件编码错误，请确认是UTF-8编码的txt文件"}), 400

    # 1. 解析消息
    parsed = parse_whatsapp_export(raw_text)
    if not parsed:
        return jsonify({"error": "无法解析聊天记录，请确认是WhatsApp导出的txt格式"}), 400

    # 2. AI分析
    analysis = analyze_chat_history(raw_text)

    return jsonify({
        "ok": True,
        "message_count": len(parsed),
        "parsed_messages": parsed[:20],  # 只返回前20条预览
        "total_messages": len(parsed),
        "analysis": analysis,
    })


@app.route("/api/customers/<int:cid>/import-chat/save", methods=["POST"])
def api_save_chat_history(cid):
    """确认保存解析后的聊天记录和AI分析到客户备注"""
    data = request.json
    analysis = data.get("analysis", {})
    parsed_messages = data.get("messages", [])

    # 保存到消息表
    from database import add_message
    saved = 0
    for msg in parsed_messages:
        content = msg.get("content", "")
        sender = msg.get("sender", "")
        # 判断方向：对方发的=received，我方发的=sent
        is_from_us = any(kw in sender.lower() for kw in ["philip", "bohui", "glowforge", "杨", "chen"])
        direction = "sent" if is_from_us else "received"
        add_message(cid, direction, content_cn=content, content_en="")
        saved += 1

    # 保存分析结果到客户备注
    from database import get_customer, update_customer
    c = get_customer(cid)
    existing_notes = (c.get("notes") or "") if c else ""
    summary_parts = []
    profile = analysis.get("customer_profile", {})
    if profile.get("interest_products"):
        summary_parts.append(f"【意向产品】{', '.join(profile['interest_products'])}")
    if analysis.get("key_needs"):
        summary_parts.append(f"【关键需求】{', '.join(analysis['key_needs'])}")
    if analysis.get("chat_summary"):
        summary_parts.append(f"【历史小结】{analysis['chat_summary']}")
    if analysis.get("decision_stage"):
        summary_parts.append(f"【阶段】{analysis['decision_stage']}")
    if analysis.get("price_sensitivity") and analysis['price_sensitivity'] != '未提及':
        summary_parts.append(f"【价格敏感度】{analysis['price_sensitivity']}")
    if analysis.get("next_steps"):
        summary_parts.append(f"【下一步】{analysis['next_steps']}")
    if analysis.get("tags"):
        summary_parts.append(f"【标签】{', '.join(analysis['tags'])}")
    if analysis.get("special_requirements"):
        summary_parts.append(f"【特殊要求】{', '.join(analysis['special_requirements'])}")
    if analysis.get("price_quoted", {}).get("has_quote"):
        summary_parts.append(f"【报价】{analysis['price_quoted'].get('quote_details', '')}")

    new_notes = (existing_notes + "\n\n" + "\n".join(summary_parts)).strip()
    update_customer(cid, notes=new_notes)

    # 更新客户语言
    lang = analysis.get("customer_profile", {}).get("language", "")
    if lang and lang in ("English", "中文"):
        update_customer(cid, language=lang)

    return jsonify({"ok": True, "saved": saved, "notes_updated": True})


# ========= API: 阅读消息 =========
@app.route("/api/read-whatsapp")
def api_read_whatsapp():
    result = read_messages()
    return jsonify({"result": result})


# ========= API: WhatsApp监控状态 =========
@app.route("/api/whatsapp-status")
def api_whatsapp_status():
    return jsonify(get_monitor_status())


@app.route("/api/whatsapp-refresh", methods=["POST"])
def api_whatsapp_refresh():
    """手动刷新 WhatsApp Web 页面（二维码过期时用）"""
    ok = refresh_whatsapp_page()
    return jsonify({"ok": ok, "msg": "刷新成功" if ok else "刷新失败"})


# ========= WhatsApp 24×7自动监控 =========
# AI自动回复总开关（True=自动回复开启，False=只录入不回复）
_auto_reply_enabled = True

# 最近自动回复活动记录（用于前端通知）
_recent_wa_activity = []
_wa_activity_lock = threading.Lock()

def _add_wa_activity(typ, customer_id, customer_name, summary):
    """添加一条活动记录"""
    entry = {
        "type": typ,  # "new_customer", "received", "replied", "error"
        "customer_id": customer_id,
        "customer_name": customer_name,
        "summary": summary,
        "time": time.strftime("%H:%M:%S")
    }
    with _wa_activity_lock:
        _recent_wa_activity.insert(0, entry)
        _recent_wa_activity[:] = _recent_wa_activity[:50]  # 最多保留50条


def _do_auto_reply(cid, chat_name, reply_en, reply_cn):
    """在独立线程中执行自动回复，不阻塞事件循环
    - 等待1-5分钟（不定时，模拟真人）
    - 发前检查是否已被手动回复
    """
    try:
        # 1-5分钟不定时，模拟真人回复节奏
        wait = random.uniform(60, 300)
        print(f"[Auto] 等待{wait:.0f}秒后回复 {chat_name}...")
        time.sleep(wait)

        # ===== 防冲突检查：等待期间是否有人工回复 =====
        latest = get_messages(cid, limit=3)
        if latest:
            # get_messages返回按时间升序，最后一条是最新的
            last = latest[-1]
            if last["direction"] == "sent":
                print(f"[Auto] ⏭ {chat_name} 等待期间已被回复，跳过AI自动回复")
                _add_wa_activity("skipped", cid, chat_name, "AI等待期间已被手动回复，跳过")
                return

        # 真正发送
        send_text(reply_en, contact_name=chat_name)
        add_message(cid, "sent", reply_cn, reply_en)
        _add_wa_activity("replied", cid, chat_name, f"已自动回复: {reply_en[:50]}...")
        print(f"[Auto] ✅ 已回复 {chat_name}")
    except Exception as e:
        _add_wa_activity("error", cid, chat_name, f"自动回复失败: {e}")
        print(f"[Auto] 回复出错: {e}")


def _whatsapp_message_handler(chat_name, messages):
    """收到新消息时自动分析+记录+回复（不会阻塞事件循环）"""
    try:
        text = messages[-1]["text"] if messages else ""
        if not text:
            return

        print(f"[Auto] 收到 {chat_name}: {text[:60]}...")

        # 查找CRM中对应的客户，找不到就自动添加
        customers = get_customers()
        profile = _get_profile()
        c = next((c for c in customers if c["name"] == chat_name), None)
        is_new = False
        if not c:
            print(f"[Auto] 新客户「{chat_name}」，自动添加到CRM")
            # 先用AI greeting分析客户（基于知识库做背调+分级）
            greeting = get_ai_greeting(customer_name=chat_name, country="", sales_name=profile.get("name", "Philip"))
            wa_country = greeting.get("country_detected", "") if greeting and not greeting.get("error") else ""
            result = add_customer(name=chat_name, status="new", source="whatsapp", lead_status="new", country=wa_country, notes="WhatsApp自动添加")
            if result.get("duplicate"):
                c = get_customer(result["id"])
            elif result.get("id"):
                c = get_customer(result["id"])
            if not c:
                print(f"[Auto] 添加客户失败")
                return
            is_new = True

            # 更新AI评分和评级
            if greeting and not greeting.get("error"):
                grade = greeting.get("customer_grade", "")
                estimated_status = "qualified" if grade in ("A", "B") else "new"
                update_lead_status(c["id"], estimated_status)
                update_lead_source(c["id"], "whatsapp")
                print(f"[Auto] AI评级={grade}, lead_status={estimated_status}, 国家={wa_country}")

        # AI分析客户消息（注入国家上下文 + 聊天历史 + 知识库）
        customer_country = c.get("country", "") if c else ""
        chat_history = get_messages(c["id"], limit=10)
        history_for_ai = []
        for m in chat_history:
            history_for_ai.append({
                "role": m["direction"],  # "received" 或 "sent"
                "content_cn": m.get("content_cn", ""),
                "content_en": m.get("content_en", "")
            })
        style_samples = _get_style_samples(5)
        analysis = analyze_customer_message(text, country=customer_country, history=history_for_ai,
                                           style_samples=style_samples, sales_name=profile.get("name", "Philip"))
        if not analysis or "error" in analysis:
            print(f"[Auto] AI分析失败: {analysis}")
            _add_wa_activity("error", c["id"], chat_name, f"AI分析失败")
            return

        translation = analysis.get("translation", text)
        reply_en = analysis.get("suggested_reply_en", "")

        # 保存收到的消息到数据库
        add_message(c["id"], "received", translation, text)

        # 记录活动
        if is_new:
            _add_wa_activity("new_customer", c["id"], chat_name, f"新客户自动添加: {text[:40]}...")
        _add_wa_activity("received", c["id"], chat_name, f"收到消息: {translation[:40]}...")

        # 自动回复（检查总开关后在独立线程执行）
        if reply_en and _auto_reply_enabled:
            reply_cn = analysis.get("suggested_reply_cn", "")
            t = threading.Thread(
                target=_do_auto_reply,
                args=(c["id"], chat_name, reply_en, reply_cn),
                daemon=True
            )
            t.start()
        else:
            print(f"[Auto] 无需回复 {chat_name}")

    except Exception as e:
        print(f"[Auto] 处理出错: {e}")


# ========= API: 聊天活动通知 =========
@app.route("/api/whatsapp-activity")
def api_wa_activity():
    """获取最近的WhatsApp自动活动（新客户、收到消息、自动回复）"""
    since = request.args.get("since", "0")
    with _wa_activity_lock:
        if since == "0":
            return jsonify(_recent_wa_activity[:10])
        try:
            idx = int(since)
            return jsonify(_recent_wa_activity[:idx])
        except:
            return jsonify(_recent_wa_activity[:10])


# ========= API: AI风格学习状态 =========
@app.route("/api/style-samples")
def api_style_samples():
    """查看AI学到了多少你的回复风格"""
    samples = _get_style_samples(30)
    return jsonify({
        "total": len(samples),
        "samples": samples
    })


# ========= API: 销售个人资料 =========
@app.route("/api/profile", methods=["GET", "POST"])
def api_profile():
    """读取/修改销售个人资料（名字、称呼等）"""
    if request.method == "POST":
        data = request.json or {}
        profile = _save_profile(data)
        return jsonify(profile)
    return jsonify(_get_profile())


# ========= API: AI自动回复开关 =========
@app.route("/api/whatsapp-auto-reply", methods=["GET", "POST"])
def api_wa_auto_reply():
    """GET获取当前状态，POST切换自动回复开关"""
    global _auto_reply_enabled
    if request.method == "POST":
        data = request.json or {}
        if "enabled" in data:
            _auto_reply_enabled = bool(data["enabled"])
        else:
            _auto_reply_enabled = not _auto_reply_enabled
        status = "开启" if _auto_reply_enabled else "关闭"
        print(f"[Auto] AI自动回复已{status}")
        _add_wa_activity("toggle", 0, "系统", f"AI自动回复已{status}")
    return jsonify({"enabled": _auto_reply_enabled})


# ========= API: 客户简报 =========
@app.route("/api/customers/<int:cid>/brief")
def api_customer_brief(cid):
    """根据历史聊天记录生成客户简报"""
    msgs = get_messages(cid, limit=50)
    summary = summarize_chat(msgs)
    c = get_customer(cid)
    return jsonify({
        "summary": summary,
        "customer": c
    })


# ========= API: 导入WhatsApp聊天历史 =========
@app.route("/api/customers/<int:cid>/import-chat", methods=["POST"])
def api_import_chat(cid):
    """从WhatsApp读取当前聊天记录，存入数据库并分析"""
    try:
        raw = read_messages()
        if not raw or raw == "读取失败":
            return jsonify({"error": "WhatsApp读取失败，请确认已打开该客户的聊天窗口"}), 400

        # 尝试解析结构化消息
        parsed = parse_whatsapp_export(raw)
        imported = 0
        if parsed and len(parsed) > 1:
            # 获取客户信息以判断哪一方是"我们"
            customer = get_customer(cid)
            customer_name = customer["name"] if customer else "客户"
            for pm in parsed:
                sender = pm.get("sender", "")
                is_me = sender and sender.lower() not in customer_name.lower()
                direction = "sent" if is_me else "received"
                content_en = pm.get("text", "")
                # 去重检查：避免重复导入
                existing = get_messages(cid, limit=3)
                if any(m.get("content_en", "") == content_en for m in existing):
                    continue
                add_message(cid, direction, content_en=content_en)
                imported += 1

        if imported == 0:
            # 未能结构化解析，整段存为收到消息
            add_message(cid, "received", content_en=raw[:2000])
            imported = 1

        # 分析导入的内容
        msgs = get_messages(cid, limit=50)
        summary = summarize_chat(msgs)
        return jsonify({
            "imported": imported,
            "summary": summary,
            "total": len(msgs)
        })
    except Exception as e:
        return jsonify({"error": f"导入失败: {str(e)}"}), 500


# ========= API: 客户意图分析 =========
@app.route("/api/analyze-message", methods=["POST"])
def api_analyze_message():
    """分析客户消息意图，返回翻译+意图+建议回复"""
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "请输入客户消息"}), 400
    result = analyze_customer_message(text)
    return jsonify(result or {"error": "分析失败"})


# ========= API: 爆款分析 =========
@app.route("/api/analyze-viral", methods=["POST"])
def api_analyze_viral():
    """分析爆款内容"""
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "请输入爆款文案"}), 400
    result = analyze_viral(text)
    return jsonify(result or {"error": "分析失败"})

@app.route("/api/rewrite-copy", methods=["POST"])
def api_rewrite_copy():
    """仿写爆款文案"""
    data = request.json
    analysis_text = data.get("analysis_text", "").strip()
    industry = data.get("industry", "发光字/亚克力")
    if not analysis_text:
        return jsonify({"error": "缺少分析内容"}), 400
    result = rewrite_copy(analysis_text, industry)
    return jsonify({"result": result or "生成失败"})

@app.route("/api/oembed")
def api_oembed():
    """通过oEmbed获取视频页面信息（YouTube/TikTok，无需API Key）"""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "缺少URL"}), 400

    oembed_url = None
    if "youtube.com" in url or "youtu.be" in url:
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    elif "tiktok.com" in url:
        oembed_url = f"https://www.tiktok.com/oembed?url={url}"
    else:
        return jsonify({"error": "仅支持YouTube和TikTok链接"}), 400

    try:
        r = http_requests.get(oembed_url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return jsonify({
                "title": data.get("title", ""),
                "author_name": data.get("author_name", ""),
                "description": data.get("description", "") or data.get("title", ""),
                "thumbnail_url": data.get("thumbnail_url", ""),
            })
        return jsonify({"error": f"oEmbed请求失败: {r.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": f"请求异常: {str(e)}"}), 502


@app.route("/api/read-and-analyze")
def api_read_and_analyze():
    """读取WhatsApp消息并分析客户意图"""
    raw = read_messages()
    if not raw:
        return jsonify({"error": "读取WhatsApp失败，请确认WhatsApp窗口已打开"})
    analysis = analyze_customer_message(raw)
    return jsonify({"raw": raw, "analysis": analysis or {}})


# ========= API: 文件管理 =========
@app.route("/api/media")
def api_media():
    ft = request.args.get("type")
    tag = request.args.get("tag")
    if tag:
        return jsonify(get_media_by_tag(tag_id=int(tag), filetype=ft))
    return jsonify(get_media(ft))

@app.route("/api/media/upload", methods=["POST"])
def api_upload_media():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    filename = f"{uuid.uuid4().hex[:8]}_{f.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    f.save(filepath)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ft = "image" if ext in ("jpg","jpeg","png","gif","bmp","webp") else "video" if ext in ("mp4","mov","avi","wmv") else "document"
    mid = add_media(filename, filepath, ft, os.path.getsize(filepath), request.form.get("description", ""))
    return jsonify({"id": mid, "filename": filename, "filepath": filepath, "filetype": ft})

@app.route("/api/media/<int:mid>", methods=["DELETE"])
def api_delete_media(mid):
    delete_media(mid)
    return jsonify({"ok": True})

@app.route("/api/media/<int:mid>/tags")
def api_media_tags_for(mid):
    return jsonify(get_media_tags_for(mid))


@app.route("/api/media/<int:mid>/tags", methods=["PUT"])
def api_update_media_tags(mid):
    data = request.json or {}
    tag_ids = data.get("tag_ids", [])
    update_media_tags(mid, tag_ids)
    return jsonify({"ok": True})


@app.route("/api/media/tags")
def api_media_tags_list():
    return jsonify(get_media_tags())


@app.route("/api/media/tags", methods=["POST"])
def api_add_media_tag():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "缺少标签名"}), 400
    tag_type = data.get("type", "general")
    color = data.get("color", "#00f2ff")
    result = add_media_tag(name, tag_type, color)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/media/tags/<int:tid>", methods=["DELETE"])
def api_delete_media_tag(tid):
    delete_media_tag(tid)
    return jsonify({"ok": True})


# ========= API: 产品视频/图片库（G盘视频库） =========
@app.route("/api/media-library")
def api_media_library():
    """列出产品视频/图片库，按分类组织"""
    from database import get_db as _get_db
    conn = _get_db()

    mtype = request.args.get("type", "video")  # video / image
    ft = "video_library" if mtype == "video" else "image_library"

    rows = conn.execute(
        "SELECT * FROM media_files WHERE filetype=? ORDER BY description ASC",
        (ft,)
    ).fetchall()
    conn.close()

    items = [dict(r) for r in rows]
    # 按分类分组
    categories = {}
    for item in items:
        cat = "未分类"
        desc = item.get("description", "")
        if "分类:" in desc:
            cat = desc.split("分类:")[1].split("|")[0].strip()
        if cat not in categories:
            categories[cat] = []
        # 提取产品名
        prod_name = ""
        if "产品:" in desc:
            prod_name = desc.split("产品:")[1].strip()
        categories[cat].append({
            "id": item["id"],
            "filename": item["filename"],
            "filepath": item["filepath"],
            "filesize": item["filesize"],
            "product_name": prod_name,
            "description": desc,
        })

    return jsonify({
        "total": len(items),
        "categories": [{"name": k, "items": v} for k, v in categories.items()]
    })


@app.route("/api/media-library/categories")
def api_media_library_categories():
    """获取视频/图片库分类列表"""
    from database import get_db as _get_db
    conn = _get_db()

    mtype = request.args.get("type", "video")
    ft = "video_library" if mtype == "video" else "image_library"

    rows = conn.execute(
        "SELECT description FROM media_files WHERE filetype=?", (ft,)
    ).fetchall()
    conn.close()

    cat_counts = {}
    for r in rows:
        desc = r["description"]
        cat = "未分类"
        if "分类:" in desc:
            cat = desc.split("分类:")[1].split("|")[0].strip()
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return jsonify([
        {"name": k, "count": v} for k, v in sorted(cat_counts.items())
    ])


@app.route("/api/media-library/search")
def api_media_library_search():
    """搜索产品视频/图片"""
    from database import get_db as _get_db
    conn = _get_db()

    q = request.args.get("q", "").strip().lower()
    mtype = request.args.get("type", "video")
    ft = "video_library" if mtype == "video" else "image_library"

    if q:
        rows = conn.execute(
            "SELECT * FROM media_files WHERE filetype=? AND (filename LIKE ? OR description LIKE ?) ORDER BY description LIMIT 50",
            (ft, f"%{q}%", f"%{q}%")
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM media_files WHERE filetype=? ORDER BY description LIMIT 50",
            (ft,)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/media-library/send-whatsapp", methods=["POST"])
def api_media_library_send():
    """从视频/图片库发送文件到WhatsApp客户"""
    from database import get_db as _get_db
    data = request.json
    media_id = data.get("media_id")
    customer_id = data.get("customer_id")

    if not media_id or not customer_id:
        return jsonify({"error": "缺少media_id或customer_id"}), 400

    conn = _get_db()
    media = conn.execute("SELECT * FROM media_files WHERE id=?", (media_id,)).fetchone()
    c = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    conn.close()

    if not media:
        return jsonify({"error": "文件不存在"}), 404
    if not c:
        return jsonify({"error": "客户不存在"}), 404

    filepath = media["filepath"]
    contact_name = c["name"]

    if not os.path.exists(filepath):
        return jsonify({"error": f"文件不存在: {filepath}"}), 404

    def job():
        try:
            send_media_file(filepath, contact_name=contact_name)
            desc = media.get("description", "")
            prod = ""
            if "产品:" in desc:
                prod = desc.split("产品:")[1].strip()
            is_video = media["filetype"] == "video_library"
            media_type_str = "视频" if is_video else "图片"
            media_type_en = "video" if is_video else "image"
            msg_cn = f"[发送产品{media_type_str}] {prod}"
            msg_en = f"Sent product {media_type_en}: {prod}"
            add_message(customer_id, "sent", msg_cn, msg_en)
            _add_wa_activity("replied", customer_id, contact_name, f"已发送产品{prod}")
        except Exception as e:
            print(f"[MediaSend] 发送失败: {e}")

    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True, "msg": "发送中"})


# ========= AI生成记录 =========
@app.route("/api/ai-generations")
def api_ai_generations():
    gtype = request.args.get("type")
    return jsonify(get_ai_generations(gtype))

@app.route("/api/ai-generations/stats")
def api_ai_generation_stats():
    return jsonify(get_ai_generation_stats())

@app.route("/api/ai-generations/<int:gid>", methods=["DELETE"])
def api_delete_ai_generation(gid):
    delete_ai_generation(gid)
    return jsonify({"ok": True})

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ========= 邮件 =========
def send_email_smtp(settings, to_email, subject, body, attachments=None):
    """底层SMTP发送，返回 (ok, error_msg)"""
    msg = MIMEMultipart()
    msg["From"] = f"{settings['from_name']} <{settings['from_email']}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if "<html" in body else "plain", "utf-8"))

    for att in (attachments or []):
        fp = att.get("filepath") or att.get("path", "")
        if not os.path.exists(fp):
            continue
        with open(fp, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{att.get("filename", os.path.basename(fp))}"')
        msg.attach(part)

    try:
        port = int(settings.get("smtp_port", 587))
        use_tls = settings.get("use_tls", True)
        if use_tls:
            if port == 465:
                srv = smtplib.SMTP_SSL(settings["smtp_host"], port, timeout=30)
            else:
                srv = smtplib.SMTP(settings["smtp_host"], port, timeout=30)
                srv.starttls()
        else:
            srv = smtplib.SMTP(settings["smtp_host"], port, timeout=30)
        if settings.get("smtp_user"):
            srv.login(settings["smtp_user"], settings.get("smtp_pass", ""))
        srv.sendmail(settings["from_email"], [to_email], msg.as_string())
        srv.quit()
        return True, ""
    except Exception as e:
        return False, str(e)

@app.route("/api/email/settings", methods=["GET", "PUT"])
def api_email_settings():
    if request.method == "PUT":
        data = request.json
        save_email_settings(data)
        return jsonify({"ok": True})
    s = get_email_settings()
    # 密码脱敏
    pw = s.get("smtp_pass", "")
    if pw and len(pw) > 4:
        s["smtp_pass"] = pw[:4] + "****"
    elif pw:
        s["smtp_pass"] = "****"
    return jsonify(s)

@app.route("/api/email/test", methods=["POST"])
def api_email_test():
    s = get_email_settings()
    ok, err = send_email_smtp(s, s["from_email"], "GLOWFORGE CRM - 测试邮件", "如果收到此邮件，SMTP配置正确 ✅")
    if ok:
        return jsonify({"ok": True, "msg": "✅ 测试邮件发送成功！请检查收件箱"})
    return jsonify({"ok": False, "msg": f"❌ 连接失败: {err}"})

@app.route("/api/customers/<int:cid>/send-email", methods=["POST"])
def api_send_email(cid):
    data = request.json
    to_email = data.get("to_email", "").strip()
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    attachments = data.get("attachments", [])
    if not to_email:
        return jsonify({"error": "请输入收件人邮箱"}), 400
    if not subject:
        return jsonify({"error": "请输入邮件主题"}), 400
    if not body:
        return jsonify({"error": "请输入邮件正文"}), 400

    settings = get_email_settings()

    def job():
        ok, err = send_email_smtp(settings, to_email, subject, body, attachments)
        if ok:
            add_email_log(cid, to_email, subject, body, attachments, "sent", "")
            add_message(cid, "sent", f"[邮件] {subject}", f"[Email] {subject}")
        else:
            add_email_log(cid, to_email, subject, body, attachments, "failed", err)
            add_message(cid, "sent", f"[邮件失败] {subject}: {err}", f"[Email Failed] {subject}: {err}")

    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True, "msg": "邮件发送中..."})

@app.route("/api/customers/<int:cid>/email-log")
def api_email_log(cid):
    return jsonify(get_email_log(cid))

@app.route("/api/email/log")
def api_email_log_all():
    return jsonify(get_all_email_log())


# ========= 产品目录 =========
@app.route("/api/products")
def api_products():
    cat = request.args.get("category")
    if cat == "__all__":
        cat = None
    return jsonify(get_products(cat))

@app.route("/api/products/categories")
def api_product_categories():
    return jsonify(get_product_categories())

@app.route("/api/products/<int:pid>")
def api_product(pid):
    p = get_product(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    return jsonify(p)

@app.route("/api/products", methods=["POST"])
def api_add_product():
    data = request.json
    pid = add_product(data)
    return jsonify({"ok": True, "id": pid})

@app.route("/api/products/<int:pid>", methods=["PUT"])
def api_update_product(pid):
    data = request.json
    update_product(pid, data)
    return jsonify({"ok": True})

@app.route("/api/products/<int:pid>", methods=["DELETE"])
def api_delete_product(pid):
    delete_product(pid)
    return jsonify({"ok": True})

# ========= 工程案例 =========
@app.route("/api/cases")
def api_cases():
    cat = request.args.get("category")
    if cat == "__all__":
        cat = None
    return jsonify(get_cases(cat))

@app.route("/api/cases/categories")
def api_case_categories():
    return jsonify(get_case_categories())

@app.route("/api/cases/<int:cid>")
def api_case(cid):
    c = get_case(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    return jsonify(c)

@app.route("/api/cases", methods=["POST"])
def api_add_case():
    data = request.json
    cid = add_case(data)
    return jsonify({"ok": True, "id": cid})

@app.route("/api/cases/<int:cid>", methods=["PUT"])
def api_update_case(cid):
    data = request.json
    update_case(cid, data)
    return jsonify({"ok": True})

@app.route("/api/cases/<int:cid>", methods=["DELETE"])
def api_delete_case(cid):
    delete_case(cid)
    return jsonify({"ok": True})

@app.route("/api/products/analyze-image", methods=["POST"])
def api_analyze_product_image():
    """上传产品图片 → AI分析 → 返回结构化产品信息 + 生图提示词"""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    import base64
    image_data = base64.b64encode(f.read()).decode("utf-8")
    image_b64 = f"data:{f.content_type or 'image/jpeg'};base64,{image_data}"
    result = analyze_product_image(image_b64)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route("/api/products/<int:pid>/quote", methods=["POST"])
def api_generate_quote(pid):
    """生成 PDF 报价单（博汇标准格式）"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)
    from datetime import datetime

    p = get_product(pid)
    if not p:
        return jsonify({"error": "产品不存在"}), 404

    data = request.json or {}
    customer_name = data.get("customer_name", "")
    notes = data.get("notes", "")

    # 报价编号 BH-YYYYMMDD-CUSTOMER-XXX
    date_str = time.strftime("%Y%m%d")
    seq = random.randint(100, 999)
    cust_code = (customer_name[:6] if customer_name else p.get("category", "PROD")).upper().replace(" ", "_")
    if not cust_code:
        cust_code = "PROD"
    quote_no = f"BH-{date_str}-{cust_code}-{seq}"

    # 目录
    quotes_dir = os.path.join(UPLOAD_DIR, "quotes")
    os.makedirs(quotes_dir, exist_ok=True)
    pdf_path = os.path.join(quotes_dir, f"{quote_no}.pdf")

    # 注册 Arial 字体（匹配博汇现有报价单）
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    arial_ok = False
    arial_paths = [r"C:\Windows\Fonts\Arial.ttf", r"C:\Windows\Fonts\arial.ttf"]
    arial_bold_paths = [r"C:\Windows\Fonts\Arialbd.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
    for ap in arial_paths:
        if os.path.exists(ap):
            try:
                pdfmetrics.registerFont(TTFont("Arial", ap))
                arial_ok = True
                break
            except:
                pass
    for ap in arial_bold_paths:
        if os.path.exists(ap):
            try:
                pdfmetrics.registerFont(TTFont("Arial-Bold", ap))
                break
            except:
                pass

    FONT = "Arial" if arial_ok else "Helvetica"
    FONT_BOLD = "Arial-Bold" if arial_ok else "Helvetica-Bold"

    # 构建 PDF
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            topMargin=18*mm, bottomMargin=18*mm,
                            leftMargin=22*mm, rightMargin=22*mm)

    styles = getSampleStyleSheet()

    s_title = ParagraphStyle("CompanyTitle", fontSize=16, leading=18,
                              fontName=FONT_BOLD, alignment=0, spaceAfter=1*mm)
    s_subtitle = ParagraphStyle("CompanySub", fontSize=10, leading=13,
                                fontName=FONT, textColor=colors.HexColor("#333"), alignment=0, spaceAfter=0.5*mm)
    s_ref = ParagraphStyle("RefLine", fontSize=9, leading=12,
                           fontName=FONT, spaceAfter=1*mm, spaceBefore=3*mm)
    s_section = ParagraphStyle("SectionHead", fontSize=12, leading=15,
                                fontName=FONT_BOLD, spaceBefore=5*mm, spaceAfter=3*mm,
                                textColor=colors.HexColor("#222"))
    s_body = ParagraphStyle("Body", fontSize=9, leading=13,
                            fontName=FONT, spaceAfter=1.5*mm, alignment=0)
    s_bold = ParagraphStyle("BodyBold", parent=s_body, fontName=FONT_BOLD)
    s_small = ParagraphStyle("Small", fontSize=8, leading=10,
                              fontName=FONT, textColor=colors.HexColor("#666"))
    s_tcell = ParagraphStyle("TCell", fontSize=8.5, leading=11, fontName=FONT, alignment=1)
    s_tcell_l = ParagraphStyle("TCellLeft", fontSize=8.5, leading=11, fontName=FONT, alignment=0)
    s_tcell_bold = ParagraphStyle("TCellBold", parent=s_tcell, fontName=FONT_BOLD)
    s_tcell_bold_l = ParagraphStyle("TCellBoldLeft", parent=s_tcell_l, fontName=FONT_BOLD)

    elements = []

    # ===== HEADER =====
    elements.append(Paragraph("Zhongshan Bohui", s_title))
    elements.append(Paragraph("Advertising Craft Products", s_subtitle))
    elements.append(Paragraph("Co., Ltd.", s_subtitle))
    elements.append(Spacer(1, 1*mm))
    elements.append(Paragraph(
        "Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China", s_small))
    elements.append(Paragraph(
        "Official Site: wa.bohui-sign.com | Tel: 13824779947", s_small))
    elements.append(Spacer(1, 2*mm))
    elements.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#222")))
    elements.append(Spacer(1, 3*mm))

    # ===== REFERENCE =====
    month_names = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    now = datetime.now()
    date_formatted = f"{month_names[now.month-1]} {now.day}, {now.year}"

    ref_data = [
        [Paragraph(f"<b>ORDER REF NO:</b>", s_ref), Paragraph(quote_no, s_ref)],
        [Paragraph(f"<b>DATE:</b>", s_ref), Paragraph(date_formatted, s_ref)],
    ]
    if customer_name:
        ref_data.append([Paragraph(f"<b>CLIENT:</b>", s_ref), Paragraph(customer_name, s_ref)])
    ref_table = Table(ref_data, colWidths=[38*mm, doc.width-38*mm])
    ref_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
    ]))
    elements.append(ref_table)
    elements.append(Spacer(1, 2*mm))

    # Status
    elements.append(Paragraph(
        "QUOTATION STATUS: OFFICIAL FINAL PROPOSAL (Tax & Service Included Version)", s_bold))
    elements.append(Spacer(1, 3*mm))

    # ===== SECTION I: SPECIFICATIONS =====
    elements.append(Paragraph("I. TECHNICAL SPECIFICATIONS & CRAFT", s_section))

    # Product name
    elements.append(Paragraph(f"<b>Product Name:</b> {p['name']}", s_body))

    # Specs
    specs = p.get("specs", {})
    if specs and isinstance(specs, dict):
        spec_lines = []
        if specs.get("material"):
            spec_lines.append(f"Material: {specs['material']}")
        if specs.get("thickness"):
            spec_lines.append(f"Thickness: {specs['thickness']}")
        if specs.get("size_range"):
            spec_lines.append(f"Dimensions: {specs['size_range']}")
        if specs.get("color_options"):
            spec_lines.append(f"Color Options: {specs['color_options']}")
        for line in spec_lines:
            elements.append(Paragraph(line, s_body))
        elements.append(Spacer(1, 1*mm))

    # Description
    if p.get("description"):
        elements.append(Paragraph(f"<b>Description:</b> {p['description']}", s_body))
        elements.append(Spacer(1, 2*mm))

    # ===== SECTION II: PRICING =====
    elements.append(Paragraph("II. PARTNER PRICING ANALYSIS", s_section))

    tiers = p.get("price_tiers", [])
    currency = p.get("currency", "USD")
    unit = p.get("unit", "个")
    min_order = p.get("min_order", 1)

    if tiers and isinstance(tiers, list) and len(tiers) > 0:
        # Header row
        hdr = [Paragraph("<b>Item</b>", s_tcell_bold_l),
               Paragraph("<b>Qty</b>", s_tcell_bold),
               Paragraph(f"<b>Net Price<br/>(excl. tax)</b>", s_tcell_bold),
               Paragraph(f"<b>10% Service<br/>Surcharge</b>", s_tcell_bold),
               Paragraph(f"<b>Final Unit<br/>Price (incl.)</b>", s_tcell_bold),
               Paragraph(f"<b>Total<br/>(incl. tax)</b>", s_tcell_bold)]

        rows = [hdr]
        for i, t in enumerate(tiers):
            qty = t.get("qty", "")
            price_str = t.get("price", "0")
            try:
                net_price = float(price_str)
            except:
                net_price = 0
            surcharge = round(net_price * 0.1, 2)
            unit_price = round(net_price + surcharge, 2)
            total = round(unit_price * (float(qty) if qty else 1), 2)

            item_name = f"{p['name']} — Tier {i+1}" if len(tiers) > 1 else p['name']
            rows.append([
                Paragraph(item_name, s_tcell_l),
                Paragraph(f"{qty} {unit}", s_tcell),
                Paragraph(f"{currency} {net_price:,.2f}", s_tcell),
                Paragraph(f"{currency} {surcharge:,.2f}", s_tcell),
                Paragraph(f"{currency} {unit_price:,.2f}", s_tcell),
                Paragraph(f"{currency} {total:,.2f}", s_tcell),
            ])

        # Summary rows
        net_total = sum(float(t.get("price", 0)) * (float(t.get("qty", 1)) if t.get("qty") else 1) for t in tiers)
        grand_total = round(net_total * 1.1, 2)

        rows.append([Paragraph("<b>Net Total (excl. tax)</b>", s_tcell_bold_l), "", "", "", "",
                     Paragraph(f"<b>{currency} {net_total:,.2f}</b>", s_tcell_bold)])
        rows.append([Paragraph(f"<b>Grand Total (Tax & Service Included)</b>", s_tcell_bold_l), "", "", "", "",
                     Paragraph(f"<b>{currency} {grand_total:,.2f}</b>", s_tcell_bold)])

        col_widths = [doc.width*0.26, doc.width*0.12, doc.width*0.16, doc.width*0.14, doc.width*0.16, doc.width*0.16]
        price_table = Table(rows, colWidths=col_widths, repeatRows=1)
        price_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2c2c2c")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-3), 0.4, colors.HexColor("#aaa")),
            ('LINEABOVE', (0,-2), (-1,-2), 0.8, colors.HexColor("#333")),
            ('LINEABOVE', (0,-1), (-1,-1), 0.8, colors.HexColor("#333")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(price_table)
        elements.append(Spacer(1, 3*mm))

    # Min order
    if min_order > 1:
        elements.append(Paragraph(f"Minimum Order: {min_order} {unit}", s_body))
        elements.append(Spacer(1, 2*mm))

    # Notes
    if notes:
        elements.append(Paragraph(f"Notes: {notes}", s_body))
        elements.append(Spacer(1, 3*mm))

    # ===== SIGNATURE =====
    elements.append(Spacer(1, 5*mm))
    elements.append(HRFlowable(width="60%", thickness=0.5, color=colors.HexColor("#999")))
    elements.append(Spacer(1, 1*mm))
    elements.append(Paragraph("<b>Authorized Signature:</b>", s_body))
    elements.append(Paragraph("Yang Junliang", s_body))
    elements.append(Paragraph("COO | Zhongshan Bohui Advertising Craft Products Co., Ltd.", s_small))

    # ===== FOOTER =====
    elements.append(Spacer(1, 8*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#ccc")))
    elements.append(Spacer(1, 1*mm))
    footer = (f"Zhongshan Bohui Advertising Craft Products Co., Ltd. | "
              f"Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China | "
              f"Official Site: wa.bohui-sign.com | Tel: 13824779947 | {quote_no}")
    elements.append(Paragraph(footer, ParagraphStyle("Footer", fontSize=7, leading=9,
                                                      fontName="Helvetica", textColor=colors.HexColor("#888"),
                                                      alignment=1)))

    doc.build(elements)

    # 注册到文件库
    fsize = os.path.getsize(pdf_path)
    fname = f"{quote_no}.pdf"
    add_media(f"Quote-{p['name']}-{quote_no}.pdf", pdf_path, "document", fsize)

    return jsonify({
        "ok": True,
        "quote_no": quote_no,
        "path": pdf_path,
        "url": f"/uploads/quotes/{fname}",
        "filename": f"Quote-{p['name']}-{quote_no}.pdf",
    })


# ========= 报价管理 =========
@app.route("/api/quotes")
def api_quotes():
    status = request.args.get("status")
    cid = request.args.get("customer_id", type=int)
    return jsonify(get_quotes(status, cid))

@app.route("/api/quotes/<int:qid>")
def api_quote(qid):
    q = get_quote(qid)
    return jsonify(q) if q else (jsonify({"error": "not found"}), 404)

@app.route("/api/quotes", methods=["POST"])
def api_add_quote():
    data = request.json
    result = add_quote(data)
    uid = session.get("user_id")
    if uid and result.get("id"):
        add_activity_log(uid, "create", "quote", result["id"],
            f"创建了报价 {result.get('quote_no','')} (ID:{result['id']})")
    return jsonify(result)

@app.route("/api/quotes/<int:qid>", methods=["PUT"])
def api_update_quote(qid):
    data = request.json
    q = get_quote(qid)
    update_quote(qid, data)
    uid = session.get("user_id")
    if uid and q:
        add_activity_log(uid, "update", "quote", qid,
            f"修改了报价 {q.get('quote_no','')} (ID:{qid})")
    return jsonify({"ok": True})

@app.route("/api/quotes/<int:qid>", methods=["DELETE"])
def api_delete_quote(qid):
    q = get_quote(qid)
    delete_quote(qid)
    uid = session.get("user_id")
    if uid and q:
        add_activity_log(uid, "delete", "quote", qid,
            f"删除了报价 {q.get('quote_no','')} (ID:{qid})")
    return jsonify({"ok": True})

@app.route("/api/quotes/<int:qid>/send", methods=["POST"])
def api_send_quote(qid):
    q = get_quote(qid)
    if not q:
        return jsonify({"error": "报价单不存在"}), 404
    data = request.json or {}
    contact_name = data.get("contact_name", "")
    text = data.get("text", f"Quote {q['quote_no']} — Please check the attached quotation.")
    uid = session.get("user_id")
    if uid and q:
        add_activity_log(uid, "send", "quote", qid,
            f"发送了报价 {q.get('quote_no','')} 给客户 {q.get('customer_id','')}")
    def job():
        try:
            from whatsapp_engine import send_text, send_media_file
            if q.get("pdf_path") and os.path.exists(q["pdf_path"]):
                send_media_file(q["pdf_path"], text, contact_name=contact_name)
            else:
                send_text(text, contact_name=contact_name)
            update_quote(qid, {"status": "sent"})
        except Exception as e:
            print(f"[Quote] send error: {e}")
    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True, "msg": "发送中"})


# ========= 产品目录 =========
@app.route("/api/generate-catalog", methods=["POST"])
def api_generate_catalog():
    """生成高级感PDF产品目录"""
    data = request.json or {}
    cat = data.get("category", "__all__")
    lang = data.get("language", "bilingual")
    title = data.get("title", "GLOWFORGE Product Catalog")

    def job():
        try:
            generate_catalog(category_filter=cat, language=lang, title=title)
        except Exception as e:
            print(f"[Catalog] 生成失败: {e}")

    # Run in thread for large catalogs
    import threading
    threading.Thread(target=job, daemon=True).start()

    return jsonify({"ok": True, "msg": "目录生成中，请稍后查看 uploads/catalogs/ 目录"})


@app.route("/api/catalogs")
def api_catalogs():
    """列出已生成的产品目录"""
    cat_dir = os.path.join(UPLOAD_DIR, "catalogs")
    if not os.path.isdir(cat_dir):
        return jsonify([])
    files = []
    for f in sorted(os.listdir(cat_dir), reverse=True):
        if f.endswith(".pdf"):
            fpath = os.path.join(cat_dir, f)
            files.append({
                "name": f,
                "size": os.path.getsize(fpath),
                "mtime": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                "url": f"/uploads/catalogs/{f}",
            })
    return jsonify(files)


# ==================== 报价计算器 PDF 生成 ====================
CALC_PRODUCT_SPECS = {
    "front": {"name":"Front-Lit LED Letters","craft":"Front-illuminated LED letters. Face illumination via 5mm high-transparency milky white acrylic sheet. High-brightness SMD LED beads, uniform light distribution without dark spots.","install":"Bottom stainless steel base with M4×40mm threaded rod mounting + industrial adhesive. Includes 1:1 installation template."},
    "back": {"name":"Halo Backlit LED Letters","craft":"Halo backlit LED letters. Light emitted from the back creating a soft halo/glow effect on the mounting surface. 5mm high-transparency acrylic for even light diffusion.","install":"Stand-off mounting from wall surface. Includes M4 threaded rods + 1:1 installation template."},
    "double": {"name":"Double-Sided Illuminated Letters","craft":"Double-sided illuminated letters. Front & back both fitted with 5mm high-transparency acrylic for even light transmission. Overall thickness with lighting chamber.","install":"Suspended or wall-mounted. Includes M4 hardware + 1:1 installation template."},
    "bottom": {"name":"Bottom-Lit LED Letters","craft":"Bottom-lit LED letters. Light emitted from the base channel creating a floating illusion effect on the mounting surface.","install":"Surface mounted with concealed base channel. Includes mounting hardware + template."},
    "rgb": {"name":"RGB Full-Color Dynamic Letters","craft":"RGB full-color dynamic LED letters. Built-in waterproof LED light strips with T8 controller for color management — static colors, fading, flashing, and gradient effects.","install":"Bottom stainless steel base. Includes RGB controller + waterproof connectors + 1:1 installation template."},
    "neon": {"name":"LED Neon Flex Letters","craft":"LED neon flex letters. Flexible silicone LED neon tube, energy-efficient, uniform brightness, 360° seamless bend. Durable for outdoor use.","install":"Aluminum backing frame with mounting clips. Pre-wired with LED driver."},
    "mini": {"name":"Mini LED Illuminated Letters","craft":"Mini LED illuminated letters. Compact SMD LED, high brightness density. Suitable for indoor signage and detail-oriented applications.","install":"Surface mounting with mini stand-offs. Includes 1:1 template."},
    "metal": {"name":"Solid Metal Letters (Non-Illuminated)","craft":"Solid metal letters, non-illuminated. Precision laser-cut, seamless welding, grinding, polishing to mirror/brushed finish.","install":"Direct surface mounting with industrial adhesive and/or mechanical fixings."},
    "acrylic_display": {"name":"Acrylic Display Signage","craft":"Acrylic display signage. Premium acrylic sheet with reverse UV printing available for vibrant graphics. High transparency and gloss.","install":"Stand-off wall mounting or free-standing base option."},
    "flat": {"name":"Flat Metal Letters (Non-Illuminated)","craft":"Flat metal letters, non-illuminated. Laser-cut from metal plate. Clean edges, deburred finish.","install":"Direct surface mounting with adhesive pads or screws."},
}

@app.route("/api/calc/pdf", methods=["POST"])
def api_calc_pdf():
    """Generate professional ReportLab PDF quotation from calculator data"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Register fonts
    FONT_DIR = "C:/Windows/Fonts"
    for f in [("SimSun","simsun.ttc"),("SimHei","simhei.ttf"),
               ("MSYH","msyh.ttc"),("MSYHBD","msyhbd.ttc"),
               ("Arial","arial.ttf"),("ArialBD","arialbd.ttf")]:
        try:
            pdfmetrics.registerFont(TTFont(f[0], os.path.join(FONT_DIR, f[1])))
        except:
            pass

    # Colours matching Bohui quote style
    C_PRI    = HexColor("#1a237e")
    C_ACC    = HexColor("#283593")
    C_THDR   = HexColor("#1a237e")
    C_TALT   = HexColor("#f5f5f5")
    C_DARK   = HexColor("#212121")
    C_MID    = HexColor("#616161")
    C_BORD   = HexColor("#c5cae9")
    C_RED    = HexColor("#c62828")
    C_TBG    = HexColor("#eef2ff")
    C_GBG    = HexColor("#fff3e0")

    PAGE_W, PAGE_H = A4
    ML, MR, MT, MB = 50, 50, 50, 45
    CW = PAGE_W - ML - MR

    def ps(name, font, size, color=C_DARK, align=TA_LEFT, leading=None, before=0, after=0):
        return ParagraphStyle(name, fontName=font, fontSize=size, textColor=color,
                              alignment=align, leading=leading or size*1.4,
                              spaceBefore=before, spaceAfter=after)

    S = {
        "co_name":ps("co_name","ArialBD",22,C_PRI,leading=28),
        "co_addr":ps("co_addr","Arial",9,C_DARK,leading=13),
        "ref":ps("ref","ArialBD",12,C_PRI,TA_RIGHT,leading=15),
        "date":ps("date","Arial",9,C_MID,TA_RIGHT,leading=12),
        "status":ps("status","ArialBD",13,C_RED,TA_CENTER,leading=17,before=2,after=6),
        "sec_hdr":ps("sec_hdr","ArialBD",11,C_PRI,leading=16,before=10,after=4),
        "spec_lbl":ps("spec_lbl","ArialBD",8.5,C_ACC,before=4,after=1,leading=13),
        "spec_it":ps("spec_it","Arial",8.5,C_DARK,after=1,leading=13),
        "spec_det":ps("spec_det","Arial",8,C_DARK,after=1,leading=12),
        "tbl_hdr":ps("tbl_hdr","ArialBD",8,white,TA_CENTER,leading=10),
        "tbl_cell":ps("tbl_cell","Arial",8,C_DARK,TA_CENTER,leading=10),
        "tbl_l":ps("tbl_l","Arial",8,C_DARK,TA_LEFT,leading=10),
        "net_lbl":ps("net_lbl","ArialBD",8.5,C_DARK,TA_RIGHT,leading=11),
        "net_val":ps("net_val","ArialBD",9,C_PRI,TA_CENTER,leading=11),
        "grand_lbl":ps("grand_lbl","ArialBD",11,C_DARK,TA_RIGHT,leading=14),
        "grand_val":ps("grand_val","ArialBD",12,C_RED,TA_CENTER,leading=15),
        "sig_lbl":ps("sig_lbl","Arial",8,C_MID,TA_RIGHT,leading=10),
        "sig_txt":ps("sig_txt","ArialBD",10,C_DARK,leading=13),
        "footer":ps("footer","Arial",7,C_MID,TA_CENTER,leading=9),
        "note":ps("note","Arial",8,C_DARK,leading=12,before=2,after=1),
        "note_bold":ps("note_bold","ArialBD",8.5,C_ACC,leading=13,before=4,after=1),
    }

    data = request.json or {}
    ref_no = data.get("ref", "BH-000000-000")
    date_str = data.get("date", "")
    client_name = data.get("client", "—")
    currency = data.get("currency", "CNY")
    markup_pct = int(data.get("markupPct", 30))
    exchange_rate = float(data.get("exchangeRate", 6.8))

    ptype = data.get("productType", "front")
    mat_type = data.get("material", "ss304")
    mat_label = data.get("materialLabel", "304 Stainless Steel")
    electro_color = data.get("electroColor", "")
    is_electro = data.get("isElectro", False)
    kelvin = data.get("kelvin", "6000K-6500K / Cool White")
    items = data.get("items", [{"w":50,"h":50,"thick":8,"qty":1}])
    total_qty = sum(it.get("qty",1) for it in items)
    total_len_cm = sum(max(it.get("w",0),it.get("h",0)) * it.get("qty",1) for it in items)

    box_size = data.get("boxSize", "0×0×0cm")
    sea_freight = data.get("seaFreight", "3969")
    air_freight = data.get("airFreight", "7677")

    cost_items = data.get("costBreakdown", {})
    formal_total = data.get("formalTotal", "0")

    # Build spec descriptions from product type
    spec = CALC_PRODUCT_SPECS.get(ptype, CALC_PRODUCT_SPECS["front"])
    prod_name = spec["name"]
    craft_desc = spec["craft"]
    install_desc = spec["install"]

    # Material description
    if is_electro:
        mat_desc = f"{mat_label} stainless steel, {electro_color} electroplating finish, corrosion-resistant, premium appearance."
    elif "ss" in mat_type:
        mat_desc = f"{mat_label}, precision laser-cut, seamless welding, grinding and polishing fine finish."
    elif mat_type == "zn":
        mat_desc = "Galvanized steel plate, durable and cost-effective."
    elif mat_type == "zn_paint":
        mat_desc = "Galvanized steel plate with painted finish, weather-resistant."
    else:
        mat_desc = mat_label

    # Build specs list for PDF
    specs_list = []
    specs_list.append(("Product Type:", prod_name))
    specs_list.append(("Material:", mat_desc))
    if is_electro:
        specs_list.append(("Plating Finish:", f"{electro_color} electroplating — uniform color, anti-corrosion."))
    specs_list.append(("Craft & Construction:", craft_desc))
    specs_list.append(("LED & Lighting:", f"Color temperature: {kelvin}. Even illumination."))

    # Power description
    power_desc = data.get("powerDesc", "Mean Well 400W 12V power supply")
    specs_list.append(("Power Supply:", power_desc))
    specs_list.append(("Dimensions:", ', '.join(f"{it['w']}×{it['h']}×{it['thick']}cm ×{it['qty']}" for it in items)))
    specs_list.append(("Installation:", install_desc))
    specs_list.append(("Packaging:", "15mm thick plywood crate, pearl cotton foam interior. Shockproof, moisture-proof for international shipping. External size: " + box_size))

    # Build table rows
    price_items = data.get("priceItems", [])
    net_total_val = data.get("netTotal", "0")
    grand_total_val = data.get("grandTotal", "0")

    def cell(t):
        return Paragraph(str(t), S["tbl_cell"])

    def spec_bold(t):
        return Paragraph(f"<b>{t}</b>", S["spec_lbl"])

    def spec_item(l, d):
        return Paragraph(f"<b>{l}</b> {d}", S["spec_it"])

    def spec_detail(d):
        return Paragraph(f"\xa0\xa0\xa0{d}", S["spec_det"])

    # Generate PDF
    pdf_dir = os.path.join(UPLOAD_DIR, "quotes")
    os.makedirs(pdf_dir, exist_ok=True)
    safe_ref = ref_no.replace("/","-").replace("\\","-")
    output_path = os.path.join(pdf_dir, f"QUOTE_{safe_ref}.pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB,
                            title=f"Bohui Quote {ref_no}",
                            author="Bohui Advertising Craft")
    story = []

    # ── HEADER ──
    left = [
        Paragraph("Zhongshan Bohui Advertising Craft Products Co., Ltd.", S["co_name"]),
        Paragraph("Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China 528415", S["co_addr"]),
        Paragraph("Official Site: wa.bohui-sign.com | Tel: +86 13824779947", S["co_addr"]),
    ]
    right = [
        Paragraph(f"ORDER REF NO: {ref_no}", S["ref"]),
        Paragraph(f"DATE: {date_str}", S["date"]),
    ]
    hdr = Table([[left, right]], colWidths=[CW*0.6, CW*0.4])
    hdr.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(0,0),0),
        ('RIGHTPADDING',(1,1),(1,1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
    ]))
    story.append(hdr)
    story.append(Spacer(1,4))
    story.append(HRFlowable(width="100%", thickness=1, color=C_PRI, spaceAfter=6, spaceBefore=2))
    story.append(Paragraph("OFFICIAL FINAL PROPOSAL (Tax & Service Fee Included)", S["status"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORD, spaceAfter=8, spaceBefore=2))

    # CLIENT
    story.append(Paragraph(f"<b>CLIENT:</b> {client_name}", ps("client","Arial",10,C_DARK,leading=14,before=4,after=8)))

    # ── SECTION I: SPECS ──
    story.append(Paragraph("I. TECHNICAL SPECIFICATIONS & CRAFT", S["sec_hdr"]))
    story.append(Spacer(1,2))
    for label, desc in specs_list:
        story.append(Paragraph(f"<b>{label}</b> {desc}", S["spec_it"]))
    story.append(Spacer(1,10))

    # ── SECTION II: PRICING ──
    story.append(Paragraph("II. PARTNER PRICING ANALYSIS", S["sec_hdr"]))
    story.append(Spacer(1,6))

    col_w = [CW*0.20, CW*0.09, CW*0.15, CW*0.13, CW*0.16, CW*0.27]

    def h(t):
        return Paragraph(t, S["tbl_hdr"])

    sym = "¥" if currency == "CNY" else "$"
    rate_note = f" (1 USD = {exchange_rate} CNY)" if currency == "CNY" else ""

    tbl_rows = [
        [h("Item"), h("Qty"),
         h(f"Net Price<br/><font size=6>(excl. tax){rate_note}</font>"),
         h("10% Service<br/><font size=6>Surcharge</font>"),
         h("Final Unit<br/><font size=6>Price (incl.)</font>"),
         h("Total Subtotal<br/><font size=6>(incl. tax)</font>")],
    ]

    for pi in price_items:
        item_desc = pi.get("item") or pi.get("desc", "Item")
        net_val   = pi.get("netUnit") or pi.get("net", "0")
        unit_val  = pi.get("unitPrice") or pi.get("unit", "0")
        tbl_rows.append([
            Paragraph(str(item_desc), S["tbl_l"]),
            Paragraph(str(pi.get("qty","")), S["tbl_l"]),
            cell(f"{sym}{net_val}"),
            cell(f"{sym}{pi.get('service','0')}"),
            cell(f"{sym}{unit_val}"),
            cell(f"{sym}{pi.get('total','0')}"),
        ])

    n_data = len(tbl_rows)
    tbl_rows.append([
        Paragraph("Net Total (excl. tax)", S["net_lbl"]),
        cell(""), cell(""), cell(""), cell(""),
        Paragraph(f"{sym}{net_total_val} (RMB)", S["net_val"])])
    tbl_rows.append([
        Paragraph("Grand Total (Tax & Service Included)", S["grand_lbl"]),
        cell(""), cell(""), cell(""), cell(""),
        Paragraph(f"{sym}{grand_total_val} (RMB)", S["grand_val"])])

    tbl = Table(tbl_rows, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ('BACKGROUND',(0,0),(-1,0),C_THDR),
        ('TEXTCOLOR',(0,0),(-1,0),white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('GRID',(0,0),(-1,0),0.5,C_BORD),
        ('GRID',(0,1),(-1,n_data-1),0.5,C_BORD),
        ('TOPPADDING',(0,0),(-1,-1),5),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),5),
        ('RIGHTPADDING',(0,0),(-1,-1),5),
        ('ALIGN',(0,1),(0,-1),'LEFT'),
    ]
    for idx in range(1, n_data):
        if idx % 2 == 1:
            tbl_style.append(('BACKGROUND',(0,idx),(-1,idx),C_TALT))
    tbl_style += [
        ('SPAN',(0,-2),(4,-2)),
        ('BACKGROUND',(0,-2),(-1,-2),C_TBG),
        ('LINEABOVE',(0,-2),(-1,-2),1,C_PRI),
        ('LINEBELOW',(0,-2),(-1,-2),0.5,C_BORD),
        ('SPAN',(0,-1),(4,-1)),
        ('BACKGROUND',(0,-1),(-1,-1),C_GBG),
        ('LINEABOVE',(0,-1),(-1,-1),1.5,C_RED),
        ('LINEBELOW',(0,-1),(-1,-1),1.5,C_RED),
        ('TOPPADDING',(0,-1),(-1,-1),8),
        ('BOTTOMPADDING',(0,-1),(-1,-1),8),
    ]
    tbl.setStyle(tbl_style)
    story.append(tbl)
    story.append(Spacer(1,8))

    # ── Formal Total (Marked Up) ──
    formal_total_val = data.get("formalTotal", grand_total_val)
    formal_sym = "¥" if currency == "CNY" else "$"
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph(
        f"<b>FORMAL QUOTATION PRICE (including +{markup_pct}% markup):</b>"
        f" <font color='#c62828' size=14>{formal_sym}{formal_total_val}</font>",
        ps("formal","ArialBD",10,C_DARK,TA_CENTER,leading=16,before=4,after=4)))

    # ── Notes ──
    notes = [
        ("Markup:", f"+{markup_pct}% markup applied to base cost covering business operation fees, freight forwarder handling, warehousing, customer negotiation reserve, and variable cost fluctuations."),
        ("Marking:", "All-inclusive: materials, processing, accessories, crate, shipping, customs, delivery." if currency=="CNY" else "All-inclusive: materials, processing, accessories, crate, shipping, customs, delivery."),
        ("Payment:", "50% deposit to start production. 50% balance before shipment."),
        ("Lead Time:", "10 working days (counted from day after deposit received)."),
        ("Validity:", "Quote valid 30 days from date of issue."),
        ("", None),
        ("SHIPPING OPTIONS (DDU — Delivered Duty Unpaid):", None),
        ("", f"Sea freight: {sym}{sea_freight} — Transit: 28-35 days after sailing."),
        ("", f"Air freight: {sym}{air_freight} — Transit: 3-5 working days after departure."),
    ]

    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORD, spaceAfter=4, spaceBefore=2))
    for label, desc in notes:
        if label and desc:
            story.append(Paragraph(f"<b>{label}</b> {desc}", S["note"]))
        elif label and not desc:
            story.append(Paragraph(f"<b>{label}</b>", S["note_bold"]))
        elif desc:
            story.append(Paragraph(f"\xa0\xa0\xa0{desc}", S["note"]))
    story.append(Spacer(1,12))

    # ── Signature ──
    sig = Table([
        [Paragraph("Authorized Signature:", S["sig_lbl"]),
         Paragraph("Yang Junliang<br/><font size=7>COO | Zhongshan Bohui Advertising Craft Products Co., Ltd.</font>",
                   S["sig_txt"])]
    ], colWidths=[CW*0.30, CW*0.70])
    sig.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ('LINEABOVE',(0,0),(-1,0),1,C_PRI),
    ]))
    story.append(sig)
    story.append(Spacer(1,18))

    # ── Footer ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph(
        "Zhongshan Bohui Advertising Craft Products Co., Ltd. | "
        "Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China<br/>"
        f"Official Site: wa.bohui-sign.com | Tel: +86 13824779947 | {ref_no}",
        S["footer"]
    ))

    doc.build(story)

    # Return the PDF file
    return send_from_directory(pdf_dir, f"QUOTE_{safe_ref}.pdf",
                               mimetype="application/pdf",
                               as_attachment=True,
                               download_name=f"QUOTE_{safe_ref}.pdf")


# ==================== AI 润色正式报价 ====================

def _build_ai_polish_prompt(ptype, mat_label, is_electro, electro_color, kelvin,
                             items, total_qty, total_len_cm, power_desc, has_acrylic, is_rgb):
    """Build a prompt for AI to write professional product description."""
    item_str = ', '.join(f"{it['w']}×{it['h']}×{it['thick']}cm ×{it['qty']}pcs" for it in items)
    prompt = f"""You are a professional sales engineer for Zhongshan Bohui Advertising Craft Products Co., Ltd., a premium LED sign manufacturer. Write a formal, polished product description for this quotation in English.

PRODUCT TYPE: {ptype}
MATERIAL: {mat_label}{f', {electro_color} electroplating finish' if is_electro else ''}
COLOR TEMPERATURE: {kelvin}
DIMENSIONS: {item_str} (Total {total_qty} characters)
POWER: {power_desc}
ACRYLIC: {"Yes, 5mm high-transparency milky white acrylic" if has_acrylic else "No"}
RGB: {"Yes, full-color dynamic LED" if is_rgb else "No"}

Please generate a professional quotation description with these 6 sections. Each section should be 1-2 sentences, formal business English:

1) PRODUCT: One-line product name
2) MATERIAL & FINISH: Describe the material and any surface treatment
3) CRAFT & CONSTRUCTION: How it's made (laser cutting, welding, polishing, etc.)
4) LED & LIGHTING: LED specs, color temp, illumination effect
5) INSTALLATION: How it's mounted
6) PACKAGING: 15mm plywood crate with foam interior

IMPORTANT: Do NOT mention any markup, discount, or internal pricing. This is a customer-facing quotation.
Respond in this format:
PRODUCT: <text>
MATERIAL: <text>
CRAFT: <text>
LIGHTING: <text>
INSTALLATION: <text>
PACKAGING: <text>"""
    return prompt


@app.route("/api/calc/ai-quote", methods=["POST"])
def api_calc_ai_quote():
    """Generate AI-polished formal quotation PDF (customer-ready)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Register fonts
    FONT_DIR = "C:/Windows/Fonts"
    for f in [("SimSun","simsun.ttc"),("SimHei","simhei.ttf"),
               ("MSYH","msyh.ttc"),("MSYHBD","msyhbd.ttc"),
               ("Arial","arial.ttf"),("ArialBD","arialbd.ttf")]:
        try:
            pdfmetrics.registerFont(TTFont(f[0], os.path.join(FONT_DIR, f[1])))
        except:
            pass

    C_PRI = HexColor("#1a237e")
    C_ACC = HexColor("#283593")
    C_TALT = HexColor("#f5f5f5")
    C_DARK = HexColor("#212121")
    C_MID = HexColor("#616161")
    C_BORD = HexColor("#c5cae9")
    C_RED = HexColor("#c62828")

    PAGE_W, PAGE_H = A4
    ML, MR, MT, MB = 50, 50, 50, 45
    CW = PAGE_W - ML - MR

    def ps(name, font, size, color=C_DARK, align=TA_LEFT, leading=None, before=0, after=0):
        return ParagraphStyle(name, fontName=font, fontSize=size, textColor=color,
                              alignment=align, leading=leading or size*1.4,
                              spaceBefore=before, spaceAfter=after)

    S = {
        "co_name":ps("co_name","ArialBD",22,C_PRI,leading=28),
        "co_addr":ps("co_addr","Arial",9,C_DARK,leading=13),
        "ref":ps("ref","ArialBD",12,C_PRI,TA_RIGHT,leading=15),
        "date":ps("date","Arial",9,C_MID,TA_RIGHT,leading=12),
        "status":ps("status","ArialBD",13,C_PRI,TA_CENTER,leading=17),
        "client":ps("client","Arial",10,C_DARK,leading=14),
        "sec_hdr":ps("sec_hdr","ArialBD",11,C_PRI,leading=16),
        "spec_lbl":ps("spec_lbl","ArialBD",8.5,C_ACC,leading=13),
        "spec_it":ps("spec_it","Arial",8.5,C_DARK,leading=13),
        "tbl_hdr":ps("tbl_hdr","ArialBD",8,white,TA_CENTER,leading=10),
        "tbl_cell":ps("tbl_cell","Arial",8,C_DARK,TA_CENTER,leading=10),
        "tbl_l":ps("tbl_l","Arial",8,C_DARK,TA_LEFT,leading=10),
        "total_lbl":ps("total_lbl","ArialBD",10,C_DARK,TA_RIGHT,leading=13),
        "total_val":ps("total_val","ArialBD",14,C_PRI,TA_CENTER,leading=17),
        "sig_lbl":ps("sig_lbl","Arial",8,C_MID,TA_RIGHT,leading=10),
        "sig_txt":ps("sig_txt","ArialBD",10,C_DARK,leading=13),
        "footer":ps("footer","Arial",7,C_MID,TA_CENTER,leading=9),
        "note":ps("note","Arial",8,C_DARK,leading=12),
    }

    data = request.json or {}
    ref_no = data.get("ref", "BH-000000-000")
    date_str = data.get("date", "")
    client_name = data.get("client", "—")
    currency = data.get("currency", "CNY")
    cust_rate = float(data.get("custRate", 6.6))
    ptype = data.get("productType", "front")
    mat_label = data.get("materialLabel", "Stainless Steel")
    is_electro = data.get("isElectro", False)
    electro_color = data.get("electroColor", "")
    kelvin = data.get("kelvin", "6000K-6500K")
    items = data.get("items", [{"w":50,"h":50,"thick":8,"qty":1}])
    total_qty = data.get("totalQty", sum(it.get("qty",1) for it in items))
    total_len_cm = data.get("totalLenCm", 0)
    power_desc = data.get("powerDesc", "")
    has_acrylic = data.get("hasAcrylic", False)
    is_rgb = data.get("isRgb", False)
    formal_total = data.get("formalTotal", "0")
    product_label = data.get("productLabel", "LED Letters")

    # Call AI to polish descriptions
    prompt = _build_ai_polish_prompt(ptype, mat_label, is_electro, electro_color, kelvin,
                                      items, total_qty, total_len_cm, power_desc, has_acrylic, is_rgb)
    try:
        ai_result = ask_ali(prompt, "", max_tokens=2000, timeout=60)
    except Exception as e:
        ai_result = None
        print(f"[AI Quote] AI call failed: {e}")

    # Parse AI result
    ai_sections = {"PRODUCT": product_label, "MATERIAL": "", "CRAFT": "", "LIGHTING": "", "INSTALLATION": "", "PACKAGING": ""}
    if ai_result:
        for line in ai_result.split("\n"):
            line = line.strip()
            for key in ai_sections:
                if line.upper().startswith(key + ":"):
                    ai_sections[key] = line[len(key)+1:].strip()
                    break

    # Build specs list
    specs_list = [
        ("Product Type:", f"{ai_sections['PRODUCT']}"),
        ("Material & Finish:", ai_sections["MATERIAL"] or f"{mat_label}{' with '+electro_color+' electroplating' if is_electro else ''}"),
        ("Craft & Construction:", ai_sections["CRAFT"] or "Precision laser-cut, seamless welding, grinding and polishing fine finish."),
        ("LED & Lighting:", ai_sections["LIGHTING"] or f"Color temperature: {kelvin}. Even illumination."),
        ("Power Supply:", power_desc or "As per specification"),
        ("Dimensions:", ', '.join(f"{it['w']}×{it['h']}×{it['thick']}cm ×{it['qty']}" for it in items)),
        ("Installation:", ai_sections["INSTALLATION"] or "Includes mounting hardware and 1:1 installation template."),
        ("Packaging:", ai_sections["PACKAGING"] or "15mm thick plywood crate, foam interior. Suitable for international shipping."),
    ]

    # Generate clean PDF
    pdf_dir = os.path.join(UPLOAD_DIR, "quotes")
    os.makedirs(pdf_dir, exist_ok=True)
    safe_ref = ref_no.replace("/","-").replace("\\","-")
    output_path = os.path.join(pdf_dir, f"FORMAL_QUOTE_{safe_ref}.pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB,
                            title=f"Bohui Formal Quote {ref_no}",
                            author="Bohui Advertising Craft")
    story = []

    # ── HEADER ──
    sym = "$" if currency == "USD" else "¥"
    left = [
        Paragraph("Zhongshan Bohui Advertising Craft Products Co., Ltd.", S["co_name"]),
        Paragraph("Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China 528415", S["co_addr"]),
        Paragraph(f"Official Site: wa.bohui-sign.com | Tel: +86 13824779947", S["co_addr"]),
    ]
    right = [
        Paragraph(f"QUOTATION REF: {ref_no}", S["ref"]),
        Paragraph(f"DATE: {date_str}", S["date"]),
    ]
    hdr = Table([[left, right]], colWidths=[CW*0.6, CW*0.4])
    hdr.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(0,0),0),
        ('RIGHTPADDING',(1,1),(1,1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
    ]))
    story.append(hdr)
    story.append(Spacer(1,4))
    story.append(HRFlowable(width="100%", thickness=1, color=C_PRI, spaceAfter=6, spaceBefore=2))
    story.append(Paragraph("FORMAL QUOTATION", S["status"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORD, spaceAfter=8, spaceBefore=2))

    # CLIENT
    story.append(Paragraph(f"<b>TO:</b> {client_name}", ps("client","Arial",10,C_DARK,leading=14,before=4,after=8)))

    # ── SECTION I: SPECIFICATIONS ──
    story.append(Paragraph("I. PRODUCT SPECIFICATIONS", S["sec_hdr"]))
    story.append(Spacer(1,2))
    for label, desc in specs_list:
        story.append(Paragraph(f"<b>{label}</b> {desc}", S["spec_it"]))
    story.append(Spacer(1,10))

    # ── SECTION II: PRICE ──
    story.append(Paragraph("II. QUOTATION PRICE", S["sec_hdr"]))
    story.append(Spacer(1,6))

    # Clean the formal total - remove currency symbols and commas
    clean_total = formal_total.replace("¥","").replace("$","").replace("￥","").replace(",","").strip()

    # Try to convert with customer rate
    try:
        total_num = float(clean_total)
        if currency == "USD":
            total_usd = round(total_num / cust_rate, 2)
            total_display = f"¥{clean_total} (≈ ${total_usd} @ {cust_rate})"
        else:
            total_display = f"¥{clean_total}"
    except:
        total_display = formal_total

    # Price table - clean, no markup
    price_col_w = [CW*0.50, CW*0.15, CW*0.35]
    tbl_data = [
        [Paragraph("Description", S["tbl_hdr"]),
         Paragraph("Quantity", S["tbl_hdr"]),
         Paragraph(f"Total Price ({currency})", S["tbl_hdr"])],
    ]
    item_desc = f"{product_label} - {mat_label}"
    if is_electro:
        item_desc += f" ({electro_color} electroplating)"
    tbl_data.append([
        Paragraph(item_desc, S["tbl_l"]),
        Paragraph(str(total_qty), S["tbl_cell"]),
        Paragraph(total_display, S["tbl_cell"]),
    ])

    # Net total row
    tbl_data.append([
        Paragraph("Total Amount", ps("net_lbl","ArialBD",9,C_DARK,TA_RIGHT,leading=11)),
        Paragraph("", S["tbl_cell"]),
        Paragraph(total_display, ps("net_val","ArialBD",12,C_PRI,TA_CENTER,leading=14)),
    ])

    tbl = Table(tbl_data, colWidths=price_col_w)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),C_PRI),
        ('TEXTCOLOR',(0,0),(-1,0),white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('GRID',(0,0),(-1,1),0.5,C_BORD),
        ('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('BACKGROUND',(0,1),(-1,1),C_TALT),
        ('SPAN',(0,-1),(1,-1)),
        ('LINEABOVE',(0,-1),(-1,-1),1.5,C_PRI),
        ('LINEBELOW',(0,-1),(-1,-1),0.5,C_BORD),
        ('TOPPADDING',(0,-1),(-1,-1),8),
        ('BOTTOMPADDING',(0,-1),(-1,-1),8),
    ]))
    story.append(tbl)
    story.append(Spacer(1,12))

    # ── Shipping Options ──
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph("<b>SHIPPING OPTIONS (DDU — Delivered Duty Unpaid):</b>", S["note"]))
    sea = "$3,969" if currency == "USD" else "¥3,969"
    air = "$7,677" if currency == "USD" else "¥7,677"
    story.append(Paragraph(f"   Sea freight: {sea} — Transit: 28-35 days after sailing.", S["note"]))
    story.append(Paragraph(f"   Air freight: {air} — Transit: 3-5 working days after departure.", S["note"]))
    story.append(Spacer(1,8))

    # ── Notes ──
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph("<b>TERMS & CONDITIONS:</b>", ps("nb","ArialBD",8.5,C_ACC,leading=13)))
    notes = [
        "Payment: 50% deposit to start production. 50% balance before shipment.",
        "Production Lead Time: 10 working days (counted from day after deposit received).",
        "Validity: This quotation is valid for 30 days from the date of issue.",
        "All-inclusive: Prices cover materials, processing, accessories, crate packing, and shipping as selected.",
        "Exchange Rate: Reference rate 1 USD = " + str(cust_rate) + " CNY. Final exchange rate may vary at time of payment.",
    ]
    for n in notes:
        story.append(Paragraph(f"• {n}", S["note"]))
    story.append(Spacer(1,12))

    # ── Signature ──
    sig = Table([
        [Paragraph("Authorized Signature:", S["sig_lbl"]),
         Paragraph("Yang Junliang<br/><font size=7>COO | Zhongshan Bohui Advertising Craft Products Co., Ltd.</font>",
                   S["sig_txt"])]
    ], colWidths=[CW*0.30, CW*0.70])
    sig.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ('LINEABOVE',(0,0),(-1,0),1,C_PRI),
    ]))
    story.append(sig)
    story.append(Spacer(1,18))

    # ── Footer ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph(
        "Zhongshan Bohui Advertising Craft Products Co., Ltd. | "
        "Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China<br/>"
        f"Official Site: wa.bohui-sign.com | Tel: +86 13824779947 | {ref_no}",
        S["footer"]
    ))

    doc.build(story)

    return send_from_directory(pdf_dir, f"FORMAL_QUOTE_{safe_ref}.pdf",
                               mimetype="application/pdf",
                               as_attachment=True,
                               download_name=f"FORMAL_QUOTE_{safe_ref}.pdf")


@app.route("/api/calc/save-quote", methods=["POST"])
def api_calc_save_quote():
    """Auto-save AI-generated quotation to CRM quotes table."""
    data = request.json or {}
    client_id = data.get("clientId", "")
    if not client_id:
        return jsonify({"ok": False, "error": "No client selected"}), 400

    ref = data.get("ref", "BH-" + datetime.now().strftime("%Y%m%d") + "-001")
    formal_total = data.get("formalTotal", "0")
    clean = formal_total.replace("¥","").replace("$","").replace(",","").strip()
    try:
        amt = float(clean)
    except:
        amt = 0

    from datetime import date, timedelta
    valid_until = (date.today() + timedelta(days=30)).isoformat()

    quote_data = {
        "customer_id": client_id,
        "quote_no": ref,
        "currency": data.get("currency", "CNY"),
        "total_amount": amt,
        "valid_until": valid_until,
        "status": "draft",
        "notes": "AI-Generated Formal Quotation (auto-saved)",
        "items": json.dumps([{
            "product_id": "",
            "name": f"{data.get('productLabel','LED Letters')} - {data.get('materialLabel','')}",
            "qty": data.get("totalQty", 1),
            "unit": "set",
            "unit_price": round(amt / max(data.get("totalQty", 1), 1), 2),
            "total": amt
        }]),
    }
    try:
        qid = add_quote(quote_data)
        return jsonify({"ok": True, "id": qid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/quotes/<int:qid>/ai-quote", methods=["POST"])
def api_quote_ai_quote(qid):
    """Generate AI-polished formal quotation PDF from a saved CRM quote."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    FONT_DIR = "C:/Windows/Fonts"
    for f in [("SimSun","simsun.ttc"),("SimHei","simhei.ttc"),
               ("MSYH","msyh.ttc"),("MSYHBD","msyhbd.ttc"),
               ("Arial","arial.ttf"),("ArialBD","arialbd.ttf")]:
        try:
            pdfmetrics.registerFont(TTFont(f[0], os.path.join(FONT_DIR, f[1])))
        except:
            pass

    C_PRI = HexColor("#1a237e")
    C_ACC = HexColor("#283593")
    C_TALT = HexColor("#f5f5f5")
    C_DARK = HexColor("#212121")
    C_MID = HexColor("#616161")
    C_BORD = HexColor("#c5cae9")

    PAGE_W, PAGE_H = A4
    ML, MR, MT, MB = 50, 50, 50, 45
    CW = PAGE_W - ML - MR

    def ps(name, font, size, color=C_DARK, align=TA_LEFT, leading=None, before=0, after=0):
        return ParagraphStyle(name, fontName=font, fontSize=size, textColor=color,
                              alignment=align, leading=leading or size*1.4,
                              spaceBefore=before, spaceAfter=after)

    S = {
        "co_name":ps("co_name","ArialBD",22,C_PRI,leading=28),
        "co_addr":ps("co_addr","Arial",9,C_DARK,leading=13),
        "ref":ps("ref","ArialBD",12,C_PRI,TA_RIGHT,leading=15),
        "date":ps("date","Arial",9,C_MID,TA_RIGHT,leading=12),
        "status":ps("status","ArialBD",13,C_PRI,TA_CENTER,leading=17),
        "client":ps("client","Arial",10,C_DARK,leading=14),
        "sec_hdr":ps("sec_hdr","ArialBD",11,C_PRI,leading=16),
        "spec_it":ps("spec_it","Arial",8.5,C_DARK,leading=13),
        "tbl_hdr":ps("tbl_hdr","ArialBD",8,white,TA_CENTER,leading=10),
        "tbl_cell":ps("tbl_cell","Arial",8,C_DARK,TA_CENTER,leading=10),
        "tbl_l":ps("tbl_l","Arial",8,C_DARK,TA_LEFT,leading=10),
        "total_lbl":ps("total_lbl","ArialBD",10,C_DARK,TA_RIGHT,leading=13),
        "total_val":ps("total_val","ArialBD",14,C_PRI,TA_CENTER,leading=17),
        "sig_lbl":ps("sig_lbl","Arial",8,C_MID,TA_RIGHT,leading=10),
        "sig_txt":ps("sig_txt","ArialBD",10,C_DARK,leading=13),
        "footer":ps("footer","Arial",7,C_MID,TA_CENTER,leading=9),
        "note":ps("note","Arial",8,C_DARK,leading=12),
    }

    # Load quote from database
    quote = get_quote(qid)
    if not quote:
        return jsonify({"ok": False, "error": "Quote not found"}), 404

    ref_no = quote.get("quote_no", f"Q-{qid}")
    date_str = (quote.get("created_at") or "")[:10]
    client_name = quote.get("customer_name", "—")
    currency = quote.get("currency", "CNY")
    total_amt = float(quote.get("total_amount", 0))
    notes = quote.get("notes", "")
    items_raw = quote.get("items", "[]")
    try:
        items = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
    except:
        items = []

    sym = "$" if currency == "USD" else "¥"
    total_display = f"{sym}{total_amt:.2f}"

    # Build quote items list for PDF
    if items and isinstance(items, list):
        item_desc = items[0].get("name", "LED Signage") if len(items) > 0 else "LED Signage"
        item_qty = str(items[0].get("qty", 1)) if len(items) > 0 else "1"
    else:
        item_desc = "LED Signage"
        item_qty = "1"

    # Generate PDF
    pdf_dir = os.path.join(UPLOAD_DIR, "quotes")
    os.makedirs(pdf_dir, exist_ok=True)
    safe_ref = ref_no.replace("/","-").replace("\\","-")
    output_path = os.path.join(pdf_dir, f"FORMAL_QUOTE_{safe_ref}.pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB,
                            title=f"Bohui Formal Quote {ref_no}",
                            author="Bohui Advertising Craft")
    story = []

    # ── HEADER ──
    left = [
        Paragraph("Zhongshan Bohui Advertising Craft Products Co., Ltd.", S["co_name"]),
        Paragraph("Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China 528415", S["co_addr"]),
        Paragraph("Official Site: wa.bohui-sign.com | Tel: +86 13824779947", S["co_addr"]),
    ]
    right = [
        Paragraph(f"QUOTATION REF: {ref_no}", S["ref"]),
        Paragraph(f"DATE: {date_str}", S["date"]),
    ]
    hdr = Table([[left, right]], colWidths=[CW*0.6, CW*0.4])
    hdr.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(0,0),0),
        ('RIGHTPADDING',(1,1),(1,1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
    ]))
    story.append(hdr)
    story.append(Spacer(1,4))
    story.append(HRFlowable(width="100%", thickness=1, color=C_PRI, spaceAfter=6, spaceBefore=2))
    story.append(Paragraph("FORMAL QUOTATION", S["status"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORD, spaceAfter=8, spaceBefore=2))

    # CLIENT
    story.append(Paragraph(f"<b>TO:</b> {client_name}", ps("client","Arial",10,C_DARK,leading=14,before=4,after=8)))

    # ── SECTION I: PRODUCT ──
    story.append(Paragraph("I. PRODUCT SPECIFICATIONS", S["sec_hdr"]))
    story.append(Spacer(1,2))
    story.append(Paragraph(f"<b>Product:</b> {item_desc}", S["spec_it"]))

    # Try AI polish
    try:
        prompt = _build_ai_polish_prompt("general", "", False, "", "6000K",
                                          [{"w":50,"h":50,"thick":8,"qty":1}],
                                          1, 0, "Standard", False, False)
        ai_result = ask_ali(prompt, "", max_tokens=2000, timeout=60)
        if ai_result:
            for line in ai_result.split("\n"):
                line = line.strip()
                for key_start in ["PRODUCT:", "MATERIAL:", "CRAFT:", "LIGHTING:", "INSTALLATION:", "PACKAGING:"]:
                    if line.upper().startswith(key_start):
                        val = line[len(key_start):].strip()
                        if val:
                            lbl = key_start.replace(":", "")
                            story.append(Paragraph(f"<b>{lbl}:</b> {val}", S["spec_it"]))
    except Exception as e:
        print(f"[AI Quote] AI call failed for saved quote: {e}")
        story.append(Paragraph(f"<b>Craft & Construction:</b> Precision manufactured LED signage.", S["spec_it"]))

    if notes:
        story.append(Paragraph(f"<b>Notes:</b> {notes}", S["spec_it"]))
    story.append(Spacer(1,10))

    # ── SECTION II: PRICE ──
    story.append(Paragraph("II. QUOTATION PRICE", S["sec_hdr"]))
    story.append(Spacer(1,6))

    price_col_w = [CW*0.50, CW*0.15, CW*0.35]
    tbl_data = [
        [Paragraph("Description", S["tbl_hdr"]),
         Paragraph("Quantity", S["tbl_hdr"]),
         Paragraph(f"Total Price ({currency})", S["tbl_hdr"])],
    ]
    tbl_data.append([
        Paragraph(item_desc, S["tbl_l"]),
        Paragraph(item_qty, S["tbl_cell"]),
        Paragraph(total_display, S["tbl_cell"]),
    ])
    tbl_data.append([
        Paragraph("Total Amount", ps("nl","ArialBD",9,C_DARK,TA_RIGHT,leading=11)),
        Paragraph("", S["tbl_cell"]),
        Paragraph(total_display, ps("nv","ArialBD",12,C_PRI,TA_CENTER,leading=14)),
    ])

    tbl = Table(tbl_data, colWidths=price_col_w)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),C_PRI),
        ('TEXTCOLOR',(0,0),(-1,0),white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('GRID',(0,0),(-1,1),0.5,C_BORD),
        ('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('BACKGROUND',(0,1),(-1,1),C_TALT),
        ('SPAN',(0,-1),(1,-1)),
        ('LINEABOVE',(0,-1),(-1,-1),1.5,C_PRI),
        ('LINEBELOW',(0,-1),(-1,-1),0.5,C_BORD),
        ('TOPPADDING',(0,-1),(-1,-1),8),
        ('BOTTOMPADDING',(0,-1),(-1,-1),8),
    ]))
    story.append(tbl)
    story.append(Spacer(1,12))

    # ── Shipping ──
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph("<b>SHIPPING OPTIONS (DDU):</b>", S["note"]))
    sea = "$3,969" if currency == "USD" else "¥3,969"
    air = "$7,677" if currency == "USD" else "¥7,677"
    story.append(Paragraph(f"   Sea freight: {sea} — 28-35 days", S["note"]))
    story.append(Paragraph(f"   Air freight: {air} — 3-5 working days", S["note"]))
    story.append(Spacer(1,8))

    # ── Terms ──
    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph("<b>TERMS & CONDITIONS:</b>", ps("nb","ArialBD",8.5,C_ACC,leading=13)))
    for n in [
        "Payment: 50% deposit to start production. 50% balance before shipment.",
        "Lead Time: 10 working days after deposit received.",
        "Validity: 30 days from date of issue.",
    ]:
        story.append(Paragraph(f"• {n}", S["note"]))
    story.append(Spacer(1,12))

    # ── Signature ──
    sig = Table([
        [Paragraph("Authorized Signature:", S["sig_lbl"]),
         Paragraph("Yang Junliang<br/><font size=7>COO | Zhongshan Bohui Advertising Craft Products Co., Ltd.</font>",
                   S["sig_txt"])]
    ], colWidths=[CW*0.30, CW*0.70])
    sig.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ('LINEABOVE',(0,0),(-1,0),1,C_PRI),
    ]))
    story.append(sig)
    story.append(Spacer(1,18))

    # ── Footer ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORD, spaceAfter=4, spaceBefore=2))
    story.append(Paragraph(
        "Zhongshan Bohui Advertising Craft Products Co., Ltd. | "
        "Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China<br/>"
        f"Official Site: wa.bohui-sign.com | Tel: +86 13824779947 | {ref_no}",
        S["footer"]
    ))

    doc.build(story)

    pdf_url = f"/uploads/quotes/FORMAL_QUOTE_{safe_ref}.pdf"
    return jsonify({
        "ok": True,
        "url": pdf_url,
        "filename": f"FORMAL_QUOTE_{safe_ref}.pdf"
    })


# ==================== 用户认证 ====================
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "请先登录"}), 401
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator: require the logged-in user to have one of the given roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({"error": "请先登录"}), 401
            if session.get("role") not in roles:
                return jsonify({"error": "权限不足"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    from werkzeug.security import check_password_hash
    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "用户名或密码错误"}), 401
    if not user.get("active", 1):
        return jsonify({"error": "账号已被禁用"}), 403
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["display_name"] = user["display_name"]
    session["role"] = user["role"]
    return jsonify({
        "ok": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "title": user.get("title", ""),
        }
    })


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def api_auth_me():
    if 'user_id' not in session:
        return jsonify({"error": "未登录"}), 401
    user = get_user_by_username(session.get("username", ""))
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "title": user.get("title", ""),
    })


# ==================== 通知 API ====================
@app.route("/api/notifications")
@login_required
def api_notifications():
    return jsonify(get_notifications(session["user_id"]))


@app.route("/api/notifications/unread-count")
@login_required
def api_unread_count():
    return jsonify({"count": get_unread_count(session["user_id"])})


@app.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def api_mark_read(nid):
    mark_notification_read(nid, session["user_id"])
    return jsonify({"ok": True})


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_mark_all_read():
    mark_all_notifications_read(session["user_id"])
    return jsonify({"ok": True})


@app.route("/api/auth/users")
@login_required
def api_auth_users():
    if session.get("role") != "admin":
        return jsonify({"error": "仅管理员可查看用户列表"}), 403
    return jsonify(get_users())


@app.route("/api/auth/users", methods=["POST"])
@login_required
def api_auth_add_user():
    if session.get("role") != "admin":
        return jsonify({"error": "仅管理员可创建用户"}), 403
    data = request.json or {}
    result = add_user(data)
    if "error" in result:
        return jsonify(result), 400
    logged_uid = session.get("user_id")
    if logged_uid and result.get("id"):
        add_activity_log(logged_uid, "create", "user", result["id"],
            f"创建了用户 {data.get('username','')} ({data.get('display_name','')})")
    return jsonify(result)


@app.route("/api/auth/users/<int:uid>", methods=["PUT"])
@login_required
def api_auth_update_user(uid):
    if session.get("role") != "admin":
        return jsonify({"error": "仅管理员可修改用户"}), 403
    data = request.json or {}
    update_user(uid, data)
    logged_uid = session.get("user_id")
    if logged_uid:
        changed = [f"{k}={v}" for k, v in data.items()]
        add_activity_log(logged_uid, "update", "user", uid,
            f"修改了用户 ID:{uid}: {', '.join(changed)}")
    return jsonify({"ok": True})


# ==================== 订单管理 ====================
@app.route("/api/orders")
@login_required
def api_orders():
    status = request.args.get("status")
    customer_id = request.args.get("customer_id")
    if status:
        status = status.split(",")
    return jsonify(get_orders(status=status, customer_id=customer_id))


@app.route("/api/orders/<int:oid>")
@login_required
def api_order(oid):
    order = get_order(oid)
    if not order:
        return jsonify({"error": "订单不存在"}), 404
    return jsonify(order)


@app.route("/api/orders", methods=["POST"])
@login_required
def api_create_order():
    data = request.json or {}
    data["created_by"] = session.get("user_id")
    result = add_order(data)
    if "error" in result:
        return jsonify(result), 400
    uid = session.get("user_id")
    if uid and result.get("id"):
        add_activity_log(uid, "create", "order", result["id"],
            f"创建了订单 {result.get('order_no','')} (ID:{result['id']})")
    return jsonify({"ok": True, "id": result["id"], "order_no": result["order_no"]})


@app.route("/api/orders/<int:oid>", methods=["PUT"])
@login_required
def api_update_order(oid):
    data = request.json or {}
    existing = get_order(oid)
    uid = session.get("user_id")
    # Track status change
    if "status" in data and existing:
        if existing.get("status") != data["status"]:
            old_status = existing.get("status", "")
            new_status = data["status"]
            add_timeline_entry(oid, new_status, session.get("user_id", 0),
                               f"状态变更: {old_status} → {new_status}")
            # Send WhatsApp notification for meaningful transitions
            if new_status in ("confirmed", "in_production", "shipped", "delivered"):
                customer = get_customer(existing.get("customer_id"))
                if customer and customer.get("whatsapp"):
                    def _notify_job():
                        _notify_order_status_change(existing, customer, old_status, new_status)
                    threading.Thread(target=_notify_job, daemon=True).start()
            # 通知所有活跃用户订单状态变更
            for auid in get_active_user_ids():
                add_notification(auid, 'order',
                    f'订单 {existing["order_no"]} 状态变更',
                    f'{old_status} → {new_status}',
                    link=f'/orders/{oid}',
                    related_type='order', related_id=oid)
            # Log the status change
            if uid:
                add_activity_log(uid, "update", "order", oid,
                    f"修改了订单 {existing.get('order_no','')}: 状态 {old_status}→{new_status}")
    update_order(oid, data)
    return jsonify({"ok": True})


@app.route("/api/orders/<int:oid>", methods=["DELETE"])
@login_required
def api_delete_order(oid):
    existing = get_order(oid)
    delete_order(oid)
    uid = session.get("user_id")
    if uid and existing:
        add_activity_log(uid, "delete", "order", oid,
            f"删除了订单 {existing.get('order_no','')} (ID:{oid})")
    return jsonify({"ok": True})


@app.route("/api/orders/<int:oid>/payment", methods=["POST"])
@login_required
def api_order_payment(oid):
    data = request.json or {}
    ptype = data.get("type", "deposit")  # 'deposit' or 'balance'
    update_data = {}
    if ptype == "deposit":
        update_data["deposit_amount"] = data.get("amount", 0)
        update_data["deposit_date"] = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        update_data["deposit_method"] = data.get("method", "")
        update_data["deposit_received"] = 1
    else:
        update_data["balance_amount"] = data.get("amount", 0)
        update_data["balance_date"] = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        update_data["balance_method"] = data.get("method", "")
        update_data["balance_received"] = 1
    update_order(oid, update_data)
    # 同步写入付款流水表
    order_currency = "USD"
    o_check = get_order(oid)
    if o_check:
        order_currency = o_check.get("currency", "USD")
    add_payment(
        order_id=oid,
        ptype=ptype,
        amount=data.get("amount", 0),
        currency=order_currency,
        payment_date=data.get("date", datetime.now().strftime("%Y-%m-%d")),
        method=data.get("method", ""),
        recorded_by=session.get("user_id"),
    )
    add_timeline_entry(oid, "payment", session.get("user_id", 0),
                       f"收到{data.get('method','')}付款 {data.get('amount',0)} ({'定金' if ptype=='deposit' else '尾款'})")
    # Send WhatsApp notification for payment
    order = get_order(oid)
    if order:
        customer = get_customer(order.get("customer_id"))
        if customer and customer.get("whatsapp"):
            def _pay_notify_job():
                _notify_payment_received(order, customer, ptype, data.get("amount", 0))
            threading.Thread(target=_pay_notify_job, daemon=True).start()
    uid = session.get("user_id")
    if uid and order:
        add_activity_log(uid, "payment", "order", oid,
            f"订单 {order.get('order_no','')} 收款 {data.get('amount',0)} ({'定金' if ptype=='deposit' else '尾款'})")
    return jsonify({"ok": True})


# ==================== 生产步骤追踪 API ====================
@app.route("/api/orders/<int:oid>/tasks")
@login_required
def api_get_production_tasks(oid):
    """获取订单的生产任务列表"""
    return jsonify(get_production_tasks(oid))


@app.route("/api/orders/<int:oid>/tasks", methods=["POST"])
@login_required
@role_required('admin', 'production')
def api_save_production_tasks(oid):
    """批量保存生产任务（管理员预设步骤）"""
    data = request.json or {}
    tasks = data.get("tasks", [])
    save_production_tasks(oid, tasks)
    uid = session.get("user_id")
    if uid:
        order = get_order(oid)
        add_activity_log(uid, "update", "order", oid,
            f"更新生产步骤 ({len(tasks)} 项) - {order.get('order_no','')}")
    return jsonify({"ok": True})


@app.route("/api/orders/<int:oid>/tasks/<int:tid>", methods=["PUT"])
@login_required
def api_update_task_status(oid, tid):
    """勾选/取消勾选单个任务"""
    data = request.json or {}
    is_done = data.get("is_done", 0)
    done_by = session.get("user_id")
    update_production_task_status(tid, is_done, done_by)
    return jsonify({"ok": True})


@app.route("/api/orders/<int:oid>/generate-tasks", methods=["POST"])
@login_required
@role_required('admin', 'production')
def api_generate_tasks(oid):
    """按默认模板为订单生成初始任务列表"""
    defaults = get_production_task_defaults()
    save_production_tasks(oid, defaults)
    uid = session.get("user_id")
    if uid:
        order = get_order(oid)
        add_activity_log(uid, "create", "order", oid,
            f"生成默认生产步骤 - {order.get('order_no','')}")
    return jsonify({"ok": True, "tasks": get_production_tasks(oid)})


@app.route("/api/quotes/<int:qid>/convert", methods=["POST"])
@login_required
def api_convert_quote_to_order(qid):
    quote = get_quote(qid)
    if not quote:
        return jsonify({"error": "报价不存在"}), 404
    if quote.get("status") != "accepted":
        return jsonify({"error": "仅已接受的报价可以转订单"}), 400
    data = {
        "customer_id": quote["customer_id"],
        "quote_id": qid,
        "items": quote.get("items", []),
        "total_amount": quote.get("total_amount", 0),
        "currency": quote.get("currency", "USD"),
        "status": "pending_approval",
        "created_by": session.get("user_id"),
        "order_no": quote.get("quote_no", "").replace("BH-", "ORD-"),
        "notes": f"源自报价 {quote.get('quote_no','')}",
    }
    result = add_order(data)
    if "error" in result:
        return jsonify(result), 400
    uid = session.get("user_id")
    if uid and result.get("id"):
        add_activity_log(uid, "convert", "order", result["id"],
            f"报价 {quote.get('quote_no','')} 转为订单 {result.get('order_no','')}")
    return jsonify({"ok": True, "id": result["id"], "order_no": result["order_no"]})


@app.route("/api/payment-dashboard")
@login_required
def api_payment_dashboard():
    return jsonify(get_payment_dashboard())


# ==================== 应收账款 API ====================
@app.route("/api/ar/summary")
@login_required
@role_required('admin', 'sales')
def api_ar_summary():
    return jsonify(get_ar_summary())


@app.route("/api/ar/by-customer")
@login_required
@role_required('admin', 'sales')
def api_ar_by_customer():
    return jsonify(get_ar_by_customer())


@app.route("/api/ar/payment-history")
@login_required
@role_required('admin', 'sales')
def api_ar_payment_history():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_payment_history(limit))


@app.route("/api/ar/aging")
@login_required
@role_required('admin', 'sales')
def api_ar_aging():
    return jsonify(get_aging_analysis())


@app.route("/api/ar/migrate", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_ar_migrate():
    count = migrate_payments_from_orders()
    return jsonify({"ok": True, "migrated": count})

# ==================== 潜客管理 API (Leads) ====================
@app.route("/api/leads")
@login_required
@role_required('admin', 'sales')
def api_leads():
    source = request.args.get("source")
    status = request.args.get("status")
    assigned_to = request.args.get("assigned_to", type=int)
    country = request.args.get("country")
    pool = request.args.get("pool", type=int)
    if pool:
        return jsonify(get_leads_with_pool_info(source=source, status=status, assigned_to=assigned_to, country=country))
    return jsonify(get_leads(source=source, status=status, assigned_to=assigned_to, country=country))


@app.route("/api/leads/summary")
@login_required
@role_required('admin', 'sales')
def api_leads_summary():
    return jsonify(get_lead_summary())


@app.route("/api/leads/funnel")
@login_required
@role_required('admin', 'sales')
def api_leads_funnel():
    return jsonify(get_lead_funnel())


@app.route("/api/leads/<int:cid>/assign", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_leads_assign(cid):
    data = request.json or {}
    uid = data.get("user_id")
    if uid is None:
        return jsonify({"error": "缺少 user_id"}), 400
    assign_lead(cid, uid)
    logged_uid = session.get("user_id")
    customer = get_customer(cid)
    cname = customer["name"] if customer else f"ID:{cid}"
    if logged_uid:
        target_user = get_user_by_id(uid)
        tname = target_user["display_name"] if target_user else str(uid)
        add_activity_log(logged_uid, "assign", "lead", cid,
            f"分配潜客 {cname} 给 {tname}")
    # 通知被分配者
    if uid:
        if customer:
            add_notification(int(uid), 'assign',
                f'新潜客分配: {customer["name"]}',
                f'来源: {customer.get("source","")} | {customer.get("country","")}',
                link=f'/leads/{cid}',
                related_type='lead', related_id=cid)
    return jsonify({"ok": True})


@app.route("/api/leads/<int:cid>/status", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_leads_status(cid):
    data = request.json or {}
    status = data.get("lead_status")
    if not status:
        return jsonify({"error": "缺少 lead_status"}), 400
    customer = get_customer(cid)
    update_lead_status(cid, status)
    uid = session.get("user_id")
    if uid and customer:
        add_activity_log(uid, "status_change", "lead", cid,
            f"修改潜客 {customer.get('name','')} 阶段为 {status}")
    return jsonify({"ok": True})


@app.route("/api/leads/<int:cid>/source", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_leads_source(cid):
    data = request.json or {}
    source = data.get("source", "")
    campaign = data.get("campaign", "")
    update_lead_source(cid, source, campaign)
    uid = session.get("user_id")
    customer = get_customer(cid)
    if uid and customer:
        add_activity_log(uid, "update", "lead", cid,
            f"修改潜客 {customer.get('name','')} 来源为 {source}")
    return jsonify({"ok": True})


# ==================== 公海自动流转 API ====================

@app.route("/api/users")
@login_required
@role_required('admin', 'sales')
def api_users():
    """获取所有销售用户（供分配弹窗和过滤下拉使用）"""
    return jsonify(get_users())


@app.route("/api/leads/<int:cid>/unassign", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_leads_unassign(cid):
    """退回公海"""
    customer = get_customer(cid)
    unassign_lead(cid)
    uid = session.get("user_id")
    if uid and customer:
        add_activity_log(uid, "unassign", "lead", cid,
            f"将潜客 {customer.get('name','')} 退回公海")
    return jsonify({"ok": True})


@app.route("/api/leads/<int:cid>/claim", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_leads_claim(cid):
    """认领潜客"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "未登录"}), 401
    ok = claim_lead(cid, uid)
    if not ok:
        return jsonify({"error": "该潜客已被他人认领"}), 409
    customer = get_customer(cid)
    if uid and customer:
        add_activity_log(uid, "claim", "lead", cid,
            f"认领了潜客 {customer.get('name','')}")
    return jsonify({"ok": True})


@app.route("/api/leads/reclaim", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_leads_reclaim():
    """手动触发回收检查"""
    reclaimed = reclaim_expired_leads(days=14)
    return jsonify({"ok": True, "count": len(reclaimed), "items": reclaimed})


# ==================== 跟进提醒 API ====================

@app.route("/api/leads/followup")
@login_required
@role_required('admin', 'sales')
def api_leads_followup():
    """获取需要跟进的潜客列表"""
    return jsonify(get_leads_due_followup())


@app.route("/api/leads/followup/summary")
@login_required
@role_required('admin', 'sales')
def api_leads_followup_summary():
    """获取跟进汇总数据"""
    return jsonify(get_today_followup_summary())


@app.route("/api/leads/<int:cid>/contacted", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_leads_contacted(cid):
    """标记潜客为已联系（更新 last_contacted_at）"""
    update_last_contacted(cid)
    return jsonify({"ok": True})


@app.route("/api/leads/<int:cid>/followup-msg", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_leads_followup_msg(cid):
    """AI生成跟进消息"""
    from database import get_customer
    customer = get_customer(cid)
    if not customer:
        return jsonify({"error": "客户不存在"}), 404
    data = request.json or {}
    followup_type = data.get("followup_type", "3day")
    result = get_ai_followup_message(
        customer_name=customer["name"],
        language=customer.get("language", "English"),
        followup_type=followup_type,
        sales_name="Philip"
    )
    return jsonify({"ok": True, "followup_type": followup_type, "message": result})


@app.route("/api/knowledge-base/reload", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_reload_knowledge_base():
    """重新加载销售知识库"""
    clear_knowledge_base_cache()
    return jsonify({"ok": True, "message": "知识库已重新加载"})


@app.route("/api/ai/greeting", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_ai_greeting():
    """测试AI招呼（用于调试）"""
    data = request.json or {}
    name = data.get("name", "Test Customer")
    country = data.get("country", "")
    result = get_ai_greeting(customer_name=name, country=country)
    return jsonify(result)


@app.route("/api/orders/profit-stats")
@login_required
def api_order_profit_stats():
    group = request.args.get("group")
    return jsonify(get_order_profit_stats(group=group))


@app.route("/api/orders/stats")
@login_required
def api_order_stats():
    return jsonify(get_order_stats())


@app.route("/api/commission-stats")
@login_required
@role_required('admin', 'sales')
def api_commission_stats():
    return jsonify(get_commission_stats())


@app.route("/api/users/<int:uid>/commission", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_update_commission_rate(uid):
    data = request.json or {}
    rate = data.get("commission_rate")
    if rate is not None:
        update_user(uid, {"commission_rate": float(rate)})
        return jsonify({"ok": True})
    return jsonify({"error": "缺少 commission_rate"}), 400


@app.route("/api/production/schedule")
@login_required
def api_production_schedule():
    return jsonify(get_production_schedule())


# ==================== 库存管理 ====================
@app.route("/api/inventory")
@login_required
def api_inventory_items():
    category = request.args.get("category")
    low_stock = request.args.get("low_stock", "false").lower() == "true"
    return jsonify(get_inventory_items(category=category, low_stock=low_stock))


@app.route("/api/inventory/summary")
@login_required
def api_inventory_summary():
    return jsonify(get_inventory_summary())


@app.route("/api/inventory/<int:iid>")
@login_required
def api_inventory_item(iid):
    item = get_inventory_item(iid)
    if not item:
        return jsonify({"error": "物料不存在"}), 404
    return jsonify(item)


@app.route("/api/inventory", methods=["POST"])
@login_required
def api_add_inventory_item():
    data = request.json or {}
    result = add_inventory_item(data)
    return jsonify({"ok": True, "id": result["id"]})


@app.route("/api/inventory/<int:iid>", methods=["PUT"])
@login_required
def api_update_inventory_item(iid):
    data = request.json or {}
    update_inventory_item(iid, data)
    return jsonify({"ok": True})


@app.route("/api/inventory/<int:iid>", methods=["DELETE"])
@login_required
def api_delete_inventory_item(iid):
    delete_inventory_item(iid)
    return jsonify({"ok": True})


@app.route("/api/inventory/movements")
@login_required
def api_all_stock_movements():
    return jsonify(get_stock_movements(item_id=None))


@app.route("/api/inventory/<int:iid>/movements")
@login_required
def api_stock_movements(iid):
    return jsonify(get_stock_movements(item_id=iid))


@app.route("/api/inventory/<int:iid>/movements", methods=["POST"])
@login_required
def api_add_stock_movement(iid):
    data = request.json or {}
    mtype = data.get("type", "in")
    quantity = float(data.get("quantity", 0))
    if quantity <= 0:
        return jsonify({"error": "数量必须大于0"}), 400
    add_stock_movement(
        item_id=iid,
        mtype=mtype,
        quantity=quantity,
        reference=data.get("reference", ""),
        notes=data.get("notes", ""),
        created_by=session.get("user_id"),
    )
    return jsonify({"ok": True})




# ==================== 数据导出 ====================
@app.route("/api/export/customers")
@login_required
def api_export_customers():
    customers = get_customers()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "客户列表"
    ws.append(["ID", "姓名", "公司", "WhatsApp", "国家", "语言", "状态",
               "来源", "活动", "潜客阶段", "潜客评分", "负责人",
               "首次联系", "最近联系", "创建人", "备注", "创建时间", "更新时间"])
    for c in customers:
        # 查找负责人姓名
        assigned_name = ""
        if c.get("assigned_to"):
            u = get_user_by_id(c["assigned_to"])
            if u: assigned_name = u.get("display_name", "")
        ws.append([
            c.get("id", ""),
            c.get("name", ""),
            c.get("company", ""),
            c.get("whatsapp", ""),
            c.get("country", ""),
            c.get("language", "English"),
            c.get("status", ""),
            c.get("source", ""),
            c.get("campaign", ""),
            c.get("lead_status", ""),
            c.get("lead_score", 0),
            assigned_name,
            c.get("first_contacted_at", ""),
            c.get("last_contacted_at", ""),
            c.get("created_by", ""),
            c.get("notes", ""),
            c.get("created_at", ""),
            c.get("updated_at", ""),
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return _send_excel(output, "客户导出.xlsx")


@app.route("/api/export/orders")
@login_required
def api_export_orders():
    orders = get_orders()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "订单列表"
    ws.append(["订单号", "客户", "金额", "币种", "状态", "成本", "利润", "利润率%", "创建时间"])
    for o in orders:
        ws.append([
            o.get("order_no", ""),
            o.get("customer_name", ""),
            o.get("total_amount", 0),
            o.get("currency", "USD"),
            o.get("status", ""),
            o.get("partner_cost", 0),
            o.get("profit", 0),
            o.get("profit_margin", 0),
            o.get("created_at", ""),
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return _send_excel(output, "订单导出.xlsx")


@app.route("/api/export/inventory")
@login_required
def api_export_inventory():
    items = get_inventory_items()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "库存清单"
    ws.append(["物料名称", "分类", "单位", "库存量", "警戒线", "单价", "库存价值", "备注"])
    for item in items:
        ws.append([
            item.get("name", ""),
            item.get("category", ""),
            item.get("unit", ""),
            item.get("quantity", 0),
            item.get("reorder_level", 0),
            item.get("unit_cost", 0),
            item.get("stock_value", 0),
            item.get("notes", ""),
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return _send_excel(output, "库存导出.xlsx")


@app.route("/api/export/commission")
@login_required
@role_required('admin', 'sales')
def api_export_commission():
    data = get_commission_stats()
    wb = openpyxl.Workbook()
    # Sheet 1: 按销售员汇总
    ws1 = wb.active
    ws1.title = "提成汇总"
    ws1.append(["销售员", "订单数", "营收", "成本", "利润", "提成率%", "提成金额"])
    for s in data.get("sales_summary", []):
        ws1.append([
            s.get("sales_name", ""),
            s.get("order_count", 0),
            s.get("total_revenue", 0),
            s.get("total_cost", 0),
            s.get("total_profit", 0),
            s.get("commission_rate", 0),
            s.get("total_commission", 0),
        ])
    # Sheet 2: 明细
    ws2 = wb.create_sheet("提成明细")
    ws2.append(["订单号", "客户", "销售员", "金额", "成本", "利润", "提成率%", "提成", "日期"])
    for d in data.get("detail", []):
        ws2.append([
            d.get("order_no", ""),
            d.get("customer_name", ""),
            d.get("sales_name", ""),
            d.get("total_amount", 0),
            d.get("partner_cost", 0),
            d.get("profit", 0),
            d.get("commission_rate", 0),
            d.get("commission", 0),
            d.get("created_at", ""),
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return _send_excel(output, "提成导出.xlsx")


def _send_excel(output, filename):
    from flask import send_file
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


# ==================== 客户导入 ====================
import csv

COLUMN_ALIASES = {
    "name": ["name", "姓名", "名字", "客户名", "客户名称"],
    "company": ["company", "公司", "企业", "单位"],
    "whatsapp": ["whatsapp", "whatsapp号", "手机", "phone", "电话"],
    "country": ["country", "国家", "地区", "region"],
    "language": ["language", "语言", "语种"],
    "status": ["status", "状态", "客户状态"],
    "source": ["source", "来源", "渠道"],
    "campaign": ["campaign", "活动", "营销活动"],
    "lead_status": ["lead_status", "潜客阶段", "阶段", "lead status"],
    "lead_score": ["lead_score", "潜客评分", "评分", "分数", "score"],
    "notes": ["notes", "备注", "备注说明"],
}

def _resolve_csv_col(header):
    h = header.strip().lower()
    for field, aliases in COLUMN_ALIASES.items():
        if h in [a.lower() for a in aliases]:
            return field
    return None

@app.route("/api/import/customers", methods=["POST"])
@login_required
def api_import_customers():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "请上传CSV文件"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return jsonify({"ok": False, "error": "仅支持CSV格式"}), 400
    try:
        stream = io.StringIO(f.stream.read().decode("utf-8-sig"))
    except Exception:
        stream = io.StringIO(f.stream.read().decode("gbk"))
    reader = csv.reader(stream)
    try:
        headers = next(reader)
    except StopIteration:
        return jsonify({"ok": False, "error": "CSV文件为空"}), 400
    # 映射列头到字段名
    col_map = {}
    for h in headers:
        fld = _resolve_csv_col(h)
        if fld:
            col_map[fld] = len(col_map)  # use index
    if "name" not in col_map:
        return jsonify({"ok": False, "error": "CSV缺少必要列: name/姓名"}), 400
    # 重新构建 col_map: 字段名 → 列索引
    col_map = {}
    for idx, h in enumerate(headers):
        fld = _resolve_csv_col(h)
        if fld:
            col_map[fld] = idx
    if "name" not in col_map:
        return jsonify({"ok": False, "error": "CSV缺少必要列: name/姓名"}), 400
    rows = []
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue  # 跳过空行
        d = {}
        for fld, idx in col_map.items():
            if idx < len(row):
                d[fld] = row[idx].strip()
        rows.append(d)
    if not rows:
        return jsonify({"ok": False, "error": "CSV无有效数据"}), 400
    imported, skipped, errors = bulk_add_customers(rows)
    return jsonify({
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "total": len(rows),
        "errors": errors[:10],  # 最多返回10个错误
    })


# ==================== 系统备份 ====================
import shutil

BACKUP_DIR = os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


@app.route("/api/backup", methods=["POST"])
@login_required
def api_create_backup():
    from database import DB_PATH
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"crm_backup_{ts}.db"
    dest = os.path.join(BACKUP_DIR, filename)
    try:
        shutil.copy2(DB_PATH, dest)
        # Keep only last 20 backups
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
            reverse=True
        )
        for old in backups[20:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except:
                pass
        return jsonify({"ok": True, "filename": filename, "size": os.path.getsize(dest)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/backups")
@login_required
def api_list_backups():
    backups = []
    if os.path.isdir(BACKUP_DIR):
        for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if f.endswith(".db"):
                fp = os.path.join(BACKUP_DIR, f)
                backups.append({
                    "filename": f,
                    "size": os.path.getsize(fp),
                    "created_at": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M:%S"),
                })
    return jsonify(backups)


# ==================== 合作方管理 ====================
@app.route("/api/partners")
@login_required
@role_required('admin', 'sales')
def api_partners():
    return jsonify(get_partners())


@app.route("/api/partners/<int:pid>")
@login_required
@role_required('admin', 'sales')
def api_partner(pid):
    partner = get_partner(pid)
    if not partner:
        return jsonify({"error": "合作方不存在"}), 404
    return jsonify(partner)


@app.route("/api/partners", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_add_partner():
    data = request.json or {}
    result = add_partner(data)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "id": result["id"]})


@app.route("/api/partners/<int:pid>", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_update_partner(pid):
    data = request.json or {}
    update_partner(pid, data)
    return jsonify({"ok": True})


@app.route("/api/partners/<int:pid>", methods=["DELETE"])
@login_required
@role_required('admin', 'sales')
def api_delete_partner(pid):
    delete_partner(pid)
    return jsonify({"ok": True})


# ==================== 采购订单管理 ====================
@app.route("/api/purchase-orders")
@login_required
@role_required('admin', 'sales')
def api_purchase_orders():
    status = request.args.get("status")
    partner_id = request.args.get("partner_id")
    order_id = request.args.get("order_id")
    if status:
        status = status.split(",")
    return jsonify(get_purchase_orders(status=status, partner_id=partner_id, order_id=order_id))


@app.route("/api/purchase-orders/<int:oid>")
@login_required
@role_required('admin', 'sales')
def api_purchase_order(oid):
    po = get_purchase_order(oid)
    if not po:
        return jsonify({"error": "采购单不存在"}), 404
    return jsonify(po)


@app.route("/api/purchase-orders", methods=["POST"])
@login_required
@role_required('admin', 'sales')
def api_create_purchase_order():
    data = request.json or {}
    data["created_by"] = session.get("user_id")
    result = add_purchase_order(data)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "id": result["id"], "po_no": result["po_no"]})


@app.route("/api/purchase-orders/<int:oid>", methods=["PUT"])
@login_required
@role_required('admin', 'sales')
def api_update_purchase_order(oid):
    data = request.json or {}
    if "status" in data:
        existing = get_purchase_order(oid)
        if existing and existing.get("status") != data["status"]:
            add_po_timeline_entry(oid, data["status"], session.get("user_id", 0),
                                  f"状态变更: {existing.get('status','')} → {data['status']}")
    update_purchase_order(oid, data)
    return jsonify({"ok": True})


@app.route("/api/purchase-orders/<int:oid>", methods=["DELETE"])
@login_required
@role_required('admin', 'sales')
def api_delete_purchase_order(oid):
    delete_purchase_order(oid)
    return jsonify({"ok": True})


# ==================== 单实例保护 & 稳定启动 ====================
LOCK_DIR = os.path.join(BASE_DIR, ".crm_lock")
LOCK_FILE = os.path.join(LOCK_DIR, "app.lock")
PID_FILE = os.path.join(LOCK_DIR, "app.pid")


def _ensure_single_instance(port):
    """确保只有一个实例在运行。用socket端口锁定 + PID文件双保险"""
    os.makedirs(LOCK_DIR, exist_ok=True)

    # 1. 检查PID文件，杀掉旧进程
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            # 检查进程是否还在
            if sys.platform == "win32":
                chk = subprocess.run(f"tasklist /FI \"PID eq {old_pid}\" /NH",
                                     shell=True, capture_output=True, text=True)
                if str(old_pid) in chk.stdout:
                    print(f"[启动] 发现旧进程 PID={old_pid}，正在终止...")
                    subprocess.run(f"taskkill /F /PID {old_pid}", shell=True)
                    time.sleep(1)
            else:
                try:
                    os.kill(old_pid, 0)  # 检查进程存在
                    print(f"[启动] 发现旧进程 PID={old_pid}，正在终止...")
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(1)
                except OSError:
                    pass  # 进程已死
        except Exception:
            pass

    # 2. 尝试绑定端口（防冲突）
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
    except OSError:
        print(f"[启动] 端口 {port} 已被占用！尝试关闭旧进程...")
        if sys.platform == "win32":
            subprocess.run(f"netstat -ano | findstr :{port}",
                           shell=True)
        sys.exit(1)

    # 3. 写当前PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    print(f"[启动] PID={os.getpid()}")


def _cleanup():
    """退出时清理锁文件"""
    for f in [LOCK_FILE, PID_FILE]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
    # 清理空的锁目录
    try:
        if os.path.exists(LOCK_DIR) and not os.listdir(LOCK_DIR):
            os.rmdir(LOCK_DIR)
    except Exception:
        pass


def _kill_orphan_playwright():
    """杀掉残留的Playwright浏览器进程（避免多个窗口）"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                'wmic process where "name=\'chrome.exe\'" get commandline /format:csv',
                shell=True, capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if "playwright" in line.lower() and "persistent_profile" in line:
                    # 提取PID
                    pid_line = line.strip()
                    if pid_line:
                        print(f"[启动] 发现残留Playwright: {pid_line[:80]}...")
                        subprocess.run(
                            'wmic process where "name=\'chrome.exe\'" delete',
                            shell=True, capture_output=True, timeout=10
                        )
                        break
    except Exception:
        pass


if __name__ == "__main__":
    import webbrowser
    port = 5789

    # 启动前清理
    _kill_orphan_playwright()
    _ensure_single_instance(port)

    # 注册退出清理
    atexit.register(_cleanup)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, lambda *a: _cleanup() or sys.exit(0))

    print(f"GLOWFORGE CRM 启动中: http://localhost:{port}")
    webbrowser.open(f"http://localhost:{port}")

    # 后台启动WhatsApp 24×7监控
    def _start_bg():
        time.sleep(3)
        # 先尝试连接独立 WhatsApp 服务（127.0.0.1:15789）
        import urllib.request, json as _json
        remote_url = "http://127.0.0.1:15789"
        try:
            with urllib.request.urlopen(f"{remote_url}/health", timeout=3) as r:
                data = _json.loads(r.read().decode())
                if data.get("ok"):
                    set_remote_server(remote_url)
                    print("[启动] ✓ 已连接到独立 WhatsApp 服务")
                    return
        except Exception:
            print("[启动] 独立 WhatsApp 服务未运行，启动本地引擎...")
        # 回退：本地启动引擎
        try:
            start_monitor(_whatsapp_message_handler)
        except Exception as e:
            print(f"[启动] WhatsApp引擎启动失败: {e}")
    threading.Thread(target=_start_bg, daemon=True).start()

    # 后台线程：每30分钟回收过期未跟进的潜客
    def _reclaim_pool_loop():
        while True:
            try:
                reclaimed = reclaim_expired_leads(days=14)
                if reclaimed:
                    print(f"[Pool] 自动回收 {len(reclaimed)} 个过期潜客: {[r['name'] for r in reclaimed]}")
            except Exception as e:
                print(f"[Pool] 回收检查异常: {e}")
            threading.Event().wait(1800)

    threading.Thread(target=_reclaim_pool_loop, daemon=True).start()

    try:
        app.run(host="127.0.0.1", port=port, debug=False)
    finally:
        _cleanup()
