"""从 CRM 数据库生成产品目录知识文件
查询所有 active 产品，按分类组格式化输出到 knowledge/prod_产品目录.txt

用法:
  python scripts/generate_product_catalog.py
"""
import os
import json
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
OUTPUT_FILE = os.path.join(KNOWLEDGE_DIR, "prod_产品目录.txt")


def _fmt_specs(specs_json):
    """解析 specs JSON 为可读文本"""
    try:
        spec_dict = json.loads(specs_json) if specs_json not in ('{}', '', None) else {}
    except json.JSONDecodeError:
        return ""
    if not spec_dict:
        return ""
    parts = []
    for k, v in spec_dict.items():
        parts.append(f"  {k}: {v}")
    return "\n".join(parts)


def _fmt_price(price_json):
    """解析 price_tiers JSON 为价格描述"""
    try:
        tiers = json.loads(price_json) if price_json not in ('[]', '{}', '', None) else []
    except json.JSONDecodeError:
        return ""
    if not tiers:
        return "  价格: 面议"
    parts = []
    for t in tiers:
        if "qty" in t and "price" in t:
            parts.append(f"  起订{t['qty']}个，单价USD{t['price']}")
        elif "tier" in t and "price" in t:
            parts.append(f"  [{t['tier']}] USD{t['price']}")
        elif "tier" in t and "note" in t:
            parts.append(f"  [{t['tier']}] {t['note']}")
        elif "price" in t:
            parts.append(f"  USD{t['price']}")
        elif "note" in t:
            parts.append(f"  {t['note']}")
    return "\n".join(parts) if parts else ""


def generate_product_catalog():
    """生成产品目录知识文件"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM products WHERE status='active' ORDER BY category, name"
    ).fetchall()
    conn.close()

    # 按分类分组
    by_category = {}
    for r in rows:
        cat = r["category"] or "其他"
        by_category.setdefault(cat, []).append(r)

    total = len(rows)
    lines = [
        "GLOWFORGE 完整产品目录",
        "═" * 47,
        "类别: prod",
        f"生成日期: {datetime.now().strftime('%Y-%m-%d')}",
        f"产品总数: {total}",
        "",
    ]

    for category in sorted(by_category.keys()):
        products = by_category[category]
        lines.append(f"=== {category} ({len(products)}款) ===")
        lines.append("")
        for p in products:
            name = p["name"] or "未命名产品"
            lines.append(f"【{name}】")
            desc = (p["description"] or "").strip()
            if desc:
                lines.append(f"  描述: {desc}")
            specs_txt = _fmt_specs(p["specs"])
            if specs_txt:
                lines.append(specs_txt)
            price_txt = _fmt_price(p["price_tiers"])
            if price_txt:
                lines.append(price_txt)
            unit = p["unit"] or "个"
            currency = p["currency"] or "USD"
            lines.append(f"  单位: {unit} | 币种: {currency}")
            lines.append("")

    content = "\n".join(lines)
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    size_kb = os.path.getsize(OUTPUT_FILE) // 1024
    print(f"OK 产品目录已生成: {OUTPUT_FILE}")
    print(f"   共 {total} 个产品, {len(by_category)} 个分类, {size_kb}KB")

    # 刷新 AI 知识库缓存
    try:
        sys.path.insert(0, BASE_DIR)
        import ai_engine
        ai_engine.clear_knowledge_base_cache()
        print("OK AI 知识库缓存已清除")
    except Exception as e:
        print(f"!! 清除缓存失败: {e}")

    return OUTPUT_FILE


if __name__ == "__main__":
    import sys
    generate_product_catalog()
