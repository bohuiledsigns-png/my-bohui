"""GLOWFORGE CRM — Premium Product Catalog (高级外贸目录)"""
import os, json, glob as globmod
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image, Frame, NextPageTemplate, BaseDocTemplate,
)
from reportlab.platypus.doctemplate import PageTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_LIB_ROOT = r"G:\发光字视频\图片库"

# ——— Font Registration ———
FONT_CN = "Helvetica"
FONT_CN_BOLD = "Helvetica-Bold"
FONT_EN = "Helvetica"
FONT_EN_BOLD = "Helvetica-Bold"

_font_list = [
    # Chinese (TTF files first; TTC may not embed properly)
    ("cn", r"C:\Windows\Fonts\Deng.ttf", "DengXian"),
    ("cn", r"C:\Windows\Fonts\NotoSansSC-VF.ttf", "NotoSansSC"),
    ("cn_bold", r"C:\Windows\Fonts\simhei.ttf", "SimHei"),
    ("cn_bold", r"C:\Windows\Fonts\Dengb.ttf", "DengXianB"),
    ("cn_bold", r"C:\Windows\Fonts\HYZhongHeiTi-197.ttf", "HYZhongHei"),
    # English
    ("en", r"C:\Windows\Fonts\arial.ttf", "Arial"),
    ("en_bold", r"C:\Windows\Fonts\arialbd.ttf", "Arial-Bold"),
]
for key_type, path, name in _font_list:
    if os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            if key_type == "cn" and FONT_CN == "Helvetica":
                FONT_CN = name
            elif key_type == "cn_bold" and FONT_CN_BOLD == "Helvetica-Bold":
                FONT_CN_BOLD = name
            elif key_type == "en" and FONT_EN == "Helvetica":
                FONT_EN = name
            elif key_type == "en_bold" and FONT_EN_BOLD == "Helvetica-Bold":
                FONT_EN_BOLD = name
        except:
            pass

# ——— Premium Color Palette ———
GOLD = colors.HexColor("#BF8C2A")        # rich gold
GOLD_LIGHT = colors.HexColor("#D4AF37")
GOLD_PALE = colors.HexColor("#F0E0B0")
DARK = colors.HexColor("#0D0D0D")
DARK_SEC = colors.HexColor("#1A1A1A")
DARK_CARD = colors.HexColor("#F8F8F8")
CHARCOAL = colors.HexColor("#2A2A2A")
STEEL = colors.HexColor("#6B7280")
WHITE = colors.white
TEXT_DARK = colors.HexColor("#1A1A1A")
TEXT_MED = colors.HexColor("#4B5563")
TEXT_LIGHT = colors.HexColor("#9CA3AF")

PAGE_W, PAGE_H = A4
MARGIN_L = 22*mm        # left/right generous
MARGIN_R = 22*mm
MARGIN_T = 20*mm
MARGIN_B = 20*mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# ========== Data Helpers ==========
def _get_db():
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))
    conn.row_factory = sqlite3.Row
    return conn

def _load_products(cat_filter=None):
    conn = _get_db()
    if cat_filter and cat_filter != "__all__":
        rows = conn.execute("SELECT * FROM products WHERE category=? AND status='active' ORDER BY name", (cat_filter,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products WHERE status='active' ORDER BY category, name").fetchall()
    conn.close()
    groups = {}
    for r in rows:
        p = dict(r)
        p["specs"] = json.loads(p.get("specs","{}") or "{}")
        p["images"] = json.loads(p.get("images","[]") or "[]")
        cat = p.get("category", "其他") or "其他"
        groups.setdefault(cat, []).append(p)
    return groups

def _load_images():
    m = {}
    if not os.path.isdir(IMG_LIB_ROOT): return m
    for folder in sorted(os.listdir(IMG_LIB_ROOT)):
        fp = os.path.join(IMG_LIB_ROOT, folder)
        if not os.path.isdir(fp): continue
        imgs = sorted([os.path.join(fp,f) for f in os.listdir(fp) if f.lower().endswith(('.jpg','.jpeg','.png','.webp'))])
        if imgs: m[folder] = imgs
    return m

def _match_img(prod, cat_images, all_images):
    pname = prod.get("name","")
    for fp in all_images:
        base = os.path.splitext(os.path.basename(fp))[0]
        if pname and any(len(p)>1 and p in base for p in pname.split()):
            return fp
    if prod.get("images"):
        for ref in prod["images"]:
            if os.path.exists(ref): return ref
            alt = os.path.join(BASE_DIR,"uploads",ref)
            if os.path.exists(alt): return alt
    return None

# ========== CATEGORY ENGLISH NAMES ==========
CAT_EN = {
    "发光字": "Illuminated Signs",
    "不锈钢发光字": "Stainless Steel Signs",
    "正面发光": "Front-Lit Signs",
    "背面发光": "Back-Lit Signs",
    "正背面发光": "Front & Back Lit",
    "霓虹灯": "Neon Lights",
    "霓虹灯产品": "Neon Lights",
    "亚克力工艺": "Acrylic Craft",
    "亚克力家具": "Acrylic Furniture",
    "亚克力家具-Aikokou": "Aikokou Collection",
    "亚克力展示": "Acrylic Displays",
    "灯箱广告": "Light Boxes",
    "标识标牌": "Signage & Nameplates",
    "喷漆工艺": "Spray-Painted Signs",
    "安装工程": "Installation Projects",
    "色温展示": "Color Temperature",
    "其他工艺": "Special Processes",
    "双面色": "Dual-Color Signs",
    "双面彩": "Dual-Color Signs",
    "LED模组": "LED Modules",
    "电商平台选品": "E-Commerce Selection",
}

# ========== PDF GENERATION ==========
def generate_catalog(output_path=None, category_filter=None, language="bilingual",
                     title="GLOWFORGE Product Catalog"):
    product_groups = _load_products(category_filter)
    cat_images = _load_images()
    all_images = []
    for imgs in cat_images.values(): all_images.extend(imgs)
    total = sum(len(v) for v in product_groups.values())
    if total == 0: return {"error": "没有找到产品","product_count":0}

    if not output_path:
        cat_dir = os.path.join(BASE_DIR,"uploads","catalogs")
        os.makedirs(cat_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = (category_filter or "all").replace(" ","_")[:20]
        output_path = os.path.join(cat_dir, f"GLOWFORGE_Catalog_{slug}_{ts}.pdf")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ========== STYLES ==========
    S = {}  # styles dict

    S["gold_rule"] = ParagraphStyle("gr", fontName=FONT_EN, fontSize=7, leading=9, textColor=GOLD, alignment=1)
    S["cover_top"] = ParagraphStyle("ct", fontName=FONT_EN, fontSize=8, leading=12, textColor=GOLD, alignment=1, spaceAfter=25*mm)
    S["cover_title"] = ParagraphStyle("cvti", fontName=FONT_EN_BOLD, fontSize=36, leading=42, textColor=GOLD, alignment=1, spaceAfter=2*mm)
    S["cover_sub_en"] = ParagraphStyle("cvse", fontName=FONT_EN, fontSize=13, leading=17, textColor=GOLD_PALE, alignment=1, spaceAfter=3*mm)
    S["cover_sub_cn"] = ParagraphStyle("cvsc", fontName=FONT_CN_BOLD, fontSize=16, leading=22, textColor=GOLD_LIGHT, alignment=1, spaceAfter=12*mm)
    S["cover_contact"] = ParagraphStyle("cvc", fontName=FONT_EN, fontSize=7.5, leading=12, textColor=colors.HexColor("#999"), alignment=1)
    S["cover_line"] = HRFlowable(width="35%", thickness=0.4, color=GOLD, spaceAfter=6*mm, spaceBefore=3*mm)

    S["toc_head"] = ParagraphStyle("tich", fontName=FONT_EN_BOLD, fontSize=16, leading=20, textColor=TEXT_DARK, spaceAfter=8*mm)
    S["toc_entry"] = ParagraphStyle("tice", fontName=FONT_CN_BOLD, fontSize=10, leading=16, textColor=TEXT_DARK, spaceAfter=1*mm)
    S["toc_entry_en"] = ParagraphStyle("ticee", fontName=FONT_EN, fontSize=7.5, leading=11, textColor=TEXT_MED, spaceAfter=3*mm)

    S["div_num"] = ParagraphStyle("dvnm", fontName=FONT_EN, fontSize=11, leading=14, textColor=GOLD, alignment=1, spaceAfter=3*mm)
    S["div_cn"] = ParagraphStyle("dvcn", fontName=FONT_CN_BOLD, fontSize=22, leading=28, textColor=WHITE, alignment=1, spaceAfter=2*mm)
    S["div_en"] = ParagraphStyle("dven", fontName=FONT_EN_BOLD, fontSize=24, leading=30, textColor=GOLD_LIGHT, alignment=1, spaceAfter=6*mm)
    S["div_count"] = ParagraphStyle("dvcnt", fontName=FONT_EN, fontSize=8, leading=12, textColor=colors.HexColor("#888"), alignment=1)

    S["prod_name"] = ParagraphStyle("pn", fontName=FONT_CN_BOLD, fontSize=9.5, leading=13, textColor=TEXT_DARK, spaceBefore=3*mm, spaceAfter=1*mm)
    S["prod_name_en"] = ParagraphStyle("pne", fontName=FONT_EN, fontSize=7.5, leading=10, textColor=TEXT_MED, spaceAfter=2*mm)
    S["spec_key"] = ParagraphStyle("sk", fontName=FONT_EN, fontSize=6.5, leading=9, textColor=TEXT_LIGHT, alignment=0)
    S["spec_val"] = ParagraphStyle("sv", fontName=FONT_CN, fontSize=6.5, leading=9, textColor=TEXT_DARK, alignment=0)
    S["prod_desc"] = ParagraphStyle("pd", fontName=FONT_CN, fontSize=7, leading=10, textColor=TEXT_MED, spaceBefore=2*mm, spaceAfter=0)

    # ========== PAGE TEMPLATES ==========
    page_num = [0]

    def _draw_cover(c, d):
        page_num[0] += 1
        # Full dark background
        c.setFillColor(DARK)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # Gold border frame
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.3)
        c.rect(12*mm, 10*mm, PAGE_W-24*mm, PAGE_H-20*mm, fill=0, stroke=1)
        # Inner gold border
        c.rect(14*mm, 12*mm, PAGE_W-28*mm, PAGE_H-24*mm, fill=0, stroke=1)
        # Top accent line
        c.setLineWidth(0.5)
        c.line(35*mm, PAGE_H-18*mm, PAGE_W-35*mm, PAGE_H-18*mm)
        # Bottom accent line
        c.line(35*mm, 22*mm, PAGE_W-35*mm, 22*mm)

    def _draw_divider(c, d):
        page_num[0] += 1
        # Dark gradient-like background
        c.setFillColor(DARK_SEC)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # Gold left bar
        c.setFillColor(GOLD)
        c.rect(0, 0, 4*mm, PAGE_H, fill=1, stroke=0)
        # Subtle top line
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.3)
        c.line(20*mm, PAGE_H-16*mm, PAGE_W-20*mm, PAGE_H-16*mm)

    def _draw_normal(c, d):
        page_num[0] += 1
        # Header
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.3)
        c.line(MARGIN_L, PAGE_H-13*mm, PAGE_W-MARGIN_R, PAGE_H-13*mm)
        # Footer
        c.line(MARGIN_L, 15*mm, PAGE_W-MARGIN_R, 15*mm)
        # Header text
        c.setFillColor(TEXT_LIGHT)
        c.setFont(FONT_EN, 6.5)
        c.drawString(MARGIN_L, PAGE_H-10.5*mm, "GLOWFORGE  |  Zhongshan Bohui")
        c.drawRightString(PAGE_W-MARGIN_R, PAGE_H-10.5*mm, str(page_num[0]))
        # Footer text
        c.setFont(FONT_EN, 6)
        c.drawCentredString(PAGE_W/2, 11*mm,
            "wa.bohui-sign.com  |  Tel: +86 13824779947  |  No.239 Fumin Ave, Xiaolan, Zhongshan, Guangdong, China")
        # Gold dot separator
        c.setFillColor(GOLD)
        c.circle(PAGE_W/2, PAGE_H-10*mm, 0.8, fill=1)

    def _draw_back(c, d):
        page_num[0] += 1
        c.setFillColor(DARK)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.3)
        c.rect(12*mm, 10*mm, PAGE_W-24*mm, PAGE_H-20*mm, fill=0, stroke=1)

    cover_f = Frame(MARGIN_L, MARGIN_B, CONTENT_W, PAGE_H-MARGIN_T-MARGIN_B, id="cover")
    normal_f = Frame(MARGIN_L, 18*mm, CONTENT_W, PAGE_H-38*mm, id="normal")

    class _Doc(BaseDocTemplate):
        def __init__(self, fn, **kw):
            BaseDocTemplate.__init__(self, fn, **kw)
            self.addPageTemplates([
                PageTemplate(id="Cover", frames=cover_f, onPage=_draw_cover),
                PageTemplate(id="Divider", frames=cover_f, onPage=_draw_divider),
                PageTemplate(id="Normal", frames=normal_f, onPage=_draw_normal),
                PageTemplate(id="Back", frames=cover_f, onPage=_draw_back),
            ])

    # ========== BUILD FLOWABLES ==========
    F = []
    F.append(NextPageTemplate("Cover"))

    # ===== COVER =====
    F.append(Spacer(1, 42*mm))
    F.append(Paragraph("ZHONGSHAN BOHUI", S["cover_top"]))
    F.append(Paragraph("GLOWFORGE", S["cover_title"]))
    F.append(S["cover_line"])
    F.append(Paragraph("PRODUCT CATALOG  |  产 品 目 录", S["cover_sub_en"]))
    F.append(Paragraph("Premium Illuminated Signs & Acrylic Products", S["cover_sub_cn"]))
    F.append(Spacer(1, 40*mm))
    for line in [
        "Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China",
        "Official Site: wa.bohui-sign.com  |  Tel: +86 13824779947",
        f"Catalogue issued: {datetime.now().strftime('%B %d, %Y')}",
    ]:
        F.append(Paragraph(line, S["cover_contact"]))
    F.append(NextPageTemplate("Normal"))

    # ===== TOC =====
    F.append(PageBreak())
    F.append(Spacer(1, 12*mm))
    F.append(Paragraph("CONTENTS", S["toc_head"]))
    F.append(HRFlowable(width="100%", thickness=0.4, color=GOLD, spaceAfter=8*mm))
    for ci, (cn, prods) in enumerate(product_groups.items(), 1):
        en = CAT_EN.get(cn, cn)
        F.append(Paragraph(
            f'<font color="#BF8C2A">{ci:02d}.</font>  {cn}',
            S["toc_entry"]))
        F.append(Paragraph(
            f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{en}  —  {len(prods)} products',
            S["toc_entry_en"]))
    F.append(PageBreak())

    # ===== CATEGORIES =====
    for ci, (cat_name, products) in enumerate(product_groups.items(), 1):
        en_name = CAT_EN.get(cat_name, cat_name)
        # --- Category divider ---
        F.append(NextPageTemplate("Divider"))
        F.append(Spacer(1, 50*mm))
        F.append(Paragraph(f"{ci:02d}", S["div_num"]))
        F.append(Paragraph(cat_name, S["div_cn"]))
        F.append(Paragraph(en_name, S["div_en"]))
        F.append(Spacer(1, 3*mm))
        F.append(HRFlowable(width="25%", thickness=0.4, color=GOLD, spaceAfter=4*mm))
        F.append(Paragraph(f"{len(products)} products", S["div_count"]))
        F.append(NextPageTemplate("Normal"))

        # --- Category images ---
        cat_media = cat_images.get(cat_name, [])
        for fname, imgs in cat_images.items():
            if fname in cat_name or cat_name in fname:
                cat_media.extend(imgs)
        if not cat_media:
            cat_media = all_images

        # --- Products grid (2 per page) ---
        for i in range(0, len(products), 2):
            row_prods = products[i:i+2]
            cells = []

            for prod in row_prods:
                img_path = _match_img(prod, cat_images, all_images)
                if not img_path and cat_media:
                    idx = hash(prod["name"]) % len(cat_media)
                    img_path = cat_media[idx]

                items = []

                # IMAGE
                img_ok = False
                if img_path and os.path.exists(img_path):
                    try:
                        # Try fitting image maintaining aspect ratio
                        img = Image(img_path, width=76*mm, height=55*mm)
                        items.append(img)
                        img_ok = True
                    except: pass
                if not img_ok:
                    ph = Table([[""]], colWidths=[76*mm], rowHeights=[55*mm])
                    ph.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor("#F0F0F0")),
                        ('BOX',(0,0),(-1,-1),0.5,colors.HexColor("#DDD")),
                    ]))
                    items.append(ph)

                # PRODUCT NAME
                items.append(Paragraph(prod.get("name",""), S["prod_name"]))
                if language in ("english","bilingual"):
                    items.append(Paragraph(prod.get("name",""), S["prod_name_en"]))

                # SPEC TABLE
                specs = prod.get("specs",{})
                spec_rows = []
                spec_map = [
                    ("material","Material"), ("材质","材料"),
                    ("thickness","Thickness"), ("厚度","厚度"),
                    ("size_range","Size"), ("尺寸","尺寸"),
                    ("color_options","Colors"), ("颜色","颜色"),
                    ("工艺","Process"), ("制作工艺","工艺"),
                    ("常用颜色","Colors"), ("常规尺寸","Size"),
                ]
                for db_key, label in spec_map:
                    val = specs.get(db_key,"")
                    if val:
                        spec_rows.append([
                            Paragraph(f'<font color="#9CA3AF">{label}</font>', S["spec_key"]),
                            Paragraph(val, S["spec_val"]),
                        ])
                if spec_rows:
                    st = Table(spec_rows, colWidths=[20*mm, 56*mm])
                    st.setStyle(TableStyle([
                        ('VALIGN',(0,0),(-1,-1),'TOP'),
                        ('TOPPADDING',(0,0),(-1,-1),0.5),
                        ('BOTTOMPADDING',(0,0),(-1,-1),0.5),
                        ('LINEBELOW',(0,0),(-1,-2),0.2,colors.HexColor("#ECECEC")),
                    ]))
                    items.append(Spacer(1, 1*mm))
                    items.append(st)

                # DESCRIPTION
                desc = prod.get("description","")
                if desc:
                    items.append(Paragraph(desc[:150], S["prod_desc"]))

                # WRAP IN CARD
                card = Table([[items]], colWidths=[76*mm])
                card.setStyle(TableStyle([
                    ('BOX',(0,0),(-1,-1),0.4,colors.HexColor("#E5E5E5")),
                    ('BACKGROUND',(0,0),(-1,-1),WHITE),
                    ('TOPPADDING',(0,0),(-1,-1),3),
                    ('BOTTOMPADDING',(0,0),(-1,-1),5),
                    ('LEFTPADDING',(0,0),(-1,-1),5),
                    ('RIGHTPADDING',(0,0),(-1,-1),5),
                    ('ROUNDEDCORNERS',(0,0),(-1,-1),4),
                ]))
                cells.append(card)

            # LAYOUT
            if len(cells) == 1:
                rt = Table([[cells[0]]], colWidths=[CONTENT_W])
            else:
                rt = Table([cells], colWidths=[CONTENT_W*0.49, CONTENT_W*0.49])
                rt.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
            F.append(rt)
            F.append(Spacer(1, 5*mm))

    # ===== BACK COVER =====
    F.append(NextPageTemplate("Back"))
    F.append(Spacer(1, 55*mm))
    F.append(Paragraph("GLOWFORGE", ParagraphStyle("bct",
        fontName=FONT_EN_BOLD, fontSize=28, leading=34,
        textColor=GOLD, alignment=1, spaceAfter=3*mm)))
    F.append(HRFlowable(width="25%", thickness=0.4, color=GOLD, spaceAfter=8*mm, spaceBefore=3*mm))
    for line in [
        "Zhongshan Bohui Advertising Craft Products Co., Ltd.",
        "Factory: No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China",
        "Official Site: wa.bohui-sign.com  |  Tel: +86 13824779947",
    ]:
        F.append(Paragraph(line, ParagraphStyle("bcc",
            fontName=FONT_EN, fontSize=7.5, leading=12, textColor=colors.HexColor("#999"), alignment=1)))

    # ========== BUILD ==========
    doc = _Doc(output_path,
               topMargin=MARGIN_T, bottomMargin=MARGIN_B,
               leftMargin=MARGIN_L, rightMargin=MARGIN_R,
               title=title,
               author="Zhongshan Bohui Advertising Craft Products Co., Ltd.")
    doc.build(F)

    return {
        "ok": True,
        "path": output_path,
        "page_count": page_num[0],
        "product_count": total,
        "category_count": len(product_groups),
    }

if __name__ == "__main__":
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else None
    result = generate_catalog(category_filter=cat)
    print(json.dumps(result, ensure_ascii=False, indent=2))
