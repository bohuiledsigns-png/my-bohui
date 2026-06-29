"""BOHUI SIGN — GLOWFORGE Product Catalog 2026 | Modern Editorial Design"""
import os, json, io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, HRFlowable,
    PageBreak, Image, NextPageTemplate, BaseDocTemplate,
)
from reportlab.platypus.doctemplate import PageTemplate
from reportlab.platypus.frames import Frame
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

qrcode_ok = False
try:
    import qrcode
    qrcode_ok = True
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = r"I:\桌面\catalog_images"

# ===== FONTS =====
FONT_CN = "Helvetica"
FONT_CN_B = "Helvetica-Bold"
FONT_EN = "Helvetica"
FONT_EN_B = "Helvetica-Bold"

_fonts = [
    ("cn", r"C:\Windows\Fonts\Deng.ttf", "DengXian"),
    ("cn_b", r"C:\Windows\Fonts\Dengb.ttf", "DengXianB"),
    ("en", r"C:\Windows\Fonts\arial.ttf", "Arial"),
    ("en_b", r"C:\Windows\Fonts\arialbd.ttf", "Arial-Bold"),
]
for k, p, n in _fonts:
    if os.path.exists(p):
        try:
            pdfmetrics.registerFont(TTFont(n, p))
            if k == "cn" and FONT_CN == "Helvetica": FONT_CN = n
            if k == "cn_b" and FONT_CN_B == "Helvetica-Bold": FONT_CN_B = n
            if k == "en" and FONT_EN == "Helvetica": FONT_EN = n
            if k == "en_b" and FONT_EN_B == "Helvetica-Bold": FONT_EN_B = n
        except:
            pass

TECH_TAG = "Proprietary Technology: GLOWFORGE Independent Logic Control"

# ===== COLOR PALETTE — sophisticated minimal =====
BG = colors.HexColor("#0D0D0D")       # deep charcoal
GD = colors.HexColor("#BF8C2A")        # muted gold
GL = colors.HexColor("#D4AF37")        # light gold
GP = colors.HexColor("#E8D5A3")        # pale gold
WH = colors.white
TD = colors.HexColor("#111111")        # near-black text
TM = colors.HexColor("#4B5563")        # medium grey
TG = colors.HexColor("#9CA3AF")        # light grey
DV = colors.HexColor("#E5E5E5")        # divider

PW, PH = A4
ML = 22*mm
MR = 22*mm
MT = 15*mm
MB = 15*mm
CW = PW - ML - MR

CAT_EN = {
    "正面发光": "Front-Lit LED Letters",
    "背面发光": "Back-Lit (Halo) LED Letters",
    "正背面发光": "Front & Back Lit Signs",
    "不锈钢发光字": "Stainless Steel Luminous Letters",
    "灯箱广告": "LED Light Boxes",
    "霓虹灯产品": "LED Neon Signs",
    "亚克力工艺": "Acrylic Craft Signs",
    "标识标牌": "Signage & Nameplates",
    "喷漆工艺": "Spray-Painted Signs",
    "色温展示": "Color Temperature Range",
    "其他工艺": "Special Processes",
    "安装工程": "Installation Projects",
}
CAT_ORDER = [
    "正面发光", "背面发光", "正背面发光", "不锈钢发光字",
    "灯箱广告", "霓虹灯产品", "亚克力工艺", "标识标牌",
    "喷漆工艺", "色温展示", "其他工艺", "安装工程",
]
IMG_CAT_MAP = {
    "front_lit": "正面发光", "back_lit": "背面发光",
    "front_back_lit": "正背面发光", "stainless_steel_luminous": "不锈钢发光字",
    "light_box": "灯箱广告", "neon": "霓虹灯产品",
    "acrylic_craft": "亚克力工艺", "signage": "标识标牌",
    "spray_paint": "喷漆工艺", "color_temp": "色温展示",
    "other_process": "其他工艺", "installation": "安装工程",
}

# Keywords indicating non-product content (selfies, street views, etc.)
_BAD_KEYWORDS = ["口播", "街道", "街景", "自拍", "selfie"]

def _is_product_image(filename):
    """Filter out non-product images (selfies, street views, etc.)."""
    fn = filename.lower()
    for kw in _BAD_KEYWORDS:
        if kw in fn:
            return False
    return True

def _load_images():
    m = {}
    if not os.path.isdir(IMG_DIR): return m
    for folder in sorted(os.listdir(IMG_DIR)):
        fp = os.path.join(IMG_DIR, folder)
        if not os.path.isdir(fp): continue
        imgs = sorted([os.path.join(fp, f) for f in os.listdir(fp)
                       if f.lower().endswith(('.jpg','.jpeg','.png','.webp'))
                       and _is_product_image(f)])
        if imgs: m[folder] = imgs
    return m

def _deduplicate(images):
    seen = set()
    result = []
    for p in images:
        fn = os.path.splitext(os.path.basename(p))[0]
        key = fn.split("_")[1] if len(fn.split("_")) > 1 else fn
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result

def _make_qr(data):
    if not qrcode_ok: return None
    try:
        q = qrcode.QRCode(box_size=2, border=1)
        q.add_data(data)
        q.make(fit=True)
        b = io.BytesIO()
        q.make_image(fill_color="black", back_color="white").save(b, format="PNG")
        b.seek(0)
        return Image(b, width=14*mm, height=14*mm)
    except:
        return None


def generate_catalog(output_path=None):
    all_images = _load_images()
    if not all_images:
        return {"error": "No images found"}

    if not output_path:
        d = os.path.join(BASE_DIR, "uploads", "catalogs")
        os.makedirs(d, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(d, f"Bohui_Product_Catalog_{ts}.pdf")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ===== MODERN STYLES — clean, bold, editorial =====
    S = {}
    # Cover
    S["c_company"] = ParagraphStyle("cc", fontName=FONT_EN, fontSize=9, leading=13, textColor=GP, alignment=TA_CENTER)
    S["c_brand"] = ParagraphStyle("cb", fontName=FONT_EN_B, fontSize=56, leading=62, textColor=GL, alignment=TA_CENTER)
    S["c_line"] = ParagraphStyle("cl", fontName=FONT_EN, fontSize=7, leading=9, textColor=GD, alignment=TA_CENTER)
    S["c_title"] = ParagraphStyle("ct", fontName=FONT_CN_B, fontSize=15, leading=20, textColor=WH, alignment=TA_CENTER)
    S["c_sub"] = ParagraphStyle("cs", fontName=FONT_EN, fontSize=10, leading=14, textColor=GP, alignment=TA_CENTER)
    S["c_tech"] = ParagraphStyle("cte", fontName=FONT_EN, fontSize=6.5, leading=10, textColor=TG, alignment=TA_CENTER)
    S["c_contact"] = ParagraphStyle("cco", fontName=FONT_EN_B, fontSize=8, leading=12, textColor=GD, alignment=TA_CENTER)
    # About
    S["a_head_cn"] = ParagraphStyle("ahc", fontName=FONT_CN_B, fontSize=20, leading=28, textColor=TD, alignment=TA_LEFT)
    S["a_head_en"] = ParagraphStyle("ahe", fontName=FONT_EN, fontSize=9, leading=13, textColor=GD, alignment=TA_LEFT)
    S["a_body"] = ParagraphStyle("ab", fontName=FONT_CN, fontSize=9, leading=16, textColor=TM, alignment=TA_LEFT)
    S["a_body_en"] = ParagraphStyle("abe", fontName=FONT_EN, fontSize=8, leading=14, textColor=TM, alignment=TA_LEFT)
    S["a_tag"] = ParagraphStyle("at", fontName=FONT_EN_B, fontSize=10, leading=14, textColor=GD, alignment=TA_LEFT)
    # TOC
    S["t_head"] = ParagraphStyle("th", fontName=FONT_EN_B, fontSize=18, leading=24, textColor=TD, alignment=TA_CENTER)
    S["t_num"] = ParagraphStyle("tn", fontName=FONT_EN_B, fontSize=10, leading=14, textColor=GD, alignment=TA_LEFT)
    S["t_cn"] = ParagraphStyle("tc", fontName=FONT_CN_B, fontSize=10, leading=16, textColor=TD, alignment=TA_LEFT)
    S["t_en"] = ParagraphStyle("te", fontName=FONT_EN, fontSize=7.5, leading=11, textColor=TG, alignment=TA_LEFT)
    # Divider
    S["d_num"] = ParagraphStyle("dn", fontName=FONT_EN_B, fontSize=72, leading=80, textColor=GD, alignment=TA_LEFT)
    S["d_cn"] = ParagraphStyle("dc", fontName=FONT_CN_B, fontSize=34, leading=42, textColor=WH, alignment=TA_LEFT)
    S["d_en"] = ParagraphStyle("de", fontName=FONT_EN_B, fontSize=20, leading=26, textColor=GL, alignment=TA_LEFT)
    # Product page
    S["p_cat_cn"] = ParagraphStyle("pcc", fontName=FONT_CN_B, fontSize=12, leading=16, textColor=TD, alignment=TA_LEFT)
    S["p_cat_en"] = ParagraphStyle("pce", fontName=FONT_EN, fontSize=7, leading=10, textColor=TG, alignment=TA_LEFT)
    S["p_cta"] = ParagraphStyle("pc", fontName=FONT_EN, fontSize=6, leading=9, textColor=TG, alignment=TA_CENTER)
    # Back
    S["b_brand"] = ParagraphStyle("bb", fontName=FONT_EN_B, fontSize=32, leading=38, textColor=GL, alignment=TA_CENTER)
    S["b_text"] = ParagraphStyle("bt", fontName=FONT_EN, fontSize=7, leading=12, textColor=TG, alignment=TA_CENTER)

    # ===== PAGE TEMPLATES — no decorative borders =====
    pn = [0]

    def _cover_bg(c, d):
        pn[0] += 1
        c.setFillColor(BG)
        c.rect(0, 0, PW, PH, fill=1, stroke=0)
        # No borders, no frames — just pure dark canvas

    def _divider_bg(c, d):
        pn[0] += 1
        c.setFillColor(BG)
        c.rect(0, 0, PW, PH, fill=1, stroke=0)
        # clean dark page — no decorations

    def _white_bg(c, d):
        pn[0] += 1
        c.setFillColor(WH)
        c.rect(0, 0, PW, PH, fill=1, stroke=0)
        # Subtle page number bottom-right
        c.setFillColor(TG)
        c.setFont(FONT_EN, 6.5)
        c.drawRightString(PW-MR, 10*mm, str(pn[0]))

    def _back_bg(c, d):
        pn[0] += 1
        c.setFillColor(BG)
        c.rect(0, 0, PW, PH, fill=1, stroke=0)

    # Content frames
    cf = Frame(ML, MB, CW, PH-MT-MB, id="cf")       # cover/divider/back: full area
    wf = Frame(ML, 14*mm, CW, PH-32*mm, id="wf")     # white: room for page number
    af = Frame(ML, MB, CW, PH-MT-MB, id="af")         # about: full area

    class Doc(BaseDocTemplate):
        def __init__(self, fn, **kw):
            BaseDocTemplate.__init__(self, fn, **kw)
            self.addPageTemplates([
                PageTemplate(id="Cover", frames=cf, onPage=_cover_bg),
                PageTemplate(id="Divider", frames=cf, onPage=_divider_bg),
                PageTemplate(id="White", frames=wf, onPage=_white_bg),
                PageTemplate(id="Back", frames=cf, onPage=_back_bg),
            ])

    F = []
    F.append(NextPageTemplate("Cover"))

    # ===================================================================
    # PAGE 1 — COVER (no borders, bold typography)
    # ===================================================================
    F.append(Spacer(1, 30*mm))
    F.append(Paragraph("BOHUI SIGN", S["c_company"]))
    F.append(Spacer(1, 4*mm))
    F.append(Paragraph("GLOWFORGE", S["c_brand"]))
    F.append(Spacer(1, 1*mm))
    F.append(Paragraph("—" * 6, S["c_line"]))
    F.append(Spacer(1, 2*mm))
    F.append(Paragraph("PRODUCT CATALOG  |  产 品  目 录", S["c_title"]))
    F.append(Spacer(1, 2*mm))
    F.append(Paragraph("Premium Illuminated Signs & Acrylic Fabrication", S["c_sub"]))
    F.append(Spacer(1, 35*mm))
    F.append(Paragraph(TECH_TAG, S["c_tech"]))
    F.append(Spacer(1, 8*mm))
    F.append(Paragraph("www.bohui-sign.com  |  +86 13824779947", S["c_contact"]))
    F.append(Paragraph("No.239 Fumin Ave, Xiaolan, Zhongshan, Guangdong, China", S["c_tech"]))

    # ===================================================================
    # PAGE 2 — ABOUT / COMPANY PROFILE (modern editorial layout)
    # ===================================================================
    F.append(NextPageTemplate("White"))
    F.append(PageBreak())
    F.append(Spacer(1, 4*mm))
    F.append(Paragraph("关于博汇", S["a_head_cn"]))
    F.append(Paragraph("ABOUT BOHUI SIGN", S["a_head_en"]))
    F.append(Spacer(1, 1*mm))
    F.append(HRFlowable(width="30%", thickness=0.3, color=GD, spaceAfter=6*mm))

    about_cn = [
        "中山市博汇广告工艺制品有限公司，坐落于中国灯饰之都——中山市小榄镇，是一家集研发、设计、生产、安装于一体的专业发光字与广告标识制造商。",
        "旗下品牌 GLOWFORGE，专注于高端 LED 发光字与亚克力工艺制品的智能化制造。采用独立逻辑控制技术，实现每颗灯珠的精准调光与动态效果，让每一件产品都具备独特的视觉表现力。",
        "公司拥有20年行业经验，产品远销欧美、中东、东南亚等50多个国家和地区，服务超过3000家商业客户，涵盖连锁品牌、酒店、商场、金融机构等高端应用场景。",
    ]
    about_en = [
        "Zhongshan Bohui Advertising Craft Products Co., Ltd. is located in Xiaolan Town, Zhongshan — the \"Capital of Lights\" in China. We specialize in R&D, design, production, and installation of premium LED illuminated signs and advertising signage.",
        "Our brand GLOWFORGE focuses on intelligent manufacturing of high-end LED illuminated signs and acrylic craft products. With proprietary Independent Logic Control technology, each LED can be individually calibrated for precise brightness and dynamic effects, delivering unparalleled visual impact.",
        # Note: keep English paragraphs pure English — no mixed CJK characters
        "With 20 years of industry experience, our products are exported to 50+ countries across Europe, America, Middle East, and Southeast Asia, serving 3000+ commercial clients including chain brands, hotels, shopping malls, and financial institutions.",
    ]
    for i, (cn, en) in enumerate(zip(about_cn, about_en)):
        if i > 0:
            F.append(Spacer(1, 3*mm))
        F.append(Paragraph(cn, S["a_body"]))
        F.append(Paragraph(en, S["a_body_en"]))

    F.append(Spacer(1, 6*mm))
    F.append(Paragraph("CORE CAPABILITIES", S["a_tag"]))
    F.append(Spacer(1, 2*mm))
    caps = [
        "LED Illuminated Signs  |  Acrylic Fabrication  |  Neon Signs  |  Light Boxes",
        "Custom Design & Engineering  |  Professional Installation  |  Global Shipping",
    ]
    for cap in caps:
        F.append(Paragraph(cap, S["a_body_en"]))
    F.append(Spacer(1, 4*mm))
    F.append(HRFlowable(width="100%", thickness=0.2, color=DV, spaceAfter=4*mm))
    F.append(Paragraph(
        "Proprietary Technology: GLOWFORGE Independent Logic Control  |  Patent Pending",
        ParagraphStyle("at2", fontName=FONT_EN, fontSize=7, leading=10, textColor=GD, alignment=TA_CENTER)))

    # ===================================================================
    # PAGE 3 — TABLE OF CONTENTS
    # ===================================================================
    F.append(PageBreak())
    F.append(Spacer(1, 8*mm))
    F.append(Paragraph("CONTENTS", S["t_head"]))
    F.append(HRFlowable(width="12%", thickness=0.3, color=GD, spaceAfter=6*mm))

    # 2-column TOC
    cat_items = []
    ci = 0
    for cat_key in CAT_ORDER:
        if not any(IMG_CAT_MAP.get(f) == cat_key and imgs for f, imgs in all_images.items()):
            continue
        ci += 1
        en = CAT_EN.get(cat_key, cat_key)
        cell = Table([
            [Paragraph(f"{ci:02d}", S["t_num"]),
             Paragraph(f"{cat_key}", S["t_cn"])],
            [Paragraph("", S["t_en"]),
             Paragraph(en, S["t_en"])],
        ], colWidths=[10*mm, CW//2 - 10*mm])
        cell.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,-1), 0.1, DV),
            ('TOPPADDING', (0,0), (-1,-1), 1),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('SPAN', (0,0), (0,1)),
        ]))
        cat_items.append(cell)

    # Split into two columns
    half = (len(cat_items) + 1) // 2
    left_col = cat_items[:half]
    right_col = cat_items[half:]
    # Pad right if needed
    while len(right_col) < len(left_col):
        right_col.append(Table([[""]], colWidths=[CW//2]))
    toc_rows = []
    for l, r in zip(left_col, right_col):
        toc_rows.append([l, r])
    toc_table = Table(toc_rows, colWidths=[CW*0.48, CW*0.48])
    toc_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (0,-1), 0),
        ('RIGHTPADDING', (1,0), (1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    F.append(toc_table)

    # ===================================================================
    # CATEGORY SECTIONS
    # ===================================================================
    ci = 0
    for cat_key in CAT_ORDER:
        # Find image folder
        folder = None
        for f, imgs in all_images.items():
            if IMG_CAT_MAP.get(f) == cat_key and imgs:
                folder = f
                break
        if not folder: continue

        imgs = _deduplicate(all_images[folder])
        ci += 1
        en = CAT_EN.get(cat_key, cat_key)

        # --- DIVIDER: bold editorial, asymmetric ---
        F.append(NextPageTemplate("Divider"))
        F.append(PageBreak())
        # Large number on left, name stacked below-right
        divider_content = []
        divider_content.append(Spacer(1, 35*mm))
        # Section number in huge type
        num_style = ParagraphStyle("dn2", fontName=FONT_EN_B, fontSize=96, leading=105, textColor=GD, alignment=TA_LEFT)
        divider_content.append(Paragraph(f"{ci:02d}", num_style))
        divider_content.append(Spacer(1, 4*mm))
        divider_content.append(Paragraph(cat_key, S["d_cn"]))
        divider_content.append(Paragraph(en, S["d_en"]))

        qr = _make_qr(f"https://www.bohui-sign.com/catalog/{cat_key}")
        if qr:
            divider_content.append(Spacer(1, 6*mm))
            qt = Table([[qr]], colWidths=[14*mm])
            qt.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT')]))
            divider_content.append(qt)

        for item in divider_content:
            F.append(item)

        # --- PRODUCT PAGES: 2-column grid, clean white ---
        F.append(NextPageTemplate("White"))
        F.append(PageBreak())
        F.append(Spacer(1, 2*mm))
        F.append(Paragraph(cat_key, S["p_cat_cn"]))
        F.append(Paragraph(en, S["p_cat_en"]))
        F.append(HRFlowable(width="100%", thickness=0.15, color=DV, spaceAfter=4*mm))

        # 2-column grid — larger images, more breathing room
        iw = 78*mm   # image width
        ih = 55*mm   # image height
        gap = 4*mm   # padding around each image
        rows_data = []
        for i in range(0, len(imgs), 2):
            row = []
            for j in range(2):
                if i+j < len(imgs):
                    try:
                        img = Image(imgs[i+j], width=iw, height=ih)
                        cell = Table([[img]], colWidths=[iw], rowHeights=[ih],
                            style=[('ALIGN',(0,0),(-1,-1),'CENTER'),
                                   ('LEFTPADDING',(0,0),(-1,-1),0),
                                   ('RIGHTPADDING',(0,0),(-1,-1),0),
                                   ('TOPPADDING',(0,0),(-1,-1),0),
                                   ('BOTTOMPADDING',(0,0),(-1,-1),0)])
                    except:
                        cell = Table([[""]], colWidths=[iw], rowHeights=[ih],
                            style=[('BACKGROUND',(0,0),(-1,-1),colors.HexColor("#F5F5F5"))])
                    row.append(cell)
                else:
                    row.append(Table([[""]], colWidths=[iw], rowHeights=[ih],
                        style=[('BACKGROUND',(0,0),(-1,-1),WH)]))
            rows_data.append(row)

        if rows_data:
            gt = Table(rows_data, colWidths=[iw, iw])
            gt.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('LEFTPADDING', (0,0), (-1,-1), gap),
                ('RIGHTPADDING', (0,0), (-1,-1), gap),
                ('TOPPADDING', (0,0), (-1,-1), gap),
                ('BOTTOMPADDING', (0,0), (-1,-1), gap),
            ]))
            F.append(gt)

        # Subtle CTA
        F.append(Spacer(1, 4*mm))
        F.append(HRFlowable(width="40%", thickness=0.1, color=DV, spaceAfter=2*mm))
        F.append(Paragraph(
            "Custom fabricated to your specifications with GLOWFORGE Independent Logic Control technology.",
            S["p_cta"]))

    # ===================================================================
    # BACK COVER — minimal, contact only
    # ===================================================================
    F.append(NextPageTemplate("Back"))
    F.append(PageBreak())
    F.append(Spacer(1, 55*mm))
    F.append(Paragraph("GLOWFORGE", S["b_brand"]))
    F.append(HRFlowable(width="18%", thickness=0.3, color=GD, spaceAfter=8*mm, spaceBefore=3*mm))
    for txt in [
        "Zhongshan Bohui Advertising Craft Products Co., Ltd.",
        "No.239 Fumin Avenue, Xiaolan Town, Zhongshan, Guangdong, China",
        "www.bohui-sign.com  |  +86 13824779947  |  bohuimedia@163.com",
    ]:
        F.append(Paragraph(txt, S["b_text"]))
    F.append(Spacer(1, 6*mm))
    F.append(Paragraph(TECH_TAG,
        ParagraphStyle("bt2", fontName=FONT_EN, fontSize=6, leading=9, textColor=GD, alignment=TA_CENTER)))

    # ===== BUILD =====
    doc = Doc(output_path, topMargin=MT, bottomMargin=MB, leftMargin=ML, rightMargin=MR,
              title="Bohui Product Catalog", author="Zhongshan Bohui Advertising Craft Products Co., Ltd.")
    doc.build(F)
    return {"ok": True, "path": output_path, "page_count": pn[0], "category_count": ci}


if __name__ == "__main__":
    result = generate_catalog()
    print(json.dumps(result, ensure_ascii=False, indent=2))
