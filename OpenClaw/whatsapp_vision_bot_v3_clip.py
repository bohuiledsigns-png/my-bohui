#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp 视觉驱动机器人 V3 — 剪贴板粘贴版
完全绕过输入法，零乱码风险
"""

import pyautogui
import random
import time
import base64
import json
import requests
import io
import subprocess
from PIL import Image

API_KEY = "sk-ym9wY6TMotRVF8K4JnaEUt2mnK5cH71M5KhVMob55LSLjoft"
API_URL = "https://api.getgoapi.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

MIN_WAIT = 10
MAX_WAIT = 45

# ================= 剪贴板打字 =================
def paste_text(text):
    """把文字塞进剪贴板，然后 Ctrl+V 粘贴——零输入法问题"""
    # 方法1: 用 powershell 塞剪贴板
    import subprocess
    # 先把特殊字符转义
    escaped = text.replace('"', '\\"')
    cmd = f'powershell -command "Set-Clipboard -Value \\"{escaped}\\""'
    subprocess.run(cmd, shell=True, capture_output=True)
    time.sleep(0.3)
    # Ctrl+V 粘贴
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)

def human_move_click(x, y):
    pyautogui.moveTo(x, y, duration=random.uniform(0.4, 1.2))
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.click()
    time.sleep(random.uniform(0.5, 1.5))

def random_disturb():
    for _ in range(random.randint(2, 5)):
        rx = random.randint(300, 1500)
        ry = random.randint(200, 700)
        pyautogui.moveTo(rx, ry, duration=random.uniform(0.3, 0.8))
        time.sleep(random.uniform(0.3, 1))
    pyautogui.hotkey('alt', 'tab')
    time.sleep(random.uniform(1, 3))
    pyautogui.hotkey('alt', 'tab')

# ================= AI视觉找输入框 =================
def screenshot_base64():
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def ask_ai(prompt):
    b64 = screenshot_base64()
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}],
        "max_tokens": 200
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
    except:
        pass
    return None

import re
def find_input_box():
    resp = ask_ai("你看到的是WhatsApp界面。找到底部的聊天输入框（'Type a message'），回复它的中心坐标，格式: (x,y)。只回复坐标。")
    if resp:
        m = re.search(r'[\(（]\s*(\d{1,4})\s*[,，]\s*(\d{1,4})\s*[\)）]', resp)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    return (800, 950)

# ================= 主流程 =================
def run(messages):
    print("=" * 60)
    print("  WhatsApp V3 — 剪贴板粘贴版")
    print("  零输入法问题 · 零乱码风险")
    print("=" * 60)
    
    for i, msg in enumerate(messages, 1):
        print(f"\n--- 第{i}/{len(messages)}条 ---")
        
        # AI找输入框
        pos = find_input_box()
        print(f"[视觉] 输入框: {pos}")
        human_move_click(*pos)
        time.sleep(random.uniform(1, 2))
        
        # 剪贴板粘贴（无输入法问题）
        print(f"[粘贴] {msg[:40]}...")
        paste_text(msg)
        time.sleep(random.uniform(0.5, 1))
        
        # 发送
        pyautogui.press('enter')
        print("[OK] 发送完成")
        
        if i < len(messages):
            w = random.randint(MIN_WAIT, MAX_WAIT)
            print(f"[等待] {w}秒...")
            time.sleep(w)
        if i % 3 == 0:
            random_disturb()
    
    print(f"\n✅ 全部完成！")

if __name__ == "__main__":
    messages = [
        "Hi there \u2014 Philip from Bohui, Zhongshan. We specialize in GLOWFORGE dual-channel illuminated signage. Quick question: what's the approximate letter height on your current project?",
        "If it's over 400mm we can do the full independent outline + fill control setup. Below that we recommend our single-channel chroma \u2014 same great quality, lower cost.",
        "Also \u2014 all our signs ship pre-wired with Raceway mounting. Your crew just hangs and plugs. 15 minutes vs 3 hours. Saves roughly $1k in installation per job.",
    ]
    print("请确保 WhatsApp 窗口可见")
    print("5秒后开始...")
    time.sleep(5)
    run(messages)
