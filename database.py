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
            created_by INTEGER DEFAULT NULL,
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
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'deposit',
            amount REAL NOT NULL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            payment_date TEXT DEFAULT '',
            method TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            recorded_by INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
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

    # 获客模块：客户表加字段
    for col_lead in [("customers","source"), ("customers","campaign"), ("customers","assigned_to"),
                     ("customers","lead_status"), ("customers","lead_score"),
                     ("customers","first_contacted_at"), ("customers","last_contacted_at")]:
        try:
            if col_lead[1] in ("lead_score",):
                conn.execute(f"ALTER TABLE {col_lead[0]} ADD COLUMN {col_lead[1]} INTEGER DEFAULT 0")
            elif col_lead[1] in ("last_contacted_at",):
                # SQLite不允许ALTER TABLE加非固定DEFAULT，先加列再UPDATE
                conn.execute(f"ALTER TABLE {col_lead[0]} ADD COLUMN {col_lead[1]} TIMESTAMP")
                conn.execute(f"UPDATE {col_lead[0]} SET {col_lead[1]} = updated_at")
            else:
                conn.execute(f"ALTER TABLE {col_lead[0]} ADD COLUMN {col_lead[1]} TEXT DEFAULT ''")
        except:
            pass

    # 跟进提醒：对已有数据的 NULL 值回填为 updated_at（兼容旧数据库）
    try:
        conn.execute("UPDATE customers SET last_contacted_at = updated_at WHERE last_contacted_at IS NULL AND updated_at IS NOT NULL")
    except:
        pass

    # 公海自动流转：索引
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_assigned_to ON customers(assigned_to)")
    except:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_last_contacted ON customers(last_contacted_at)")
    except:
        pass

    # 媒体标签表
    conn.execute(
        "CREATE TABLE IF NOT EXISTS media_tags ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT NOT NULL UNIQUE,"
        "type TEXT DEFAULT 'general',"
        "color TEXT DEFAULT '#00f2ff',"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS media_tag_relations ("
        "media_id INTEGER NOT NULL,"
        "tag_id INTEGER NOT NULL,"
        "PRIMARY KEY (media_id, tag_id),"
        "FOREIGN KEY (media_id) REFERENCES media_files(id),"
        "FOREIGN KEY (tag_id) REFERENCES media_tags(id)"
        ")"
    )

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
    # 通知表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            link TEXT DEFAULT '',
            related_type TEXT DEFAULT '',
            related_id INTEGER DEFAULT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read)")
    except:
        pass
    # 操作日志表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            performed_by INTEGER NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER DEFAULT NULL,
            summary TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_entity ON activity_log(entity_type, entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_time ON activity_log(created_at)")
    except:
        pass
    # 生产任务表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_done INTEGER DEFAULT 0,
            done_at TIMESTAMP,
            done_by INTEGER DEFAULT NULL,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_tasks_order ON production_tasks(order_id)")
    except:
        pass
    # 发货物流表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            ship_date TEXT DEFAULT '',
            tracking_no TEXT DEFAULT '',
            carrier TEXT DEFAULT '',
            shipping_cost REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            package_info TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            notes TEXT DEFAULT '',
            created_by INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shipments_order ON shipments(order_id)")
    except:
        pass
    # 质检模板表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qc_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            items TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 质检记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qc_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            template_id INTEGER DEFAULT NULL,
            inspector_id INTEGER DEFAULT NULL,
            result TEXT DEFAULT 'pending',
            items TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            inspected_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_inspections_order ON qc_inspections(order_id)")
    except:
        pass

    # ==================== V5 — Global Revenue OS tables ====================
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            base_currency TEXT NOT NULL DEFAULT 'USD',
            default_markup REAL DEFAULT 1.3,
            status TEXT DEFAULT 'active',
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS region_countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_id INTEGER NOT NULL,
            country_code TEXT NOT NULL,
            country_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (region_id) REFERENCES regions(id),
            UNIQUE(region_id, country_code)
        );
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_currency TEXT NOT NULL,
            to_currency TEXT NOT NULL DEFAULT 'USD',
            rate REAL NOT NULL,
            date TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_currency, to_currency, date)
        );
        CREATE TABLE IF NOT EXISTS factories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT DEFAULT '',
            country TEXT DEFAULT 'China',
            base_currency TEXT DEFAULT 'CNY',
            capability_tags TEXT DEFAULT '[]',
            max_capacity_monthly INTEGER DEFAULT 0,
            current_load INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            shipping_zones TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agent_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL UNIQUE,
            region_id INTEGER,
            name TEXT DEFAULT '',
            role TEXT DEFAULT 'sales',
            languages TEXT DEFAULT '[]',
            pricing_multiplier REAL DEFAULT 1.0,
            culture_context TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (region_id) REFERENCES regions(id)
        );
        CREATE TABLE IF NOT EXISTS market_pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_id INTEGER NOT NULL,
            product_category TEXT NOT NULL,
            min_price REAL DEFAULT 0,
            max_price REAL DEFAULT 0,
            target_margin REAL DEFAULT 0.50,
            min_margin REAL DEFAULT 0.35,
            competitor_factor REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (region_id) REFERENCES regions(id),
            UNIQUE(region_id, product_category)
        );
        CREATE TABLE IF NOT EXISTS production_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factory_id INTEGER NOT NULL,
            product_category TEXT NOT NULL,
            base_cost REAL DEFAULT 0,
            currency TEXT DEFAULT 'CNY',
            material_cost REAL DEFAULT 0,
            labor_cost REAL DEFAULT 0,
            overhead_cost REAL DEFAULT 0,
            effective_from TEXT NOT NULL,
            effective_to TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (factory_id) REFERENCES factories(id)
        );
    """)

    # V5: ALTER TABLE migrations for existing tables
    for col_v5 in [
        ("partners","country", "TEXT DEFAULT ''"),
        ("partners","region_id", "INTEGER DEFAULT NULL"),
        ("partners","commission_type", "TEXT DEFAULT 'percentage'"),
        ("partners","commission_rate", "REAL DEFAULT 0"),
        ("partners","currency", "TEXT DEFAULT 'USD'"),
        ("partners","payment_terms", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {col_v5[0]} ADD COLUMN {col_v5[1]} {col_v5[2]}")
        except:
            pass

    for col_cust in [("customers","region_id", "INTEGER DEFAULT NULL")]:
        try:
            conn.execute(f"ALTER TABLE {col_cust[0]} ADD COLUMN {col_cust[1]} {col_cust[2]}")
        except:
            pass

    for col_order in [
        ("orders","region_id", "INTEGER DEFAULT NULL"),
        ("orders","base_amount", "REAL DEFAULT 0"),
        ("orders","exchange_rate", "REAL DEFAULT 1.0"),
        ("orders","factory_id", "INTEGER DEFAULT NULL"),
        ("orders","production_cost", "REAL DEFAULT 0"),
        ("orders","shipping_cost", "REAL DEFAULT 0"),
        ("orders","platform_fee", "REAL DEFAULT 0"),
        ("orders","net_profit", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {col_order[0]} ADD COLUMN {col_order[1]} {col_order[2]}")
        except:
            pass

    try:
        conn.execute("ALTER TABLE users ADD COLUMN region_commissions TEXT DEFAULT '{}'")
    except:
        pass

    # ==================== V6 — Financial Intelligence OS tables ====================
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pl_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('revenue','cogs','expense','other_income','other_expense')),
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pl_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_code TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK(type IN ('monthly','quarterly','yearly')),
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_closed INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pl_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            order_id INTEGER DEFAULT NULL,
            amount REAL NOT NULL DEFAULT 0,
            entry_type TEXT NOT NULL DEFAULT 'actual' CHECK(entry_type IN ('actual','budget','adjustment')),
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (period_id) REFERENCES pl_periods(id),
            FOREIGN KEY (account_id) REFERENCES pl_accounts(id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT NOT NULL UNIQUE,
            order_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            total_amount REAL NOT NULL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','sent','paid','overdue','cancelled')),
            pdf_path TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            sent_at TIMESTAMP,
            paid_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            created_by INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL CHECK(category IN ('operation','marketing','shipping','commission','salary','office','travel','maintenance','other')),
            amount REAL NOT NULL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            expense_date TEXT NOT NULL,
            vendor TEXT DEFAULT '',
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            paid_by INTEGER DEFAULT NULL,
            approved_by INTEGER DEFAULT NULL,
            approved_at TIMESTAMP,
            receipt_path TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paid_by) REFERENCES users(id),
            FOREIGN KEY (approved_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            category TEXT NOT NULL,
            planned_amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(period, category)
        );
    """)

    # V6: ALTER TABLE migrations
    for col_v6 in [
        ("customers","credit_limit", "REAL DEFAULT 0"),
        ("customers","payment_terms", "TEXT DEFAULT '30'"),
        ("customers","tax_id", "TEXT DEFAULT ''"),
        ("orders","invoice_id", "INTEGER DEFAULT NULL"),
        ("orders","tax_rate", "REAL DEFAULT 0"),
        ("orders","tax_amount", "REAL DEFAULT 0"),
        ("payments","invoice_id", "INTEGER DEFAULT NULL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {col_v6[0]} ADD COLUMN {col_v6[1]} {col_v6[2]}")
        except:
            pass

    # V6: Indexes
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_pl_entries_period ON pl_entries(period_id)",
        "CREATE INDEX IF NOT EXISTS idx_pl_entries_account ON pl_entries(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_pl_entries_order ON pl_entries(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_invoices_order ON invoices(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)",
        "CREATE INDEX IF NOT EXISTS idx_budgets_period ON budgets(period)",
    ]:
        try:
            conn.execute(idx)
        except:
            pass

    # ==================== V3 — Self-Optimizing Sales System tables ====================
    init_v3_tables(conn)

    # ==================== V4 — Autonomous Sales System tables ====================
    init_v4_tables(conn)

    conn.commit()
    conn.close()

# ==================== V7 — AI Evolution / Feedback Rules ====================

def init_ai_evolution():
    """初始化 AI 进化系统（建表 + 添加默认规则）"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'general',
            trigger_condition TEXT DEFAULT '',
            action_rule TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'suggestion' CHECK(severity IN ('hard_rule','suggestion')),
            source_scenario TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 插入默认进化规则（从评估结果中提炼）
    defaults = [
        ("b2b_rule", "客户询价", "报价前必须先问图纸/尺寸/安装环境，不得直接报具体金额。回复格式：先确认需求→要求提供图纸或尺寸→再报价。", "hard_rule", "system_eval"),
        ("b2b_rule", "客户问价格区间", "如果客户坚持要价格范围，用ABC三级配置报价法（标准/高端/豪华），但必须加一句'最终价格需要根据您的具体图纸确认'。", "hard_rule", "system_eval"),
        ("objection_handling", "客户比价", "比价场景必须做三件事：①指出低价产品的具体偷工减料点（电源认证/钢材等级/LED芯片）；②反问对方报价单是否包含同等规格；③提供梯度配置选项而不是直接降价。", "hard_rule", "system_eval"),
        ("objection_handling", "客户说太贵", "砍价场景禁止用ABC分级报价。话术结构：①理解对方预算考虑→②解释为什么我们的配置值这个价（具体到部件）→③问对方预算，提供配置调整方案而不是直接降价。", "hard_rule", "system_eval"),
        ("objection_handling", "客户投诉售后", "售后场景三步骤：①立即道歉安抚→②要求提供照片/视频证据→③说明保修政策并给出具体解决方案（换件/维修/退换）。必须中英文双语回复。", "hard_rule", "system_eval"),
        ("regional_strategy", "中东客户", "中东客户强调：①尊重宗教文化；②清真/合规认证；③家族企业信誉；④长期合作关系。报价中包含FOB/DDP选项。", "suggestion", "system_eval"),
        ("regional_strategy", "欧美客户", "欧美客户强调：①认证标准（UL/CE/ISO）；②环保合规（RoHS）；③知识产权保护；④交货准时率。提供详细的spec sheet。", "suggestion", "system_eval"),
        ("sales_tactic", "OEM合作咨询", "OEM客户必须说明：①客户保护政策（不接触终端客户）；②批次一致性控制流程；③产能证明。给出梯度定价框架而不是固定报价。", "hard_rule", "system_eval"),
        ("sales_tactic", "客户要样品", "样品政策话术：①样品需要付费但批量订单可退还；②询问具体测试需求以便准备正确样品；③提供样品种类选项（不锈钢/亚克力/定制logo）。", "hard_rule", "system_eval"),
        ("sales_tactic", "客户要目录", "解释为什么没有固定价格表（全定制业务），然后引导客户选择产品类别，发送对应案例和参考价格。", "hard_rule", "system_eval"),
        ("sales_tactic", "客户问交期", "交期回复必须包含：①标准生产时间（10-15天）；②运输方式和时间选项（空运vs海运DDP）；③要求确认项目时间线以便锁定生产槽位。", "hard_rule", "system_eval"),
        ("sales_tactic", "A/B/C报价结尾", "禁止所有回复以'回复A、B或C'结尾。必须根据对话语境使用其他推进话术：如'发我图纸/尺寸，我给您精确报价'或'您倾向哪个配置？我锁定最终价格。'。ABC格式仅作为内部参考，客户看到的必须是自然对话。", "hard_rule", "system_eval"),
    ]
    for cat, trigger, rule, severity, source in defaults:
        existing = conn.execute(
            "SELECT COUNT(*) FROM ai_feedback WHERE category=? AND trigger_condition=? AND action_rule=?",
            (cat, trigger, rule)
        ).fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO ai_feedback (category, trigger_condition, action_rule, severity, source_scenario) VALUES (?,?,?,?,?)",
                (cat, trigger, rule, severity, source)
            )

    # AI 测试结果表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT NOT NULL,
            persona_name TEXT DEFAULT '',
            conversation TEXT DEFAULT '[]',
            summary TEXT DEFAULT '{}',
            scores TEXT DEFAULT '{}',
            generated_rules INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_ai_test_result(persona_id, persona_name, conversation, summary, scores, generated_rules=0):
    """保存 AI 测试结果"""
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO ai_test_results (persona_id, persona_name, conversation, summary, scores, generated_rules)
           VALUES (?,?,?,?,?,?)""",
        (persona_id, persona_name,
         json.dumps(conversation, ensure_ascii=False),
         json.dumps(summary, ensure_ascii=False),
         json.dumps(scores, ensure_ascii=False),
         generated_rules)
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def get_ai_test_results(limit=20):
    """获取 AI 测试历史"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, persona_id, persona_name, summary, scores, generated_rules, created_at "
        "FROM ai_test_results ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("scores"), str):
            try:
                item["scores"] = json.loads(item["scores"])
            except Exception:
                item["scores"] = {}
        if isinstance(item.get("summary"), str):
            try:
                item["summary"] = json.loads(item["summary"])
            except Exception:
                item["summary"] = {}
        results.append(item)
    return results


def get_ai_test_result(test_id):
    """获取单次测试详情"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM ai_test_results WHERE id=?", (test_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    for field in ["conversation", "summary", "scores"]:
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except Exception:
                pass
    return result


def get_ai_feedback_rules(active_only=True, category=None):
    """获取 AI 进化规则列表"""
    conn = get_db()
    sql = "SELECT * FROM ai_feedback WHERE 1=1"
    params = []
    if active_only:
        sql += " AND is_active=1"
    if category:
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY severity DESC, category, id"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_ai_feedback_rule(data):
    """添加一条进化规则"""
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO ai_feedback (category, trigger_condition, action_rule, severity, source_scenario)
           VALUES (?,?,?,?,?)""",
        (data.get("category", "general"), data.get("trigger_condition", ""),
         data.get("action_rule", ""), data.get("severity", "suggestion"),
         data.get("source_scenario", ""))
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def update_ai_feedback_rule(rule_id, **kwargs):
    """更新一条进化规则"""
    allowed = ['category', 'trigger_condition', 'action_rule', 'severity', 'is_active']
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
    conn.execute(f"UPDATE ai_feedback SET {', '.join(sets)} WHERE id=?", (*vals, rule_id))
    conn.commit()
    conn.close()


def delete_ai_feedback_rule(rule_id):
    """删除一条进化规则"""
    conn = get_db()
    conn.execute("DELETE FROM ai_feedback WHERE id=?", (rule_id,))
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


def get_customer_detail(cid):
    """聚合客户详情：客户信息 + 消息 + 报价 + 订单 + 邮件 + AI生成 + 媒体文件"""
    conn = get_db()
    customer = conn.execute(
        "SELECT c.*, u.display_name as assigned_name FROM customers c LEFT JOIN users u ON c.assigned_to=u.id WHERE c.id=?",
        (cid,)
    ).fetchone()
    if not customer:
        conn.close()
        return None
    messages = conn.execute("SELECT * FROM messages WHERE customer_id=? ORDER BY created_at DESC LIMIT 10", (cid,)).fetchall()
    quotes = conn.execute("SELECT * FROM quotes WHERE customer_id=? ORDER BY created_at DESC", (cid,)).fetchall()
    orders = conn.execute("SELECT * FROM orders WHERE customer_id=? ORDER BY created_at DESC", (cid,)).fetchall()
    emails = conn.execute("SELECT * FROM email_log WHERE customer_id=? ORDER BY created_at DESC LIMIT 10", (cid,)).fetchall()
    generations = conn.execute("SELECT * FROM ai_generations WHERE customer_id=? ORDER BY created_at DESC LIMIT 10", (cid,)).fetchall()
    media = conn.execute("SELECT * FROM media_files WHERE customer_id=? ORDER BY created_at DESC LIMIT 10", (cid,)).fetchall()
    conn.close()
    return {
        "customer": dict(customer),
        "messages": [dict(r) for r in messages],
        "quotes": [dict(r) for r in quotes],
        "orders": [dict(r) for r in orders],
        "email_log": [dict(r) for r in emails],
        "ai_generations": [dict(r) for r in generations],
        "media_files": [dict(r) for r in media],
    }


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

def bulk_add_customers(rows):
    """批量导入客户，rows为dict列表，key为字段名。
    去重逻辑同 add_customer (whatsapp → name+company)。
    返回 (imported, skipped, errors)"""
    imported = 0
    skipped = 0
    errors = []
    allowed_fields = ['name','company','whatsapp','country','language','status','source',
                      'campaign','lead_status','lead_score','notes']
    conn = get_db()
    for i, row in enumerate(rows):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                skipped += 1
                continue
            whatsapp = (row.get("whatsapp") or "").strip()
            # 去重：WhatsApp
            if whatsapp:
                existing = conn.execute(
                    "SELECT id FROM customers WHERE whatsapp=? AND whatsapp!=''", (whatsapp,)
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
            # 去重：姓名+公司
            company = (row.get("company") or "").strip()
            existing = conn.execute(
                "SELECT id FROM customers WHERE name=? AND company=? AND name!=''",
                (name, company)
            ).fetchone()
            if existing:
                skipped += 1
                continue
            # 构建 INSERT
            cols = ['name','company','whatsapp','country','language','status','notes',
                    'source','campaign','lead_status','lead_score']
            vals = [name, company, whatsapp,
                    (row.get("country") or "").strip(),
                    (row.get("language") or "English").strip(),
                    (row.get("status") or "warm").strip(),
                    (row.get("notes") or "").strip(),
                    (row.get("source") or "").strip(),
                    (row.get("campaign") or "").strip(),
                    (row.get("lead_status") or "").strip(),
                    0]
            # lead_score 为整数
            try:
                vals[-1] = int(row.get("lead_score", 0))
            except (ValueError, TypeError):
                vals[-1] = 0
            placeholders = ",".join("?" for _ in cols)
            conn.execute(f"INSERT INTO customers ({','.join(cols)}) VALUES ({placeholders})", vals)
            imported += 1
        except Exception as e:
            errors.append(f"第{i+2}行错误: {e}")
    if imported:
        conn.commit()
    conn.close()
    return imported, skipped, errors

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
    conn.execute("UPDATE customers SET updated_at=CURRENT_TIMESTAMP, last_contacted_at=CURRENT_TIMESTAMP WHERE id=?", (customer_id,))
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
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return mid

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
def get_quotes(status=None, customer_id=None, created_by=None):
    conn = get_db()
    sql = """SELECT q.*, c.name as customer_name, c.company as customer_company,
             u.display_name as created_by_name
             FROM quotes q
             LEFT JOIN customers c ON q.customer_id=c.id
             LEFT JOIN users u ON q.created_by=u.id"""
    where = []
    params = []
    if status:
        where.append("q.status=?")
        params.append(status)
    if customer_id:
        where.append("q.customer_id=?")
        params.append(customer_id)
    if created_by:
        where.append("q.created_by=?")
        params.append(created_by)
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
        "INSERT INTO quotes (quote_no,customer_id,items,total_amount,currency,status,valid_until,notes,created_by) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            quote_no,
            data.get("customer_id"),
            json.dumps(data.get("items", [])),
            data.get("total_amount", 0),
            data.get("currency", "USD"),
            data.get("status", "draft"),
            data.get("valid_until", ""),
            data.get("notes", ""),
            data.get("created_by"),
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


def get_revenue_trend(months=12):
    """按月统计营收趋势，返回 [{month, revenue, cost}]"""
    conn = get_db()
    rows = conn.execute(
        """SELECT strftime('%Y-%m', created_at) as month,
                  SUM(total_amount) as revenue,
                  COALESCE(SUM(partner_cost), 0) as cost
           FROM orders
           WHERE status IN ('shipped', 'delivered')
             AND created_at >= date('now', ?)
           GROUP BY month ORDER BY month""",
        (f"-{months} months",)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "month": r["month"],
            "revenue": round(float(r["revenue"] or 0), 2),
            "cost": round(float(r["cost"] or 0), 2),
        })
    return result


def get_chart_data():
    """聚合图表数据"""
    conn = get_db()
    # 订单状态分布
    order_statuses = conn.execute(
        "SELECT status, COUNT(*) as count FROM orders GROUP BY status ORDER BY count DESC"
    ).fetchall()
    # 潜客来源分布
    lead_sources = conn.execute(
        "SELECT source, COUNT(*) as count FROM customers WHERE source!='' AND source IS NOT NULL GROUP BY source ORDER BY count DESC"
    ).fetchall()
    # Top 10 客户
    top_customers = conn.execute(
        """SELECT c.name, COALESCE(SUM(o.total_amount), 0) as total
           FROM orders o JOIN customers c ON o.customer_id = c.id
           WHERE o.status IN ('shipped', 'delivered')
           GROUP BY c.id ORDER BY total DESC LIMIT 10"""
    ).fetchall()
    # 近12月订单数
    monthly_orders = conn.execute(
        """SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
           FROM orders
           WHERE created_at >= date('now', '-12 months')
           GROUP BY month ORDER BY month"""
    ).fetchall()
    conn.close()
    return {
        "order_status_counts": [dict(r) for r in order_statuses],
        "lead_source_distribution": [dict(r) for r in lead_sources],
        "top_customers": [dict(r) for r in top_customers],
        "monthly_orders": [dict(r) for r in monthly_orders],
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


# ========= 通知 CRUD =========
def add_notification(user_id, type, title, message='', link='', related_type='', related_id=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO notifications (user_id, type, title, message, link, related_type, related_id) VALUES (?,?,?,?,?,?,?)",
        (user_id, type, title, message, link, related_type, related_id)
    )
    conn.commit()
    conn.close()


def get_notifications(user_id, limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unread_count(user_id):
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,)
    ).fetchone()[0]
    conn.close()
    return count


def mark_notification_read(nid, user_id):
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, user_id))
    conn.commit()
    conn.close()


def mark_all_notifications_read(user_id):
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0", (user_id,))
    conn.commit()
    conn.close()


def get_user_by_id(uid):
    conn = get_db()
    u = conn.execute("SELECT id, username, display_name, role FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(u) if u else None


def get_active_user_ids():
    conn = get_db()
    rows = conn.execute("SELECT id FROM users WHERE active=1").fetchall()
    conn.close()
    return [r["id"] for r in rows]


# ========= 操作日志 =========
def add_activity_log(performed_by, action, entity_type, entity_id, summary, details=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO activity_log (performed_by,action,entity_type,entity_id,summary,details) VALUES (?,?,?,?,?,?)",
        (performed_by, action, entity_type, entity_id, summary, details)
    )
    conn.commit()
    conn.close()


def get_activity_logs(limit=100, offset=0):
    conn = get_db()
    rows = conn.execute(
        """SELECT a.*, u.display_name as user_name
           FROM activity_log a LEFT JOIN users u ON a.performed_by=u.id
           ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_activity_logs_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    conn.close()
    return count


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


# ==================== 应收账款 (AR) ====================

def add_payment(order_id, ptype, amount, currency="USD", payment_date="", method="", notes="", recorded_by=None):
    """记录一笔付款流水"""
    conn = get_db()
    conn.execute(
        "INSERT INTO payments (order_id,type,amount,currency,payment_date,method,notes,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
        (order_id, ptype, amount, currency, payment_date, method, notes, recorded_by)
    )
    conn.commit()
    conn.close()


def migrate_payments_from_orders():
    """回填：将订单已有的 deposit/balance 写入 payments 表"""
    conn = get_db()
    orders = conn.execute(
        "SELECT id, currency, deposit_amount, deposit_date, deposit_method, deposit_received, "
        "balance_amount, balance_date, balance_method, balance_received FROM orders"
    ).fetchall()
    count = 0
    for o in orders:
        if o["deposit_received"] and o["deposit_amount"] > 0:
            existing = conn.execute("SELECT id FROM payments WHERE order_id=? AND type='deposit'", (o["id"],)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO payments (order_id,type,amount,currency,payment_date,method) VALUES (?,?,?,?,?,?)",
                    (o["id"], "deposit", o["deposit_amount"], o["currency"] or "USD", o["deposit_date"], o["deposit_method"])
                )
                count += 1
        if o["balance_received"] and o["balance_amount"] > 0:
            existing = conn.execute("SELECT id FROM payments WHERE order_id=? AND type='balance'", (o["id"],)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO payments (order_id,type,amount,currency,payment_date,method) VALUES (?,?,?,?,?,?)",
                    (o["id"], "balance", o["balance_amount"], o["currency"] or "USD", o["balance_date"], o["balance_method"])
                )
                count += 1
    conn.commit()
    conn.close()
    return count


def get_ar_summary():
    """AR 总览：总应收、本月已收、逾期金额、待收订单数"""
    conn = get_db()
    total_receivable = conn.execute(
        "SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status NOT IN ('cancelled','archived')"
    ).fetchone()[0]
    total_received = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payments"
    ).fetchone()[0]
    received_this_month = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payments "
        "WHERE strftime('%Y-%m', payment_date)=strftime('%Y-%m', 'now')"
    ).fetchone()[0]
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE "
        "(deposit_received=0 OR balance_received=0) "
        "AND status NOT IN ('cancelled','archived','pending_approval')"
    ).fetchone()[0]
    overdue_amount = conn.execute(
        "SELECT COALESCE(SUM(total_amount),0) FROM orders "
        "WHERE status IN ('confirmed','in_production','shipped','delivered') "
        "AND julianday('now') - julianday(created_at) > 30"
    ).fetchone()[0]
    conn.close()
    return {
        "total_receivable": round(total_receivable, 2),
        "total_received": round(total_received, 2),
        "received_this_month": round(received_this_month, 2),
        "pending_count": pending_count,
        "overdue_amount": round(overdue_amount, 2),
    }


def get_ar_by_customer():
    """按客户汇总应收"""
    conn = get_db()
    rows = conn.execute(
        "SELECT c.id as customer_id, c.name as customer_name, c.company, "
        "COUNT(o.id) as order_count, "
        "COALESCE(SUM(o.total_amount),0) as total_amount, "
        "COALESCE(SUM(p.paid),0) as total_paid, "
        "COALESCE(SUM(o.total_amount),0) - COALESCE(SUM(p.paid),0) as balance_due, "
        "MAX(p.last_date) as last_payment_date "
        "FROM customers c "
        "JOIN orders o ON o.customer_id=c.id "
        "LEFT JOIN (SELECT order_id, SUM(amount) as paid, MAX(payment_date) as last_date "
        "FROM payments GROUP BY order_id) p ON p.order_id=o.id "
        "WHERE o.status NOT IN ('cancelled','archived') "
        "GROUP BY c.id HAVING balance_due > 0 "
        "ORDER BY balance_due DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_payment_history(limit=50):
    """最近付款流水"""
    conn = get_db()
    rows = conn.execute(
        "SELECT p.*, o.order_no, "
        "c.name as customer_name, c.company as customer_company, "
        "u.display_name as recorded_name "
        "FROM payments p "
        "JOIN orders o ON p.order_id=o.id "
        "LEFT JOIN customers c ON o.customer_id=c.id "
        "LEFT JOIN users u ON p.recorded_by=u.id "
        "ORDER BY p.created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_aging_analysis():
    """账龄分析四段"""
    conn = get_db()
    buckets = [
        ("0-30天", 0, 30),
        ("31-60天", 31, 60),
        ("61-90天", 61, 90),
        ("90天以上", 91, 9999),
    ]
    result = []
    for label, lo, hi in buckets:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_amount),0) as amount, "
            "COUNT(*) as order_count "
            "FROM orders "
            "WHERE status NOT IN ('cancelled','archived','pending_approval') "
            "AND julianday('now') - julianday(created_at) BETWEEN ? AND ?",
            (lo, hi)
        ).fetchone()
        result.append({
            "label": label,
            "amount": round(row["amount"], 2),
            "order_count": row["order_count"],
        })
    conn.close()
    return result

# ==================== 获客模块 (Leads) ====================

def get_leads(source=None, status=None, assigned_to=None, country=None, limit=100):
    """查询潜客列表"""
    conn = get_db()
    sql = "SELECT c.*, u.display_name as assigned_name FROM customers c LEFT JOIN users u ON c.assigned_to=u.id WHERE 1=1"
    params = []
    if source:
        sql += " AND c.source=?"
        params.append(source)
    if status:
        sql += " AND c.lead_status=?"
        params.append(status)
    if assigned_to is not None:
        if assigned_to == -1:
            sql += " AND (c.assigned_to = '' OR c.assigned_to IS NULL)"
        else:
            sql += " AND c.assigned_to=?"
            params.append(str(assigned_to))
    if country:
        sql += " AND c.country=?"
        params.append(country)
    sql += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_lead_summary():
    """获客统计：按来源/状态/国家的汇总"""
    conn = get_db()
    by_source = conn.execute(
        "SELECT source, COUNT(*) as count FROM customers WHERE source!='' GROUP BY source ORDER BY count DESC"
    ).fetchall()
    by_status = conn.execute(
        "SELECT lead_status, COUNT(*) as count FROM customers GROUP BY lead_status ORDER BY count DESC"
    ).fetchall()
    by_country = conn.execute(
        "SELECT country, COUNT(*) as count FROM customers WHERE country!='' GROUP BY country ORDER BY count DESC"
    ).fetchall()
    month_new = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE strftime('%Y-%m', created_at)=strftime('%Y-%m', 'now')"
    ).fetchone()[0]
    unassigned = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE (assigned_to IS NULL OR assigned_to = '') AND lead_status NOT IN ('customer','lost')"
    ).fetchone()[0]
    conn.close()
    return {
        "by_source": [dict(r) for r in by_source],
        "by_status": [dict(r) for r in by_status],
        "by_country": [dict(r) for r in by_country],
        "month_new": month_new,
        "unassigned": unassigned,
    }

def get_lead_funnel():
    """潜客漏斗数据"""
    conn = get_db()
    stages = ["new", "contacted", "qualified", "customer"]
    result = []
    for s in stages:
        count = conn.execute("SELECT COUNT(*) FROM customers WHERE lead_status=?", (s,)).fetchone()[0]
        result.append({"stage": s, "count": count})
    conn.close()
    return result

def assign_lead(customer_id, user_id):
    """分配潜客给销售"""
    conn = get_db()
    conn.execute("UPDATE customers SET assigned_to=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (user_id, customer_id))
    conn.commit()
    conn.close()

def update_lead_status(customer_id, status):
    """更新潜客状态"""
    conn = get_db()
    conn.execute("UPDATE customers SET lead_status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, customer_id))
    conn.commit()
    conn.close()

def update_lead_source(customer_id, source, campaign=""):
    """更新潜客来源"""
    conn = get_db()
    if campaign:
        conn.execute("UPDATE customers SET source=?, campaign=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (source, campaign, customer_id))
    else:
        conn.execute("UPDATE customers SET source=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (source, customer_id))
    conn.commit()
    conn.close()


# ==================== 跟进提醒 (Follow-up Reminder) ====================

def update_last_contacted(customer_id):
    """更新客户最后联系时间为当前时间"""
    conn = get_db()
    conn.execute("UPDATE customers SET last_contacted_at=CURRENT_TIMESTAMP WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()

def get_leads_due_followup():
    """获取需要跟进的潜客列表，按逾期天数分组"""
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.company, c.country, c.language, c.lead_status,
               c.assigned_to, c.whatsapp, c.last_contacted_at,
               u.display_name as assigned_name,
               CAST(julianday('now') - julianday(c.last_contacted_at) AS INTEGER) as days_since,
               CASE
                   WHEN CAST(julianday('now') - julianday(c.last_contacted_at) AS INTEGER) >= 15 THEN '15day'
                   WHEN CAST(julianday('now') - julianday(c.last_contacted_at) AS INTEGER) >= 7 THEN '7day'
                   WHEN CAST(julianday('now') - julianday(c.last_contacted_at) AS INTEGER) >= 3 THEN '3day'
               END as followup_type
        FROM customers c
        LEFT JOIN users u ON c.assigned_to = u.id
        WHERE c.lead_status NOT IN ('lost', 'customer')
          AND c.last_contacted_at IS NOT NULL
          AND CAST(julianday('now') - julianday(c.last_contacted_at) AS INTEGER) >= 3
        ORDER BY days_since DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_today_followup_summary():
    """获取今日跟进汇总：总数 + 各类型数量"""
    conn = get_db()
    sql_base = """
        FROM customers
        WHERE lead_status NOT IN ('lost', 'customer')
          AND last_contacted_at IS NOT NULL
          AND CAST(julianday('now') - julianday(last_contacted_at) AS INTEGER)
    """
    total = conn.execute("SELECT COUNT(*)" + sql_base + " >= 3").fetchone()[0]
    day3 = conn.execute("SELECT COUNT(*)" + sql_base + " BETWEEN 3 AND 6").fetchone()[0]
    day7 = conn.execute("SELECT COUNT(*)" + sql_base + " BETWEEN 7 AND 14").fetchone()[0]
    day15 = conn.execute("SELECT COUNT(*)" + sql_base + " >= 15").fetchone()[0]
    conn.close()
    return {"total": total, "day3": day3, "day7": day7, "day15": day15}


# ==================== 公海自动流转 (Lead Pool Auto-Rotation) ====================

def get_users():
    """获取所有销售用户"""
    conn = get_db()
    rows = conn.execute("SELECT id, username, display_name, role, title FROM users WHERE active=1 ORDER BY display_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def unassign_lead(customer_id):
    """将潜客退回公海（清除分配人）"""
    conn = get_db()
    conn.execute("UPDATE customers SET assigned_to = '' WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()


def claim_lead(customer_id, user_id):
    """销售认领潜客（只有未分配的可认领），认领时重置 last_contacted_at"""
    conn = get_db()
    conn.execute(
        "UPDATE customers SET assigned_to = ?, last_contacted_at = CURRENT_TIMESTAMP WHERE id = ? AND (assigned_to = '' OR assigned_to IS NULL)",
        (str(user_id), customer_id)
    )
    conn.commit()
    changed = conn.total_changes > 0
    conn.close()
    return changed


def reclaim_expired_leads(days=14):
    """回收超过指定天数未联系的已分配潜客，退回公海"""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, name, assigned_to FROM customers
           WHERE assigned_to != '' AND assigned_to IS NOT NULL
             AND lead_status NOT IN ('lost', 'customer')
             AND CAST(julianday('now') - julianday(COALESCE(last_contacted_at, updated_at)) AS INTEGER) >= ?""",
        (days,)
    ).fetchall()
    reclaimed = []
    for r in rows:
        conn.execute("UPDATE customers SET assigned_to = '' WHERE id = ?", (r["id"],))
        reclaimed.append(dict(r))
    conn.commit()
    conn.close()
    return reclaimed


def get_leads_with_pool_info(source=None, status=None, assigned_to=None, country=None, limit=100):
    """增强版潜客列表：额外返回公海天数、剩余天数、状态"""
    conn = get_db()
    sql = """SELECT c.*, u.display_name as assigned_name,
               CAST(julianday('now') - julianday(COALESCE(c.last_contacted_at, c.updated_at)) AS INTEGER) as pool_days,
               14 - CAST(julianday('now') - julianday(COALESCE(c.last_contacted_at, c.updated_at)) AS INTEGER) as pool_remaining
        FROM customers c LEFT JOIN users u ON c.assigned_to = u.id WHERE 1=1"""
    params = []
    if source:
        sql += " AND c.source=?"
        params.append(source)
    if status:
        sql += " AND c.lead_status=?"
        params.append(status)
    if assigned_to is not None:
        if assigned_to == -1:
            sql += " AND (c.assigned_to = '' OR c.assigned_to IS NULL)"
        else:
            sql += " AND c.assigned_to=?"
            params.append(str(assigned_to))
    if country:
        sql += " AND c.country=?"
        params.append(country)
    sql += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        pd = d.get("pool_days", 0) or 0
        if d.get("assigned_to") and d["assigned_to"] != "":
            if pd >= 14:
                d["pool_status"] = "expired"
            elif pd >= 8:
                d["pool_status"] = "warning"
            else:
                d["pool_status"] = "safe"
        else:
            d["pool_status"] = "unassigned"
        result.append(d)
    return result


# ==================== 媒体标签 ====================

def get_media_tags():
    """所有标签"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM media_tags ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_media_tag(name, tag_type="general", color="#00f2ff"):
    """创建标签"""
    conn = get_db()
    try:
        conn.execute("INSERT INTO media_tags (name,type,color) VALUES (?,?,?)", (name, tag_type, color))
        conn.commit()
        tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"id": tid, "name": name}
    except Exception as e:
        conn.close()
        return {"error": str(e)}

def delete_media_tag(tag_id):
    """删除标签"""
    conn = get_db()
    conn.execute("DELETE FROM media_tag_relations WHERE tag_id=?", (tag_id,))
    conn.execute("DELETE FROM media_tags WHERE id=?", (tag_id,))
    conn.commit()
    conn.close()

def get_media_tags_for(media_id):
    """获取媒体文件的标签"""
    conn = get_db()
    rows = conn.execute(
        "SELECT t.* FROM media_tags t JOIN media_tag_relations r ON t.id=r.tag_id WHERE r.media_id=?",
        (media_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_media_tags(media_id, tag_ids):
    """更新媒体文件的标签"""
    conn = get_db()
    conn.execute("DELETE FROM media_tag_relations WHERE media_id=?", (media_id,))
    for tid in tag_ids:
        conn.execute("INSERT OR IGNORE INTO media_tag_relations (media_id,tag_id) VALUES (?,?)", (media_id, tid))
    conn.commit()
    conn.close()

def get_media_by_tag(tag_id=None, filetype=None, limit=100):
    """按标签+类型筛选媒体"""
    conn = get_db()
    sql = "SELECT DISTINCT f.* FROM media_files f"
    params = []
    if tag_id:
        sql += " JOIN media_tag_relations r ON f.id=r.media_id WHERE r.tag_id=?"
        params.append(tag_id)
    else:
        sql += " WHERE 1=1"
    if filetype and filetype != "all":
        sql += " AND f.filetype=?"
        params.append(filetype)
    sql += " ORDER BY f.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
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


# ========= 生产任务追踪 =========
def get_production_task_defaults():
    """返回默认生产步骤模板"""
    return [
        {"task_name": "设计确认", "sort_order": 0},
        {"task_name": "材料准备", "sort_order": 1},
        {"task_name": "雕刻制作", "sort_order": 2},
        {"task_name": "组装焊接", "sort_order": 3},
        {"task_name": "接线测试", "sort_order": 4},
        {"task_name": "质检包装", "sort_order": 5},
        {"task_name": "发货准备", "sort_order": 6},
    ]


def get_production_tasks(order_id):
    """获取某订单的生产任务列表，JOIN users 取 done_by 人名"""
    conn = get_db()
    rows = conn.execute("""
        SELECT pt.*, u.display_name AS done_by_name
        FROM production_tasks pt
        LEFT JOIN users u ON pt.done_by = u.id
        WHERE pt.order_id = ?
        ORDER BY pt.sort_order ASC, pt.id ASC
    """, (order_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_production_tasks(order_id, tasks):
    """批量保存任务列表（先删后插）"""
    conn = get_db()
    conn.execute("DELETE FROM production_tasks WHERE order_id=?", (order_id,))
    for t in tasks:
        conn.execute(
            "INSERT INTO production_tasks (order_id, task_name, sort_order) VALUES (?,?,?)",
            (order_id, t.get("task_name", ""), t.get("sort_order", 0))
        )
    conn.commit()
    conn.close()
    return True


def update_production_task_status(task_id, is_done, done_by=None):
    """勾选/取消勾选单个任务，自动记录 done_at"""
    conn = get_db()
    if is_done:
        conn.execute(
            "UPDATE production_tasks SET is_done=1, done_at=CURRENT_TIMESTAMP, done_by=? WHERE id=?",
            (done_by, task_id)
        )
    else:
        conn.execute(
            "UPDATE production_tasks SET is_done=0, done_at=NULL, done_by=NULL WHERE id=?",
            (task_id,)
        )
    conn.commit()
    conn.close()
    return True


# ========= 发货 CRUD =========
def get_shipments(order_id):
    """获取订单的所有发货记录"""
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*, u.display_name AS created_name
        FROM shipments s
        LEFT JOIN users u ON s.created_by = u.id
        WHERE s.order_id = ?
        ORDER BY s.created_at DESC
    """, (order_id,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["package_info"] = json.loads(d.get("package_info", "{}"))
        except:
            d["package_info"] = {}
        result.append(d)
    return result


def get_shipment(sid):
    """获取单条发货记录"""
    conn = get_db()
    row = conn.execute("""
        SELECT s.*, u.display_name AS created_name
        FROM shipments s
        LEFT JOIN users u ON s.created_by = u.id
        WHERE s.id = ?
    """, (sid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["package_info"] = json.loads(d.get("package_info", "{}"))
    except:
        d["package_info"] = {}
    return d


def add_shipment(data):
    """创建发货记录"""
    conn = get_db()
    conn.execute(
        """INSERT INTO shipments (order_id, ship_date, tracking_no, carrier,
           shipping_cost, currency, package_info, status, notes, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("order_id"),
            data.get("ship_date", ""),
            data.get("tracking_no", ""),
            data.get("carrier", ""),
            data.get("shipping_cost", 0),
            data.get("currency", "USD"),
            json.dumps(data.get("package_info", {})),
            data.get("status", "pending"),
            data.get("notes", ""),
            data.get("created_by"),
        )
    )
    conn.commit()
    sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": sid}


def update_shipment(sid, data):
    """更新发货记录"""
    allowed = ["ship_date", "tracking_no", "carrier", "shipping_cost",
               "currency", "status", "notes"]
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if "package_info" in data:
        sets.append("package_info=?")
        vals.append(json.dumps(data["package_info"]))
    if sets:
        sets.append("updated_at=CURRENT_TIMESTAMP")
        conn = get_db()
        conn.execute(f"UPDATE shipments SET {', '.join(sets)} WHERE id=?", (*vals, sid))
        conn.commit()
        conn.close()


def delete_shipment(sid):
    """删除发货记录"""
    conn = get_db()
    conn.execute("DELETE FROM shipments WHERE id=?", (sid,))
    conn.commit()
    conn.close()


# ========= 质检管理 (QC) =========
def get_qc_templates():
    """获取所有质检模板"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM qc_templates ORDER BY name").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["items"] = json.loads(d.get("items", "[]"))
        except:
            d["items"] = []
        result.append(d)
    return result


def get_qc_template(tid):
    """获取单个质检模板"""
    conn = get_db()
    row = conn.execute("SELECT * FROM qc_templates WHERE id=?", (tid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["items"] = json.loads(d.get("items", "[]"))
    except:
        d["items"] = []
    return d


def save_qc_template(tid, name, items):
    """创建或更新质检模板"""
    items_json = json.dumps(items)
    conn = get_db()
    if tid:
        conn.execute("UPDATE qc_templates SET name=?, items=? WHERE id=?", (name, items_json, tid))
    else:
        conn.execute("INSERT INTO qc_templates (name, items) VALUES (?,?)", (name, items_json))
    conn.commit()
    conn.close()
    return True


def delete_qc_template(tid):
    """删除质检模板"""
    conn = get_db()
    conn.execute("DELETE FROM qc_templates WHERE id=?", (tid,))
    conn.commit()
    conn.close()


def get_order_qc_inspections(order_id):
    """获取订单的所有质检记录"""
    conn = get_db()
    rows = conn.execute("""
        SELECT qi.*, u.display_name AS inspector_name, qt.name AS template_name
        FROM qc_inspections qi
        LEFT JOIN users u ON qi.inspector_id = u.id
        LEFT JOIN qc_templates qt ON qi.template_id = qt.id
        WHERE qi.order_id = ?
        ORDER BY qi.created_at DESC
    """, (order_id,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["items"] = json.loads(d.get("items", "[]"))
        except:
            d["items"] = []
        result.append(d)
    return result


def get_qc_inspection(iid):
    """获取单条质检记录"""
    conn = get_db()
    row = conn.execute("""
        SELECT qi.*, u.display_name AS inspector_name, qt.name AS template_name
        FROM qc_inspections qi
        LEFT JOIN users u ON qi.inspector_id = u.id
        LEFT JOIN qc_templates qt ON qi.template_id = qt.id
        WHERE qi.id = ?
    """, (iid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["items"] = json.loads(d.get("items", "[]"))
    except:
        d["items"] = []
    return d


def add_qc_inspection(data):
    """创建质检记录"""
    conn = get_db()
    conn.execute(
        """INSERT INTO qc_inspections (order_id, template_id, inspector_id, result, items, notes, inspected_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            data.get("order_id"),
            data.get("template_id"),
            data.get("inspector_id"),
            data.get("result", "pending"),
            json.dumps(data.get("items", [])),
            data.get("notes", ""),
            data.get("inspected_at"),
        )
    )
    conn.commit()
    iid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": iid}


def update_qc_inspection(iid, data):
    """更新质检记录"""
    allowed = ["result", "notes"]
    sets = []
    vals = []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if "items" in data:
        sets.append("items=?")
        vals.append(json.dumps(data["items"]))
    if "inspected_at" in data:
        sets.append("inspected_at=?")
        vals.append(data["inspected_at"])
    if sets:
        conn = get_db()
        conn.execute(f"UPDATE qc_inspections SET {', '.join(sets)} WHERE id=?", (*vals, iid))
        conn.commit()
        conn.close()


def delete_qc_inspection(iid):
    """删除质检记录"""
    conn = get_db()
    conn.execute("DELETE FROM qc_inspections WHERE id=?", (iid,))
    conn.commit()
    conn.close()


# ========= 报表统计 =========
def get_monthly_sales_detail(months=12):
    """每月销售额/成本/利润/订单数 (已发货+已交付)"""
    conn = get_db()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', created_at) AS month,
               COUNT(*) AS order_count,
               COALESCE(SUM(total_amount),0) AS revenue,
               COALESCE(SUM(partner_cost),0) AS cost
        FROM orders
        WHERE status IN ('shipped','delivered')
          AND created_at >= date('now', ?)
        GROUP BY month ORDER BY month ASC
    """, (f"-{months} months",)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["profit"] = round(d["revenue"] - d["cost"], 2)
        result.append(d)
    return result


def get_customer_acquisition_stats(months=12):
    """每月新增客户数"""
    conn = get_db()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', created_at) AS month,
               COUNT(*) AS new_customers
        FROM customers
        WHERE created_at >= date('now', ?)
        GROUP BY month ORDER BY month ASC
    """, (f"-{months} months",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_production_stats():
    """生产完成率统计"""
    conn = get_db()
    result = {}
    # Total tasks per order
    rows = conn.execute("""
        SELECT order_id, COUNT(*) AS total,
               SUM(CASE WHEN is_done=1 THEN 1 ELSE 0 END) AS done
        FROM production_tasks
        GROUP BY order_id
    """).fetchall()
    total_tasks = sum(r["total"] for r in rows) if rows else 0
    done_tasks = sum(r["done"] for r in rows) if rows else 0
    result["total_tasks"] = total_tasks
    result["done_tasks"] = done_tasks
    result["completion_rate"] = round(done_tasks / total_tasks * 100, 1) if total_tasks else 0
    result["order_task_count"] = len(rows)

    # QC pass/fail stats
    qc_rows = conn.execute("""
        SELECT result, COUNT(*) AS cnt
        FROM qc_inspections
        GROUP BY result
    """).fetchall()
    qc_stats = {}
    for r in qc_rows:
        qc_stats[r["result"]] = r["cnt"]
    result["qc_stats"] = qc_stats

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


# ==================== V5 — Global Revenue OS CRUD ====================

# === Regions ===
def get_regions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM regions ORDER BY sort_order, name").fetchall()
    # Attach country count
    result = []
    for r in rows:
        d = dict(r)
        d["country_count"] = conn.execute(
            "SELECT COUNT(*) FROM region_countries WHERE region_id=?", (d["id"],)
        ).fetchone()[0]
        result.append(d)
    conn.close()
    return result


def get_region(rid):
    conn = get_db()
    row = conn.execute("SELECT * FROM regions WHERE id=?", (rid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_region(data):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO regions (code, name, description, base_currency, default_markup, sort_order) VALUES (?,?,?,?,?,?)",
        (data.get("code",""), data.get("name",""), data.get("description",""),
         data.get("base_currency","USD"), data.get("default_markup",1.3), data.get("sort_order",0))
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def update_region(rid, data):
    conn = get_db()
    for k, v in data.items():
        if k in ("code","name","description","base_currency","default_markup","status","sort_order"):
            conn.execute(f"UPDATE regions SET {k}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (v, rid))
    conn.commit()
    conn.close()


def delete_region(rid):
    conn = get_db()
    conn.execute("DELETE FROM region_countries WHERE region_id=?", (rid,))
    conn.execute("DELETE FROM regions WHERE id=?", (rid,))
    conn.commit()
    conn.close()


def get_region_countries(region_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM region_countries WHERE region_id=?", (region_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_region_country(region_id, country_code, country_name=""):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO region_countries (region_id, country_code, country_name) VALUES (?,?,?)",
            (region_id, country_code, country_name)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def remove_region_country(rid):
    conn = get_db()
    conn.execute("DELETE FROM region_countries WHERE id=?", (rid,))
    conn.commit()
    conn.close()


def get_region_for_country(country_code):
    conn = get_db()
    row = conn.execute(
        """SELECT r.* FROM regions r
           JOIN region_countries rc ON r.id = rc.region_id
           WHERE rc.country_code = ?""",
        (country_code.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_default_regions():
    """Seed predefined regions if table is empty."""
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
    if existing > 0:
        conn.close()
        return 0
    definitions = {
        "NA": {"name":"North America", "countries":{"US":"United States","CA":"Canada"}, "base_currency":"USD", "markup":1.4, "sort":1},
        "EU": {"name":"Europe", "countries":{"GB":"United Kingdom","DE":"Germany","FR":"France","IT":"Italy","ES":"Spain","NL":"Netherlands"}, "base_currency":"EUR", "markup":1.35, "sort":2},
        "APAC": {"name":"Asia Pacific", "countries":{"JP":"Japan","AU":"Australia","SG":"Singapore","NZ":"New Zealand"}, "base_currency":"USD", "markup":1.25, "sort":3},
        "LATAM": {"name":"Latin America", "countries":{"BR":"Brazil","MX":"Mexico","AR":"Argentina","CL":"Chile","CO":"Colombia"}, "base_currency":"USD", "markup":1.3, "sort":4},
        "MEA": {"name":"Middle East & Africa", "countries":{"AE":"UAE","SA":"Saudi Arabia","ZA":"South Africa","EG":"Egypt"}, "base_currency":"USD", "markup":1.35, "sort":5},
    }
    count = 0
    for code, defn in definitions.items():
        cur = conn.execute(
            "INSERT INTO regions (code, name, base_currency, default_markup, sort_order) VALUES (?,?,?,?,?)",
            (code, defn["name"], defn["base_currency"], defn["markup"], defn["sort"])
        )
        rid = cur.lastrowid
        count += 1
        for cc, cname in defn["countries"].items():
            try:
                conn.execute("INSERT INTO region_countries (region_id, country_code, country_name) VALUES (?,?,?)",
                             (rid, cc, cname))
            except:
                pass
    conn.commit()
    conn.close()
    return count


# === Exchange Rates ===
def get_exchange_rates(from_currency=None, date=None):
    conn = get_db()
    sql = "SELECT * FROM exchange_rates WHERE 1=1"
    params = []
    if from_currency:
        sql += " AND from_currency=?"
        params.append(from_currency.upper())
    if date:
        sql += " AND date=?"
        params.append(date)
    sql += " ORDER BY date DESC, from_currency"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_exchange_rate(from_currency, to_currency, rate, date=None, source="manual"):
    from datetime import date as dt_date
    if date is None:
        date = dt_date.today().isoformat()
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO exchange_rates (from_currency, to_currency, rate, date, source)
               VALUES (?,?,?,?,?)
               ON CONFLICT(from_currency, to_currency, date) DO UPDATE SET rate=?, source=?""",
            (from_currency.upper(), to_currency.upper(), rate, date, source, rate, source)
        )
        conn.commit()
    except Exception:
        # SQLite without ON CONFLICT support
        existing = conn.execute(
            "SELECT id FROM exchange_rates WHERE from_currency=? AND to_currency=? AND date=?",
            (from_currency.upper(), to_currency.upper(), date)
        ).fetchone()
        if existing:
            conn.execute("UPDATE exchange_rates SET rate=?, source=? WHERE id=?",
                         (rate, source, existing["id"]))
        else:
            conn.execute(
                "INSERT INTO exchange_rates (from_currency, to_currency, rate, date, source) VALUES (?,?,?,?,?)",
                (from_currency.upper(), to_currency.upper(), rate, date, source)
            )
        conn.commit()
    conn.close()


def get_exchange_rate(from_currency, to_currency="USD", date=None):
    from datetime import date as dt_date
    if date is None:
        date = dt_date.today().isoformat()
    conn = get_db()
    row = conn.execute(
        "SELECT rate FROM exchange_rates WHERE from_currency=? AND to_currency=? AND date=?",
        (from_currency.upper(), to_currency.upper(), date)
    ).fetchone()
    conn.close()
    return row["rate"] if row else None


# === Factories ===
def get_factories(region_code=None):
    conn = get_db()
    if region_code:
        rows = conn.execute(
            "SELECT * FROM factories WHERE shipping_zones LIKE ? ORDER BY name",
            (f'%{region_code}%',)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM factories ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_factory(fid):
    conn = get_db()
    row = conn.execute("SELECT * FROM factories WHERE id=?", (fid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_factory(data):
    conn = get_db()
    import json
    cur = conn.execute(
        """INSERT INTO factories (name, location, country, base_currency, capability_tags,
           max_capacity_monthly, current_load, status, shipping_zones, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (data.get("name",""), data.get("location",""), data.get("country","China"),
         data.get("base_currency","CNY"),
         json.dumps(data.get("capability_tags",[])),
         data.get("max_capacity_monthly",0), data.get("current_load",0),
         data.get("status","active"),
         json.dumps(data.get("shipping_zones",[])),
         data.get("notes",""))
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def update_factory(fid, data):
    conn = get_db()
    import json
    for k, v in data.items():
        if k in ("name","location","country","base_currency","status","notes"):
            conn.execute(f"UPDATE factories SET {k}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (v, fid))
        elif k in ("max_capacity_monthly","current_load"):
            conn.execute(f"UPDATE factories SET {k}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(v), fid))
        elif k in ("capability_tags","shipping_zones"):
            conn.execute(f"UPDATE factories SET {k}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(v), fid))
    conn.commit()
    conn.close()


def delete_factory(fid):
    conn = get_db()
    conn.execute("DELETE FROM production_costs WHERE factory_id=?", (fid,))
    conn.execute("DELETE FROM factories WHERE id=?", (fid,))
    conn.commit()
    conn.close()


# === Production Costs ===
def get_production_costs(factory_id=None):
    conn = get_db()
    if factory_id:
        rows = conn.execute(
            "SELECT pc.*, f.name as factory_name FROM production_costs pc LEFT JOIN factories f ON pc.factory_id=f.id WHERE pc.factory_id=? ORDER BY pc.product_category",
            (factory_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT pc.*, f.name as factory_name FROM production_costs pc LEFT JOIN factories f ON pc.factory_id=f.id ORDER BY pc.factory_id, pc.product_category"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_production_cost(data):
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO production_costs (factory_id, product_category, base_cost, currency,
           material_cost, labor_cost, overhead_cost, effective_from, effective_to)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (data.get("factory_id"), data.get("product_category",""), data.get("base_cost",0),
         data.get("currency","CNY"), data.get("material_cost",0), data.get("labor_cost",0),
         data.get("overhead_cost",0), data.get("effective_from",""), data.get("effective_to"))
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


# === Agent Profiles ===
def get_agent_profiles(region_id=None):
    conn = get_db()
    if region_id:
        rows = conn.execute(
            "SELECT ap.*, r.name as region_name FROM agent_profiles ap LEFT JOIN regions r ON ap.region_id=r.id WHERE ap.region_id=? ORDER BY ap.sort_order",
            (region_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ap.*, r.name as region_name FROM agent_profiles ap LEFT JOIN regions r ON ap.region_id=r.id ORDER BY ap.sort_order"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_agent_profile(agent_id):
    conn = get_db()
    row = conn.execute(
        "SELECT ap.*, r.name as region_name FROM agent_profiles ap LEFT JOIN regions r ON ap.region_id=r.id WHERE ap.agent_id=?",
        (agent_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_agent_profile(data):
    import json
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO agent_profiles (agent_id, region_id, name, role, languages, pricing_multiplier, culture_context, sort_order)
           VALUES (?,?,?,?,?,?,?,?)""",
        (data.get("agent_id",""), data.get("region_id"), data.get("name",""),
         data.get("role","sales"), json.dumps(data.get("languages",[])),
         data.get("pricing_multiplier",1.0), data.get("culture_context",""), data.get("sort_order",0))
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def update_agent_profile(aid, data):
    import json
    conn = get_db()
    for k, v in data.items():
        if k in ("name","role","culture_context","agent_id"):
            conn.execute(f"UPDATE agent_profiles SET {k}=? WHERE id=?", (v, aid))
        elif k == "languages":
            conn.execute(f"UPDATE agent_profiles SET {k}=? WHERE id=?", (json.dumps(v), aid))
        elif k in ("pricing_multiplier","sort_order","region_id"):
            conn.execute(f"UPDATE agent_profiles SET {k}=? WHERE id=?", (v, aid))
    conn.commit()
    conn.close()


# === Market Pricing ===
def get_market_pricing(region_id=None):
    conn = get_db()
    if region_id:
        rows = conn.execute(
            "SELECT mp.*, r.name as region_name, r.code as region_code FROM market_pricing mp LEFT JOIN regions r ON mp.region_id=r.id WHERE mp.region_id=? ORDER BY mp.product_category",
            (region_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT mp.*, r.name as region_name, r.code as region_code FROM market_pricing mp LEFT JOIN regions r ON mp.region_id=r.id ORDER BY mp.region_id, mp.product_category"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_market_pricing(data):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO market_pricing (region_id, product_category, min_price, max_price, target_margin, min_margin, competitor_factor)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(region_id, product_category) DO UPDATE SET
               min_price=?, max_price=?, target_margin=?, min_margin=?, competitor_factor=?""",
            (data.get("region_id"), data.get("product_category",""),
             data.get("min_price",0), data.get("max_price",0),
             data.get("target_margin",0.5), data.get("min_margin",0.35),
             data.get("competitor_factor",1.0),
             data.get("min_price",0), data.get("max_price",0),
             data.get("target_margin",0.5), data.get("min_margin",0.35),
             data.get("competitor_factor",1.0))
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


# ==================== V6 — P&L Engine CRUD ====================

def get_pl_accounts(active_only=True):
    conn = get_db()
    if active_only:
        rows = conn.execute("SELECT * FROM pl_accounts WHERE is_active=1 ORDER BY sort_order, code").fetchall()
    else:
        rows = conn.execute("SELECT * FROM pl_accounts ORDER BY sort_order, code").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pl_account(account_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM pl_accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_pl_account(data):
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO pl_accounts (code, name, type, category, description, sort_order)
           VALUES (?,?,?,?,?,?)""",
        (data.get("code"), data.get("name"), data.get("type"),
         data.get("category", ""), data.get("description", ""), data.get("sort_order", 0))
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def get_pl_periods():
    conn = get_db()
    rows = conn.execute("SELECT * FROM pl_periods ORDER BY start_date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pl_period(period_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM pl_periods WHERE id=?", (period_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_pl_period(data):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO pl_periods (period_code, type, start_date, end_date, notes) VALUES (?,?,?,?,?)",
        (data.get("period_code"), data.get("type"), data.get("start_date"),
         data.get("end_date"), data.get("notes", ""))
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def close_pl_period(period_id):
    conn = get_db()
    conn.execute("UPDATE pl_periods SET is_closed=1 WHERE id=?", (period_id,))
    conn.commit()
    conn.close()


def add_pl_entry(data):
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO pl_entries (period_id, account_id, order_id, amount, entry_type, notes)
           VALUES (?,?,?,?,?,?)""",
        (data.get("period_id"), data.get("account_id"), data.get("order_id"),
         data.get("amount", 0), data.get("entry_type", "actual"), data.get("notes", ""))
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def get_pl_entries(period_id, account_id=None):
    conn = get_db()
    if account_id:
        rows = conn.execute(
            "SELECT pe.*, a.code as account_code, a.name as account_name, a.type as account_type, a.category as account_category "
            "FROM pl_entries pe LEFT JOIN pl_accounts a ON pe.account_id=a.id "
            "WHERE pe.period_id=? AND pe.account_id=? ORDER BY a.sort_order", (period_id, account_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT pe.*, a.code as account_code, a.name as account_name, a.type as account_type, a.category as account_category "
            "FROM pl_entries pe LEFT JOIN pl_accounts a ON pe.account_id=a.id "
            "WHERE pe.period_id=? ORDER BY a.sort_order", (period_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== V6 — Invoice CRUD ====================

def get_invoices(status=None, limit=50):
    conn = get_db()
    if status:
        rows = conn.execute(
            """SELECT i.*, c.name as customer_name, c.company as customer_company
               FROM invoices i LEFT JOIN customers c ON i.customer_id=c.id
               WHERE i.status=? ORDER BY i.created_at DESC LIMIT ?""",
            (status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT i.*, c.name as customer_name, c.company as customer_company
               FROM invoices i LEFT JOIN customers c ON i.customer_id=c.id
               ORDER BY i.created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_invoice(invoice_id):
    conn = get_db()
    row = conn.execute(
        """SELECT i.*, c.name as customer_name, c.company as customer_company, c.country as customer_country
           FROM invoices i LEFT JOIN customers c ON i.customer_id=c.id
           WHERE i.id=?""",
        (invoice_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_invoice_by_no(invoice_no):
    conn = get_db()
    row = conn.execute(
        "SELECT i.*, c.name as customer_name FROM invoices i LEFT JOIN customers c ON i.customer_id=c.id WHERE i.invoice_no=?",
        (invoice_no,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_invoice(data):
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO invoices (invoice_no, order_id, customer_id, issue_date, due_date,
           total_amount, currency, status, notes, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (data.get("invoice_no"), data.get("order_id"), data.get("customer_id"),
         data.get("issue_date"), data.get("due_date"), data.get("total_amount", 0),
         data.get("currency", "USD"), data.get("status", "draft"),
         data.get("notes", ""), data.get("created_by"))
    )
    iid = cur.lastrowid
    conn.commit()
    conn.close()
    return iid


def update_invoice(invoice_id, **kwargs):
    allowed = ['status', 'pdf_path', 'notes', 'sent_at', 'paid_at', 'cancelled_at']
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    conn = get_db()
    conn.execute(f"UPDATE invoices SET {', '.join(sets)} WHERE id=?", (*vals, invoice_id))
    conn.commit()
    conn.close()


def get_overdue_invoices():
    conn = get_db()
    rows = conn.execute(
        """SELECT i.*, c.name as customer_name, c.company as customer_company, c.whatsapp as customer_whatsapp
           FROM invoices i LEFT JOIN customers c ON i.customer_id=c.id
           WHERE i.status='sent' AND i.due_date < date('now')
           ORDER BY i.due_date ASC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_invoice_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    by_status = dict(conn.execute(
        "SELECT status, COUNT(*) as count FROM invoices GROUP BY status"
    ).fetchall())
    total_amount = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status NOT IN ('cancelled')").fetchone()[0]
    paid_amount = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status='paid'").fetchone()[0]
    overdue_amount = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status='overdue'").fetchone()[0]
    conn.close()
    return {
        "total": total,
        "by_status": by_status,
        "total_amount": round(total_amount, 2),
        "paid_amount": round(paid_amount, 2),
        "overdue_amount": round(overdue_amount, 2),
    }


# ==================== V6 — Expense CRUD ====================

def get_expenses(category=None, status=None, start_date=None, end_date=None, limit=50):
    conn = get_db()
    sql = """SELECT e.*, u.display_name as paid_by_name
             FROM expenses e LEFT JOIN users u ON e.paid_by=u.id WHERE 1=1"""
    params = []
    if category:
        sql += " AND e.category=?"
        params.append(category)
    if status:
        sql += " AND e.status=?"
        params.append(status)
    if start_date:
        sql += " AND e.expense_date>=?"
        params.append(start_date)
    if end_date:
        sql += " AND e.expense_date<=?"
        params.append(end_date)
    sql += " ORDER BY e.expense_date DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_expense(eid):
    conn = get_db()
    row = conn.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_expense(data):
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO expenses (category, amount, currency, expense_date, vendor, description, status, paid_by, notes, receipt_path)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (data.get("category"), data.get("amount", 0), data.get("currency", "USD"),
         data.get("expense_date"), data.get("vendor", ""), data.get("description", ""),
         data.get("status", "pending"), data.get("paid_by"), data.get("notes", ""),
         data.get("receipt_path", ""))
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def update_expense(eid, **kwargs):
    allowed = ['status', 'approved_by', 'approved_at', 'notes', 'receipt_path']
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    conn = get_db()
    conn.execute(f"UPDATE expenses SET {', '.join(sets)} WHERE id=?", (*vals, eid))
    conn.commit()
    conn.close()


def get_expense_summary(group_by="category", start_date=None, end_date=None):
    conn = get_db()
    sql = f"SELECT {group_by}, SUM(amount) as total, COUNT(*) as count FROM expenses WHERE status='approved'"
    params = []
    if start_date:
        sql += " AND expense_date>=?"
        params.append(start_date)
    if end_date:
        sql += " AND expense_date<=?"
        params.append(end_date)
    sql += f" GROUP BY {group_by} ORDER BY total DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_expense_trend(months=6):
    conn = get_db()
    rows = conn.execute(
        """SELECT strftime('%Y-%m', expense_date) as month,
                  SUM(amount) as total, COUNT(*) as count
           FROM expenses WHERE status='approved'
           AND expense_date >= date('now', ? || ' months')
           GROUP BY strftime('%Y-%m', expense_date)
           ORDER BY month""",
        (f"-{months}",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== V6 — Budget CRUD ====================

def get_budgets(period=None, category=None):
    conn = get_db()
    sql = "SELECT * FROM budgets WHERE 1=1"
    params = []
    if period:
        sql += " AND period=?"
        params.append(period)
    if category:
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY category"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_budget(data):
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO budgets (period, category, planned_amount, notes)
               VALUES (?,?,?,?)
               ON CONFLICT(period, category) DO UPDATE SET
               planned_amount=?, notes=?, updated_at=CURRENT_TIMESTAMP""",
            (data.get("period"), data.get("category"), data.get("amount", 0),
             data.get("notes", ""), data.get("amount", 0), data.get("notes", ""))
        )
        bid = cur.lastrowid
        conn.commit()
        conn.close()
        return bid
    except Exception:
        conn.close()
        return None


def delete_budget(bid):
    conn = get_db()
    conn.execute("DELETE FROM budgets WHERE id=?", (bid,))
    conn.commit()
    conn.close()


# ==================== V3 — Self-Optimizing Sales System ====================

def init_v3_tables(conn=None):
    """初始化 V3 自优化销售系统表"""
    if conn is None:
        conn = get_db()
        close_after = True
    else:
        close_after = False

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS v3_conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            country TEXT DEFAULT '',
            intent TEXT DEFAULT '',
            initial_state TEXT DEFAULT '',
            final_state TEXT DEFAULT '',
            state_path TEXT DEFAULT '[]',
            price_tier TEXT DEFAULT 'UNKNOWN',
            ab_version TEXT DEFAULT '',
            quote_sent TEXT DEFAULT '',
            quote_amount REAL DEFAULT 0,
            final_result TEXT DEFAULT 'open' CHECK(final_result IN ('open','won','lost','silent')),
            lost_reason TEXT DEFAULT '',
            reply_latency_seconds INTEGER DEFAULT 0,
            messages_count INTEGER DEFAULT 0,
            conversion_score INTEGER DEFAULT 0,
            deal_probability REAL DEFAULT 0,
            revenue REAL DEFAULT 0,
            profit REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS v3_ab_test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            ab_version TEXT NOT NULL CHECK(ab_version IN ('A','B','C')),
            total_trials INTEGER DEFAULT 0,
            won_count INTEGER DEFAULT 0,
            lost_count INTEGER DEFAULT 0,
            silent_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            avg_conversion_score REAL DEFAULT 0,
            avg_deal_probability REAL DEFAULT 0,
            weight REAL DEFAULT 1.0,
            last_optimized_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(state, ab_version)
        );
        CREATE TABLE IF NOT EXISTS v3_price_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_tier TEXT NOT NULL CHECK(price_tier IN ('LOW','MID','HIGH','UNKNOWN')),
            ab_label TEXT NOT NULL,
            price_label TEXT DEFAULT '',
            price_range TEXT DEFAULT '',
            midpoint_price REAL DEFAULT 0,
            total_trials INTEGER DEFAULT 0,
            won_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            avg_revenue REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(price_tier, ab_label)
        );
        CREATE TABLE IF NOT EXISTS v3_intent_conversion_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent TEXT NOT NULL UNIQUE,
            total_occurrences INTEGER DEFAULT 0,
            won_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            current_weight INTEGER DEFAULT 0,
            optimized_weight INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0,
            last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS v3_weight_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            weight_type TEXT NOT NULL,
            weight_key TEXT NOT NULL,
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            reason TEXT DEFAULT 'auto_optimize',
            triggered_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS v3_deal_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversion_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('won','lost')),
            winning_factors TEXT DEFAULT '[]',
            lost_reasons TEXT DEFAULT '[]',
            key_insight TEXT DEFAULT '',
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversion_id) REFERENCES v3_conversions(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS v3_optimization_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            optimizer_type TEXT NOT NULL,
            summary TEXT DEFAULT '',
            changes_made INTEGER DEFAULT 0,
            details TEXT DEFAULT '{}',
            triggered_by TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Indexes
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_v3_conv_customer ON v3_conversions(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_v3_conv_result ON v3_conversions(final_result)",
        "CREATE INDEX IF NOT EXISTS idx_v3_conv_created ON v3_conversions(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_v3_ab_state ON v3_ab_test_results(state)",
        "CREATE INDEX IF NOT EXISTS idx_v3_price_tier ON v3_price_experiments(price_tier)",
        "CREATE INDEX IF NOT EXISTS idx_v3_weight_type ON v3_weight_history(weight_type)",
        "CREATE INDEX IF NOT EXISTS idx_v3_deal_conv ON v3_deal_analyses(conversion_id)",
        "CREATE INDEX IF NOT EXISTS idx_v3_opt_type ON v3_optimization_log(optimizer_type)",
    ]:
        try:
            conn.execute(idx)
        except:
            pass

    if close_after:
        conn.commit()
        conn.close()


# ==================== V4 — Autonomous Sales System tables ====================

def init_v4_tables(conn=None):
    """Initialize V4 Autonomous Sales System tables"""
    if conn is None:
        conn = get_db()
        close_after = True
    else:
        close_after = False

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS v4_customer_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL UNIQUE,
            priority_score INTEGER DEFAULT 0,
            priority_class TEXT DEFAULT 'C' CHECK(priority_class IN ('A','B','C')),
            priority_action TEXT DEFAULT 'HOLD' CHECK(priority_action IN ('HOLD','PUSH','CLOSE_NOW')),
            priority_reason TEXT DEFAULT '',
            priority_updated_at TIMESTAMP,
            price_tier_override TEXT DEFAULT NULL,
            price_anchors_json TEXT DEFAULT NULL,
            discount_percent REAL DEFAULT 0,
            discount_reason TEXT DEFAULT '',
            pricing_updated_at TIMESTAMP,
            total_messages INTEGER DEFAULT 0,
            avg_reply_speed_hours REAL DEFAULT 0,
            quote_view_count INTEGER DEFAULT 0,
            last_activity_at TIMESTAMP,
            last_push_at TIMESTAMP,
            last_followup_at TIMESTAMP,
            push_count INTEGER DEFAULT 0,
            scheduler_state TEXT DEFAULT 'idle',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS v4_pricing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            old_tier TEXT DEFAULT '',
            new_tier TEXT DEFAULT '',
            old_anchors TEXT DEFAULT '',
            new_anchors TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            triggered_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS v4_scheduler_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_slot TEXT NOT NULL,
            action TEXT NOT NULL,
            customer_id INTEGER,
            status TEXT DEFAULT 'completed' CHECK(status IN ('completed','skipped','error')),
            detail TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """)

    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_v4_state_customer ON v4_customer_state(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_v4_state_class ON v4_customer_state(priority_class)",
        "CREATE INDEX IF NOT EXISTS idx_v4_sched_slot ON v4_scheduler_log(schedule_slot)",
        "CREATE INDEX IF NOT EXISTS idx_v4_pricing_customer ON v4_pricing_history(customer_id)",
    ]:
        try:
            conn.execute(idx)
        except:
            pass

    if close_after:
        conn.commit()
        conn.close()


# ==================== V5 — Agent Competition tables ====================

def init_v5_tables(conn=None):
    """Initialize V5 Agent Competition tables"""
    if conn is None:
        conn = get_db()
        close_after = True
    else:
        close_after = False

    conn.executescript("""
        DROP TABLE IF EXISTS v5_agent_assignments;
        DROP TABLE IF EXISTS v5_agent_memory;

        CREATE TABLE IF NOT EXISTS v5_agent_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            scene_state TEXT DEFAULT NULL,
            scene_priority TEXT DEFAULT NULL,
            total_matches INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            last_score REAL DEFAULT 0.0,
            last_win TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS v5_competition_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_msg_snippet TEXT DEFAULT '',
            agent_ids TEXT DEFAULT '',
            scores_json TEXT DEFAULT '[]',
            winner_agent_id TEXT DEFAULT '',
            winner_score REAL DEFAULT 0.0,
            customer_state TEXT DEFAULT '',
            context_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_v5_weights_agent ON v5_agent_weights(agent_id)",
        "CREATE INDEX IF NOT EXISTS idx_v5_weights_scene ON v5_agent_weights(scene_state, scene_priority)",
        "CREATE INDEX IF NOT EXISTS idx_v5_comp_winner ON v5_competition_log(winner_agent_id)",
        "CREATE INDEX IF NOT EXISTS idx_v5_comp_created ON v5_competition_log(created_at)",
    ]:
        try:
            conn.execute(idx)
        except:
            pass

    if close_after:
        conn.commit()
        conn.close()


