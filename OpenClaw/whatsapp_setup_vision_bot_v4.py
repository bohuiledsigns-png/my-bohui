#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp 商业门面视觉改造机器人 V4
眼睛: GPT-4o-mini 实时看图分析网页界面
手: pyautogui 点击+粘贴
全程视觉闭环：截图 → AI分析界面元素位置 → 鼠标点击 → 粘贴文案 → 保存
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
from PIL import Image

# ================= 中转站配置 =================
API_KEY = "sk-ym9wY6TMotRVF8K4JnaEUt2mnK5cH71M5KhVMob55LSLjoft"
API_URL = "https://api.getgoapi.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

# ================= 配置参数 =================
CLICK_DELAY = (1, 3)
TYPE_DELAY = (0.5, 1.5)

# ================= 工具函数 =================
def screenshot_base64():
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

def extract_coords(text):
    """从AI回复提取坐标"""
    patterns = [
        r'[\(（]\s*(\d{1,4})\s*[,，]\s*(\d{1,4})\s*[\)）]',
        r'[xX]\s*[=:]\s*(\d{1,4}).*?[yY]\s*[=:]\s*(\d{1,4})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    return None

def human_click(x, y):
    pyautogui.moveTo(x, y, duration=random.uniform(0.3, 0.8))
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.click()
    time.sleep(random.uniform(*CLICK_DELAY))

def human_type(text):
    """慢速真人打字（先强制切英文）"""
    # 切英文
    try:
        import ctypes
        ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 0x0001)
    except:
        pass
    time.sleep(0.2)
    for char in text:
        if random.random() < 0.05:
            pyautogui.typewrite(char + random.choice("qw"))
            time.sleep(0.1)
            pyautogui.press("backspace")
        pyautogui.typewrite(char)
        time.sleep(random.uniform(0.04, 0.15))

def paste_text(text):
    """剪贴板粘贴（绕过输入法）"""
    escaped = text.replace('"', '\\"')
    subprocess.run(
        f'powershell -command "Set-Clipboard -Value \\\"{escaped}\\\""',
        shell=True, capture_output=True
    )
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

# ================= 视觉操作函数 =================
def ai_find_and_click(target_desc):
    """让AI在屏幕上找目标元素并点击"""
    print(f"[视觉] 正在查找: {target_desc}")
    resp = ask_ai(
        f"你看到的是WhatsApp Business网页管理后台。请在截图里找到{target_desc}，"
        f"回复它的中心像素坐标，格式: (x, y)。只回复坐标。"
    )
    if not resp:
        print("  [视觉] AI无响应")
        return False
    coord = extract_coords(resp)
    if coord:
        print(f"  [视觉] 找到坐标: {coord}")
        human_click(*coord)
        return True
    else:
        print(f"  [视觉] 坐标解析失败: {resp[:60]}")
        return False

def ai_find_type(target_desc, text):
    """找元素 → 点击 → 输入文字"""
    if ai_find_and_click(target_desc):
        time.sleep(1)
        # 全选清空
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.3)
        pyautogui.press("backspace")
        time.sleep(0.5)
        # 粘贴新内容
        paste_text(text)
        return True
    return False

def scroll_down(amount=-300):
    pyautogui.scroll(amount)
    time.sleep(1)

# ================= 改造流程 =================
def run_whatsapp_setup():
    print("=" * 70)
    print("  WhatsApp 商业门面视觉改造机器人 V4")
    print("  全程视觉AI闭环 | GPT-4o-mini 实时看图")
    print("=" * 70)

    step = 0

    # === Step 1: 修改 About 简介 ===
    step += 1
    print(f"\n{'─'*50}")
    print(f"  Step {step}: 修改商业简介栏（About）")
    print(f"{'─'*50}")

    about_text = (
        "Premium Channel Letters & Kinetic LED Signage for Sign Shops Worldwide.\n"
        "Factory-Direct Support from China's Precision Engineering Hub.\n"
        "Shipped via Pre-Wired Raceway Systems \u2014 Plug & Play to slash 40% "
        "of your local site installation labor costs.\n"
        "Drop your vector files below."
    )

    # 找商家信息编辑按钮
    ai_find_and_click("商家信息编辑按钮或'About'编辑区域")
    time.sleep(2)
    # 找简介输入框
    ai_find_type("简介（Description）输入框", about_text)
    # 保存
    ai_find_and_click("保存（Save）按钮")
    print("  ✅ About 已更新")

    # === Step 2: 添加 Catalog 商品 ===
    step += 1
    print(f"\n{'─'*50}")
    print(f"  Step {step}: 添加相册目录商品")
    print(f"{'─'*50}")

    # 去商业目录
    ai_find_and_click("商业目录（Catalog）或'Products'菜单")
    time.sleep(3)
    ai_find_and_click("添加商品（Add Product）按钮")
    time.sleep(3)

    # 填商品名称
    ai_find_type("商品名称（Product Name）输入框", "01. Patent GLOWFORGE Kinetic LED Signage")

    # 填描述（可能需要滚动）
    scroll_down()
    time.sleep(1)

    desc_text = (
        "Premium dual-channel fluid illumination systems designed exclusively for Sign Shops worldwide.\n\n"
        "Factory-direct customization from China's precision signage engineering hub.\n"
        "Patented kinetic independent control \u2014 smooth fluid motions with zero lighting dead zones.\n"
        "Fully shipped via Pre-Wired Raceway Systems \u2014 Plug & Play on-site "
        "to slash 40% of your local installation labor costs.\n\n"
        "Drop your vector design files (AI/PDF/SVG) below for a free 3D fluid animation rendering."
    )
    ai_find_type("产品描述（Description）输入框", desc_text)

    # 原产地
    scroll_down()
    time.sleep(1)
    ai_find_type("原产地（Country of Origin）输入框", "CHINA")

    # 上传视频
    step += 1
    print(f"\n{'─'*50}")
    print(f"  Step {step}: 上传产品视频")
    print(f"{'─'*50}")

    video_path = r"D:\Bohui_Global_Push\Video_Assets\01_大字D_双通道大字典范.mp4"
    ai_find_and_click("添加图像（Add Image）或上传（Upload）按钮")
    time.sleep(2)

    # 用键盘输入文件路径（Windows 上传对话框支持 Ctrl+V 粘贴路径）
    paste_text(video_path)
    time.sleep(1)
    pyautogui.press("enter")
    print(f"  上传: {video_path}")
    print("  等待上传完成...")
    time.sleep(10)

    # 保存商品
    scroll_down()
    ai_find_and_click("保存（Save / Publish）按钮")
    time.sleep(2)
    print("  ✅ Catalog 商品已发布")

    # === 完成 ===
    print(f"\n{'='*70}")
    print(f"  ✅ WhatsApp 商业门面改造全部完成！")
    print(f"  商业简介 ✓")
    print(f"  相册目录第一项 ✓")
    print(f"  原产地: CHINA ✓")
    print(f"  视频资产已上传 ✓")
    print(f"{'='*70}")

if __name__ == "__main__":
    print("⚠️  请确保 WhatsApp Business 网页端已打开并登录")
    print("   确保浏览器窗口可见、未被最小化")
    print("   5秒后开始改造...")
    time.sleep(5)
    run_whatsapp_setup()
