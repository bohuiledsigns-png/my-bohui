"""假设引擎 - 用默认模型填补客户缺失信息，实现无规格也能报价"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


# ==================== 默认模型 ====================

DEFAULT_MODELS = {
    "restaurant": {
        "width_m": 1.2,
        "height_m": 0.4,
        "letters": "6-8",
        "usage": "outdoor",
        "sign_type": "backlit_led",
        "description": "Standard restaurant storefront"
    },
    "bar": {
        "width_m": 1.5,
        "height_m": 0.5,
        "letters": "5-10",
        "usage": "outdoor",
        "sign_type": "neon_sign",
        "description": "Bar / nightclub storefront"
    },
    "retail": {
        "width_m": 2.0,
        "height_m": 0.6,
        "letters": "8-12",
        "usage": "outdoor",
        "sign_type": "channel_letters",
        "description": "Retail shop storefront"
    },
    "office": {
        "width_m": 0.8,
        "height_m": 0.3,
        "letters": "4-8",
        "usage": "indoor",
        "sign_type": "acrylic_letters",
        "description": "Office lobby / door sign"
    },
    "hotel": {
        "width_m": 3.0,
        "height_m": 0.8,
        "letters": "6-15",
        "usage": "outdoor",
        "sign_type": "channel_letters",
        "description": "Hotel exterior sign"
    },
}

# ==================== 行业关键词检测 ====================

_INDUSTRY_KEYWORDS = [
    ("restaurant", ["restaurant", "cafe", "coffee", "pizza", "burger", "diner",
                    "bistro", "food", "grill", "kitchen", "bakery", "bar & grill",
                    "takeout", "takeaway", "fast food", "dining", " eatery"]),
    ("bar", ["bar", "pub", "club", "lounge", "nightclub", "cocktail", "brewery",
             "wine", "tavern", "speakeasy"]),
    ("retail", ["retail", "shop", "store", "boutique", "showroom", "market",
                "salon", "spa", "fitness", "gym", "studio"]),
    ("office", ["office", "lobby", "corporate", "business", "suite", "agency",
                "firm", "consulting"]),
    ("hotel", ["hotel", "motel", "inn", "hostel", "resort", "lodge", "guesthouse"]),
]


def detect_industry(text):
    """从客户消息中检测所属行业"""
    if not text:
        return "restaurant"
    t = text.lower()
    for industry, keywords in _INDUSTRY_KEYWORDS:
        if any(kw in t for kw in keywords):
            return industry
    return "restaurant"  # 默认餐厅


# ==================== 缺失字段检测 ====================

_REQUIRED_FIELDS = ["width", "height", "photo", "letters"]


def detect_missing_fields(input_data):
    """检测客户已提供数据中缺失哪些必填字段"""
    missing = []
    for field in _REQUIRED_FIELDS:
        val = input_data.get(field)
        if val is None or val == "" or val == 0:
            missing.append(field)
    return missing


# ==================== 核心假设引擎 ====================

class AssumptionEngine:
    """用默认模型填补客户缺失信息"""

    def __init__(self, models=None):
        self.models = models or DEFAULT_MODELS

    def build_assumption(self, industry=None, input_data=None):
        """根据行业和已有输入构建完整假设模型

        参数:
            industry: 行业标签（restaurant/bar/retail等），None则自动检测
            input_data: 客户已提供的数据字典，可选

        返回:
            dict: {industry, width_m, height_m, letters, sign_type,
                   usage, description, is_assumed, overrides}
        """
        input_data = input_data or {}
        industry = industry or detect_industry(
            input_data.get("text", "")
        )
        model = self.models.get(industry, self.models["restaurant"])

        # 基础假设
        assumption = {
            "industry": industry,
            "width_m": model["width_m"],
            "height_m": model["height_m"],
            "letters": model["letters"],
            "sign_type": model["sign_type"],
            "usage": model["usage"],
            "description": model["description"],
            "is_assumed": True,
            "overrides": {},
        }

        # 客户已提供的数据覆盖假设（保留用户输入）
        override_keys = ["width", "height", "letters"]
        for k in override_keys:
            if k in input_data and input_data[k]:
                assumption[k + "_m" if k == "width" or k == "height" else k] = input_data[k]
                assumption["overrides"][k] = input_data[k]

        if assumption["overrides"]:
            assumption["is_assumed"] = False  # 部分实际数据=部分假设

        return assumption

    def build_explanation(self, assumption):
        """将假设模型转换为客户可读的解释文本"""
        lines = [
            f"Based on a typical {assumption['description']}:",
            f"  Width: {assumption['width_m']}m",
            f"  Letters: {assumption['letters']}",
            f"  Type: {assumption['sign_type'].replace('_', ' ')}",
        ]
        if assumption["overrides"]:
            lines.append("  (adjusted based on your input)")
        lines.append("This is a standard estimation — final price refines with your exact size.")
        return "\n".join(lines)


# ==================== 报价计算（轻量） ====================

def _load_category_prices():
    """从DB加载各分类的价格范围"""
    cat_prices = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT category, price_tiers FROM products WHERE status='active'"
        ).fetchall()
        conn.close()
        for cat, pt_json in rows:
            try:
                tiers = json.loads(pt_json)
                prices = []
                if isinstance(tiers, list):
                    for t in tiers:
                        if isinstance(t, dict) and "price" in t:
                            prices.append(float(t["price"]))
                if prices:
                    cat_prices[cat] = (min(prices), max(prices))
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception:
        pass
    return cat_prices


_CATEGORY_PRICES_CACHE = None


def _get_cached_prices():
    global _CATEGORY_PRICES_CACHE
    if _CATEGORY_PRICES_CACHE is None:
        _CATEGORY_PRICES_CACHE = _load_category_prices()
    return _CATEGORY_PRICES_CACHE


# ==================== 价格模型映射 ====================

_SIGN_TYPE_TO_CATEGORY = {
    "backlit_led": ["3D LED发光字", "背光字"],
    "neon_sign": ["LED霓虹灯字"],
    "channel_letters": ["3D LED发光字", "正面发光字"],
    "acrylic_letters": ["广告招牌", "亚克力工艺制品"],
    "stainless_steel": ["不锈钢金属字"],
    "chromatic": ["炫彩字"],
}


def estimate_price_range(assumption, margin=0.2):
    """根据假设模型估算价格区间（基础版，不依赖DB）

    参数:
        assumption: AssumptionEngine.build_assumption() 输出
        margin: 浮动范围（默认±20%）

    返回:
        (min_price, max_price, currency)
    """
    # 预算默认值（按类型）
    base_prices = {
        "acrilic_covered": (120, 250),
        "backlit_led": (250, 520),
        "neon_sign": (200, 400),
        "channel_letters": (280, 600),
        "acrylic_letters": (100, 300),
        "stainless_steel": (300, 750),
    }

    sign_type = assumption.get("sign_type", "backlit_led")
    base_min, base_max = base_prices.get(sign_type, (200, 500))

    # 尝试从DB获取更精确的区间
    categories = _SIGN_TYPE_TO_CATEGORY.get(sign_type, [])
    db_prices = _get_cached_prices()
    for cat in categories:
        if cat in db_prices:
            db_min, db_max = db_prices[cat]
            base_min = min(base_min, db_min)
            base_max = max(base_max, db_max)

    # 宽幅影响（更宽的招牌通常更贵）
    width = assumption.get("width_m", 1.2)
    width_factor = max(0.6, width / 1.2)

    min_p = int(base_min * width_factor * (1 - margin))
    max_p = int(base_max * width_factor * (1 + margin))

    return (min_p, max_p, "USD")


# ==================== 主要入口 ====================

def generate_quote(user_input, industry=None):
    """主入口：根据用户输入生成报价

    参数:
        user_input: dict — 客户已提供的信息
            {"width": ..., "height": ..., "letters": ..., "photo": ..., "text": "..."}
        industry: 可选，指定行业

    返回:
        dict:
            mode: "ASSUMPTION_BASED" 或 "PRECISE"
            assumption: 假设模型数据
            price_range: (min, max, currency)
            missing: 缺失字段列表
            explanation: 客户可读解释
            next_actions: 推荐的下一步行动
    """
    # 1. 检测缺失信息
    missing = detect_missing_fields(user_input)

    # 2. 构建假设模型
    engine = AssumptionEngine()
    assumption = engine.build_assumption(industry=industry, input_data=user_input)

    # 3. 估算价格
    price_range = estimate_price_range(assumption)

    # 4. 决定模式
    has_photo = bool(user_input.get("photo"))
    has_all_specs = len(missing) <= 1  # 至多缺1项=接近精确

    if has_photo and has_all_specs:
        mode = "PRECISE"
    else:
        mode = "ASSUMPTION_BASED"

    # 5. 解释
    explanation = engine.build_explanation(assumption)

    # 6. 推荐下一步
    if "photo" in missing:
        next_actions = ["send storefront photo", "confirm standard size"]
    elif "width" in missing or "letters" in missing:
        next_actions = ["confirm letter count", "choose A/B/C size"]
    else:
        next_actions = ["confirm quote", "proceed to deposit"]

    return {
        "mode": mode,
        "assumption": assumption,
        "price_range": price_range,
        "missing": missing,
        "explanation": explanation,
        "next_actions": next_actions,
    }


def clear_price_cache():
    """清除价格缓存（产品更新后调用）"""
    global _CATEGORY_PRICES_CACHE
    _CATEGORY_PRICES_CACHE = None


# ==================== 快速测试 ====================
if __name__ == "__main__":
    # 场景1: 客户只说"how much for restaurant sign"
    r1 = generate_quote({"text": "how much for a restaurant sign"})
    print("=== 场景1: 无规格 ===")
    print(f"模式: {r1['mode']}")
    print(f"假设: {r1['assumption']['width_m']}m, {r1['assumption']['letters']} letters, {r1['assumption']['sign_type']}")
    print(f"价格: USD {r1['price_range'][0]} - {r1['price_range'][1]}")
    print(f"缺失: {r1['missing']}")
    print()

    # 场景2: 客户给了宽度
    r2 = generate_quote({"text": "I need a sign for my bar", "width": 2.0})
    print("=== 场景2: 部分规格 ===")
    print(f"模式: {r2['mode']}")
    print(f"假设: {r2['assumption']['width_m']}m, {r2['assumption']['letters']} letters, industry={r2['assumption']['industry']}")
    print(f"价格: USD {r2['price_range'][0]} - {r2['price_range'][1]}")
    print(f"覆盖: {r2['assumption']['overrides']}")
    print(f"解释:\\n{r2['explanation']}")
    print()

    # 场景3: 酒吧
    r3 = generate_quote({"text": "I run a cocktail bar in NYC"})
    print("=== 场景3: 酒吧 ===")
    print(f"行业: {r3['assumption']['industry']}")
    print(f"价格: USD {r3['price_range'][0]} - {r3['price_range'][1]}")
