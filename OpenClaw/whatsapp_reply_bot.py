#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp 中译英回复助手 v1
你打中文，它翻译成地道英文发出去
博汇 — 发光字 · 炫彩字 · 亚克力工艺 · 亚克力家具
出口美国、欧洲等全球市场
"""

import pyautogui
import random
import time
import base64
import json
import requests
import io
import re
import subprocess
import sys
from PIL import Image

# ================= 中转站配置 =================
API_KEY = "sk-ym9wY6TMotRVF8K4JnaEUt2mnK5cH71M5KhVMob55LSLjoft"
API_URL = "https://api.getgoapi.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

# ================= 视觉定位（复用V3已验证代码） =================

def screenshot_base64():
    """截屏并返回base64"""
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def ask_ai(prompt):
    """让AI看屏幕，返回文字分析"""
    b64 = screenshot_base64()
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}],
        "max_tokens": 500
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=45)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"  API错误({r.status_code}), 重试{attempt+1}...")
            time.sleep(2)
        except Exception as e:
            print(f"  请求异常: {e}, 重试{attempt+1}...")
            time.sleep(2)
    return None

def ask_ai_text(prompt, text):
    """纯文本调用AI（不带图片），用于翻译"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt + "\n\n" + text}],
        "max_tokens": 1000
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=45)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"  API错误({r.status_code}), 重试{attempt+1}...")
            time.sleep(2)
        except Exception as e:
            print(f"  请求异常: {e}, 重试{attempt+1}...")
            time.sleep(2)
    return None

def find_input_box():
    """AI视觉找WhatsApp输入框"""
    print("[视觉] 正在找输入框...")
    resp = ask_ai(
        "你看到的是WhatsApp界面。找到底部的聊天输入框（'Type a message'），"
        "回复它的中心像素坐标，格式: (x, y)。只回复坐标，不要其他内容。"
    )
    if resp:
        m = re.search(r'[\(（]\s*(\d{1,4})\s*[,，]\s*(\d{1,4})\s*[\)）]', resp)
        if m:
            coord = (int(m.group(1)), int(m.group(2)))
            print(f"  [视觉] 输入框坐标: {coord}")
            return coord
    print(f"  [视觉] AI无响应或解析失败，用默认坐标 (800, 950)")
    return (800, 950)

def human_move_click(x, y):
    pyautogui.moveTo(x, y, duration=random.uniform(0.3, 0.8))
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.click()
    time.sleep(random.uniform(0.5, 1.5))

def paste_text(text):
    """剪贴板粘贴（绕过输入法，零乱码）"""
    escaped = text.replace('"', '\\"').replace('\n', '\\n')
    subprocess.run(
        f'powershell -command "Set-Clipboard -Value \\\"{escaped}\\""',
        shell=True, capture_output=True
    )
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

def send_message(text):
    """找输入框 → 粘贴 → 发送"""
    pos = find_input_box()
    human_move_click(*pos)
    time.sleep(random.uniform(1, 2))
    print(f"[发送] {text[:60]}...")
    paste_text(text)
    time.sleep(random.uniform(0.3, 0.8))
    pyautogui.press("enter")
    print("  ✅ 已发送！")
    time.sleep(1)

# ================= 翻译引擎 =================

TRANSLATE_PROMPT = """你是一个专业的中译英翻译，专精于广告标识与亚克力制品行业。用户给你中文，你输出地道英文。

公司背景：Bohui（博汇），中国GLOWFORGE工厂，产品出口美国、英国、德国、法国、西班牙、俄罗斯、日本、意大利等全球市场。

产品线：
- 招牌广告发光字 / 炫彩发光字 → illuminated signage, channel letters, GLOWFORGE chromatic LED signs (RGB dual-channel fluid control)
- 亚克力工艺制品 → acrylic fabrication, acrylic display, acrylic signage
- 亚克力家具 → acrylic furniture (tables, chairs, shelves, display cases, retail fixtures)
- AI宣传片制作 → promotional video production (15s teaser free, 60s $119, 120s $239)

材质选项：
- 304不锈钢 → 304 stainless steel
- 201不锈钢 → 201 stainless steel
- 镀锌板 → galvanized zinc sheet / G.I. sheet

发光类型：
- RGB炫彩围边 → RGB chromatic edge-lit
- 单面发光 → single-face illuminated
- 双面发光 → double-face illuminated

规则：
- 你扮演博汇的销售Philip，语气专业、友好、B2B风格
- 保留品牌名: Bohui, GLOWFORGE, Raceway
- 行业术语用词准确: channel letters, illuminated signage, LED modules, acrylic, acrylic furniture, display case, RGB chromatic, edge-lit, face-lit, 304 stainless steel, galvanized, flush mount, raceway mounting, faceplate, trim cap, IP65, CE, RoHS, plywood crate, etc.
- 英文简洁、地道，不要中式英语
- 不要解释，不要加额外内容，直接输出翻译结果
- 如果是问候/闲聊，保持自然的商务语气

直接翻译以下中文到英文："""

def translate_chinese(text):
    """中文 → 英文翻译"""
    print("  [翻译] AI翻译中...")
    result = ask_ai_text(TRANSLATE_PROMPT, text)
    if result:
        return result.strip()
    return None

# ================= 阅读模式 =================

READ_PROMPT = """你看到的是WhatsApp聊天窗口。请做以下事情：
1. 找出最新的几条消息（对方发的+你发的）
2. 把对方发的消息翻译成中文
3. 按格式输出：

【客户】翻译后的中文内容
[原文]英文原文

【客户】翻译后的中文内容
[原文]英文原文

注意：
- 只显示最近3-5条消息
- "你发的"消息标注【我】
- "对方发的"标注【客户】
- 如果消息是图片/表情，标注 [图片/表情]"""

def read_messages():
    """截屏并翻译WhatsApp聊天消息"""
    print("[阅读] 正在截屏分析聊天内容...")
    resp = ask_ai(READ_PROMPT)
    if resp:
        print("\n" + "=" * 50)
        print("  最新聊天消息（翻译后）")
        print("=" * 50)
        print(resp)
        print("=" * 50)
    else:
        print("  ❌ 读取失败，请确保WhatsApp窗口可见")
    input("\n按回车返回菜单...")

# ================= 快捷回复 =================

QUICK_REPLIES = [
    {
        "label": "要门头照片",
        "text": "Could you send me a photo of your storefront? I'll give you a free 3D design rendering based on it."
    },
    {
        "label": "要Logo文件",
        "text": "Please share your logo file (AI/PDF/SVG format). We'll create a free mockup showing how it looks in GLOWFORGE illuminated signage."
    },
    {
        "label": "报价引导",
        "text": "Our GLOWFORGE channel letter pricing depends on letter height, font style, and finish. Could you tell me the letter size and quantity? I'll prepare a tailored quote."
    },
    {
        "label": "Raceway安装优势",
        "text": "All our signs ship pre-wired with Raceway mounting system. Your local installer just hangs and plugs — 15 minutes vs 3 hours traditional installation. Saves roughly $1k per job."
    },
    {
        "label": "免费3D设计",
        "text": "We provide free 3D rendering service — just send your artwork and we'll show you exactly how the finished sign will look, day and night."
    },
    {
        "label": "发货/物流",
        "text": "We ship worldwide via DHL/FedEx. Typical lead time is 7-15 days depending on complexity. We handle all export documentation."
    },
    {
        "label": "材质选项",
        "text": "We offer stainless steel back, acrylic faceplate, aluminum profiles, and multiple LED color temperature options (3000K warm white / 6000K cool white / RGB)."
    },
    {
        "label": "跟进CTA",
        "text": "Just following up — do you have any questions about our GLOWFORGE illuminated signage? Happy to send you a free 3D rendering if you share your artwork."
    },
    {
        "label": "价格询问（客户问价）",
        "text": "Thanks for your interest! To give you an accurate quote, I need to know: 1) Letter height? 2) Quantity? 3) Indoor or outdoor? 4) Any specific color/finish? Do you have a design file you can share?"
    },
    {
        "label": "定制尺寸",
        "text": "Custom size is never a problem — we handle all sizes from small indoor letters to large building-mounted signage. Each piece is manufactured to your exact specifications."
    },
    {
        "label": "亚克力家具介绍",
        "text": "We also custom-manufacture acrylic furniture — tables, chairs, display cases, shelves, and retail fixtures. High transparency, durable, perfect for modern interiors. Same factory-direct quality, shipped worldwide."
    },
    {
        "label": "炫彩发光字介绍",
        "text": "Our GLOWFORGE chromatic LED signs feature dual-channel independent control — smooth fluid color transitions with zero dead zones. Perfect for grabbing attention day and night. Send your artwork for a free demo video."
    },
    {
        "label": "亚克力展示柜/货架",
        "text": "We custom fabricate acrylic display cases and retail shelving — clear, tinted, or backlit. Ideal for stores, exhibitions, and museums. Fully customizable dimensions. Quote within 24 hours."
    },
    {
        "label": "欧美市场优势",
        "text": "We export regularly to the US and Europe — all products are packed in export-grade plywood crates. DHL/FedEx door-to-door. CE, RoHS, IP65 certified. Your customs clearance is stress-free."
    },
    {
        "label": "材质/不锈钢/镀锌板",
        "text": "We offer 304 stainless steel, 201 stainless steel, or galvanized zinc sheet for the sign body. Stainless steel is best for outdoor — rust-proof and durable. Galvanized is more economical for indoor."
    },
    {
        "label": "发光类型（RGB/单面/双面）",
        "text": "We have 3 lighting options: (1) RGB chromatic edge-lit — multi-color flowing effects, perfect for retail; (2) Single-face illuminated — bright, clean look; (3) Double-face illuminated — visible from both sides, great for hanging signs."
    },
    {
        "label": "宣传片服务",
        "text": "We also produce AI promotional videos for your signage: Free 15s teaser video, 60s storefront video $119, 120s brand story $239. We match local talent and voiceover for your target country — US, UK, DE, FR, ES, RU, JP, IT."
    },
    {
        "label": "多国市场（9国）",
        "text": "We export to the US, UK, Germany, France, Spain, Russia, Japan, Italy, and more. Our GLOWFORGE system supports multi-language design and country-specific video production. Tell me your target market and I'll tailor the solution."
    },
    {
        "label": "生产周期",
        "text": "Typical lead time: 7-10 days for standard channel letters, 10-15 days for custom designs. We'll send you photos/videos before shipping for your approval."
    },
]

def quick_replies():
    """快捷回复菜单"""
    while True:
        print("\n" + "=" * 50)
        print("  快捷回复 — 选择要发送的文案")
        print("=" * 50)
        for i, qr in enumerate(QUICK_REPLIES, 1):
            print(f"  [{i}] {qr['label']}")
        print("  [0] 返回主菜单")
        print("=" * 50)

        try:
            choice = input("请选择 (0-{}): ".format(len(QUICK_REPLIES))).strip()
        except (EOFError, KeyboardInterrupt):
            return

        if choice == "0":
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(QUICK_REPLIES):
                msg = QUICK_REPLIES[idx]["text"]
                print(f"\n  即将发送:\n  → {msg[:80]}...")
                confirm = input("  确认发送？[回车=y, n=取消]: ").strip().lower()
                if confirm in ("", "y", "yes"):
                    print("  5秒后开始发送，请确保WhatsApp窗口可见...")
                    time.sleep(5)
                    send_message(msg)
                else:
                    print("  已取消")
            else:
                print("  无效选择")
        except ValueError:
            print("  请输入数字")

# ================= 回复模式 =================

def reply_mode():
    """用户打中文 → 翻译成英文 → 发送"""
    print("\n" + "=" * 50)
    print("  回复模式 — 打中文，发英文")
    print("  输入 q 返回菜单")
    print("=" * 50)

    while True:
        try:
            chinese = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not chinese:
            continue
        if chinese.lower() == "q":
            break

        # 翻译
        english = translate_chinese(chinese)
        if not english:
            print("  ❌ 翻译失败，请重试")
            continue

        print(f"\n  [英文] {english}")

        # 确认
        action = input("  [回车=发送, r=重写, q=取消]: ").strip().lower()
        if action == "r":
            continue
        elif action == "q":
            print("  已取消")
            continue
        else:
            print("  5秒后开始发送，请确保WhatsApp窗口可见...")
            time.sleep(5)
            send_message(english)

# ================= 主菜单 =================

def show_banner():
    print("=" * 55)
    print("  WhatsApp 中译英回复助手 v1")
    print("  博汇 — 发光字 · 炫彩字 · 亚克力工艺 · 亚克力家具")
    print("  你打中文 · 它发地道英文")
    print("=" * 55)

def main():
    show_banner()

    while True:
        print("\n" + "-" * 45)
        print("  [1] 回复客户   — 打中文，发英文")
        print("  [2] 阅读消息   — 截屏翻译最新消息")
        print("  [3] 快捷回复   — 常用语一键发送")
        print("  [0] 退出")
        print("-" * 45)

        try:
            choice = input("  请选择 (0-3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if choice == "1":
            reply_mode()
        elif choice == "2":
            read_messages()
        elif choice == "3":
            quick_replies()
        elif choice == "0":
            print("  再见！")
            break
        else:
            print("  无效选择，请输入 0-3")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n再见！")
        sys.exit(0)
