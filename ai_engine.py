"""AI引擎 — 阿里云Qwen翻译 + 通义万相生图 + 行业知识库"""
import requests
import time
import re
import json
import os
import sqlite3

ALI_KEY = "sk-468fb68eaf4d4097abaa48327716ccc0"
ALI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
TRANSLATE_MODEL = "qwen3.7-max"
IMAGE_MODEL = "wan2.7-image-pro"
VIDEO_MODEL = "wan2.6-t2v"
VL_MODEL = "qwen-vl-max"
VIDEO_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"

# ============ 火山引擎 ============
VOLC_IMG_KEY = "ark-ee9bc98c-1e4d-4984-827d-be31793cd063-7ee17"        # 文生图(seedream)
VOLC_VID_KEY = "ark-3773ab4c-a46c-4b6f-81c8-997b654d5c8a-e1a24"        # 图生视频(seedance)
VOLC_BASE = "https://ark.cn-beijing.volces.com/api/v3"
VOLC_IMG_MODEL = "doubao-seedream-4-5-251128"
VOLC_VID_MODEL = "doubao-seedance-1-5-pro-251215"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
COUNTRIES_DIR = os.path.join(BASE_DIR, "countries")
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

# 销售知识库
KNOWLEDGE_BASE_PATH = os.path.join(BASE_DIR, "ai_sales_prompt.txt")
_KNOWLEDGE_BASE_CACHE = None

def load_knowledge_base():
    """加载销售知识库（带缓存）"""
    global _KNOWLEDGE_BASE_CACHE
    if _KNOWLEDGE_BASE_CACHE is not None:
        return _KNOWLEDGE_BASE_CACHE
    if os.path.exists(KNOWLEDGE_BASE_PATH):
        with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
            _KNOWLEDGE_BASE_CACHE = f.read()
        return _KNOWLEDGE_BASE_CACHE
    return ""

def clear_knowledge_base_cache():
    """清除缓存（知识库更新后调用）"""
    global _KNOWLEDGE_BASE_CACHE
    _KNOWLEDGE_BASE_CACHE = None

TRANSLATE_PROMPT = """你是一个专业的外贸翻译。用户给你中文，你翻译成{lang}。

公司背景：Bohui（博汇），中国GLOWFORGE工厂，产品出口全球。

产品线：
- 招牌广告发光字 / 炫彩发光字 → illuminated signage, channel letters, GLOWFORGE chromatic LED signs
- 亚克力工艺制品 → acrylic fabrication, acrylic display, acrylic signage
- 亚克力家具 → acrylic furniture
- AI宣传片 → promotional video

规则：
- 扮演博汇销售Philip，语气专业、友好、B2B
- 保留品牌名: Bohui, GLOWFORGE, Raceway
- 直接输出翻译结果，不要解释，不要加礼貌用语

翻译以下中文到{lang}："""


def ask_ali(prompt, text, max_tokens=1500, timeout=60, system=None):
    """调用阿里云Qwen"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt + "\n\n" + text})
    payload = {
        "model": TRANSLATE_MODEL,
        "messages": messages,
        "max_tokens": max_tokens
    }
    headers = {"Authorization": f"Bearer {ALI_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(f"{ALI_BASE}/chat/completions", headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            time.sleep(2)
        except:
            time.sleep(2)
    return None


def ask_ali_multimodal(prompt, image_base64, max_tokens=2000, timeout=60):
    """调用阿里云Qwen多模态模型（图片+文字分析）"""
    payload = {
        "model": VL_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_base64}},
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "max_tokens": max_tokens
    }
    headers = {"Authorization": f"Bearer {ALI_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(f"{ALI_BASE}/chat/completions", headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            time.sleep(2)
        except:
            time.sleep(2)
    return None


PRODUCT_ANALYZE_PROMPT = """你是一个专业的广告标识行业产品专家。分析这张产品图片，提取产品信息并生成AI生图提示词。

请严格按以下JSON格式输出（纯JSON，不要markdown代码块，不要其他文字）：
{
  "name": "产品中文名称（简短准确）",
  "category": "产品分类（发光字/炫彩字/亚克力字/LED招牌/亚克力展示/亚克力家具/其他）",
  "specs": {
    "material": "材料（如不锈钢/亚克力/镀锌板/铁皮等）",
    "thickness": "厚度",
    "size_range": "尺寸范围",
    "color_options": "颜色选项",
    "led_color_temp": "LED色温（如暖白3000K/冷白6500K/RGB全彩可调）",
    "packaging": "包装方式",
    "accessories": "配件清单（安装支架、螺丝、电源适配器、遥控器等）"
  },
  "description": "产品详细描述（工艺、卖点、适用场景，中文50-100字）",
  "image_prompt": "英文AI生图提示词，用于通义万相生成专业产品效果图，描述产品外观、材质、灯光效果、拍摄角度、背景风格等"
}"""


def analyze_product_image(image_base64):
    """分析产品图片，返回结构化产品信息 + 生图提示词"""
    try:
        result = ask_ali_multimodal(PRODUCT_ANALYZE_PROMPT, image_base64, max_tokens=2048, timeout=90)
        if not result:
            return {"error": "AI无返回"}
        cleaned = result.strip()
        for prefix in ("```json", "```"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": result, "error": "JSON解析失败，请重试"}
    except Exception as e:
        return {"error": str(e)}


def translate(text, target_language="English", country=""):
    """中文→指定语言翻译，可选注入国家上下文"""
    prompt = TRANSLATE_PROMPT.replace("{lang}", target_language)
    country_context = get_country_context(country)
    if country_context:
        prompt += f"\n\n注意：对方来自以下国家地区，请根据其商业文化风格调整语气：\n{country_context}"
    return ask_ali(prompt, text)


ANALYZE_PROMPT = """你扮演博汇（Bohui GLOWFORGE）外贸销售 Philip，15年行业老手。

===== 身份 =====
Philip，博汇工厂，15年广告标识外贸销售。自信果断不啰嗦，像行业顾问不像客服。
suggested_reply_en 必须纯英文，禁止夹带中文。

===== 15年老销售行为守则 =====
1. 客户问价格 → 反问尺寸/数量/图纸 + 安装环境推荐配置。绝不给空泛数字
2. 客户比价压价 → 不慌不降价，列3个偷工减料点（LED品牌/电源认证/不锈钢等级），邀请客户拿配置来比
3. 客户说"考虑一下" → 追问具体犹豫什么（价格/交期/信任），不干等
4. 客户要目录 → 先发目录，立刻追问具体项目方向
5. 客户要下单 → 确认规格+数量+贸易条款，推进到收定金
6. 客户要样品 → 明确样品付费，大货退还，引导客户给规格做样
7. 客户售后投诉 → 先道歉安抚，要求发照片/视频排查，给出保修说明

===== 每次回复嵌入B2B要素（选2项） =====
MOQ 1套起 / T/T 30%+70% / FOB Shenzhen / 木箱海运 / 10-15天交期 / 阶梯价

===== 回复规则 =====
✅ 每次回复推进对话：追问1个关键信息 或 引导下一步动作
✅ 果断自信，用肯定句："I'd recommend 304 for outdoor"
✅ 用到具体参数：材料厚度、等级、IP防水等级、LED品牌
✅ 比价列出3个差异化点（电源/材质/品控）
✅ 售后用 "Let me take care of this" 而不是 "Sorry for inconvenience"
✅ 一次最多问2个问题

❌ 不编价格 / 不卑微 / 不正式邮件腔 / 不中式英语 / 不中英混杂
❌ suggested_reply_en 纯英文，绝不含中文

===== 如何使用下方「销售策略数据」模块 =====
以下数据块会在每次分析时提供。你必须自然融入回复：

[客户角色判断 + 对应策略]
- 根据角色调整话术重心：同行强调OEM保护，设计师讲工艺细节，贸易商谈利润，工程公司讲交期
- 客户角色不明确或不相关时，忽略即可

[价格参考数据]
- 如有价格区间：可以用它做价格锚定，但必须强调"最终按图纸报价"
- 客户给了具体规格时，可以给出range："For a standard project like yours, similar clients usually invest around USD X-Y per piece"
- 不可把这个价格当作最终报价

[相关案例]
- 如有匹配的客户案例：自然引用增加信任感
- 不要编造案例细节，只引用给出的内容

[工厂排期]
- 用排期信息制造合理紧迫感或给客户信心
- 如果工厂有空余：强调快速交货能力
- 如果排期满：建议尽早确认

===== 输出JSON =====
{
  "translation": "中文翻译",
  "intent": "询价/比价/问工艺/要样品/问交期/下单/售后/合作/要目录/跟进/其他",
  "intent_detail": "一句话分析客户真实需求+阶段判断",
  "urgency": "高/中/低",
  "suggested_reply_cn": "中文回复思路（客户阶段、要追的信息、策略）",
  "suggested_reply_en": "纯英文回复，遵守以上规则"
}
"""


def get_country_context(country):
    """加载国家档案中的AI上下文注入段落"""
    if not country:
        return ""
    country_map = {
        "USA": "USA.txt", "US": "USA.txt", "United States": "USA.txt", "America": "USA.txt",
        "UK": "UK.txt", "United Kingdom": "UK.txt", "Britain": "UK.txt", "England": "UK.txt",
        "Germany": "Germany.txt", "German": "Germany.txt", "Deutschland": "Germany.txt",
        "France": "France.txt", "French": "France.txt",
        "Spain": "Spain.txt", "Spanish": "Spain.txt", "España": "Spain.txt",
        "Russia": "Russia.txt", "Russian": "Russia.txt",
        "Japan": "Japan.txt", "Japanese": "Japan.txt",
        "Italy": "Italy.txt", "Italian": "Italy.txt",
    }
    filename = country_map.get(country)
    if not filename:
        return ""
    path = os.path.join(COUNTRIES_DIR, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "=== AI上下文注入 ===" in content:
        ctx = content.split("=== AI上下文注入 ===")[1]
        ctx = ctx.split("===")[0] if "===" in ctx else ctx
        return ctx.strip()
    return ""


# ==================== 知识库加载（智能选择） ====================

# 意图 → 知识前缀映射
_INTENT_KNOWLEDGE_MAP = {
    "询价": ["prod_", "tech_", "core_"],
    "比价": ["prod_", "tech_", "media_"],
    "问工艺": ["tech_", "core_"],
    "要样品": ["core_"],
    "问交期": ["core_"],
    "下单": ["prod_", "tech_"],
    "售后": ["core_", "tech_"],
    "合作": ["prod_", "media_"],
    "要目录": ["prod_"],
    "跟进": ["media_", "prod_"],
    "其他": ["tech_", "prod_"],
}

# 现有6个旧文件自动归为 core_
_CORE_FILES = {"客户FAQ.txt", "行业中英文术语.txt", "国际认证与标准.txt",
               "LED技术与色温.txt", "发光字材料与工艺.txt", "亚克力材料与应用.txt"}

# ==================== 销售策略4模块 ====================

# 英文关键词 → 产品分类映射（用于价格锚定）
_CATEGORY_KEYWORDS = [
    (["stainless steel", "metal letter", "metal sign", "metal logo"], "不锈钢金属字"),
    (["acrylic letter", "acrylic sign", "acrylic logo"], "广告招牌"),
    (["3d", "led channel", "channel letter", "illuminated letter", "light up", "light-up"], "3D LED发光字"),
    (["front lit", "front-lit", "front light", "frontlight"], "正面发光字"),
    (["backlit", "back lit", "back-lit", "halo"], "背光字"),
    (["neon", "led neon", "flex neon", "neon light"], "LED霓虹灯字"),
    (["mini letter", "small letter", "mini"], "迷你发光字"),
    (["chromatic", "colorful", "rgb", "color changing", "glowforge"], "炫彩字"),
    (["acrylic display", "display stand", "showcase", "retail display", "display rack"], "亚克力展示制品"),
    (["acrylic furniture", "acrylic table", "acrylic chair", "acrylic shelf", "acrylic cabinet"], "亚克力家具"),
    (["signage", "signboard", "shop sign", "store sign", "storefront"], "广告招牌"),
    (["vending machine", "vending"], "电商平台选品"),
    (["office sign", "door sign", "room sign"], "广告招牌"),
    (["led module", "led sign"], "3D LED发光字"),
]

# 角色识别关键词
_ROLE_KEYWORDS = [
    ("sign_company", ["oem", "white label", "our client", "our project", "sign company",
                      "our customer", "end client", "partner", "subcontract", "we are a"]),
    ("contractor", ["install", "mount", "drill", "site", "structural", "on-site",
                    "fit out", "fitout", "builder", "general contractor"]),
    ("trader", ["moq", "bulk", "container", "volume", "exclusive", "distributor",
                "wholesale", "importer", "agent", "reseller", "trade"]),
    ("designer", ["design", "aesthetic", "visual", "concept", "render", "finish",
                  "modern", "sleek", "architect", "interior", "decorate"]),
    ("end_user", ["my store", "my shop", "my business", "retail", "my company",
                  "i need", "i want", "i run", "i own", "my restaurant", "my hotel"]),
]


def _detect_customer_role(text):
    """检测客户角色：设计师/贸易商/工程公司/终端用户"""
    t = text.lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(kw in t for kw in keywords):
            return role
    return "general"


def _get_price_anchor(text):
    """从products表查询同类型产品价格区间，用于价格锚定"""
    try:
        t = text.lower()
        matched_cats = set()
        for keywords, cat in _CATEGORY_KEYWORDS:
            if any(kw in t for kw in keywords):
                matched_cats.add(cat)
        if not matched_cats:
            return ""

        conn = sqlite3.connect(DB_PATH)
        placeholders = ",".join("?" for _ in matched_cats)
        empty_json = "{}"
        rows = conn.execute(
            f"SELECT price_tiers FROM products WHERE category IN ({placeholders}) AND status='active' AND price_tiers NOT IN ('[]','{empty_json}','')",
            list(matched_cats)
        ).fetchall()
        conn.close()

        prices = []
        for (pt,) in rows:
            try:
                tiers = json.loads(pt)
                if isinstance(tiers, list):
                    for t in tiers:
                        if isinstance(t, dict) and "price" in t:
                            prices.append(float(t["price"]))
            except (json.JSONDecodeError, TypeError):
                continue

        if len(prices) < 2:
            return ""

        min_p, max_p = int(min(prices)), int(max(prices))
        avg_p = int(sum(prices) / len(prices))
        cat_label = "/".join(sorted(matched_cats))
        return f"[价格参考] {cat_label}: 通常 USD{min_p}-{max_p}/个（均价 ~USD{avg_p}），批量有阶梯优惠（基于{len(prices)}个产品数据，仅作参考，最终按图纸报价）"
    except Exception:
        return ""


def _get_social_proof(country, text):
    """从knowledge/ media_ 文件匹配相关案例"""
    if not country and not text:
        return ""
    try:
        if not os.path.exists(KNOWLEDGE_DIR):
            return ""
        t_lower = text.lower()
        country_lower = country.lower() if country else ""

        matches = []
        for f in sorted(os.listdir(KNOWLEDGE_DIR)):
            if not f.startswith("media_") or not f.endswith(".txt"):
                continue
            # 从文件名提取国家和行业线索
            f_lower = f.lower()
            country_match = not country or any(
                kw in f_lower for kw in [country_lower, country_lower[:3]]
            )
            # 从文件内容匹配客户消息关键词
            path = os.path.join(KNOWLEDGE_DIR, f)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    content = fp.read()
            except Exception:
                continue
            title = content.strip().split("\n")[0] if content.strip() else f
            intro = content.strip().split("\n")[1] if len(content.strip().split("\n")) > 1 else ""
            score = 0
            if country_match:
                score += 2
            # 内容关键词重叠
            text_words = set(t_lower.split())
            content_words = set(content.lower().split())
            overlap = len(text_words & content_words)
            if overlap > 3:
                score += 1
            if score > 0:
                matches.append((score, title[:60], intro[:80]))

        if not matches:
            return ""
        matches.sort(key=lambda x: -x[0])
        lines = ["[相关案例]"]
        for _, title, intro in matches[:2]:
            lines.append(f"  - {title}: {intro}")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_urgency_context():
    """从orders表查生产排期，生成紧迫感上下文"""
    try:
        conn = sqlite3.connect(DB_PATH)
        in_prod = conn.execute("SELECT COUNT(*) FROM orders WHERE status='in_production'").fetchone()[0]
        confirmed = conn.execute("SELECT COUNT(*) FROM orders WHERE status='confirmed'").fetchone()[0]
        conn.close()

        total_load = in_prod + confirmed
        if total_load == 0:
            return "[工厂排期] 目前生产线有空余产能，新订单可以快速排产，预计7-10个工作日可出货"
        elif total_load <= 3:
            return f"[工厂排期] 目前有{in_prod}个订单在生产、{confirmed}个待生产，产能正常情况下新订单排期约10-15个工作日"
        else:
            return f"[工厂排期] 目前有{in_prod}个订单在生产、{confirmed}个排队待产，建议尽早确认订单锁定排期"
    except Exception:
        return ""


def _get_role_strategy(role):
    """根据客户角色返回对应话术策略"""
    strategies = {
        "sign_company": "【OEM同行】强调客户保护（不接触终端）、中性包装、批次一致性、阶梯OEM价",
        "contractor": "【工程公司】强调交期准确性、安装便捷性、结构牢固度、批次一致性",
        "trader": "【贸易商】强调利润空间、分销保护、中性包装、灵活MOQ、优质售后支持",
        "designer": "【设计师】强调定制灵活性、表面处理工艺、色彩还原度、可实现性",
        "end_user": "【终端用户】强调品质保障、保修期、使用体验、安装指导",
        "general": "",
    }
    return strategies.get(role, "")


def _build_sales_strategy(text, country=""):
    """组装销售策略数据块"""
    role = _detect_customer_role(text)
    role_strategy = _get_role_strategy(role)
    price_anchor = _get_price_anchor(text)
    social_proof = _get_social_proof(country, text)
    urgency = _get_urgency_context()

    parts = []
    if role_strategy:
        parts.append(role_strategy)
    if price_anchor:
        parts.append(price_anchor)
    if social_proof:
        parts.append(social_proof)
    if urgency:
        parts.append(urgency)

    return "\n".join(parts) if parts else ""


def _detect_knowledge_intent(text):
    """根据客户消息快速判断意图（基于关键词，无AI调用）"""
    t = text.lower()
    if any(w in t for w in ["how much", "price", "cost", "cheap", "expensive",
                             "quote", "budget", "quotation", "多少钱", "报价",
                             "price list", "catalog", "rate"]):
        return "询价"
    if any(w in t for w in ["cheaper", "competitor", "other supplier", "compare",
                             "比价", "别家", "更便宜", "别处"]):
        return "比价"
    if any(w in t for w in ["material", "thickness", "acrylic", "stainless",
                             "waterproof", "led", "工艺", "材质", "材料", "尺寸",
                             "color", "font", "install", "怎么安装"]):
        return "问工艺"
    if any(w in t for w in ["sample", "样品", "打样", "试样"]):
        return "要样品"
    if any(w in t for w in ["delivery", "lead time", "shipping", "how long",
                             "交期", "多久", "什么时候能", "发货"]):
        return "问交期"
    if any(w in t for w in ["order", "place", "buy", "purchase", "下单", "订购", "定做"]):
        return "下单"
    if any(w in t for w in ["damage", "broken", "not working", "problem", "issue",
                             "坏了", "问题", "不亮", "不工作"]):
        return "售后"
    if any(w in t for w in ["catalog", "brochure", "product list", "目录", "产品", "产品图"]):
        return "要目录"
    if any(w in t for w in ["follow", "update", "any news", "any update",
                             "跟进", "有没有消息"]):
        return "跟进"
    return "其他"


def _load_knowledge_context(text, max_chars=8000):
    """根据客户消息加载相关知识文件，限总大小 max_chars 字符"""
    intent = _detect_knowledge_intent(text)
    prefixes = _INTENT_KNOWLEDGE_MAP.get(intent, ["tech_", "prod_"])

    if not os.path.exists(KNOWLEDGE_DIR):
        return ""

    all_files = sorted(os.listdir(KNOWLEDGE_DIR))
    selected = set()

    # 1. core_ 文件始终选中（旧6文件 + prod_产品目录）
    for f in all_files:
        if f in _CORE_FILES or f.startswith("prod_"):
            selected.add(f)

    # 2. 按意图前缀选择
    for f in all_files:
        if not f.endswith(".txt") or f in selected:
            continue
        if any(f.startswith(p) for p in prefixes):
            # media_ 文件量大，只选文件名匹配关键词的
            if f.startswith("media_") and intent != "跟进":
                file_words = set(f.lower().replace("_", " ").replace(".txt", "").split())
                text_words = set(text.lower().split())
                if not (file_words & text_words):
                    continue
            selected.add(f)

    # 3. 加载内容，限总量
    parts = []
    chars = 0
    max_per_file = max_chars // max(len(selected), 1)
    for f in sorted(selected):
        path = os.path.join(KNOWLEDGE_DIR, f)
        try:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            if len(content) > max_per_file:
                content = content[:max_per_file] + "\n...(截断)"
            title = content.strip().split("\n")[0] if content.strip() else f
            parts.append(f"=== 【{title}】 ===\n{content}")
            chars += len(content)
            if chars >= max_chars:
                break
        except Exception:
            continue

    return "\n\n".join(parts) if parts else ""


def analyze_customer_message(text, country="", history=None, style_samples=None, sales_name="Philip"):
    """分析客户消息：翻译 + 意图分析 + 建议回复，返回字典
    history: 可选，之前几轮聊天记录列表，每项 {role, content}
    style_samples: 可选，你手动回复过的示例列表 [{cn, en}]
    sales_name: 你的名字（默认Philip）
    """
    try:
        # 加载销售知识库作为system prompt
        knowledge_base = load_knowledge_base()

        # ====== 新增：注入相关知识 ======
        knowledge_context = _load_knowledge_context(text, max_chars=8000)
        if knowledge_context:
            knowledge_base += f"""

===== GLOWFORGE 行业知识库（客户相关问题参考） =====
{knowledge_context}
===============================================================
"""
        # ==============================

        # 如有国家上下文则注入
        country_context = get_country_context(country)
        # 把提示词中的"Philip"替换为你的名字
        injected_prompt = ANALYZE_PROMPT.replace("Philip", sales_name)

        # 注入风格样本让AI学习你的语气
        if style_samples and len(style_samples) > 0:
            style_lines = []
            for s in style_samples:
                cn = s.get("cn", "")[:80]
                en = s.get("en", "")[:80]
                if cn and en:
                    style_lines.append(f'{{"cn": "{cn}", "en": "{en}"}}')
            if style_lines:
                injected_prompt += f"""

===== {sales_name}（你）的回复风格参考 =====
以下是你之前手动回复客户的例子，AI 请模仿这种语气和风格：
{chr(10).join(style_lines)}
========================================
AI 的回复要跟以上例子风格一致：简短、自然、像真人销售随手发的。
"""

        # 如有聊天历史，追加到提示词中作为上下文
        if history and len(history) > 0:
            history_lines = []
            for h in history[-6:]:  # 最多取最近6条（3轮对话）
                role_label = "客户" if h.get("role") == "received" else f"销售{sales_name}"
                text_content = h.get("content_cn") or h.get("content_en") or h.get("text", "")
                history_lines.append(f"{role_label}: {text_content[:200]}")
            if history_lines:
                injected_prompt += f"""

===== 近期聊天记录（供参考上下文） =====
{chr(10).join(history_lines)}
========================================
请结合以上聊天记录分析客户最新的这条消息，保持回复的连贯性。
"""

        if country_context:
            injected_prompt += f"""

===== 客户国家背景（请据此调整回复风格） =====
{country_context}
================================================
"""

        # ====== 销售策略4模块注入 ======
        sales_strategy = _build_sales_strategy(text, country)
        if sales_strategy:
            injected_prompt += f"""

===== 销售策略数据（引用以下数据增强回复说服力） =====
{sales_strategy}
========================================================
"""
        # ================================

        result = ask_ali(injected_prompt, text, max_tokens=2000, timeout=60, system=knowledge_base if knowledge_base else None)
        if not result:
            return {"error": "AI无返回"}
        cleaned = result.strip()
        # 去掉可能的markdown代码块
        if cleaned.startswith("```"):
            lines = cleaned.split("\n", 1)
            cleaned = lines[1] if len(lines) > 1 else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": result, "error": "JSON解析失败"}
    except Exception as e:
        return {"error": str(e)}


AI_GREETING_PROMPT = """你是博汇（Bohui GLOWFORGE）的外贸销售。

===== 当前任务 =====
这是一个新的 WhatsApp 联系人，你要：
1. 分析客户资料（名字和国家）
2. 根据你的销售知识库判断客户类型和评级
3. 生成第一条打招呼消息（英文 + 中文翻译）

===== 首条消息规则 =====
- 友好、专业、简洁（不超过 80 个英文单词）
- 自我介绍（Bohui/GLOWFORGE factory, LED signage & acrylic manufacturer）
- 顺势问一句客户做什么生意/需要什么
- 不要问"Is this a wrong number?"（肯定是客户主动加的）
- 不要报价，不要承诺任何具体价格
- 必须附带中文翻译（用 --- 分隔英文和中文）

===== 输出格式（纯JSON） =====
{
  "customer_grade": "A/B/C/D",
  "grade_reason": "简要评分理由",
  "estimated_type": "客户类型（如：连锁品牌/贸易商/工程公司/个体门店等）",
  "greeting_en": "英文招呼消息",
  "greeting_cn": "中文翻译",
  "country_detected": "推测的国家"
}
"""


def get_ai_greeting(customer_name="", country="", sales_name="Philip"):
    """AI首条招呼：分析客户 + 生成首条消息"""
    knowledge_base = load_knowledge_base()
    text = f"客户名字: {customer_name}\n国家: {country}"
    result = ask_ali(AI_GREETING_PROMPT, text, max_tokens=1500, timeout=60, system=knowledge_base if knowledge_base else None)
    if not result:
        return {"error": "AI无返回"}
    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n", 1)
            cleaned = lines[1] if len(lines) > 1 else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": result, "error": "JSON解析失败"}
    except Exception as e:
        return {"error": str(e)}


AI_FOLLOWUP_PROMPT = """你是博汇（Bohui GLOWFORGE）的外贸销售{sales_name}。

===== 当前任务 =====
你需要给客户「{customer_name}」生成一条跟进消息。
- 客户语言：{language}
- 跟进阶段：{followup_label}

===== 规则 =====
1. 参考知识库中的 "{followup_label}" 话术脚本生成跟进消息
2. 语气友好自然，不要pushy，像真人销售随手发的
3. 简短2-3句，不要写小作文
4. 必须包含中文翻译（用 --- 分隔英文和中文，遵守Rule 2）
5. 直接输出跟进消息，不要解释，不要JSON
6. 输出格式：英文消息 + "\\n\\n---\\n\\n" + 中文翻译

只输出消息文本，不要任何额外文字。"""


def get_ai_followup_message(customer_name="", language="English", followup_type="3day", sales_name="Philip"):
    """AI生成跟进话术：根据跟进类型从知识库中选择对应脚本，返回双语消息"""
    knowledge_base = load_knowledge_base()
    type_labels = {"3day": "3日跟进（温和提醒）", "7day": "7日跟进（案例分享）", "15day": "15日跟进（留门收尾）"}
    followup_label = type_labels.get(followup_type, "3日跟进（温和提醒）")
    prompt = AI_FOLLOWUP_PROMPT.replace("{sales_name}", sales_name)
    prompt = prompt.replace("{customer_name}", customer_name)
    prompt = prompt.replace("{language}", language)
    prompt = prompt.replace("{followup_label}", followup_label)
    result = ask_ali(prompt, f"客户: {customer_name}\n语言: {language}\n跟进类型: {followup_type}",
                     max_tokens=800, timeout=30,
                     system=knowledge_base if knowledge_base else None)
    if result:
        return result.strip()
    # fallback：AI失败时使用知识库中的默认话术
    fallbacks = {
        "3day": f"Hi {customer_name}! Just checking in — did you have a chance to look over the quote I sent? If anything's unclear or you'd like adjustments (different material, size, color), I'm happy to help. No pressure at all. 😊\n\n---\n\n{customer_name}您好！跟进一下——您有机会看我发给您的报价了吗？如果有不清楚的地方，或者想调整（不同材质、尺寸、颜色），我很乐意协助。完全没有压力。😊",
        "7day": f"Hi {customer_name}! Hope you're doing well. I wanted to share some project photos we recently completed — similar to what we discussed. Thought it might give you some inspiration! 📸\n\nIf you're still comparing options, I want you to know: we can adjust the design within 3 revisions free of charge, and payment is only 50% deposit to start. Whenever you're ready, just let me know! 😊\n\n---\n\n{customer_name}您好！希望您一切顺利。我想分享一些我们最近完成的项目照片——跟我们讨论的类似。也许能给您一些灵感！📸\n\n如果您还在比较选择，我想让您知道：我们可以在3次修改内免费调整设计，只需50%定金启动。准备好了随时告诉我！😊",
        "15day": f"Hi {customer_name}! Just a friendly hello — no sales pitch this time. 😊 I know you're busy and these decisions take time. If the timing isn't right now, that's totally fine. Just so you know, our standard lead time is around 7-15 working days from deposit, and the price is valid for 15 days from the original quote. Feel free to reach out whenever — the door is always open! Have a great week! 🙌\n\n---\n\n{customer_name}您好！只是友好打个招呼——这次不推销。😊 我知道您很忙，做决定需要时间。如果现在时机不合适，完全没问题。只是想告知您，我们的标准交期在收到定金后7-15个工作日，报价从发出日起15天内有效。随时欢迎联系——大门永远敞开！祝您一周愉快！🙌"
    }
    return fallbacks.get(followup_type, fallbacks["3day"])


CHAT_SUMMARY_PROMPT = """你是一个B2B销售助理。下面是客户与博汇（Bohui GLOWFORGE工厂）销售Philip的全部聊天记录。

请用中文给Philip做一个简报，包含：
1. 客户概况 — 身份、需求类型、意向产品
2. 聊了什么 — 主要话题和关键信息
3. 报价情况 — 如果有报价，具体报了什么
4. 待办事项 — 客户在等什么、Philip下一步该做什么

直接回答，不要客套。格式：
📋 客户概况：...
💬 聊了什么：...
💰 报价情况：...
📌 待办事项：...

聊天记录："""


def summarize_chat(messages):
    """根据聊天记录生成客户简报"""
    if not messages:
        return "暂无聊天记录"
    text = "\n".join(
        f"{'【我】' if m['direction'] == 'sent' else '【客户】'}"
        f"{m.get('content_cn', '') or m.get('content_en', '')}"
        for m in messages[-20:]  # 最近20条
    )
    if not text.strip():
        return "暂无聊天记录"
    result = ask_ali(CHAT_SUMMARY_PROMPT, text, max_tokens=1000, timeout=45)
    return result or "生成简报失败"


# ==================== 爆款分析 ====================

VIRAL_ANALYSIS_PROMPT = """你是一个专业的社交媒体爆款内容分析师，专注于TikTok、YouTube和短视频平台。

公司背景：Bohui（博汇），中国GLOWFORGE工厂，产品出口全球。
产品线：
- 招牌广告发光字/炫彩发光字 → illuminated signage, channel letters, GLOWFORGE chromatic LED signs
- 亚克力工艺制品 → acrylic fabrication, acrylic display, acrylic signage
- 亚克力家具 → acrylic furniture
- AI宣传片 → promotional video

请分析以下爆款文案/视频描述的爆款原因，严格按照以下JSON格式回复（直接输出纯JSON，不要markdown代码块）：
{
  "viral_score": "爆款评分 1-10",
  "hook_analysis": "开头钩子分析，一句话说明钩子类型和效果",
  "structure": "内容结构分析（开头-中间-结尾）",
  "emotional_triggers": ["情感触发点1", "情感触发点2"],
  "target_audience": "目标受众分析",
  "engagement_tactics": ["互动策略1", "互动策略2"],
  "key_takeaway": "这个内容爆款的核心原因总结，一句话",
  "applicable_to_sign_industry": "如果用于发光字/亚克力行业，哪些手法可以借鉴",
  "applicable_score": "可借鉴程度 1-10"
}

待分析的爆款内容："""

COPY_REWRITE_PROMPT = """你是一个B2B营销文案专家。下面是一段爆款内容分析结果，请根据分析结果，为{Bohui行业产品}行业创作一段新的爆款仿写文案。

行业背景：Bohui（博汇），中国GLOWFORGE工厂，产品出口全球。
产品线：
- 招牌广告发光字/炫彩发光字
- 亚克力工艺制品
- 亚克力家具
- AI宣传片

爆款分析原文：
{analysis_text}

仿写要求：
- 保留原始爆款内容的核心结构和情感触发模式
- 内容要贴合发光字/亚克力/广告标识行业
- 语言通俗有感染力，适合短视频/TikTok风格
- 60秒以内可读完
- 适合用于TikTok/YouTube Shorts/Reels

请直接输出仿写好的文案，不要解释，不要加额外说明。仿写文案："""


def analyze_viral(text):
    """分析爆款内容，返回分析结果字典"""
    try:
        result = ask_ali(VIRAL_ANALYSIS_PROMPT, text, max_tokens=2000, timeout=60)
        if not result:
            return {"error": "AI无返回"}
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n", 1)
            cleaned = lines[1] if len(lines) > 1 else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": result, "error": "JSON解析失败"}
    except Exception as e:
        return {"error": str(e)}


def rewrite_copy(analysis_text, industry="发光字/亚克力"):
    """根据爆款分析结果，仿写行业文案"""
    prompt = COPY_REWRITE_PROMPT.replace("{Bohui行业产品}", industry).replace("{analysis_text}", analysis_text)
    result = ask_ali(prompt, "", max_tokens=1500, timeout=60)
    return result or "生成失败"


# ==================== 话术生成 ====================

SCRIPT_GENERATION_PROMPT = """你是一个B2B销售文案专家，专精于广告标识和亚克力制品行业。

公司背景：Bohui（博汇），中国GLOWFORGE工厂，产品出口全球。
产品线：
- 招牌广告发光字/炫彩发光字 → illuminated signage, channel letters, GLOWFORGE chromatic LED signs
- 亚克力工艺制品 → acrylic fabrication, acrylic display, acrylic signage
- 亚克力家具 → acrylic furniture
- AI宣传片 → promotional video

下面是客户沟通场景的脚本模板和客户国家背景，请根据这些生成一段个性化的回复文案。
要求：
- 保留模板的核心结构和销售逻辑
- 根据国家背景调整语气和策略
- 结合客户最近消息上下文（如有）
- 输出中英文双语版本

脚本模板：
{script_template}

{country_context}

客户最近消息：
{customer_context}

请按以下JSON格式输出（直接输出纯JSON，不要markdown代码块）：
{{
  "reply_cn": "中文回复",
  "reply_en": "英文回复",
  "strategy_note": "策略说明（为什么这样回复）"
}}
"""


def generate_customized_script(scenario, country="", customer_context=""):
    """根据话术模板+国家上下文+客户上下文，AI生成个性化回复"""
    # 加载话术模板
    script_path = os.path.join(SCRIPTS_DIR, f"{scenario}.txt")
    if not os.path.exists(script_path):
        return {"error": f"未找到话术模板: {scenario}"}
    with open(script_path, "r", encoding="utf-8") as f:
        script_template = f.read()
    # 加载国家上下文
    country_ctx = get_country_context(country)
    country_text = ""
    if country_ctx:
        country_text = f"客户国家背景（请据此调整语气和策略）：\n{country_ctx}"
    # 组装prompt
    prompt = SCRIPT_GENERATION_PROMPT.replace("{script_template}", script_template)
    prompt = prompt.replace("{country_context}", country_text)
    prompt = prompt.replace("{customer_context}", customer_context or "无最近消息，按模板默认生成")
    result = ask_ali(prompt, "", max_tokens=2000, timeout=60)
    if not result:
        return {"error": "AI无返回"}
    # 解析JSON
    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": result, "reply_cn": result, "reply_en": result}


# ==================== 知识库AI搜索 ====================

KNOWLEDGE_SEARCH_PROMPT = """你是一个行业知识助手，专门帮助Bohui（博汇）GLOWFORGE工厂的销售Philip回答产品和技术问题。

以下是GLOWFORGE工厂的产品和行业知识库内容：

{knowledge_base}

请根据以上知识库回答客户的问题。如果知识库中能找到相关信息，请直接引用。
如果知识库中没有相关信息，请根据你自己的知识回答，并注明"注：此信息不在现有知识库中"。

回答要求：
- 用客户提问的语言回答（客户用英文问就用英文答，用中文问就用中文答）
- 简洁实用，适合B2B销售场景
- 给出具体参数和数据
- 如涉及产品推荐，给出具体建议

客户问题：{query}

请直接输出回答内容，不要加额外的说明或格式标记。"""


def search_industry_knowledge(query):
    """搜索行业知识库，AI回答问题（智能选文件，最多加载8个）"""
    if not os.path.exists(KNOWLEDGE_DIR):
        return "知识库为空，请先添加行业知识文件。"

    all_files = sorted(f for f in os.listdir(KNOWLEDGE_DIR) if f.endswith(".txt"))
    query_lower = query.lower()

    # 1. core_ 和 prod_ 文件始终入选
    selected = set()
    for f in all_files:
        if f in _CORE_FILES or f.startswith("prod_"):
            selected.add(f)

    # 2. 文件名关键词匹配选出最相关的
    scored = []
    query_words = set(query_lower.replace("_", " ").replace("-", " ").split())
    for f in all_files:
        if f in selected:
            continue
        f_words = set(f.lower().replace("_", " ").replace("-", " ").replace(".txt", "").split())
        overlap = len(query_words & f_words)
        if overlap > 0:
            scored.append((overlap, f))

    scored.sort(key=lambda x: -x[0])
    for _, f in scored[:6]:  # 最多再选6个 = 总共8个左右
        selected.add(f)

    # 3. 加载
    parts = []
    for f in sorted(selected):
        path = os.path.join(KNOWLEDGE_DIR, f)
        try:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            title = content.strip().split("\n")[0] if content.strip() else f
            parts.append(f"=== 【{title}】 ===\n{content}")
        except Exception:
            continue

    knowledge_base = "\n\n".join(parts)
    if not knowledge_base:
        return "知识库为空，请先添加行业知识文件。"
    prompt = KNOWLEDGE_SEARCH_PROMPT.replace("{knowledge_base}", knowledge_base)
    prompt = prompt.replace("{query}", query)
    result = ask_ali(prompt, "", max_tokens=1500, timeout=60)
    return result or "查询失败，请稍后重试"


def generate_image(prompt, image_data=None):
    """通义万相生图，支持文生图和图生图。返回 (url, error)
    Args:
        prompt: 文字描述
        image_data: 可选，参考图base64（图生图模式，data:image/...）
    """
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
    content = [{"text": prompt}]
    if image_data:
        content.append({"image": image_data})
    payload = {
        "model": IMAGE_MODEL,
        "input": {
            "messages": [{"role": "user", "content": content}]
        },
        "parameters": {"n": 1, "size": "1024*1024"}
    }
    headers = {
        "Authorization": f"Bearer {ALI_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable"
    }

    r = requests.post(url, headers=headers, json=payload, timeout=20)
    if r.status_code != 200:
        return None, f"提交失败: {r.text[:200]}"

    task_id = r.json().get("output", {}).get("task_id", "")
    if not task_id:
        return None, "获取task_id失败"

    status_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    for _ in range(30):
        time.sleep(3)
        r2 = requests.get(status_url, headers={"Authorization": f"Bearer {ALI_KEY}"}, timeout=15)
        data = r2.json()
        status = data.get("output", {}).get("task_status", "")
        if status == "SUCCEEDED":
            choices = data.get("output", {}).get("choices", [])
            if choices:
                for item in choices[0].get("message", {}).get("content", []):
                    if "image" in item:
                        return item["image"], None
            return None, "结果为空"
        elif status == "FAILED":
            return None, data.get("output", {}).get("message", "生成失败")
    return None, "生成超时"


# ==================== 视频生成（通义万相 wan2.6-t2v） ====================
# 支持最长15秒、多镜头叙事、带背景音乐

VIDEO_PRESETS = {
    "story_light": {
        "name": "🌙 故事型：光的力量",
        "prompt": """A cinematic short film about a newcomer immigrant girl in a foreign city. She walks alone on a cold night street, looking lost and sad. She looks up and sees a warm glowing LED sign reading "WARM & COZY" on a small restaurant. The warm light illuminates her face as she enters. Inside, a kind middle-aged female owner greets her with a genuine smile, serving her a hot bowl of soup. The girl eats and tears of warmth fill her eyes. She leaves with a grateful smile, the restaurant sign glowing behind her. The next morning, she looks in the mirror with a confident smile, ready for a new day.

Cinematic lighting, warm color palette, shallow depth of field, emotional storytelling, 4K quality, heartwarming atmosphere.""",
        "duration": 15,
        "shot_type": "multi",
        "size": "1280*720"
    },
    "sign_showcase": {
        "name": "✨ 产品展示：发光字特效",
        "prompt": """A premium product showcase video of a custom illuminated LED sign. The camera glides smoothly around the sign showing it from multiple angles. The sign reads "GLOWFORGE" in elegant channel letters with chromatic LED lighting that smoothly shifts colors from warm white to cool blue to gold. The sign is mounted on a brushed stainless steel backing. Close-up details show the precise craftsmanship, the seamless LED diffusion, and the premium acrylic face. The sign illuminates a dark storefront, creating a luxurious atmosphere.

Product cinematography style, smooth dolly movements, dramatic lighting, high contrast, 4K ultra-realistic, commercial quality.""",
        "duration": 10,
        "shot_type": "multi",
        "size": "1280*720"
    },
    "storefront": {
        "name": "🏪 门头招牌：夜间实景",
        "prompt": """A nighttime storefront scene of a modern retail shop. The store has a premium illuminated channel letter sign with the brand name glowing in warm white light. The facade features elegant acrylic signage and subtle LED strip lighting along the architecture. A customer walks by and pauses to admire the sign. The warm glow from the招牌 creates an inviting atmosphere on the street. Rain on the ground reflects the glowing lights beautifully. Street lamps and passing car lights in the background.

Realistic urban night scene, cinematic 24fps look, warm amber and cool blue color contrast, depth of field, reflective wet ground, high production value.""",
        "duration": 15,
        "shot_type": "multi",
        "size": "1280*720"
    },
    "product_promo": {
        "name": "🎬 产品宣传：亚克力展示",
        "prompt": """A professional product showcase video for premium acrylic furniture and displays. Slow elegant camera movement around a modern acrylic display case with integrated LED lighting. The transparent acrylic material catches and refracts light beautifully. Products inside the display case are illuminated perfectly. Cut to a modern acrylic desk setup in a minimalist office environment. Close-up details show the flawless clear edges of the acrylic, the precision polishing, and the sturdy construction.

Commercial cinematography, product photography lighting, clean white background, smooth gimbal movements, 4K sharp, minimal and elegant aesthetic.""",
        "duration": 10,
        "shot_type": "multi",
        "size": "1280*720"
    },
    "custom": {
        "name": "✏️ 自定义脚本",
        "prompt": "",
        "duration": 15,
        "shot_type": "multi",
        "size": "1280*720"
    }
}


def generate_video(prompt, size="1280*720", duration=15, shot_type="multi"):
    """通义万相 wan2.6-t2v 文生视频，返回 (video_url, error)
    Args:
        prompt: 视频描述（英文效果更好）
        size: 分辨率 1280*720 / 720*1280 / 960*960
        duration: 视频时长 5-15秒
        shot_type: "multi"(多镜头叙事) / "default"(单镜头)
    """
    payload = {
        "model": VIDEO_MODEL,
        "input": {"prompt": prompt},
        "parameters": {
            "size": size,
            "duration": duration,
            "shot_type": shot_type,
            "prompt_extend": True
        }
    }
    headers = {
        "Authorization": f"Bearer {ALI_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable"
    }

    # 提交任务
    try:
        r = requests.post(VIDEO_ENDPOINT, headers=headers, json=payload, timeout=30)
        if r.status_code != 200:
            return None, f"提交失败: {r.text[:300]}"
        task_id = r.json().get("output", {}).get("task_id", "")
        if not task_id:
            return None, "获取task_id失败"
    except Exception as e:
        return None, f"提交请求异常: {e}"

    print(f"[Video] 任务已提交: {task_id}，等待生成中...")
    # 视频生成通常1-5分钟，轮询间隔长一些
    status_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    for i in range(60):
        time.sleep(10)
        try:
            r2 = requests.get(status_url, headers={"Authorization": f"Bearer {ALI_KEY}"}, timeout=15)
            data = r2.json()
            status = data.get("output", {}).get("task_status", "")
            if status == "SUCCEEDED":
                output = data.get("output", {})
                video_url = output.get("video_url", "")
                if video_url:
                    return video_url, None
                return None, "视频URL为空"
            elif status == "FAILED":
                msg = data.get("output", {}).get("message", "生成失败")
                return None, f"生成失败: {msg}"
            elif i % 6 == 0:
                print(f"[Video] 生成中... ({i*10}s)")
        except Exception as e:
            print(f"[Video] 轮询异常: {e}")

    return None, "生成超时（已等待10分钟）"


# ==================== 火山引擎 seedance 图生视频 ====================

def generate_video_from_image(image_path, prompt="", duration=5):
    """火山引擎 seedance-1.5-pro 图生视频，返回 (video_url, error)
    Args:
        image_path: 图片本地路径或URL
        prompt:  视频动作描述（英文效果更好），可包含 --duration --camerafixed --watermark 参数
        duration: 视频时长（1-5秒）
    Returns:
        (video_url, error)
    """
    # 构建内容
    content = []

    # 处理图片：本地文件转base64，URL直接使用
    image_url = None
    if image_path.startswith("http://") or image_path.startswith("https://"):
        image_url = image_path
    elif image_path.startswith("data:"):
        image_url = image_path
    else:
        # 本地文件 → base64
        try:
            import base64
            with open(image_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            ext = os.path.splitext(image_path)[1].lower()
            mime = "image/png"
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".webp":
                mime = "image/webp"
            elif ext == ".gif":
                mime = "image/gif"
            image_url = f"data:{mime};base64,{img_data}"
        except Exception as e:
            return None, f"图片读取失败: {e}"

    # 组装prompt文本（含参数）
    text = prompt if prompt else "dynamic product showcase"
    # 追加参数
    text += f" --duration {duration}"
    text += " --camerafixed false"
    text += " --watermark true"

    content.append({"type": "text", "text": text})
    content.append({"type": "image_url", "image_url": {"url": image_url}})

    payload = {
        "model": VOLC_VID_MODEL,
        "content": content
    }

    headers = {
        "Authorization": f"Bearer {VOLC_VID_KEY}",
        "Content-Type": "application/json"
    }

    # 提交任务
    task_url = f"{VOLC_BASE}/contents/generations/tasks"
    try:
        r = requests.post(task_url, headers=headers, json=payload, timeout=30)
        if r.status_code != 200:
            return None, f"提交失败: {r.text[:300]}"
        task_id = r.json().get("id", "")
        if not task_id:
            return None, "获取task_id失败"
    except Exception as e:
        return None, f"提交异常: {e}"

    print(f"[Seedance] 图生视频任务已提交: {task_id}")
    status_url = f"{task_url}/{task_id}"

    # 轮询结果（seedance通常30秒-2分钟）
    for i in range(60):
        time.sleep(5)
        try:
            r2 = requests.get(status_url, headers={"Authorization": f"Bearer {VOLC_VID_KEY}"}, timeout=15)
            data = r2.json()
            status = data.get("status", "")
            if status == "succeeded":
                content = data.get("content", {})
                video_url = content.get("video_url", "")
                if video_url:
                    return video_url, None
                return None, "视频URL为空"
            elif status == "failed":
                error_msg = data.get("error", {}).get("message", str(data.get("error", "生成失败")))
                return None, f"生成失败: {error_msg}"
            elif i % 6 == 0:
                print(f"[Seedance] 生成中... ({i*5}s)")
        except Exception as e:
            print(f"[Seedance] 轮询异常: {e}")

    return None, "生成超时（已等待5分钟）"


def generate_image_volc(prompt, size="2K"):
    """火山引擎 seedream-4.5 文生图，作为阿里通义万相的备选，返回 (url, error)"""
    size_map = {
        "1024*1024": "2048x2048",  # seedream最小约3.7MP，自动提升
        "1024*768": "2048x1536",
        "2K": "2048x2048",
    }
    api_size = size_map.get(size, "2048x2048")

    payload = {
        "model": VOLC_IMG_MODEL,
        "prompt": prompt,
        "size": api_size,
        "stream": False,
        "watermark": True,
        "response_format": "url"
    }
    headers = {
        "Authorization": f"Bearer {VOLC_IMG_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(f"{VOLC_BASE}/images/generations", headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            return None, f"提交失败: {r.text[:200]}"
        data = r.json()
        results = data.get("data", [])
        if results:
            return results[0].get("url", ""), None
        return None, "结果为空"
    except Exception as e:
        return None, f"请求异常: {e}"


CHAT_HISTORY_ANALYSIS_PROMPT = """你是一个B2B销售分析师。下面是从WhatsApp导出的客户与博汇（Bohui GLOWFORGE工厂）的全部聊天记录。

请用中文分析后严格按以下JSON格式输出（不要markdown代码块，纯JSON）：
{
  "customer_profile": {
    "name": "客户姓名",
    "company_type": "客户身份/公司类型",
    "country_or_region": "国家或地区",
    "interest_products": ["感兴趣的产品列表"],
    "language": "沟通语言(English/中文等)"
  },
  "chat_summary": "聊天内容摘要，50-100字概括",
  "key_needs": ["关键需求点列表"],
  "price_quoted": {
    "has_quote": true/false,
    "quote_details": "如果有报价，具体内容"
  },
  "price_sensitivity": "高/中/低/未提及",
  "decision_stage": "初次询价/比价中/意向明确/已成交/售后",
  "special_requirements": ["特殊要求列表"],
  "next_steps": "Philip下一步该做什么，50字以内",
  "tags": ["自动打标签，如: 询价、比价、要样品、要目录、下单"]
}

聊天记录："""


def analyze_chat_history(raw_text):
    """分析WhatsApp导出的完整聊天记录，返回结构化JSON"""
    # 清理文件头
    if not raw_text or not raw_text.strip():
        return {"error": "聊天记录为空"}
    # 去掉系统提示行（加密声明等）
    lines = raw_text.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "end-to-end encrypted" in line.lower() or "端到端加密" in line:
            continue
        if "skip restoring" in line.lower():
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    if len(text) < 20:
        return {"error": "有效内容太少，请确认导出的是完整聊天记录"}
    # 截断防超token（保留最近500行）
    text_lines = text.split("\n")
    if len(text_lines) > 500:
        text_lines = text_lines[-500:]
        text = "\n...（前面省略）...\n" + "\n".join(text_lines)
    result = ask_ali(CHAT_HISTORY_ANALYSIS_PROMPT, text, max_tokens=3000, timeout=90)
    if not result:
        return {"error": "AI分析无返回"}
    cleaned_result = result.strip()
    # 去掉可能的markdown代码块
    if cleaned_result.startswith("```"):
        lines = cleaned_result.split("\n", 1)
        cleaned_result = lines[1] if len(lines) > 1 else cleaned_result[3:]
        if cleaned_result.endswith("```"):
            cleaned_result = cleaned_result[:-3]
        cleaned_result = cleaned_result.strip()
    if cleaned_result.startswith("```"):
        cleaned_result = cleaned_result[3:].strip()
        if cleaned_result.endswith("```"):
            cleaned_result = cleaned_result[:-3]
        cleaned_result = cleaned_result.strip()
    try:
        data = json.loads(cleaned_result)
        return data
    except json.JSONDecodeError:
        return {"raw": cleaned_result, "error": "AI返回格式异常，请重试"}


def parse_whatsapp_export(text):
    """解析WhatsApp导出的.txt聊天记录，返回消息列表"""
    lines = text.strip().split("\n")
    messages = []
    # 常见格式: "6/11/26, 5:30 PM - Philip: Hello"
    # 或者: "[6/11/26, 5:30:45 PM] Philip: Hello"
    pattern1 = r'^(\d{1,2}[/\.]\d{1,2}[/\.]\d{2,4},\s*\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm])\s*-\s*(.+?):\s*(.*)'
    pattern2 = r'^\[(\d{1,2}[/\.]\d{1,2}[/\.]\d{2,4},\s*\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm])\]\s*(.+?):\s*(.*)'
    # 24小时制格式: "2026/6/11, 17:30 - Philip: Hello"
    pattern3 = r'^(\d{4}[/\.]\d{1,2}[/\.]\d{1,2},\s*\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(.+?):\s*(.*)'

    current_msg = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳过系统消息
        if "end-to-end encrypted" in line.lower() or "端到端加密" in line:
            continue
        if "skip restoring" in line.lower():
            continue
        if "Messages and calls are" in line:
            continue

        matched = False
        for pat in (pattern3, pattern1, pattern2):
            m = re.match(pat, line)
            if m:
                time_str, sender, content = m.groups()
                if current_msg:
                    messages.append(current_msg)
                current_msg = {
                    "time": time_str.strip(),
                    "sender": sender.strip(),
                    "content": content.strip()
                }
                matched = True
                break
        if not matched and current_msg:
            # 多行消息的延续行
            current_msg["content"] += "\n" + line

    if current_msg:
        messages.append(current_msg)
    return messages
