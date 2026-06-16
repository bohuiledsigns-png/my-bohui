"""GLOWFORGE CRM 数据库模块"""
import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crm_data.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            company TEXT DEFAULT '',
            whatsapp TEXT DEFAULT '',
            country TEXT DEFAULT '',
            language TEXT DEFAULT 'English',
            status TEXT DEFAULT 'warm',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            direction TEXT NOT NULL DEFAULT 'sent',
            content_cn TEXT DEFAULT '',
            content_en TEXT DEFAULT '',
            media_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """)

    # 数据库迁移：旧表加language字段
    try:
        conn.execute("ALTER TABLE customers ADD COLUMN language TEXT DEFAULT 'English'")
    except:
        pass

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            prompt TEXT NOT NULL DEFAULT '',
            result_url TEXT DEFAULT '',
            result_filename TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            customer_id INTEGER DEFAULT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            filetype TEXT DEFAULT 'image',
            filesize INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            customer_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS email_settings (
            id INTEGER PRIMARY KEY CHECK(id=1),
            smtp_host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER NOT NULL DEFAULT 587,
            smtp_user TEXT DEFAULT '',
            smtp_pass TEXT DEFAULT '',
            from_email TEXT DEFAULT '',
            from_name TEXT DEFAULT 'GLOWFORGE',
            use_tls INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS email_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            to_email TEXT NOT NULL,
            subject TEXT DEFAULT '',
            body TEXT DEFAULT '',
            attachments TEXT DEFAULT '[]',
            status TEXT DEFAULT 'sent',
            error TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            category TEXT DEFAULT 'commercial',
            location TEXT DEFAULT '',
            description TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            video_url TEXT DEFAULT '',
            products_used TEXT DEFAULT '',
            badge TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS products (
            specs TEXT DEFAULT '{}',
            price_tiers TEXT DEFAULT '[]',
            description TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            unit TEXT DEFAULT '个',
            currency TEXT DEFAULT 'USD',
            min_order INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_no TEXT NOT NULL DEFAULT '',
            customer_id INTEGER DEFAULT NULL,
            items TEXT DEFAULT '[]',
            total_amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'draft',
            valid_until TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            pdf_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'sales' CHECK(role IN ('admin','sales','production')),
            title TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL DEFAULT '',
            customer_id INTEGER NOT NULL,
            quote_id INTEGER DEFAULT NULL,
            items TEXT DEFAULT '[]',
            total_amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            deposit_amount REAL DEFAULT 0,
            deposit_date TEXT DEFAULT '',
            deposit_method TEXT DEFAULT '',
            deposit_received INTEGER DEFAULT 0,
            balance_amount REAL DEFAULT 0,
            balance_date TEXT DEFAULT '',
            balance_method TEXT DEFAULT '',
            balance_received INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending_approval',
            production_notes TEXT DEFAULT '',
            assigned_to INTEGER DEFAULT NULL,
            shipping_info TEXT DEFAULT '',
            timeline TEXT DEFAULT '[]',
            created_by INTEGER DEFAULT NULL,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 迁移：已有表加用户追踪字段
    for col in [("customers","created_by"), ("quotes","created_by"), ("quotes","assigned_to")]:
        try:
            conn.execute(f"ALTER TABLE {col[0]} ADD COLUMN {col[1]} INTEGER DEFAULT NULL")
        except:
            pass
    # 迁移：订单表加合作方字段
    for col_tup in [("orders","partner_id"), ("orders","partner_cost"), ("orders","partner_notes")]:
        try:
            conn.execute(f"ALTER TABLE {col_tup[0]} ADD COLUMN {col_tup[1]} TEXT DEFAULT NULL")
        except:
            pass
    # Also try with REAL type for cost
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN partner_cost REAL DEFAULT 0")
    except:
        pass
    # 迁移：用户表加提成比例
    try:
        conn.execute("ALTER TABLE users ADD COLUMN commission_rate REAL DEFAULT 10.0")
    except:
        pass
    # 迁移：订单表生产排期字段
    for col in ["production_start_date", "production_end_date"]:
        try:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT DEFAULT ''")
        except:
            pass
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN production_progress INTEGER DEFAULT 0")
    except:
        pass

    # 库存管理表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            category TEXT DEFAULT '',
            unit TEXT DEFAULT '',
            quantity REAL DEFAULT 0,
            reorder_level REAL DEFAULT 0,
            unit_cost REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('in','out')),
            quantity REAL NOT NULL,
            reference TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_by INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES inventory_items(id)
        )
    """)

    # 合作方表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            contact_person TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            business_type TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 采购订单表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_no TEXT NOT NULL DEFAULT '',
            partner_id INTEGER NOT NULL,
            order_id INTEGER DEFAULT NULL,
            items TEXT DEFAULT '[]',
            total_amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','in_production','delivered','settled')),
            delivery_date TEXT DEFAULT '',
            payment_terms TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            timeline TEXT DEFAULT '[]',
            created_by INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 种子用户
    from werkzeug.security import generate_password_hash
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        conn.execute(
            "INSERT INTO users (username,password_hash,display_name,role) VALUES (?,?,?,?)",
            ("admin", generate_password_hash("admin123"), "管理员", "admin")
        )
    conn.commit()
    conn.close()

# ========= 客户 CRUD =========
def get_customers():
    conn = get_db()
    rows = conn.execute("SELECT * FROM customers ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_customer(cid):
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_customer(name, company="", whatsapp="", country="", language="English", status="warm", notes=""):
    conn = get_db()
    # 去重检查：相同的WhatsApp号视为同一客户
    if whatsapp:
        existing = conn.execute("SELECT id, name FROM customers WHERE whatsapp=? AND whatsapp!=''", (whatsapp,)).fetchone()
        if existing:
            conn.close()
            return {"duplicate": True, "id": existing["id"], "name": existing["name"]}
    # 没有WhatsApp时，用姓名+公司去重
    existing = conn.execute(
        "SELECT id, name FROM customers WHERE name=? AND company=? AND name!=''",
        (name, company)
    ).fetchone()
    if existing:
        conn.close()
        return {"duplicate": True, "id": existing["id"], "name": existing["name"]}

    conn.execute("INSERT INTO customers (name,company,whatsapp,country,language,status,notes) VALUES (?,?,?,?,?,?,?)",
                 (name, company, whatsapp, country, language, status, notes))
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": cid}

def update_customer(cid, **kwargs):
    allowed = ['name','company','whatsapp','country','language','status','notes']
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    sets.append("updated_at=CURRENT_TIMESTAMP")
    conn = get_db()
    conn.execute(f"UPDATE customers SET {', '.join(sets)} WHERE id=?", (*vals, cid))
    conn.commit()
    conn.close()

def delete_customer(cid):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM customers WHERE id=?", (cid,))
    conn.commit()
    conn.close()


# ========= 合作方 CRUD =========
def get_partners():
    conn = get_db()
    rows = conn.execute("SELECT * FROM partners WHERE status='active' ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_partner(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_partner(data):
    conn = get_db()
    conn.execute(
        "INSERT INTO partners (name,contact_person,phone,business_type,notes) VALUES (?,?,?,?,?)",
        (
            data.get("name", ""),
            data.get("contact_person", ""),
            data.get("phone", ""),
            data.get("business_type", ""),
            data.get("notes", ""),
        )
    )
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": pid}


def update_partner(pid, data):
    allowed = ['name','contact_person','phone','business_type','notes','status']
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    sets.append("updated_at=CURRENT_TIMESTAMP")
    conn = get_db()
    conn.execute(f"UPDATE partners SET {', '.join(sets)} WHERE id=?", (*vals, pid))
    conn.commit()
    conn.close()


def delete_partner(pid):
    conn = get_db()
    conn.execute("DELETE FROM partners WHERE id=?", (pid,))
    conn.commit()
    conn.close()


# ========= 采购订单 CRUD =========
def _gen_po_no():
    import time
    date_str = time.strftime("%Y%m%d")
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM purchase_orders WHERE po_no LIKE ?",
        (f"PO-{date_str}-%",)
    ).fetchone()[0]
    conn.close()
    return f"PO-{date_str}-{count + 1:04d}"


def get_purchase_orders(status=None, partner_id=None, order_id=None, limit=100):
    conn = get_db()
    sql = """SELECT po.*, p.name as partner_name,
             u.display_name as created_name
             FROM purchase_orders po
             LEFT JOIN partners p ON po.partner_id=p.id
             LEFT JOIN users u ON po.created_by=u.id"""
    where = []
    params = []
    if status:
        if isinstance(status, list):
            placeholders = ",".join("?" * len(status))
            where.append(f"po.status IN ({placeholders})")
            params.extend(status)
        else:
            where.append("po.status=?")
            params.append(status)
    if partner_id:
        where.append("po.partner_id=?")
        params.append(partner_id)
    if order_id:
        where.append("po.order_id=?")
        params.append(order_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY po.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for field in ('items', 'timeline'):
            try:
                d[field] = json.loads(d.get(field, '[]'))
            except:
                d[field] = []
        result.append(d)
    return result


def get_purchase_order(oid):
    conn = get_db()
    row = conn.execute(
        """SELECT po.*, p.name as partner_name,
           u.display_name as created_name
           FROM purchase_orders po
           LEFT JOIN partners p ON po.partner_id=p.id
           LEFT JOIN users u ON po.created_by=u.id
           WHERE po.id=?""",
        (oid,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for field in ('items', 'timeline'):
        try:
            d[field] = json.loads(d.get(field, '[]'))
        except:
            d[field] = []
    return d


def add_purchase_order(data):
    conn = get_db()
    po_no = data.get("po_no", "") or _gen_po_no()
    timeline = json.dumps([{
        "status": data.get("status", "pending"),
        "by": data.get("created_by", 0),
        "note": "采购单创建",
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    conn.execute(
        """INSERT INTO purchase_orders (po_no,partner_id,order_id,items,total_amount,currency,
           status,delivery_date,payment_terms,notes,timeline,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            po_no,
            data.get("partner_id"),
            data.get("order_id"),
            json.dumps(data.get("items", [])),
            data.get("total_amount", 0),
            data.get("currency", "USD"),
            data.get("status", "pending"),
            data.get("delivery_date", ""),
            data.get("payment_terms", ""),
            data.get("notes", ""),
            timeline,
            data.get("created_by"),
        )
    )
    conn.commit()
    oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": oid, "po_no": po_no}


def update_purchase_order(oid, data):
    allowed = [
        'partner_id', 'order_id', 'total_amount', 'currency',
        'status', 'delivery_date', 'payment_terms', 'notes'
    ]
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if "items" in data:
        sets.append("items=?")
        vals.append(json.dumps(data["items"]))
    if sets:
        sets.append("updated_at=CURRENT_TIMESTAMP")
        conn = get_db()
        conn.execute(f"UPDATE purchase_orders SET {', '.join(sets)} WHERE id=?", (*vals, oid))
        conn.commit()
        conn.close()


def delete_purchase_order(oid):
    conn = get_db()
    conn.execute("DELETE FROM purchase_orders WHERE id=?", (oid,))
    conn.commit()
    conn.close()


def add_po_timeline_entry(oid, status, by_user, note=""):
    conn = get_db()
    row = conn.execute("SELECT timeline FROM purchase_orders WHERE id=?", (oid,)).fetchone()
    if not row:
        conn.close()
        return
    try:
        tl = json.loads(row["timeline"])
    except:
        tl = []
    tl.append({
        "status": status,
        "by": by_user,
        "note": note,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    conn.execute("UPDATE purchase_orders SET timeline=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (json.dumps(tl), oid))
    conn.commit()
    conn.close()


# ========= 消息 CRUD =========
def get_messages(customer_id, limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit)
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))

def add_message(customer_id, direction, content_cn="", content_en="", media_path=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (customer_id,direction,content_cn,content_en,media_path) VALUES (?,?,?,?,?)",
        (customer_id, direction, content_cn, content_en, media_path)
    )
    conn.execute("UPDATE customers SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()

# ========= 文件 CRUD =========
def get_media(filetype=None):
    conn = get_db()
    if filetype:
        rows = conn.execute("SELECT * FROM media_files WHERE filetype=? ORDER BY created_at DESC", (filetype,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM media_files ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_media(filename, filepath, filetype, filesize=0, description="", customer_id=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO media_files (filename,filepath,filetype,filesize,description,customer_id) VALUES (?,?,?,?,?,?)",
        (filename, filepath, filetype, filesize, description, customer_id)
    )
    conn.commit()
    conn.close()

def delete_media(mid):
    conn = get_db()
    row = conn.execute("SELECT filepath FROM media_files WHERE id=?", (mid,)).fetchone()
    if row:
        fp = row['filepath']
        if os.path.exists(fp):
            os.remove(fp)
    conn.execute("DELETE FROM media_files WHERE id=?", (mid,))
    conn.commit()
    conn.close()

# ========= AI生成记录 CRUD =========
def add_ai_generation(type_, prompt, result_url="", result_filename="", thumbnail_url="", customer_id=None, metadata=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO ai_generations (type,prompt,result_url,result_filename,thumbnail_url,customer_id,metadata) VALUES (?,?,?,?,?,?,?)",
        (type_, prompt, result_url, result_filename, thumbnail_url, customer_id, json.dumps(metadata or {}))
    )
    conn.commit()
    gid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return gid

def get_ai_generations(type_=None, limit=50):
    conn = get_db()
    if type_:
        rows = conn.execute("SELECT * FROM ai_generations WHERE type=? ORDER BY created_at DESC LIMIT ?", (type_, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM ai_generations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_ai_generation(gid):
    conn = get_db()
    row = conn.execute("SELECT result_filename FROM ai_generations WHERE id=?", (gid,)).fetchone()
    if row and row["result_filename"]:
        fp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", row["result_filename"])
        if os.path.exists(fp):
            os.remove(fp)
    conn.execute("DELETE FROM ai_generations WHERE id=?", (gid,))
    conn.commit()
    conn.close()

def get_ai_generation_stats():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute("SELECT COUNT(*) FROM ai_generations WHERE date(created_at)=?", (today,)).fetchone()[0]
    image_count = conn.execute("SELECT COUNT(*) FROM ai_generations WHERE type='image'").fetchone()[0]
    video_count = conn.execute("SELECT COUNT(*) FROM ai_generations WHERE type='video'").fetchone()[0]
    conn.close()
    return {"today": today_count, "images": image_count, "videos": video_count}

# ========= 邮件 =========
def get_email_settings():
    conn = get_db()
    row = conn.execute("SELECT * FROM email_settings WHERE id=1").fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "from_email": "",
        "from_name": "GLOWFORGE",
        "use_tls": True,
    }

def save_email_settings(data):
    conn = get_db()
    conn.execute("""
        INSERT INTO email_settings (id, smtp_host, smtp_port, smtp_user, smtp_pass, from_email, from_name, use_tls)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            smtp_host=excluded.smtp_host, smtp_port=excluded.smtp_port,
            smtp_user=excluded.smtp_user, smtp_pass=excluded.smtp_pass,
            from_email=excluded.from_email, from_name=excluded.from_name,
            use_tls=excluded.use_tls, updated_at=CURRENT_TIMESTAMP
    """, (
        data.get("smtp_host", "smtp.gmail.com"),
        data.get("smtp_port", 587),
        data.get("smtp_user", ""),
        data.get("smtp_pass", ""),
        data.get("from_email", ""),
        data.get("from_name", "GLOWFORGE"),
        1 if data.get("use_tls", True) else 0,
    ))
    conn.commit()
    conn.close()

def add_email_log(customer_id, to_email, subject, body, attachments=None, status="sent", error=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO email_log (customer_id, to_email, subject, body, attachments, status, error) VALUES (?,?,?,?,?,?,?)",
        (customer_id, to_email, subject, body, json.dumps(attachments or []), status, error)
    )
    conn.execute("UPDATE customers SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()

def get_email_log(customer_id, limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM email_log WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_email_log(limit=100):
    conn = get_db()
    rows = conn.execute(
        "SELECT e.*, c.name as customer_name, c.company as customer_company FROM email_log e LEFT JOIN customers c ON e.customer_id=c.id ORDER BY e.created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _parse_product(row):
    p = dict(row)
    for field in ('specs', 'price_tiers', 'images'):
        try:
            p[field] = json.loads(p.get(field, '{}'))
        except:
            p[field] = {} if field == 'specs' else []
    return p

# ========= 产品 =========
def get_products(category=None):
    conn = get_db()
    if category:
        rows = conn.execute("SELECT * FROM products WHERE category=? AND status='active' ORDER BY updated_at DESC", (category,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products WHERE status='active' ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [_parse_product(r) for r in rows]

def get_product(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    return _parse_product(row) if row else None

def add_product(data):
    conn = get_db()
    conn.execute(
        "INSERT INTO products (name,category,specs,price_tiers,description,images,unit,currency,min_order,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            data.get("name", ""),
            data.get("category", ""),
            json.dumps(data.get("specs", {})),
            json.dumps(data.get("price_tiers", [])),
            data.get("description", ""),
            json.dumps(data.get("images", [])),
            data.get("unit", "个"),
            data.get("currency", "USD"),
            data.get("min_order", 1),
            data.get("status", "active"),
        )
    )
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return pid

def update_product(pid, data):
    conn = get_db()
    conn.execute("""
        UPDATE products SET name=?,category=?,specs=?,price_tiers=?,description=?,images=?,unit=?,currency=?,min_order=?,status=?,updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (
        data.get("name", ""),
        data.get("category", ""),
        json.dumps(data.get("specs", {})),
        json.dumps(data.get("price_tiers", [])),
        data.get("description", ""),
        json.dumps(data.get("images", [])),
        data.get("unit", "个"),
        data.get("currency", "USD"),
        data.get("min_order", 1),
        data.get("status", "active"),
        pid,
    ))
    conn.commit()
    conn.close()

def delete_product(pid):
    conn = get_db()
    conn.execute("UPDATE products SET status='inactive' WHERE id=?", (pid,))
    conn.commit()
    conn.close()

def get_product_categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE category!='' AND status='active' ORDER BY category").fetchall()
    conn.close()
    return [r["category"] for r in rows]


# ========= 工程案例 =========
def get_cases(category=None):
    conn = get_db()
    if category:
        rows = conn.execute("SELECT * FROM cases WHERE category=? AND status='active' ORDER BY sort_order, created_at DESC", (category,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM cases WHERE status='active' ORDER BY sort_order, created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_case(cid):
    conn = get_db()
    row = conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_case(data):
    conn = get_db()
    conn.execute(
        "INSERT INTO cases (name,category,location,description,image_url,video_url,products_used,badge,sort_order,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            data.get("name", ""),
            data.get("category", "commercial"),
            data.get("location", ""),
            data.get("description", ""),
            data.get("image_url", ""),
            data.get("video_url", ""),
            data.get("products_used", ""),
            data.get("badge", ""),
            data.get("sort_order", 0),
            data.get("status", "active"),
        )
    )
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return cid

def update_case(cid, data):
    conn = get_db()
    conn.execute("""
        UPDATE cases SET name=?,category=?,location=?,description=?,image_url=?,video_url=?,products_used=?,badge=?,sort_order=?,status=?,updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (
        data.get("name", ""),
        data.get("category", "commercial"),
        data.get("location", ""),
        data.get("description", ""),
        data.get("image_url", ""),
        data.get("video_url", ""),
        data.get("products_used", ""),
        data.get("badge", ""),
        data.get("sort_order", 0),
        data.get("status", "active"),
        cid,
    ))
    conn.commit()
    conn.close()

def delete_case(cid):
    conn = get_db()
    conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.commit()
    conn.close()

def get_case_categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM cases WHERE category!='' AND status='active' ORDER BY category").fetchall()
    conn.close()
    return [r["category"] for r in rows]


def _parse_quote(row):
    q = dict(row)
    try:
        q["items"] = json.loads(q.get("items", "[]"))
    except:
        q["items"] = []
    return q


# ========= 报价 =========
def get_quotes(status=None, customer_id=None):
    conn = get_db()
    sql = "SELECT q.*, c.name as customer_name, c.company as customer_company FROM quotes q LEFT JOIN customers c ON q.customer_id=c.id"
    where = []
    params = []
    if status:
        where.append("q.status=?")
        params.append(status)
    if customer_id:
        where.append("q.customer_id=?")
        params.append(customer_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY q.created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_parse_quote(r) for r in rows]


def get_quote(qid):
    conn = get_db()
    row = conn.execute("SELECT q.*, c.name as customer_name, c.company as customer_company FROM quotes q LEFT JOIN customers c ON q.customer_id=c.id WHERE q.id=?", (qid,)).fetchone()
    conn.close()
    return _parse_quote(row) if row else None


def add_quote(data):
    import uuid, time
    conn = get_db()
    # 生成报价编号
    date_str = time.strftime("%Y%m%d")
    seq = uuid.uuid4().hex[:4].upper()
    cust_code = "CRM"
    if data.get("customer_id"):
        c = conn.execute("SELECT name FROM customers WHERE id=?", (data["customer_id"],)).fetchone()
        if c:
            cust_code = c["name"][:6].upper().replace(" ", "_")
    quote_no = f"BH-{date_str}-{cust_code}-{seq}"

    conn.execute(
        "INSERT INTO quotes (quote_no,customer_id,items,total_amount,currency,status,valid_until,notes) VALUES (?,?,?,?,?,?,?,?)",
        (
            quote_no,
            data.get("customer_id"),
            json.dumps(data.get("items", [])),
            data.get("total_amount", 0),
            data.get("currency", "USD"),
            data.get("status", "draft"),
            data.get("valid_until", ""),
            data.get("notes", ""),
        )
    )
    conn.commit()
    qid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": qid, "quote_no": quote_no}


def update_quote(qid, data):
    conn = get_db()
    sets = []
    vals = []
    for k in ("customer_id", "total_amount", "currency", "status", "valid_until", "notes", "pdf_path"):
        if k in data:
            sets.append(f"{k}=?")
            vals.append(data[k])
    if "items" in data:
        sets.append("items=?")
        vals.append(json.dumps(data["items"]))
    if sets:
        sets.append("updated_at=CURRENT_TIMESTAMP")
        conn.execute(f"UPDATE quotes SET {', '.join(sets)} WHERE id=?", (*vals, qid))
        conn.commit()
    conn.close()


def delete_quote(qid):
    conn = get_db()
    conn.execute("DELETE FROM quotes WHERE id=?", (qid,))
    conn.commit()
    conn.close()


# ========= 统计 =========
def get_stats():
    conn = get_db()
    customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    msgs = conn.execute("SELECT COUNT(*) FROM messages WHERE date(created_at)=?", (today,)).fetchone()[0]
    files = conn.execute("SELECT COUNT(*) FROM media_files").fetchone()[0]
    recent = conn.execute(
        "SELECT id, name, company FROM customers ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()

    # 订单统计
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    pending_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status='pending_approval'").fetchone()[0]
    in_production = conn.execute("SELECT COUNT(*) FROM orders WHERE status='in_production'").fetchone()[0]
    month_revenue = conn.execute(
        """SELECT COALESCE(SUM(total_amount),0) FROM orders
           WHERE strftime('%Y-%m', created_at)=strftime('%Y-%m', 'now')"""
    ).fetchone()[0]

    # 生产排期
    prod_confirmed = conn.execute("SELECT COUNT(*) FROM orders WHERE status='confirmed'").fetchone()[0]
    prod_shipped = conn.execute("SELECT COUNT(*) FROM orders WHERE status='shipped'").fetchone()[0]

    # 库存预警
    low_stock = conn.execute(
        "SELECT COUNT(*) FROM inventory_items WHERE quantity <= reorder_level"
    ).fetchone()[0]

    # 最近订单
    recent_orders = conn.execute(
        """SELECT o.id, o.order_no, o.status, o.total_amount, o.currency,
                  c.name as customer_name
           FROM orders o LEFT JOIN customers c ON o.customer_id=c.id
           ORDER BY o.created_at DESC LIMIT 5"""
    ).fetchall()

    conn.close()
    return {
        "customers": customers,
        "today_msgs": msgs,
        "total_files": files,
        "recent": [dict(r) for r in recent],
        # 订单
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "in_production": in_production,
        "month_revenue": round(float(month_revenue), 2),
        # 生产
        "prod_confirmed": prod_confirmed,
        "prod_shipped": prod_shipped,
        # 库存
        "low_stock": low_stock,
        # 最近订单
        "recent_orders": [dict(r) for r in recent_orders],
    }


def get_workbench():
    """今日工作台：所有客户按优先级排序，附带最近联系时间和天数"""
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.company, c.status,
               CAST(julianday('now') - julianday(c.updated_at) AS INTEGER) as days_since,
               (SELECT m.content_cn FROM messages m WHERE m.customer_id=c.id ORDER BY m.created_at DESC LIMIT 1) as last_msg,
               (SELECT m.created_at FROM messages m WHERE m.customer_id=c.id ORDER BY m.created_at DESC LIMIT 1) as last_msg_time,
               (SELECT COUNT(*) FROM messages m WHERE m.customer_id=c.id AND m.direction='sent' AND date(m.created_at)=date('now')) as today_sent
        FROM customers c
        ORDER BY
            CASE c.status WHEN 'hot' THEN 0 WHEN 'warm' THEN 1 ELSE 2 END,
            days_since DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========= 用户 CRUD =========
def get_users(active_only=True):
    conn = get_db()
    if active_only:
        rows = conn.execute(
            "SELECT id, username, display_name, role, title, commission_rate, active, created_at FROM users WHERE active=1 ORDER BY display_name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, username, display_name, role, title, commission_rate, active, created_at FROM users ORDER BY display_name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_by_username(username):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_user(data):
    from werkzeug.security import generate_password_hash
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username,password_hash,display_name,role,title) VALUES (?,?,?,?,?)",
            (
                data.get("username", ""),
                generate_password_hash(data.get("password", "123456")),
                data.get("display_name", ""),
                data.get("role", "sales"),
                data.get("title", ""),
            )
        )
        conn.commit()
        uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"id": uid}
    except Exception as e:
        conn.close()
        return {"error": str(e)}


def update_user(uid, data):
    from werkzeug.security import generate_password_hash
    allowed = ['display_name', 'role', 'title', 'active', 'commission_rate']
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if "password" in data and data["password"]:
        sets.append("password_hash=?")
        vals.append(generate_password_hash(data["password"]))
    if not sets:
        return
    conn = get_db()
    conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*vals, uid))
    conn.commit()
    conn.close()


# ========= 订单 CRUD =========
def get_orders(status=None, customer_id=None, limit=100):
    conn = get_db()
    sql = """SELECT o.*, c.name as customer_name, c.company as customer_company,
             u.display_name as assigned_name,
             p.name as partner_name
             FROM orders o LEFT JOIN customers c ON o.customer_id=c.id
             LEFT JOIN users u ON o.assigned_to=u.id
             LEFT JOIN partners p ON o.partner_id=p.id"""
    where = []
    params = []
    if status:
        if isinstance(status, list):
            placeholders = ",".join("?" * len(status))
            where.append(f"o.status IN ({placeholders})")
            params.extend(status)
        else:
            where.append("o.status=?")
            params.append(status)
    if customer_id:
        where.append("o.customer_id=?")
        params.append(customer_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY o.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for field in ('items', 'timeline'):
            try:
                d[field] = json.loads(d.get(field, '[]'))
            except:
                d[field] = []
        # 利润计算
        revenue = float(d.get("total_amount", 0) or 0)
        cost = float(d.get("partner_cost", 0) or 0)
        d["profit"] = round(revenue - cost, 2)
        d["profit_margin"] = round(d["profit"] / revenue * 100, 1) if revenue else 0
        result.append(d)
    return result


def get_order(oid):
    conn = get_db()
    row = conn.execute(
        """SELECT o.*, c.name as customer_name, c.company as customer_company,
           u.display_name as assigned_name,
           p.name as partner_name
           FROM orders o LEFT JOIN customers c ON o.customer_id=c.id
           LEFT JOIN users u ON o.assigned_to=u.id
           LEFT JOIN partners p ON o.partner_id=p.id
           WHERE o.id=?""",
        (oid,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for field in ('items', 'timeline'):
        try:
            d[field] = json.loads(d.get(field, '[]'))
        except:
            d[field] = []
    # 利润计算
    revenue = float(d.get("total_amount", 0) or 0)
    cost = float(d.get("partner_cost", 0) or 0)
    d["profit"] = round(revenue - cost, 2)
    d["profit_margin"] = round(d["profit"] / revenue * 100, 1) if revenue else 0
    return d


def _gen_order_no():
    import time
    date_str = time.strftime("%Y%m%d")
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE order_no LIKE ?",
        (f"ORD-{date_str}-%",)
    ).fetchone()[0]
    conn.close()
    return f"ORD-{date_str}-{count + 1:04d}"


def add_order(data):
    conn = get_db()
    order_no = data.get("order_no", "") or _gen_order_no()
    timeline = json.dumps([{
        "status": data.get("status", "pending_approval"),
        "by": data.get("created_by", 0),
        "note": "订单创建",
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    conn.execute(
        """INSERT INTO orders (order_no,customer_id,quote_id,items,total_amount,currency,
           deposit_amount,deposit_date,deposit_method,deposit_received,
           balance_amount,balance_date,balance_method,balance_received,
           status,production_notes,assigned_to,shipping_info,timeline,created_by,notes,
           partner_id,partner_cost,partner_notes,
           production_start_date,production_end_date,production_progress)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            order_no,
            data.get("customer_id"),
            data.get("quote_id"),
            json.dumps(data.get("items", [])),
            data.get("total_amount", 0),
            data.get("currency", "USD"),
            data.get("deposit_amount", 0),
            data.get("deposit_date", ""),
            data.get("deposit_method", ""),
            1 if data.get("deposit_received") else 0,
            data.get("balance_amount", 0),
            data.get("balance_date", ""),
            data.get("balance_method", ""),
            1 if data.get("balance_received") else 0,
            data.get("status", "pending_approval"),
            data.get("production_notes", ""),
            data.get("assigned_to"),
            data.get("shipping_info", ""),
            timeline,
            data.get("created_by"),
            data.get("notes", ""),
            data.get("partner_id"),
            data.get("partner_cost", 0),
            data.get("partner_notes", ""),
            data.get("production_start_date", ""),
            data.get("production_end_date", ""),
            data.get("production_progress", 0),
        )
    )
    conn.commit()
    oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": oid, "order_no": order_no}


def update_order(oid, data):
    allowed = [
        'customer_id', 'quote_id', 'total_amount', 'currency',
        'deposit_amount', 'deposit_date', 'deposit_method', 'deposit_received',
        'balance_amount', 'balance_date', 'balance_method', 'balance_received',
        'status', 'production_notes', 'assigned_to', 'shipping_info', 'notes',
        'partner_id', 'partner_cost', 'partner_notes',
        'production_start_date', 'production_end_date', 'production_progress',
    ]
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            if k in ('deposit_received', 'balance_received'):
                v = 1 if v else 0
            sets.append(f"{k}=?")
            vals.append(v)
    if "items" in data:
        sets.append("items=?")
        vals.append(json.dumps(data["items"]))
    if sets:
        sets.append("updated_at=CURRENT_TIMESTAMP")
        conn = get_db()
        conn.execute(f"UPDATE orders SET {', '.join(sets)} WHERE id=?", (*vals, oid))
        conn.commit()
        conn.close()


def delete_order(oid):
    conn = get_db()
    conn.execute("DELETE FROM orders WHERE id=?", (oid,))
    conn.commit()
    conn.close()


def add_timeline_entry(oid, status, by_user, note=""):
    conn = get_db()
    row = conn.execute("SELECT timeline FROM orders WHERE id=?", (oid,)).fetchone()
    if not row:
        conn.close()
        return
    try:
        tl = json.loads(row["timeline"])
    except:
        tl = []
    tl.append({
        "status": status,
        "by": by_user,
        "note": note,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    conn.execute("UPDATE orders SET timeline=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (json.dumps(tl), oid))
    conn.commit()
    conn.close()


def get_payment_dashboard():
    conn = get_db()
    total_pending = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE status NOT IN ('delivered','archived','cancelled')"
    ).fetchone()[0]
    deposit_pending = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE deposit_received=0 AND status NOT IN ('delivered','archived','cancelled','pending_approval')"
    ).fetchone()[0]
    balance_pending = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE balance_received=0 AND status IN ('shipped','delivered')"
    ).fetchone()[0]
    total_receivable = conn.execute(
        "SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status NOT IN ('delivered','archived','cancelled')"
    ).fetchone()[0]
    total_received = conn.execute(
        """SELECT COALESCE(SUM(
            CASE WHEN deposit_received THEN deposit_amount ELSE 0 END +
            CASE WHEN balance_received THEN balance_amount ELSE 0 END
        ),0) FROM orders"""
    ).fetchone()[0]
    conn.close()
    return {
        "total_pending": total_pending,
        "deposit_pending": deposit_pending,
        "balance_pending": balance_pending,
        "total_receivable": round(total_receivable, 2),
        "total_received": round(total_received, 2),
    }


def get_order_profit_stats(group=None):
    conn = get_db()
    # 总体统计
    row = conn.execute(
        """SELECT COUNT(*) as total_orders,
           COALESCE(SUM(total_amount),0) as total_revenue,
           COALESCE(SUM(partner_cost),0) as total_cost
           FROM orders"""
    ).fetchone()
    total_revenue = row["total_revenue"]
    total_cost = row["total_cost"] or 0
    total_profit = round(total_revenue - total_cost, 2)
    avg_margin = round(total_profit / total_revenue * 100, 1) if total_revenue else 0

    result = {
        "total_orders": row["total_orders"],
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": total_profit,
        "avg_margin": avg_margin,
    }

    if group == "month":
        rows = conn.execute(
            """SELECT strftime('%Y-%m', created_at) as month,
               COUNT(*) as order_count,
               COALESCE(SUM(total_amount),0) as revenue,
               COALESCE(SUM(partner_cost),0) as cost
               FROM orders GROUP BY month ORDER BY month DESC"""
        ).fetchall()
        result["groups"] = []
        for r in rows:
            rev = r["revenue"]
            cst = r["cost"] or 0
            result["groups"].append({
                "label": r["month"],
                "order_count": r["order_count"],
                "revenue": round(rev, 2),
                "cost": round(cst, 2),
                "profit": round(rev - cst, 2),
                "margin": round((rev - cst) / rev * 100, 1) if rev else 0,
            })

    if group == "sales":
        rows = conn.execute(
            """SELECT COALESCE(u.display_name, '未指派') as sales_name,
               COUNT(*) as order_count,
               COALESCE(SUM(o.total_amount),0) as revenue,
               COALESCE(SUM(o.partner_cost),0) as cost
               FROM orders o LEFT JOIN users u ON o.assigned_to=u.id
               GROUP BY o.assigned_to ORDER BY revenue DESC"""
        ).fetchall()
        result["groups"] = []
        for r in rows:
            rev = r["revenue"]
            cst = r["cost"] or 0
            result["groups"].append({
                "label": r["sales_name"],
                "order_count": r["order_count"],
                "revenue": round(rev, 2),
                "cost": round(cst, 2),
                "profit": round(rev - cst, 2),
                "margin": round((rev - cst) / rev * 100, 1) if rev else 0,
            })

    conn.close()
    return result


def get_order_stats():
    """订单统计报表：一次性返回摘要、月度趋势、状态分布、销售业绩"""
    conn = get_db()
    result = {}

    # --- 摘要卡片 ---
    row = conn.execute("""
        SELECT COUNT(*) as total_orders,
               COALESCE(SUM(total_amount),0) as total_revenue,
               COALESCE(SUM(partner_cost),0) as total_cost
        FROM orders
    """).fetchone()
    revenue = row["total_revenue"]
    cost = row["total_cost"] or 0
    result["summary"] = {
        "total_orders": row["total_orders"],
        "total_revenue": round(revenue, 2),
        "total_cost": round(cost, 2),
        "total_profit": round(revenue - cost, 2),
    }

    # --- 月度趋势（升序，供折线图） ---
    rows = conn.execute("""
        SELECT strftime('%Y-%m', created_at) as month,
               COUNT(*) as order_count,
               COALESCE(SUM(total_amount),0) as revenue
        FROM orders
        GROUP BY month ORDER BY month ASC
    """).fetchall()
    result["monthly_trend"] = [
        {"label": r["month"], "order_count": r["order_count"], "revenue": round(r["revenue"], 2)}
        for r in rows
    ]

    # --- 状态分布 ---
    STATUS_LABELS = {
        "pending_approval": "待审核", "confirmed": "已确认",
        "deposit_pending": "待定金", "in_production": "生产中",
        "shipped": "已发货", "delivered": "已交付",
        "archived": "已归档", "cancelled": "已取消",
    }
    rows = conn.execute("""
        SELECT status, COUNT(*) as cnt FROM orders GROUP BY status ORDER BY cnt DESC
    """).fetchall()
    result["status_distribution"] = [
        {"status": r["status"], "label": STATUS_LABELS.get(r["status"], r["status"]), "count": r["cnt"]}
        for r in rows
    ]

    # --- 销售业绩（按营收降序） ---
    rows = conn.execute("""
        SELECT COALESCE(u.display_name, '未指派') as sales_name,
               COUNT(*) as order_count,
               COALESCE(SUM(o.total_amount),0) as revenue
        FROM orders o LEFT JOIN users u ON o.assigned_to=u.id
        GROUP BY o.assigned_to ORDER BY revenue DESC
    """).fetchall()
    result["sales_performance"] = [
        {"sales_name": r["sales_name"], "order_count": r["order_count"], "revenue": round(r["revenue"], 2)}
        for r in rows
    ]

    conn.close()
    return result


def get_commission_stats():
    """销售提成统计：按销售员汇总，含每笔订单明细"""
    conn = get_db()
    result = {}

    # 所有有订单指派的销售员
    rows = conn.execute("""
        SELECT u.id as user_id, u.display_name,
               COALESCE(u.commission_rate, 10.0) as commission_rate,
               COUNT(o.id) as order_count,
               COALESCE(SUM(o.total_amount),0) as total_revenue,
               COALESCE(SUM(CAST(o.partner_cost AS REAL)),0) as total_cost
        FROM orders o
        JOIN users u ON o.assigned_to=u.id
        WHERE o.assigned_to IS NOT NULL
        GROUP BY o.assigned_to
        ORDER BY total_revenue DESC
    """).fetchall()

    sales_summary = []
    for r in rows:
        profit = round(r["total_revenue"] - r["total_cost"], 2)
        rate = r["commission_rate"]
        commission = round(profit * rate / 100, 2)
        sales_summary.append({
            "user_id": r["user_id"],
            "sales_name": r["display_name"],
            "commission_rate": rate,
            "order_count": r["order_count"],
            "total_revenue": round(r["total_revenue"], 2),
            "total_cost": round(r["total_cost"], 2),
            "total_profit": profit,
            "total_commission": commission,
        })
    result["sales_summary"] = sales_summary

    # 全局汇总
    total_commission = sum(s["total_commission"] for s in sales_summary)
    total_profit = sum(s["total_profit"] for s in sales_summary)
    total_revenue = sum(s["total_revenue"] for s in sales_summary)
    total_orders = sum(s["order_count"] for s in sales_summary)
    result["summary"] = {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "total_profit": round(total_profit, 2),
        "total_commission": round(total_commission, 2),
        "avg_commission_rate": round(total_commission / total_profit * 100, 1) if total_profit else 0,
    }

    # 每笔订单明细
    detail_rows = conn.execute("""
        SELECT o.id, o.order_no, o.created_at, o.status,
               c.name as customer_name,
               u.display_name as sales_name,
               COALESCE(u.commission_rate, 10.0) as commission_rate,
               o.total_amount,
               CAST(o.partner_cost AS REAL) as partner_cost,
               o.assigned_to
        FROM orders o
        JOIN users u ON o.assigned_to=u.id
        LEFT JOIN customers c ON o.customer_id=c.id
        WHERE o.assigned_to IS NOT NULL
        ORDER BY o.created_at DESC
    """).fetchall()

    detail = []
    for r in detail_rows:
        revenue = float(r["total_amount"] or 0)
        cost = float(r["partner_cost"] or 0)
        profit = round(revenue - cost, 2)
        rate = r["commission_rate"]
        commission = round(profit * rate / 100, 2)
        detail.append({
            "id": r["id"],
            "order_no": r["order_no"],
            "created_at": r["created_at"],
            "status": r["status"],
            "customer_name": r["customer_name"],
            "sales_name": r["sales_name"],
            "total_amount": revenue,
            "partner_cost": cost,
            "profit": profit,
            "commission_rate": rate,
            "commission": commission,
        })
    result["detail"] = detail

    conn.close()
    return result


def get_production_schedule():
    """生产排期：按阶段分组返回订单列表"""
    conn = get_db()
    rows = conn.execute("""
        SELECT o.id, o.order_no, o.status, o.created_at,
               o.total_amount, o.currency,
               o.production_notes, o.production_start_date,
               o.production_end_date, o.production_progress,
               o.shipping_info, o.assigned_to,
               c.name as customer_name, c.company as customer_company,
               u.display_name as assigned_name
        FROM orders o
        LEFT JOIN customers c ON o.customer_id=c.id
        LEFT JOIN users u ON o.assigned_to=u.id
        WHERE o.status IN ('confirmed','in_production','shipped')
        ORDER BY
          CASE o.status
            WHEN 'in_production' THEN 0
            WHEN 'confirmed' THEN 1
            WHEN 'shipped' THEN 2
          END,
          o.production_start_date ASC,
          o.created_at DESC
    """).fetchall()

    result = {"confirmed": [], "in_production": [], "shipped": []}
    for r in rows:
        item = {
            "id": r["id"],
            "order_no": r["order_no"],
            "status": r["status"],
            "created_at": r["created_at"],
            "total_amount": float(r["total_amount"] or 0),
            "currency": r["currency"] or "USD",
            "customer_name": r["customer_name"] or "",
            "customer_company": r["customer_company"] or "",
            "assigned_name": r["assigned_name"] or "",
            "production_notes": r["production_notes"] or "",
            "production_start_date": r["production_start_date"] or "",
            "production_end_date": r["production_end_date"] or "",
            "production_progress": r["production_progress"] or 0,
            "shipping_info": r["shipping_info"] or "",
        }
        status = r["status"]
        if status in result:
            result[status].append(item)

    conn.close()
    return result


# ========= 库存管理 CRUD =========
def get_inventory_items(category=None, low_stock=False):
    conn = get_db()
    where = []
    params = []
    if category:
        where.append("category=?")
        params.append(category)
    if low_stock:
        where.append("quantity <= reorder_level")
    sql = "SELECT * FROM inventory_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY category, name"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["is_low_stock"] = d["quantity"] <= d["reorder_level"]
        d["stock_value"] = round(d["quantity"] * d["unit_cost"], 2)
        result.append(d)
    return result


def get_inventory_item(iid):
    conn = get_db()
    row = conn.execute("SELECT * FROM inventory_items WHERE id=?", (iid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["is_low_stock"] = d["quantity"] <= d["reorder_level"]
    d["stock_value"] = round(d["quantity"] * d["unit_cost"], 2)
    return d


def add_inventory_item(data):
    conn = get_db()
    conn.execute(
        """INSERT INTO inventory_items (name,category,unit,quantity,reorder_level,unit_cost,notes)
           VALUES (?,?,?,?,?,?,?)""",
        (
            data.get("name", ""),
            data.get("category", ""),
            data.get("unit", ""),
            float(data.get("quantity", 0)),
            float(data.get("reorder_level", 0)),
            float(data.get("unit_cost", 0)),
            data.get("notes", ""),
        )
    )
    conn.commit()
    iid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": iid}


def update_inventory_item(iid, data):
    allowed = ["name", "category", "unit", "quantity", "reorder_level", "unit_cost", "notes"]
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            if k in ("quantity", "reorder_level", "unit_cost"):
                v = float(v)
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    sets.append("updated_at=CURRENT_TIMESTAMP")
    conn = get_db()
    conn.execute(f"UPDATE inventory_items SET {', '.join(sets)} WHERE id=?", (*vals, iid))
    conn.commit()
    conn.close()


def delete_inventory_item(iid):
    conn = get_db()
    conn.execute("DELETE FROM inventory_items WHERE id=?", (iid,))
    conn.execute("DELETE FROM stock_movements WHERE item_id=?", (iid,))
    conn.commit()
    conn.close()


def add_stock_movement(item_id, mtype, quantity, reference="", notes="", created_by=None):
    conn = get_db()
    conn.execute(
        """INSERT INTO stock_movements (item_id,type,quantity,reference,notes,created_by)
           VALUES (?,?,?,?,?,?)""",
        (item_id, mtype, float(quantity), reference, notes, created_by)
    )
    # Update item quantity
    sign = 1 if mtype == "in" else -1
    conn.execute(
        "UPDATE inventory_items SET quantity=quantity+?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (sign * float(quantity), item_id)
    )
    conn.commit()
    conn.close()


def get_stock_movements(item_id=None, limit=50):
    conn = get_db()
    if item_id:
        rows = conn.execute(
            """SELECT m.*, i.name as item_name, u.display_name as created_name
               FROM stock_movements m
               LEFT JOIN inventory_items i ON m.item_id=i.id
               LEFT JOIN users u ON m.created_by=u.id
               WHERE m.item_id=?
               ORDER BY m.created_at DESC LIMIT ?""",
            (item_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT m.*, i.name as item_name, u.display_name as created_name
               FROM stock_movements m
               LEFT JOIN inventory_items i ON m.item_id=i.id
               LEFT JOIN users u ON m.created_by=u.id
               ORDER BY m.created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory_summary():
    conn = get_db()
    row = conn.execute(
        """SELECT COUNT(*) as total_items,
                  COALESCE(SUM(quantity),0) as total_quantity,
                  COALESCE(SUM(quantity*unit_cost),0) as total_value
           FROM inventory_items"""
    ).fetchone()
    low_count = conn.execute(
        "SELECT COUNT(*) FROM inventory_items WHERE quantity <= reorder_level"
    ).fetchone()[0]
    categories = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM inventory_items GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return {
        "total_items": row["total_items"],
        "total_quantity": round(row["total_quantity"], 2),
        "total_value": round(row["total_value"], 2),
        "low_stock_count": low_count,
        "categories": [dict(r) for r in categories],
    }
