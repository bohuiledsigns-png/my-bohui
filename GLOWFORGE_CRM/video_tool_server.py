"""Video Tool Server — AI 视频生成桌面工具后端

在浏览器打开即可使用：http://localhost:5678
"""

import os, sys, json, uuid, threading, time, base64, subprocess, datetime, hashlib
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory

# 确保能找到 ai_engine 等模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_engine import generate_video, BASE_DIR, ask_ali
from video_postprocessor import compose_video

app = Flask(__name__)

TEMP_DIR = os.path.join(BASE_DIR, "temp_jimeng")
os.makedirs(TEMP_DIR, exist_ok=True)

# ── 10 款产品模板 ──────────────────────────────────
TEMPLATES = [
    {
        "id": 1, "name": "钛金不锈钢背发光字",
        "en_name": "Titanium Brushed Backlit Sign",
        "scene": "巴黎傍晚街边美容院",
        "prompt": ("15 seconds cinematic commercial short video,8K ultra realistic,"
                   "8 shots smooth transition,evening street beauty salon scene,"
                   "female owner disappointed staring at old dim oxidized sign,"
                   "close-up rusted aged letter details,"
                   "craft shot polishing stainless steel brushed texture,"
                   "night scene backlit letters slowly light up with floating soft halo,"
                   "quiet luxury atmosphere,gentle slow dolly shot,"
                   "warm natural color grading,soft shadow layering,"
                   "emotional storytelling commercial style"),
        "voiceover": ("Dull old signs slowly lower your shop grade. "
                      "Ordinary metal signs oxidize easily outdoors. "
                      "Our brushed titanium backlit sign is fully sealed, "
                      "soft halo glow upgrades store taste totally."),
        "hook_text": "Brushed Titanium Sign — Upgrade Your Storefront",
        "bgm": "classic",
    },
    {
        "id": 2, "name": "户外防水发光字",
        "en_name": "Waterproof Outdoor LED Letters",
        "scene": "伦敦商业街雨天",
        "prompt": ("15 seconds story-style commercial video,8K real scene footage,"
                   "8 lens fast smooth transition,rainy commercial street scene,"
                   "old sign leaking water with flickering lights,"
                   "close-up water ingress inside letter,"
                   "sealed rubber edge structure detail,"
                   "water spray test showing stable internal lighting,"
                   "four seasons montage day night all weather steady glowing,"
                   "cinematic color grading,natural lighting,stable handheld documentary style"),
        "voiceover": ("Unsealed signs break fast under rain and sunshine. "
                      "Water and ultraviolet rays damage internal lights easily. "
                      "Our fully sealed LED letters are waterproof anti-UV, "
                      "run stably outdoors all year."),
        "hook_text": "All-Weather LED Sign — Zero Maintenance",
        "bgm": "ambient",
    },
    {
        "id": 3, "name": "LUMIÈRE FASHION 巴黎轻奢",
        "en_name": "Paris Boutique Fashion Sign",
        "scene": "巴黎黄昏蓝调轻奢女装店",
        "prompt": ("15s cinematic story commercial video,8K ultra real photography,"
                   "Paris street dusk blue hour scene,"
                   "European elegant lady female driver,"
                   "natural real human skin texture,"
                   "light luxury coupe driving and parking slowly,"
                   "lady look out car window,eyes attracted by store sign,"
                   "get off car walk with high heels,"
                   'top door hang "LUMIÈRE FASHION" brushed titanium backlit letters,'
                   "soft floating halo backlight,delicate metal wire drawing texture,"
                   "night warm light atmosphere,"
                   "French minimalist luxury style,Cinematic color grading"),
        "voiceover": ("A nice store sign always catches elegant eyes. "
                      "Soft halo backlit letters show your brand taste. "
                      "Premium luminous signage makes shops more attractive."),
        "hook_text": "LUMIÈRE FASHION — Paris Elegance",
        "bgm": "classic",
    },
    {
        "id": 4, "name": "亚克力通体发光字",
        "en_name": "Acrylic Through-Body Luminous Letters",
        "scene": "东京潮流街区 ins 风咖啡店",
        "prompt": ("15 seconds lifestyle commercial video,8K ultra real,"
                   "Tokyo street daytime,young woman walking past shops holding coffee,"
                   "drawn to colorful glowing sign,"
                   "plain white cafe facade cut to through-body acrylic luminous letters,"
                   "close-up light passing through entire letter cross-section crystal clear,"
                   "bright daylight sign still vivid colorful,"
                   "woman taking selfie in front of glowing sign,"
                   "cinematic color grading,warm vibrant tones,"
                   "real street photography,weathered wall texture"),
        "voiceover": ("A dull storefront never stops a passerby. "
                      "Ordinary signs fade into the street background. "
                      "Our acrylic luminous letters glow evenly day and night, "
                      "make your store the street highlight."),
        "hook_text": "Vibrant Acrylic Sign — Be the Highlight",
        "bgm": "trendy",
    },
    {
        "id": 5, "name": "迷你精细小字",
        "en_name": "Mini Delicate LED Letters",
        "scene": "巴黎小巷美甲工作室",
        "prompt": ("15 seconds commercial short video,8K ultra real,"
                   "nail studio narrow storefront scene,"
                   "female owner standing at small door unable to fit big sign,"
                   "oversized bulky sign looking mismatched,"
                   "close-up precision laser cutting 2-3cm mini LED letters,"
                   "installed mini delicate letter perfectly fitting narrow storefront,"
                   "night scene mini letters glowing clearly visible refined,"
                   "elegant boutique atmosphere,soft natural lighting"),
        "voiceover": ("Small shops don't need oversized signs. "
                      "Big bulky letters ruin your boutique store look. "
                      "Our mini delicate LED letters fit perfectly, "
                      "precision craft brings refined elegance to small storefronts."),
        "hook_text": "Mini LED Letters — Perfect for Small Shops",
        "bgm": "classic",
    },
    {
        "id": 6, "name": "夜市高亮发光字",
        "en_name": "High-Brightness Night Market Sign",
        "scene": "纽约夜市街",
        "prompt": ("15 seconds vibrant commercial video,8K ultra real,"
                   "busy night market street scene,"
                   "many mixed signs some dim and invisible,"
                   "shop with dim sign customers ignoring,"
                   "replaced by super bright high-luminous LED letters,"
                   "far distance shot clearly readable bright sign,"
                   "pedestrians attracted stop look up enter shop,"
                   "cinematic night color grading,warm neon lights,"
                   "real street photography,actual busy street"),
        "voiceover": ("In a busy night market brightness decides everything. "
                      "Dim signs blend in, customers just walk past. "
                      "Our super high-luminous LED letters shine bright from far away, "
                      "pull customers directly to your door."),
        "hook_text": "Super Bright Sign — Pull Customers From Far",
        "bgm": "trendy",
    },
    {
        "id": 7, "name": "彩色电镀发光字",
        "en_name": "Color Electroplated LED Sign",
        "scene": "纽约潮流夜店街",
        "prompt": ("15 seconds trendy commercial video,8K ultra real,"
                   "night bar street scene,"
                   "many ordinary identical signs no differentiation,"
                   "bar with boring light box youngsters walking past,"
                   "color electroplated surface rainbow metallic gradient craft close-up,"
                   "replaced with color electroplated LED sign rainbow glow effect,"
                   "passersby stop take photos attracted by unique sign,"
                   "cinematic night color grading,neon lighting,vibrant colors"),
        "voiceover": ("Same old signs make your bar invisible. "
                      "Boring storefronts lose the night crowd. "
                      "Our color electroplated LED signs shine with rainbow metallic glow, "
                      "make your bar the block highlight."),
        "hook_text": "Rainbow Metallic Sign — Stand Out at Night",
        "bgm": "trendy",
    },
    {
        "id": 8, "name": "炫彩发光字",
        "en_name": "Iridescent Color-Shifting Sign",
        "scene": "东京夜店街区",
        "prompt": ("15 seconds vibrant commercial video,8K ultra real,"
                   "night entertainment district scene,"
                   "bars game centers with ordinary static signs lack visual highlight,"
                   "plain single-color signs ignored in neon street,"
                   "close-up iridescent color-shifting sign surface rainbow gradient,"
                   "colors changing with viewing angle,"
                   "passersby attracted by unique iridescent glow stop take photos,"
                   "cinematic night color grading,vibrant neon lighting"),
        "voiceover": ("Boring static signs get zero attention at night. "
                      "Every entertainment spot looks the same. "
                      "Our iridescent color-shifting LED sign grabs eyes from every angle, "
                      "makes your venue the block standout."),
        "hook_text": "Iridescent Sign — Shift Colors, Grab Eyes",
        "bgm": "trendy",
    },
    {
        "id": 9, "name": "幻彩RGB发光字",
        "en_name": "RGB Programmable LED Sign",
        "scene": "东京赛博街区电竞网咖",
        "prompt": ("15 seconds cyberpunk commercial video,8K ultra real,"
                   "esports game center night exterior scene,"
                   "ordinary static sign zero tech vibe,"
                   "close-up RGB LED sign built-in programmable chip,"
                   "dynamic color effects demo: rainbow breathing color cycling,"
                   "esports purple ambient atmosphere multiple modes switching,"
                   "young gamers attracted by dynamic RGB sign,"
                   "cinematic cyberpunk color grading,neon blue purple lighting"),
        "voiceover": ("Static signs kill your gaming venue vibe. "
                      "Gamers want tech energy, not boring storefronts. "
                      "Our programmable RGB LED sign runs dynamic color effects, "
                      "matches your esports atmosphere perfectly."),
        "hook_text": "RGB Dynamic Sign — Level Up Your Venue",
        "bgm": "trendy",
    },
    {
        "id": 10, "name": "智能调光发光字",
        "en_name": "Smart Dimming Sensor Sign",
        "scene": "纽约科技感街区连锁门店",
        "prompt": ("15 seconds tech commercial video,8K ultra real,"
                   "chain store facade bright sunny day,"
                   "ordinary sign invisible under strong sunlight,"
                   "close-up smart light sensor detail tiny integrated inside letter,"
                   "hand covering sensor sign auto brightens,"
                   "time lapse day bright clear visible to evening soft warm,"
                   "chain stores uniform equipped smart dimming signs,"
                   "Cinematic color grading,clean modern aesthetic"),
        "voiceover": ("Fixed brightness signs fail under changing light. "
                      "Too dim at noon, too harsh at night. "
                      "Our smart sensor LED sign auto-adjusts brightness day and night, "
                      "keeps your brand visible 24/7 with zero effort."),
        "hook_text": "Smart Dimming Sign — Visible 24/7 Auto",
        "bgm": "ambient",
    },
]

BGM_MAP = {
    "classic": "D:/Bohui_Global_Push/background_music2.mp3",
    "ambient": "D:/Bohui_Global_Push/ambient_bg.mp3",
    "trendy": "D:/Bohui_Global_Push/background_music.mp3",
}

# ── 自定义模板存储 ──────────────────────────────────
CUSTOM_TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_templates.json")

def _load_custom_templates():
    if not os.path.exists(CUSTOM_TEMPLATES_FILE):
        return []
    try:
        with open(CUSTOM_TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_custom_templates(templates):
    with open(CUSTOM_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

# ── 知识库 ─────────────────────────────────────────
KNOWLEDGE_BASE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base.json")
FEEDBACK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback_log.json")
GENERATION_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generation_log.json")

def _load_knowledge_base():
    if not os.path.exists(KNOWLEDGE_BASE_FILE):
        return []
    try:
        with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _find_relevant_knowledge(product_name, scene_hint="") -> str:
    """从知识库查找与产品名/场景最相关的知识文案（含策略条目）"""
    kb = _load_knowledge_base()
    if not kb:
        return ""
    product_lower = product_name.lower()
    scene_lower = scene_hint.lower()

    # 始终包含的策略类条目ID
    ALWAYS_INCLUDE = {"kb_competitor_accounts", "kb_content_strategy",
                      "kb_script_templates", "kb_style_reference_30",
                      "kb_ai_brain_decision_logic", "kb_ai_brain_multi_role_voice",
                      "kb_ai_brain_platform_learning", "kb_ai_brain_workflow",
                      "kb_ai_voice_roles", "kb_ai_voice_emotion_params",
                      "kb_ai_multi_language_scripts", "kb_ai_voice_industry_terms",
                      "kb_camera_narrative_theory", "kb_camera_lighting_mood"}

    scored = []
    always_parts = []
    for entry in kb:
        eid = entry.get("id", "")
        if eid in ALWAYS_INCLUDE:
            # 策略类条目直接加入，不用打分
            parts = []
            if entry.get("selling_points"):
                parts.append("Selling points: " + "; ".join(entry["selling_points"]))
            if entry.get("features"):
                parts.append("Key insights: " + "; ".join(entry["features"]))
            if entry.get("technical_details"):
                parts.append("Details: " + entry["technical_details"])
            if parts:
                always_parts.append(f"[{entry.get('category', eid)}]\n" + "\n".join(parts))
            continue

        score = 0
        kw = [k.lower() for k in entry.get("keywords", [])]
        cat = entry.get("category", "").lower()
        en = entry.get("en_name", "").lower()
        for word in product_lower.split():
            if word in cat or word in en:
                score += 3
            for k in kw:
                if word in k or k in word:
                    score += 2
        for word in scene_lower.split():
            if word in cat or word in en:
                score += 2
        if any(k in product_lower for k in kw):
            score += 5
        if score > 0:
            scored.append((score, entry))

    # 取最高分产品知识
    result_parts = []
    if scored:
        scored.sort(key=lambda x: -x[0])
        best = scored[0][1]
        if best.get("selling_points"):
            result_parts.append("Selling points: " + "; ".join(best["selling_points"]))
        if best.get("features"):
            result_parts.append("Features: " + "; ".join(best["features"]))
        if best.get("technical_details"):
            result_parts.append("Technical: " + best["technical_details"])
        if best.get("process"):
            result_parts.append("Process: " + best["process"])

    # 策略条目附加在后面
    if always_parts:
        result_parts.append("\n--- Video Marketing Strategy ---\n" + "\n\n".join(always_parts))

    return "\n".join(result_parts) if result_parts else ""

# ── 反馈日志 ─────────────────────────────────────────
def _load_feedback():
    if not os.path.exists(FEEDBACK_FILE):
        return []
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_feedback(feedback):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)


# ── 生成日志（效果追踪）───────────────────────────
def _load_generation_log():
    if not os.path.exists(GENERATION_LOG_FILE):
        return []
    try:
        with open(GENERATION_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_generation_log(log):
    with open(GENERATION_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def _log_generation(task_id, data, status="running"):
    """记录一次视频生成到日志"""
    log = _load_generation_log()
    # 去重：同名 task_id 已存在则更新
    for i, entry in enumerate(log):
        if entry.get("task_id") == task_id:
            log[i]["status"] = status
            if status == "done":
                log[i]["completed_at"] = datetime.datetime.now().isoformat()
            _save_generation_log(log)
            return
    # 新记录
    entry = {
        "task_id": task_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": status,
        "product": data.get("auto_product", data.get("product", "")),
        "scene": data.get("auto_scene", data.get("scene", "")),
        "auto_mode": data.get("auto", False),
        "prompt": (data.get("prompt", "") or "")[:200],
        "voiceover": (data.get("voiceover", "") or "")[:200],
        "hook_text": (data.get("hook_text", "") or "")[:100],
        "quality": data.get("quality", "720p"),
        "duration": int(data.get("duration", 15)),
        "aspect_ratio": data.get("aspect_ratio", "9:16"),
        "bgm": data.get("bgm", ""),
        "voice": data.get("voice", "Cherry"),
        "import_mode": bool(data.get("video_path", "")),
    }
    log.append(entry)
    _save_generation_log(log)


def _auto_learn_from_feedback(entry):
    """用户好评 → 自动收录到知识库作为已验证模板"""
    prompt = entry.get("prompt", "")
    voiceover = entry.get("voiceover", "")
    hook = entry.get("hook", "")
    product = entry.get("product", "LED Sign")
    if not prompt:
        return

    kb = _load_knowledge_base()
    # 去重：同样的 prompt 已存在则跳过
    for existing in kb:
        if existing.get("category") == "已验证用户模板" and existing.get("materials") == prompt:
            return

    new_entry = {
        "id": f"kb_user_proven_{uuid.uuid4().hex[:8]}",
        "category": "已验证用户模板",
        "en_name": f"User-Approved: {product}",
        "keywords": product.lower().split()[:5] + ["user_proven", "verified_template"],
        "materials": prompt,
        "features": [f"Voiceover: {voiceover}"] if voiceover else [],
        "selling_points": [f"Hook: {hook}"] if hook else [],
        "technical_details": f"已验证的视频模板，product={product}，AI 可直接参考此 prompt 风格",
        "applications": [],
        "process": "",
        "lifespan": ""
    }
    kb.append(new_entry)
    with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    print(f"[AutoLearn] 已收录用户好评模板 → {new_entry['id']}")

# ── 脚本库 ─────────────────────────────────────────
SCRIPTS_LIBRARY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts_library.json")

def _load_scripts_library():
    if not os.path.exists(SCRIPTS_LIBRARY_FILE):
        return []
    try:
        with open(SCRIPTS_LIBRARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_scripts_library(scripts):
    with open(SCRIPTS_LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)

def _find_relevant_scripts(product_name, scene_hint=""):
    """从脚本库查找与产品/场景最相关的脚本，返回格式化字符串"""
    scripts = _load_scripts_library()
    if not scripts:
        return ""
    product_lower = product_name.lower()
    scene_lower = scene_hint.lower()

    scored = []
    for s in scripts:
        score = 0
        kw = [k.lower() for k in s.get("keywords", [])]
        tags = [t.lower() for t in s.get("style_tags", [])]
        title = s.get("title", "").lower()
        cat = s.get("category", "").lower()

        for word in product_lower.split():
            if word in title:
                score += 2
            for k in kw:
                if word in k or k in word:
                    score += 2
            for t in tags:
                if word in t:
                    score += 1

        for word in scene_lower.split():
            if word in cat:
                score += 3
            for k in kw:
                if word in k:
                    score += 2

        if "price" in scene_lower and cat == "calculator_price_contrast":
            score += 5
        if "secret" in scene_lower and cat == "mystery_insider_secrets":
            score += 5
        if any(w in scene_lower for w in ["china", "quality", "standard", "export"]):
            if cat == "china_vs_foreign_conflict":
                score += 5

        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    selected = scored[:min(3, len(scored))]
    if not selected:
        return ""

    parts = []
    for _, s in selected:
        script_lines = []
        for line in s.get("script", []):
            sp = line.get("speaker", "")
            text = line.get("text", "")
            if sp == "scene":
                script_lines.append(f"({text})")
            else:
                script_lines.append(f"{sp}: {text}")
        script_text = "\n".join(script_lines)
        parts.append(
            f"[Style Reference: {s.get('title', 'Untitled')} "
            f"({s.get('category_zh', s.get('category', ''))})]\n"
            f"{script_text}\n"
        )
    return "\n\n".join(parts)

def _get_daily_scripts():
    """每日轮播：每类取 1 条，MD5 确定性选择"""
    scripts = _load_scripts_library()
    today_key = datetime.date.today().isoformat()
    categories = ["calculator_price_contrast", "mystery_insider_secrets", "china_vs_foreign_conflict"]
    daily = []
    for cat in categories:
        cat_scripts = [s for s in scripts if s.get("category") == cat]
        if cat_scripts:
            idx = int(hashlib.md5((today_key + cat).encode()).hexdigest(), 16) % len(cat_scripts)
            daily.append(cat_scripts[idx])
    return daily


# ── 镜头叙事模板库 ──────────────────────────────────
CAMERA_SEQUENCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_sequence_library.json")

def _load_camera_sequences():
    """加载镜头叙事模板库，返回模板列表"""
    if not os.path.exists(CAMERA_SEQUENCE_FILE):
        return []
    try:
        with open(CAMERA_SEQUENCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _match_camera_template(scene_hint="", product_name="") -> dict:
    """根据场景和产品匹配最合适的镜头叙事模板

    通过关键词打分选择最佳模板，返回模板 dict 或 None
    """
    templates = _load_camera_sequences()
    if not templates:
        return None

    scene_lower = (scene_hint or "").lower()
    product_lower = (product_name or "").lower()
    text = f"{scene_lower} {product_lower}"

    best_score = 0
    best_match_count = 0
    best = None
    for t in templates:
        score = 0
        match_count = 0
        for kw in t.get("suitable_scenes", []):
            kw_lower = kw.lower()
            if kw_lower in text:
                score += 2
                match_count += 1
        for kw in t.get("suitable_products", []):
            if kw == "all":
                score += 1
            elif kw.lower() in product_lower:
                score += 1
                match_count += 1
        # 选择得分最高且匹配关键词最多的模板
        if score > best_score or (score == best_score and match_count > best_match_count):
            best_score = score
            best_match_count = match_count
            best = t

    # 无匹配时使用模板1（逆袭之路）作为默认
    if not best and templates:
        best = templates[0]
    return best


# ═══════════════════════════════════════════════════
# 素材库：镜头 / 叙事模板 / 钩子 / 故事情节
# ═══════════════════════════════════════════════════

SHOT_LIBRARY = [
    # ── 开场/场景建立 ──
    {"id":"s_wide_street","name":"街景全景","cat":"opening",
     "desc":"Wide establishing shot of {scene}, slow push-in, cinematic lighting, 8K"},
    {"id":"s_dolly_storefront","name":"推轨接近店铺","cat":"opening",
     "desc":"Smooth dolly shot approaching storefront at {time}, revealing {product} on facade, tracking movement, anamorphic"},
    {"id":"s_aerial_block","name":"航拍街景","cat":"opening",
     "desc":"Aerial drone shot gliding over {scene} at {time}, slow descent towards illuminated storefront, cinematic"},
    {"id":"s_pedestrian_approach","name":"路人视角接近","cat":"opening",
     "desc":"POV walking shot approaching store, eyes naturally drawn to glowing {product}, shallow DOF, realistic"},
    # ── 痛点/问题 ──
    {"id":"s_closeup_old_sign","name":"旧招牌特写","cat":"problem",
     "desc":"Extreme close-up old/dim/rusted sign, rain drops on surface, shallow DOF, moody lighting, texture detail, 8K"},
    {"id":"s_owner_disappointed","name":"店主失望","cat":"problem",
     "desc":"Medium shot store owner staring at dim outdated sign, disappointed expression, soft natural lighting"},
    {"id":"s_customer_ignore","name":"顾客无视","cat":"problem",
     "desc":"Wide shot pedestrians walking past store without looking, boring signage blends into background, time-lapse"},
    {"id":"s_detail_damage","name":"破损细节","cat":"problem",
     "desc":"Macro close-up water ingress/rust/peeling paint on old sign, dramatic lighting, ultra detailed texture"},
    # ── 工艺/品质 ──
    {"id":"s_craft_polish","name":"打磨抛光","cat":"craft",
     "desc":"Close-up craftsman hands polishing brushed metal surface, sparks flying, workshop warm lighting, slow motion"},
    {"id":"s_craft_laser","name":"激光切割","cat":"craft",
     "desc":"Macro shot laser cutting precision letter edge, glowing red beam, clean sharp lines, slow motion, 8K"},
    {"id":"s_craft_weld","name":"焊接组装","cat":"craft",
     "desc":"Close-up TIG welding stainless steel letter frame, blue arc light, skilled hands, workshop atmosphere"},
    {"id":"s_craft_paint","name":"喷涂上色","cat":"craft",
     "desc":"Macro shot even paint/coating application on letter surface, smooth flawless finish, bright clean lighting"},
    {"id":"s_material_texture","name":"材质纹理","cat":"craft",
     "desc":"Extreme macro brushed titanium texture, light reflecting off metal grain, premium feel, 8K"},
    {"id":"s_seal_detail","name":"密封结构","cat":"craft",
     "desc":"Close-up rubber sealing edge detail, water test droplets beading off surface, technical precision"},
    {"id":"s_rgb_chip","name":"RGB芯片","cat":"craft",
     "desc":"Macro shot programmable RGB LED chip inside letter, color cycling demo, bokeh background, tech aesthetic"},
    # ── 产品发光 ──
    {"id":"s_lightup_transition","name":"灯光点亮过渡","cat":"product",
     "desc":"Slow-motion letters transitioning from off to full brightness, soft halo glow emerging, warm light, magical"},
    {"id":"s_lightup_halo","name":"背光晕影","cat":"product",
     "desc":"Close-up backlit halo effect on wall behind letters, soft floating light gradient, premium ambiance, 8K"},
    {"id":"s_product_facade","name":"产品安装效果","cat":"product",
     "desc":"Medium shot finished {product} installed on storefront facade, {time} lighting, perfect visibility, cinematic"},
    {"id":"s_color_shift","name":"炫彩变色","cat":"product",
     "desc":"Angle-changing shot iridescent/color-shifting surface, rainbow gradient shifting with camera movement"},
    {"id":"s_brightness_compare","name":"亮度对比","cat":"product",
     "desc":"Split screen comparison: old dim sign vs new bright {product}, dramatic difference, side by side"},
    {"id":"s_rainbow_reflection","name":"彩虹反光","cat":"product",
     "desc":"Color electroplated surface reflecting rainbow light onto ground, colorful bokeh, dreamy night atmosphere"},
    # ── 客户反应/效果 ──
    {"id":"s_customer_stop","name":"路人驻足","cat":"reaction",
     "desc":"Medium shot pedestrian stops, looks up at glowing {product}, impressed expression, natural night lighting"},
    {"id":"s_customer_selfie","name":"顾客拍照","cat":"reaction",
     "desc":"Young customer taking selfie in front of {product}, phone flash, genuine smile, street night vibe"},
    {"id":"s_customer_enter","name":"顾客进店","cat":"reaction",
     "desc":"Wide shot customer attracted by sign opens door and enters store, warm interior light spills out"},
    {"id":"s_owner_proud","name":"店主自豪","cat":"reaction",
     "desc":"Medium shot owner standing proudly under new {product}, smiling, storefront fully illuminated"},
    {"id":"s_far_distance","name":"远景可见","cat":"reaction",
     "desc":"Long shot from far down street, {product} clearly readable and visible from distance, establishing context"},
    # ── 时间/环境 ──
    {"id":"s_time_lapse","name":"日夜延时","cat":"environment",
     "desc":"Time-lapse day to night, {product} consistently visible through changing light conditions, hyperlapse"},
    {"id":"s_day_bright","name":"白天强光","cat":"environment",
     "desc":"Bright sunny day, {product} clearly visible and readable despite direct sunlight, high contrast"},
    {"id":"s_night_glow","name":"夜景发光","cat":"environment",
     "desc":"Night street scene, {product} glowing beautifully, reflections on wet ground, cinematic neon atmosphere"},
    {"id":"s_rain_ambient","name":"雨夜氛围","cat":"environment",
     "desc":"Rainy night, {product} glowing through rain drops, wet pavement reflections, moody cinematic atmosphere"},
]

NARRATIVE_TEMPLATES = [
    {"id":"nt_problem_solution","name":"痛点→解决方案→效果",
     "beats":["problem","craft","product","reaction"],
     "desc":"Start with the problem (old sign failing), show craft quality, reveal new sign, show customer reaction"},
    {"id":"nt_establish_craft","name":"街景→工艺→安装→效果",
     "beats":["opening","craft","product","reaction"],
     "desc":"Establish scene, showcase manufacturing craft, install product, show final transformation"},
    {"id":"nt_comparison","name":"前后对比→工艺→效果",
     "beats":["problem","craft","product","reaction"],
     "desc":"Show before/after comparison, reveal craft process, highlight final result with customer reaction"},
    {"id":"nt_discovery","name":"路人发现→走近→赞叹",
     "beats":["opening","product","reaction"],
     "desc":"Pedestrian discovers the sign from distance, approaches, reacts with awe"},
    {"id":"nt_craft_story","name":"工匠故事→产品诞生→安装",
     "beats":["craft","craft","product","reaction"],
     "desc":"Focus on handcraft story, show letters being made, installation, final glowing result"},
    {"id":"nt_env_showcase","name":"环境→产品→全天候效果",
     "beats":["opening","product","environment","reaction"],
     "desc":"Show the environment, reveal the sign, demonstrate all-weather performance, customer satisfaction"},
    {"id":"nt_quick_hit","name":"快节奏直击→痛点→解决方案",
     "beats":["problem","product","reaction"],
     "desc":"Quick cut style: problem hits, immediate solution shown, result revealed, fast paced"},
    {"id":"nt_premium_lifestyle","name":"高端生活方式→品质→品味",
     "beats":["opening","craft","product","reaction"],
     "desc":"Premium lifestyle aesthetic, showcase elegant craft, reveal luxurious sign, admiring reaction"},
]

HOOK_LIBRARY = [
    # 问题钩
    {"id":"hk_prob_01","cat":"problem","text":"Your Old Sign Is Repelling Customers"},
    {"id":"hk_prob_02","cat":"problem","text":"Dull Storefront = Lost Revenue"},
    {"id":"hk_prob_03","cat":"problem","text":"Is Your Sign Costing You Foot Traffic?"},
    {"id":"hk_prob_04","cat":"problem","text":"Don't Let Bad Signage Kill Your Business"},
    # 好奇钩
    {"id":"hk_curious_01","cat":"curiosity","text":"What Makes This Sign So Irresistible?"},
    {"id":"hk_curious_02","cat":"curiosity","text":"The Secret Behind Irresistible Storefronts"},
    {"id":"hk_curious_03","cat":"curiosity","text":"Why Everyone Stops At This Store"},
    {"id":"hk_curious_04","cat":"curiosity","text":"This Sign Trick Boosts Sales 40%"},
    # 效果钩
    {"id":"hk_result_01","cat":"result","text":"Transform Your Storefront In 24 Hours"},
    {"id":"hk_result_02","cat":"result","text":"From Invisible To Unmissable"},
    {"id":"hk_result_03","cat":"result","text":"Night Mode: Storefront That Commands Attention"},
    {"id":"hk_result_04","cat":"result","text":"Make Your Brand Seen Block Away"},
    # 紧迫感钩
    {"id":"hk_urgent_01","cat":"urgency","text":"Stop Wasting Money On Ineffective Signs"},
    {"id":"hk_urgent_02","cat":"urgency","text":"Your Competition Already Upgraded"},
    {"id":"hk_urgency_03","cat":"urgency","text":"Every Dark Day Costs You Real Money"},
    # 社会证明钩
    {"id":"hk_social_01","cat":"social","text":"500+ Storefronts Transformed — Yours Next"},
    {"id":"hk_social_02","cat":"social","text":"Trusted By Premium Brands Worldwide"},
]

STORYLINE_LIBRARY = [
    {"id":"sl_shop_transformation","name":"店铺蜕变","desc":"Old boring shop → problem revealed → new sign crafted → installed → customers attracted → success"},
    {"id":"sl_factory_to_street","name":"从工厂到街头","desc":"Craftsmanship in factory → material close-ups → finished product → installation on street → night glow → people react"},
    {"id":"sl_day_in_life","name":"一天中的变化","desc":"Morning daylight (sign visible) → noon (bright, still visible) → evening (sign glows) → night (beautiful halo) → customers"},
    {"id":"sl_discovery_journey","name":"发现之旅","desc":"Far distance shot → approaching store → noticing the sign → getting closer → detail close-ups → wow moment"},
    {"id":"sl_side_by_side","name":"对比故事","desc":"Competitor/old sign looks bad → cut to our sign → craft details → side by side comparison → winner revealed"},
    {"id":"sl_owner_pride","name":"店主的骄傲","desc":"Owner disappointed with old sign → discovers GLOWFORGE → installation day → proud moment → customers love it → business grows"},
    {"id":"sl_viral_moment","name":"网红打卡","desc":"Street scene → influencer notices sign → takes photo/video → posts on social → crowd gathers → viral moment"},
    {"id":"sl_season_journey","name":"四季如新","desc":"Spring rain → summer sun → autumn wind → winter snow → sign looks perfect in all seasons → reliable quality"},
    {"id":"sl_tech_innovation","name":"科技感展示","desc":"RGB chip macro → smart sensor demo → programmable effects → installation on tech venue → cyberpunk night vibe"},
    {"id":"sl_night_economy","name":"夜经济","desc":"Night street scene → dark shops invisible → our sign lights up → bright from far away → customers drawn in → night business booming"},
    {"id":"sl_elegant_upgrade","name":"轻奢升级","desc":"High-end street scene → elegant storefront → premium sign detail → soft halo glow → sophisticated atmosphere → luxury brand feel"},
    {"id":"sl_small_big_impact","name":"小店大效果","desc":"Small narrow storefront → can't fit big sign → mini precise letters installed → perfectly fits → visible from street → customer enters"},
]


# ── 素材库辅助函数 ────────────────────────────────

import random
import re as _re

def pick_shots(beats, product_name, scene_hint="", time_suffix="night"):
    """根据叙事模板的 beats 选择匹配的镜头并填充变量"""
    cat_map = {"opening":"opening","problem":"problem","craft":"craft","product":"product","reaction":"reaction","environment":"environment"}
    selected = []
    for beat in beats:
        cat = cat_map.get(beat, "product")
        candidates = [s for s in SHOT_LIBRARY if s["cat"] == cat]
        if candidates:
            shot = random.choice(candidates)
        else:
            shot = random.choice(SHOT_LIBRARY)
        # 填充变量
        desc = shot["desc"].replace("{scene}", scene_hint or "commercial street")
        desc = desc.replace("{time}", time_suffix)
        desc = desc.replace("{product}", product_name)
        selected.append(desc)
    return selected


def pick_hook():
    """随机选一个钩子"""
    return random.choice(HOOK_LIBRARY)


def pick_storyline():
    """随机选一个故事情节"""
    return random.choice(STORYLINE_LIBRARY)


def pick_narrative():
    """随机选一个叙事模板"""
    return random.choice(NARRATIVE_TEMPLATES)


def compose_prompt_from_library(product_name, scene_hint="", features="", use_camera_template=True):
    """从素材库组合多镜头 prompt

    use_camera_template: True=使用镜头叙事模板库（结构化镜头序列）
                          False=使用旧版随机镜头库
    返回 (prompt, hook_text, template_name)
    """
    # 镜头叙事模板模式
    if use_camera_template:
        template = _match_camera_template(scene_hint, product_name)
        if template:
            shots = template.get("shots", [])
            template_name = f"{template.get('name_en', template['name'])} ({template['id']})"

            # 构建结构化镜头描述
            shot_descriptions = []
            pacing_info = template.get("pacing", [])
            pacing_desc = "; ".join([f"{p['phase']}: {p['tempo']} tempo" for p in pacing_info])

            for s in shots:
                desc_parts = [
                    s.get("shot_type", "shot"),
                    s.get("visual", ""),
                    f"mood: {s.get('mood', 'neutral')}",
                    f"lighting: {s.get('lighting', 'natural')}",
                    f"camera: {s.get('camera_movement', 'static')}",
                    f"{s.get('duration', 2)}s"
                ]
                shot_descriptions.append(" | ".join(desc_parts))

            shot_sequence = " → ".join(shot_descriptions)

            # 从旧钩子库随机取一个钩子
            hook = pick_hook()
            hook_text = hook["text"]
            storyline = pick_storyline()

            prompt = (
                f"15s cinematic commercial video, 8K ultra realistic, cinematic color grading, "
                f"smooth transitions between scenes. "
                f"Story: {storyline['desc']}. "
                f"Shot sequence: {shot_sequence}. "
                f"Pacing: {pacing_desc}. "
                f"Template: {template['name']} — {template.get('description', '')}. "
                f"Photorealistic, volumetric lighting, shallow depth of field, anamorphic style."
            )
            return prompt, hook_text, template_name

    # 旧版随机镜头库（降级或 use_camera_template=False）
    narrative = pick_narrative()
    storyline = pick_storyline()
    hook = pick_hook()

    shots = pick_shots(
        narrative["beats"],
        product_name,
        scene_hint or "commercial street",
        time_suffix="night"
    )

    shot_sequence = " → ".join(shots)
    prompt = (
        f"15s cinematic commercial video, 8K ultra realistic, cinematic color grading, "
        f"smooth transitions between scenes. "
        f"Story: {storyline['desc']}. "
        f"Shot sequence: {shot_sequence}. "
        f"Narrative style: {narrative['desc']}. "
        f"Photorealistic, volumetric lighting, shallow depth of field, anamorphic style."
    )

    return prompt, hook["text"], "legacy_random"


# ── AI 自动生成视频内容 ────────────────────────────
def auto_generate_video_content(product_name, scene_hint="", features="", target_duration=15, use_script_ref=True, language="en"):
    """用 AI 自动生成视频 prompt / 英文旁白 / 钩子标题

    target_duration: 视频目标时长（秒），控制旁白长度
    use_script_ref: 是否注入脚本库风格参考
    language: 输出语言代码 (en/es/fr/ar/ru/pt/de/ja)
    """
    # 语言标签映射
    LANG_LABELS = {
        "en": "English", "es": "Spanish", "fr": "French",
        "ar": "Arabic", "ru": "Russian", "pt": "Portuguese",
        "de": "German", "ja": "Japanese",
    }
    lang_name = LANG_LABELS.get(language, "English")
    # 语言特定voiceover要求
    LANG_VOICEWORD_LIMITS = {
        "en": 50, "es": 45, "fr": 45, "ar": 35,
        "ru": 40, "pt": 45, "de": 40, "ja": 35,
    }
    word_limit = LANG_VOICEWORD_LIMITS.get(language, 50)

    # 场景-语音配置映射
    SCENE_VOICE_CONFIG = {
        "price": "Price contrast scene: 【Customer】faster pace, shocked/unbelieving tone  【Factory】calm, slower reply (speed contrast creates drama)",
        "install": "Installation scene: 【Factory】slower pace (0.85), professional低沉讲解  【Wisdom】summarize with authority at end",
        "showcase": "Product showcase: 【Wisdom】slow reverent pace (0.8), suspenseful admiration  【Customer】curious interjection",
        "production": "Manufacturing scene: 【Wisdom】moderate pace (0.85), documentary-style narration, authoritative",
        "night": "Night club/bar scene: 【Wisdom】slow deep voice (0.8), magnetic and moody, matching RGB lights",
        "renovation": "Store renovation/comparison: 【Customer】from doubtful→surprised (building excitement)  【Wisdom】elevated summary",
    }
    scene_lower = (scene_hint or "").lower()
    voice_style_key = "default"
    for key in ("price", "install", "showcase", "production", "night", "renovation"):
        if key in scene_lower:
            voice_style_key = key
            break
    voice_style_note = SCENE_VOICE_CONFIG.get(voice_style_key, "")
    voice_section = (
        f"\nVoice Style (adapt to scene): {voice_style_note}\n"
        if voice_style_note else "\n"
    )
    # 先从素材库组合镜头和钩子
    lib_prompt, lib_hook, template_name = compose_prompt_from_library(
        product_name, scene_hint, features, use_camera_template=True
    )

    # 从知识库查找相关产品知识，注入到 AI prompt
    kb_context = _find_relevant_knowledge(product_name, scene_hint)
    kb_section = ""
    if kb_context:
        kb_section = f"\n\nProduct Knowledge (use these real specs and selling points):\n{kb_context}\n"

    # 从脚本库查找风格参考脚本
    script_section = ""
    if use_script_ref:
        script_refs = _find_relevant_scripts(product_name, scene_hint)
        if script_refs:
            script_section = (
                "\n\n===== Style Reference Scripts (IMITATE this exact tone, dialogue style, "
                "and emotional pacing) =====\n"
                f"{script_refs}\n"
                "These are proven video scripts from the GLOWFORGE account. Adapt YOUR output "
                "to match their style: use the same dialogue rhythm, emotional beats, "
                "scene-setting, and character voice. Replace product details with GLOWFORGE "
                "LED sign specifications. Keep the same storytelling structure.\n"
                "================================================================\n"
            )

    # 镜头叙事知识注入
    camera_section = ""
    if template_name and template_name != "legacy_random":
        camera_section = (
            "\n\nCinematography & Camera Notes — apply these principles:\n"
            "- Use specific shot types: establishing, close-up, medium, wide, insert, reaction\n"
            "- Emotional arc: cold/dim/desaturated for problem → warm/golden/saturated for solution\n"
            "- Rhythm control: slow emotional moments → fast production sequences\n"
            "- Transitions: match cuts for continuity, contrast cuts for emotional shifts\n"
            f"- Shot template: {template_name}\n"
        )

    system_instruction = "You are a professional video ad copywriter for GLOWFORGE LED sign factory. Output ONLY valid JSON, no other text."
    user_prompt = f"""{system_instruction}

Product: {product_name}
Scene: {scene_hint or "commercial street"}
Features: {features or "premium LED sign"}
Target Language: {lang_name}
Voiceover must be in {lang_name} — use natural {lang_name} sales copy for a {lang_name}-speaking audience.

CRITICAL VOICEOVER FORMAT:
The voiceover MUST use 3-role dialogue format with role markers:
【Customer】curious buyer's question, exclamation, or reaction (surprise, doubt, excitement)
【Factory】expert reply, professional explanation, confident answer
【Wisdom】authoritative summary, industry insight, emotional elevation or call to action

Each role speaks 1-2 short sentences. The three roles create a natural conversation flow: problem → solution → benefit.{voice_section}

We have prepared a multi-shot video structure:
{lib_prompt}

Hook for first 3s: {lib_hook}{kb_section}{script_section}{camera_section}
Now write the final {target_duration}s video ad content in JSON format:
{{
  "prompt": "the final polished multi-shot video prompt (keep ALL shots, make it vivid and cinematic, 8K ultra realistic, smooth transitions)",
  "voiceover": "【Customer】...【Factory】...【Wisdom】... — {target_duration}s {lang_name} 3-role dialogue, pain → solution → benefit, max {word_limit} words total",
  "hook": "short overlay text for first 3s, max 6 words, in {lang_name}"
}}
IMPORTANT: voiceover MUST use 【Customer】【Factory】【Wisdom】 markers as shown!
Output ONLY valid JSON, no other text."""

    raw = ask_ali(user_prompt, "", max_tokens=1200, timeout=60)
    if not raw:
        return None

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if "```" in clean:
            clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    try:
        data = json.loads(clean)
        if data.get("prompt"):
            return {
                "prompt": data["prompt"].strip(),
                "voiceover": data.get("voiceover", "").strip(),
                "hook_text": data.get("hook", "").strip(),
            }
    except Exception:
        pass

    # Fallback: 直接用素材库内容
    return {
        "prompt": lib_prompt,
        "voiceover": f"Tired of {scene_hint or 'boring storefronts'}? Upgrade with {product_name}. Premium quality, lasting impression. Transform your business today.",
        "hook_text": lib_hook,
    }


# ── 参考链接分析 + 仿写 ────────────────────────────

def _fetch_page_metadata(url):
    """尝试抓取页面元数据，返回 {title, description, platform}"""
    import re
    platform = "unknown"
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        platform = "YouTube"
    elif "tiktok.com" in url_lower:
        platform = "TikTok"
    elif "douyin.com" in url_lower:
        platform = "抖音"
    elif "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        platform = "小红书"
    elif "bilibili.com" in url_lower or "b23.tv" in url_lower:
        platform = "B站"
    elif "google.com" in url_lower:
        platform = "Google"
    elif "instagram.com" in url_lower:
        platform = "Instagram"
    elif "facebook.com" in url_lower or "fb.com" in url_lower:
        platform = "Facebook"

    result = {"title": "", "description": "", "platform": platform}

    # 尝试 yt-dlp（仅 YouTube，能拿到标题和字幕）
    if platform == "YouTube":
        try:
            import subprocess
            r = subprocess.run(
                ["yt-dlp", "--dump-json", "--no-check-certificate", url],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=20,
                env={**os.environ, "http_proxy": os.environ.get("http_proxy", ""),
                     "https_proxy": os.environ.get("https_proxy", "")}
            )
            if r.returncode == 0 and r.stdout:
                import json as _json
                data = _json.loads(r.stdout)
                result["title"] = (data.get("title", "") or "")[:300]
                result["description"] = (data.get("description", "") or "")[:500]
                return result
        except Exception:
            pass

    # 尝试 requests 抓取页面元数据
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=15)
        html = r.text
        m = re.search(r'<meta\s+[^>]*property="og:title"[^>]*content="(.*?)"', html, re.I)
        if m:
            result["title"] = m.group(1).strip()[:300]
        m = re.search(r'<meta\s+[^>]*property="og:description"[^>]*content="(.*?)"', html, re.I)
        if m:
            result["description"] = m.group(1).strip()[:500]
        if not result["description"]:
            m = re.search(r'<meta\s+name="description"[^>]*content="(.*?)"', html, re.I)
            if m:
                result["description"] = m.group(1).strip()[:500]
    except Exception:
        pass
    return result


def analyze_reference_url(url, paste_text=""):
    """分析参考链接/文案 → AI 仿写 → {prompt, voiceover, hook_text}"""
    meta = _fetch_page_metadata(url) if url else {"platform": "unknown", "title": "", "description": ""}
    title = meta.get("title", "") or ""
    desc = meta.get("description", "") or ""
    platform = meta.get("platform", "unknown")

    # 构建 prompt
    system_instruction = "You are a professional video ad copywriter for GLOWFORGE LED sign factory. Output ONLY valid JSON, no other text."
    ref_section = f"Reference URL: {url}\nPlatform: {platform}\nTitle: {title}\nDescription: {desc}"
    if paste_text:
        ref_section += f"\n\nCopy text:\n{paste_text[:2000]}"

    user_prompt = f"""{system_instruction}

{ref_section}

Analyze this reference video's marketing style (tone, structure, pacing, target audience).
Then create a 15s video ad for GLOWFORGE LED sign products in a SIMILAR STYLE.

Output JSON:
{{
  "analysis": "brief style analysis",
  "prompt": "15s cinematic video prompt for AI generation, scene setting + storytelling + 8K ultra realistic + cinematic grading",
  "voiceover": "13s English sales script, pain point → solution → benefit, max 50 words",
  "hook": "short overlay text for first 3s, max 6 words"
}}
Output ONLY valid JSON, no other text."""

    raw = ask_ali(user_prompt, "", max_tokens=1200, timeout=60)
    if not raw:
        return None

    # 解析 JSON
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if "```" in clean:
            clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    try:
        data = json.loads(clean)
        return {
            "prompt": data.get("prompt", "").strip(),
            "voiceover": data.get("voiceover", "").strip(),
            "hook_text": data.get("hook", "").strip(),
            "analysis": data.get("analysis", "").strip(),
        }
    except Exception:
        pass

    # Fallback
    if prompt or paste_text:
        return auto_generate_video_content("LED Sign", platform)
    return None


@app.route("/api/analyze_url", methods=["POST"])
def api_analyze_url():
    """分析参考链接 → AI 仿写 → 返回 prompt/voiceover/hook"""
    data = request.json or {}
    url = (data.get("url") or "").strip()
    paste_text = (data.get("text") or "").strip()
    if not url and not paste_text:
        return jsonify({"error": "请输入链接或粘贴文案"}), 400
    try:
        result = analyze_reference_url(url, paste_text)
    except Exception as e:
        return jsonify({"error": f"分析异常: {e}"}), 500
    if not result:
        return jsonify({"error": "AI 分析失败，请重试"}), 500
    return jsonify(result)


# ── 扫描产品图片 ──────────────────────────────────
def scan_product_images():
    dirs = [
        "D:/Bohui_Global_Push/frames",
        "D:/Bohui_Global_Push/GLOWFORGE_CRM/uploads",
    ]
    images = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                images.append({"name": fname, "path": os.path.join(d, fname)})
    return images


PRODUCT_IMAGES = scan_product_images()


# ── 图片上传 ────────────────────────────────────────

UPLOAD_DIR = "D:/Bohui_Global_Push/GLOWFORGE_CRM/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def refresh_product_images():
    global PRODUCT_IMAGES
    PRODUCT_IMAGES = scan_product_images()


@app.route("/api/upload_image", methods=["POST"])
def api_upload_image():
    """上传产品图片"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "空文件名"}), 400
    # 校验扩展名
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return jsonify({"error": "仅支持 jpg/png/webp"}), 400
    # 保存
    fname = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, fname)
    f.save(save_path)
    refresh_product_images()
    return jsonify({"name": fname, "path": save_path})


VIDEO_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads_video")
os.makedirs(VIDEO_UPLOAD_DIR, exist_ok=True)

VOICE_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads_voice")
os.makedirs(VOICE_UPLOAD_DIR, exist_ok=True)


@app.route("/api/upload_video", methods=["POST"])
def api_upload_video():
    """上传已有视频，AI 配乐/字幕/钩子"""
    if "file" not in request.files:
        return jsonify({"error": "未选择视频文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "空文件名"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".mp4", ".mov", ".avi", ".webm", ".mkv"):
        return jsonify({"error": "仅支持 mp4/mov/avi/webm/mkv"}), 400
    fname = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(VIDEO_UPLOAD_DIR, fname)
    f.save(save_path)
    dur = 15.0
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", save_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15
        )
        if r.stdout.strip():
            dur = float(r.stdout.strip())
    except Exception:
        pass
    return jsonify({"name": fname, "path": save_path, "duration": round(dur, 1)})


# ── 自定义声音 ──────────────────────────────────────

@app.route("/api/upload_voice", methods=["POST"])
def api_upload_voice():
    """上传自定义声音样本"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "空文件名"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".wav", ".mp3", ".m4a", ".ogg"):
        return jsonify({"error": "仅支持 wav/mp3/m4a/ogg"}), 400
    fname = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(VOICE_UPLOAD_DIR, fname)
    f.save(save_path)
    return jsonify({"name": fname, "path": save_path, "label": f.filename})


@app.route("/api/voices")
def api_voices():
    """列出已上传的自定义声音"""
    voices = []
    for fname in sorted(os.listdir(VOICE_UPLOAD_DIR)):
        if fname.lower().endswith((".wav", ".mp3", ".m4a", ".ogg")):
            voices.append({
                "name": fname,
                "path": os.path.join(VOICE_UPLOAD_DIR, fname),
            })
    return jsonify(voices)


# ── API 路由 ──────────────────────────────────────
@app.route("/")
def index():
    return render_template("video_tool.html")


@app.route("/api/templates")
def api_templates():
    custom = _load_custom_templates()
    # Merge: built-in templates + custom templates (assign ids > 1000 for custom)
    all_templates = list(TEMPLATES)
    for ct in custom:
        all_templates.append({
            "id": ct.get("id", 1000 + len(all_templates)),
            "name": ct.get("name", ""),
            "en_name": ct.get("en_name", ""),
            "scene": ct.get("scene", ""),
            "prompt": ct.get("prompt", ""),
            "voiceover": ct.get("voiceover", ""),
            "hook_text": ct.get("hook_text", ""),
            "bgm": ct.get("bgm", "ambient"),
            "is_custom": True,
        })
    return jsonify(all_templates)


@app.route("/api/custom_templates", methods=["GET", "POST"])
def api_custom_templates():
    if request.method == "GET":
        return jsonify(_load_custom_templates())

    # POST: create
    data = request.json or {}
    custom = _load_custom_templates()
    new_id = 1001 + len(custom)
    tmpl = {
        "id": new_id,
        "name": data.get("name", "").strip(),
        "en_name": data.get("en_name", "").strip() or data.get("name", "").strip(),
        "scene": data.get("scene", "").strip(),
        "prompt": data.get("prompt", "").strip(),
        "voiceover": data.get("voiceover", "").strip(),
        "hook_text": data.get("hook_text", "").strip(),
        "bgm": data.get("bgm", "ambient"),
    }
    if not tmpl["name"]:
        return jsonify({"error": "模板名称不能为空"}), 400
    custom.append(tmpl)
    _save_custom_templates(custom)
    return jsonify(tmpl), 201


@app.route("/api/custom_templates/<int:template_id>", methods=["DELETE"])
def api_delete_custom_template(template_id):
    custom = _load_custom_templates()
    custom = [t for t in custom if t.get("id") != template_id]
    _save_custom_templates(custom)
    return jsonify({"ok": True})


# ── 知识库 API ──────────────────────────────────────

@app.route("/api/knowledge", methods=["GET", "POST"])
def api_knowledge():
    if request.method == "GET":
        return jsonify(_load_knowledge_base())

    # POST: add or update entry
    data = request.json or {}
    kb = _load_knowledge_base()
    entry_id = data.get("id", f"kb_{uuid.uuid4().hex[:8]}")
    # Update existing or add new
    for i, e in enumerate(kb):
        if e.get("id") == entry_id:
            kb[i].update(data)
            break
    else:
        data["id"] = entry_id
        kb.append(data)
    with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    return jsonify({"id": entry_id, "ok": True})


@app.route("/api/knowledge/<entry_id>", methods=["DELETE"])
def api_delete_knowledge(entry_id):
    kb = _load_knowledge_base()
    kb = [e for e in kb if e.get("id") != entry_id]
    with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/auto_content", methods=["POST"])
def api_auto_content():
    """AI 自动生成视频 prompt / voiceover / hook"""
    data = request.json or {}
    product = data.get("product", "")
    scene = data.get("scene", "")
    features = data.get("features", "")
    use_script_ref = data.get("use_script_ref", True)
    language = data.get("language", "en")
    if not product:
        return jsonify({"error": "product is required"}), 400
    try:
        result = auto_generate_video_content(product, scene, features, use_script_ref=use_script_ref, language=language)
    except Exception as e:
        return jsonify({"error": f"AI 生成异常: {e}"}), 500
    if not result:
        # Debug: call ask_ali directly with the same params
        user_prompt = f"""Product: {product}
Scene: {scene or "commercial street"}
Features: {features or "premium LED sign"}

Generate a 15s video ad content in JSON format:
{{
  "prompt": "15s cinematic video prompt for AI generation",
  "voiceover": "13s English sales script, max 50 words",
  "hook": "short overlay text for first 3s, max 6 words"
}}
Output ONLY valid JSON, no other text."""
        debug_raw = ask_ali(
            "You are a professional video ad copywriter for GLOWFORGE LED sign factory. Output ONLY valid JSON.",
            user_prompt, max_tokens=1000, timeout=30
        )
        return jsonify({
            "error": "AI 生成失败",
            "debug_raw_len": len(debug_raw) if debug_raw else 0,
            "debug_raw_preview": (debug_raw or "None")[:600],
        }), 500
    return jsonify(result)


@app.route("/api/debug_source")
def api_debug_source():
    """Return what the server thinks the log message is"""
    return jsonify({
        "log_msg": "[1/4] 正在提交 通义万相 API v2...",
        "generate_fn": generate_video.__name__,
    })
@app.route("/api/products")
def api_products():
    return jsonify(PRODUCT_IMAGES)


# ── 脚本库 API ──────────────────────────────────────

@app.route("/api/scripts", methods=["GET"])
def api_scripts():
    """列出脚本库，支持 ?cat=xxx 和 ?search=xxx 过滤"""
    cat = request.args.get("cat", "")
    search = request.args.get("search", "")
    scripts = _load_scripts_library()
    if cat:
        scripts = [s for s in scripts if s.get("category") == cat]
    if search:
        q = search.lower()
        scripts = [s for s in scripts
                   if q in s.get("title", "").lower()
                   or q in " ".join(s.get("keywords", [])).lower()
                   or q in s.get("category_zh", "").lower()]
    return jsonify(scripts)


@app.route("/api/scripts/daily")
def api_scripts_daily():
    """返回今日 3 条轮播脚本（每类 1 条）"""
    return jsonify(_get_daily_scripts())


@app.route("/api/scripts", methods=["POST"])
def api_add_script():
    """添加一条新脚本"""
    data = request.json or {}
    scripts = _load_scripts_library()
    new_id = data.get("id", f"script_{uuid.uuid4().hex[:8]}")
    existing_ids = {s["id"] for s in scripts}
    while new_id in existing_ids:
        new_id = f"script_{uuid.uuid4().hex[:8]}"
    data["id"] = new_id
    scripts.append(data)
    _save_scripts_library(scripts)
    return jsonify(data), 201


@app.route("/api/scripts/<script_id>", methods=["DELETE"])
def api_delete_script(script_id):
    scripts = _load_scripts_library()
    scripts = [s for s in scripts if s.get("id") != script_id]
    _save_scripts_library(scripts)
    return jsonify({"ok": True})


@app.route("/api/product_image")
def api_product_image():
    path = request.args.get("path", "")
    if not path or not os.path.exists(path):
        return "Image not found", 404
    return send_file(path, mimetype="image/jpeg")


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """提交视频生成反馈（thumbs up/down）"""
    data = request.json or {}
    thumbs = data.get("thumbs", "")
    if thumbs not in ("up", "down"):
        return jsonify({"error": "thumbs must be 'up' or 'down'"}), 400

    entry = {
        "id": f"fb_{uuid.uuid4().hex[:8]}",
        "task_id": data.get("task_id", ""),
        "thumbs": thumbs,
        "prompt": data.get("prompt", ""),
        "voiceover": data.get("voiceover", ""),
        "hook": data.get("hook", ""),
        "product": data.get("product", ""),
        "scene": data.get("scene", ""),
        "quality": data.get("quality", "720p"),
        "duration": data.get("duration", 15),
        "aspect_ratio": data.get("aspect_ratio", "9:16"),
        "bgm": data.get("bgm", ""),
        "voice": data.get("voice", "Cherry"),
        "use_script_ref": data.get("use_script_ref", True),
        "timestamp": datetime.datetime.now().isoformat(),
    }
    feedback = _load_feedback()
    feedback.append(entry)
    _save_feedback(feedback)

    # 自动学习：好评内容收录到知识库
    if thumbs == "up" and entry.get("prompt"):
        _auto_learn_from_feedback(entry)

    return jsonify({"ok": True, "id": entry["id"]})


@app.route("/api/feedback/stats")
def api_feedback_stats():
    """反馈统计：总次数、好评率、各维度聚合"""
    fb = _load_feedback()
    total = len(fb)
    ups = sum(1 for f in fb if f.get("thumbs") == "up")
    downs = sum(1 for f in fb if f.get("thumbs") == "down")
    return jsonify({
        "total": total,
        "up": ups,
        "down": downs,
        "rate": round(ups / total, 3) if total else 0,
    })


@app.route("/api/stats/effectiveness")
def api_effectiveness_stats():
    """生成效果统计：总次数、成功率、模板使用排行、BGM 排行"""
    log = _load_generation_log()
    total = len(log)
    done = sum(1 for e in log if e.get("status") == "done")
    failed = sum(1 for e in log if e.get("status") == "error")
    running = total - done - failed

    # 产品排行
    product_counter = {}
    for e in log:
        p = e.get("product") or "未命名"
        product_counter[p] = product_counter.get(p, 0) + 1
    top_products = sorted(product_counter.items(), key=lambda x: -x[1])[:10]

    # BGM 排行
    bgm_counter = {}
    for e in log:
        b = e.get("bgm") or "无"
        bgm_counter[b] = bgm_counter.get(b, 0) + 1
    top_bgms = sorted(bgm_counter.items(), key=lambda x: -x[1])[:5]

    # 分辨率 / 画幅排行
    quality_counter = {}
    ratio_counter = {}
    for e in log:
        q = e.get("quality", "未知")
        quality_counter[q] = quality_counter.get(q, 0) + 1
        r = e.get("aspect_ratio", "未知")
        ratio_counter[r] = ratio_counter.get(r, 0) + 1

    # 自动 vs 手动
    auto_count = sum(1 for e in log if e.get("auto_mode"))
    manual_count = total - auto_count

    # 今日生成数
    today = datetime.date.today().isoformat()
    today_count = sum(1 for e in log if e.get("timestamp", "").startswith(today))

    return jsonify({
        "total": total,
        "done": done,
        "failed": failed,
        "running": running,
        "success_rate": round(done / total, 3) if total else 0,
        "today": today_count,
        "auto_vs_manual": {"auto": auto_count, "manual": manual_count},
        "top_products": [{"name": k, "count": v} for k, v in top_products],
        "top_bgms": [{"name": k, "count": v} for k, v in top_bgms],
        "quality_distribution": [{"name": k, "count": v} for k, v in quality_counter.items()],
        "ratio_distribution": [{"name": k, "count": v} for k, v in ratio_counter.items()],
    })


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """生成视频 + 后处理合成"""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    prompt = data.get("prompt", "")
    quality = data.get("quality", "720p")
    duration = int(data.get("duration", 15))
    aspect_ratio = data.get("aspect_ratio", "9:16")
    image_path = data.get("image_path", "")
    voiceover = data.get("voiceover", "")
    hook_text = data.get("hook_text", "")
    bgm_key = data.get("bgm", "")
    seed = int(data.get("seed", -1))
    voice = data.get("voice", "Cherry")
    auto_mode = data.get("auto", False) or not prompt
    import_video_path = data.get("video_path", "")  # 导入模式：已有视频路径
    keep_original_audio = data.get("keep_original_audio", False)
    custom_voice = data.get("custom_voice", "")  # 自定义声音文件路径

    # 获取导入视频时长（用于 AI 生成长度适配）
    import_video_duration = 15.0
    if import_video_path and os.path.exists(import_video_path):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", import_video_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15
            )
            if r.stdout.strip():
                import_video_duration = float(r.stdout.strip())
        except Exception:
            pass

    # 导入模式：AI 生成 voiceover / hook
    if import_video_path and os.path.exists(import_video_path):
        if not voiceover or not hook_text:
            product = data.get("auto_product", data.get("product", "LED Sign"))
            scene = data.get("auto_scene", "")
            ai_content = auto_generate_video_content(
                product, scene, target_duration=import_video_duration
            )
            if ai_content:
                if not voiceover:
                    voiceover = ai_content.get("voiceover", "")
                if not hook_text:
                    hook_text = ai_content.get("hook_text", "")

    # 自动模式：AI 生成 prompt / voiceover / hook
    if auto_mode:
        product = data.get("auto_product", data.get("product", ""))
        scene = data.get("auto_scene", "")
        features = data.get("auto_features", "")
        if not product and not prompt:
            return jsonify({"error": "auto mode needs product name or prompt"}), 400
        if not prompt:
            ai_content = auto_generate_video_content(product or "LED Sign", scene, features, target_duration=duration)
            if ai_content:
                prompt = ai_content["prompt"]
                if not voiceover:
                    voiceover = ai_content.get("voiceover", "")
                if not hook_text:
                    hook_text = ai_content.get("hook_text", "")
            else:
                # fallback
                if not prompt:
                    return jsonify({"error": "AI 生成失败，请手动填写 prompt"}), 400

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    def task_runner(task_id):
        logs = []
        def log(msg):
            logs.append(msg)
            _update_task(task_id, "log", msg)

        try:
            is_import = import_video_path and os.path.exists(import_video_path)
            total_steps = 3 if is_import else 4

            # Step 1: 获取原始视频（导入模式跳过通义万相）
            if is_import:
                video_url = import_video_path  # 本地路径直接用
                log(f"[1/{total_steps}] 使用导入视频...")
            else:
                log(f"[1/{total_steps}] 正在提交 通义万相 API v2...")
                img = image_path if image_path and os.path.exists(image_path) else None
                video_url, err = generate_video(
                    prompt, quality=quality, duration=duration,
                    aspect_ratio=aspect_ratio, image_path=img, seed=seed
                )
                if err:
                    _update_task(task_id, "error", f"通义万相生成失败: {err}")
                    _log_generation(task_id, data, status="error")
                    return
                log(f"[2/{total_steps}] 通义万相生成完成，开始下载...")

            # Step 2: 合成配音 + BGM + 字幕
            bgm_path = BGM_MAP.get(bgm_key, "") if bgm_key else ""
            if bgm_path and not os.path.exists(bgm_path):
                bgm_path = ""

            out_name = f"final_{uuid.uuid4().hex}.mp4"
            out_path = os.path.join(TEMP_DIR, out_name)
            step2 = 2 if is_import else 3

            # 自动检测 voiceover 是否含角色标记 → 启用多角色语音
            has_role_markers = any(f"【{r}】" in (voiceover or "") for r in ("Customer", "Factory", "Wisdom"))
            multi_role = data.get("multi_role", has_role_markers)

            if keep_original_audio:
                log(f"[{step2}/{total_steps}] 保留原声，添加字幕和钩子...")
            elif multi_role:
                log(f"[{step2}/{total_steps}] 正在合成多角色配音 + BGM + 字幕...")
            else:
                log(f"[{step2}/{total_steps}] 正在合成配音 + BGM + 字幕...")
            final_path, err = compose_video(
                video_url=video_url,
                voiceover_text=voiceover or "Premium LED sign for your business.",
                hook_text=hook_text,
                bgm_path=bgm_path or None,
                output_path=out_path,
                voice=voice,
                keep_original_audio=keep_original_audio,
                custom_voice_path=custom_voice if custom_voice and os.path.exists(custom_voice) else None,
                multi_role=multi_role,
            )
            if err:
                _update_task(task_id, "error", f"合成失败: {err}")
                _log_generation(task_id, data, status="error")
                return

            log(f"[{total_steps}/{total_steps}] 全部完成！")
            _update_task(task_id, "done", {"path": final_path, "name": out_name})
            # 更新生成日志状态
            _log_generation(task_id, data, status="done")

        except Exception as e:
            _update_task(task_id, "error", str(e))
            _log_generation(task_id, data, status="error")

    task_id = uuid.uuid4().hex
    _tasks[task_id] = {"status": "running", "logs": [], "result": None}

    # 记录生成日志
    _log_generation(task_id, data)

    threading.Thread(target=task_runner, args=(task_id,), daemon=True).start()

    return jsonify({"task_id": task_id})


# ── 任务状态管理 ──────────────────────────────────
_tasks = {}
_tasks_lock = threading.Lock()

def _update_task(task_id, typ, data):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t:
            return
        if typ == "log":
            t.setdefault("logs", []).append(data)
        elif typ == "error":
            t["status"] = "error"
            t["error"] = data
        elif typ == "done":
            t["status"] = "done"
            t["result"] = data


@app.route("/api/status/<task_id>")
def api_status(task_id):
    with _tasks_lock:
        t = _tasks.get(task_id)
    if not t:
        return jsonify({"status": "not_found"})
    return jsonify({
        "status": t["status"],
        "logs": t.get("logs", []),
        "error": t.get("error"),
        "result": t["result"],
    })


@app.route("/api/download/<filename>")
def api_download(filename):
    # 安全检查
    if ".." in filename or "/" in filename:
        return "Invalid", 400
    path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, mimetype="video/mp4", as_attachment=True,
                     download_name="jimeng_final.mp4")


@app.route("/api/clear_temp", methods=["POST"])
def api_clear_temp():
    """清理临时文件"""
    count = 0
    for fname in os.listdir(TEMP_DIR):
        if fname.startswith(("final_", "raw_", "voiceover_", "subs_", "mixed_", "seg_")):
            try:
                os.remove(os.path.join(TEMP_DIR, fname))
                count += 1
            except OSError:
                pass
    return jsonify({"cleaned": count})


# ── 主入口 ────────────────────────────────────────
if __name__ == "__main__":
    port = 5678
    print(f"\n{'='*50}")
    print(f"  AI Video Tool Server")
    print(f"  Open: http://localhost:{port}")
    print(f"{'='*50}\n")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
