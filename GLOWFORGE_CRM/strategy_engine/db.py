"""共享只读数据库连接 + 数据解析工具"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 此CRM系统中代表「已完成/有效订单」的状态列表
ACTIVE_ORDER_STATUSES = (
    "shipped", "delivered", "completed",
    "pending_approval", "in_production",
)

# 国家全名/别名 → ISO 二位代码
COUNTRY_NORMALIZE = {
    "US": "US", "USA": "US", "美国": "US",
    "UK": "GB", "英国": "GB", "GB": "GB",
    "JP": "JP", "日本": "JP",
    "CN": "CN", "中国": "CN",
    "CA": "CA", "加拿大": "CA",
    "DE": "DE", "德国": "DE",
    "FR": "FR", "法国": "FR",
    "IT": "IT", "意大利": "IT",
    "ES": "ES", "西班牙": "ES",
    "NL": "NL", "荷兰": "NL",
    "AE": "AE", "阿联酋": "AE",
    "SA": "SA", "沙特": "SA",
    "QA": "QA", "KW": "KW", "OM": "OM", "BH": "BH",
    "AU": "AU", "澳大利亚": "AU",
    "SG": "SG", "新加坡": "SG",
    "MY": "MY",
}


def _read_db():
    """获取只读数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


def normalize_country(raw):
    """将国家名/别名转为 ISO 二位代码，查不到返回原值"""
    if not raw:
        return raw
    return COUNTRY_NORMALIZE.get(raw.strip(), raw)


def parse_items(items_json):
    """解析 orders.items 字段，处理双重 JSON 编码

    此 CRM 的 items 字段存的是 json.dumps(json.dumps(list))，
    需要两次 json.loads 才能拿到真实数组。
    """
    if not items_json or items_json == "[]":
        return []
    try:
        parsed = json.loads(items_json)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return []
