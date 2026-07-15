#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp 视觉驱动机器人 V2
眼睛: GPT-4o-mini（中转站）／ 手: pyautogui
全程视觉闭环：截图 → AI分析界面 → 鼠标操作 → 发送
"""

import pyautogui
import random
import time
import base64
import json
import requests
import io
import os
import subprocess
from PIL import Image

# ================= 中转站配置 =================
API_KEY = "sk-ym9wY6TMotRVF8K4JnaEUt2mnK5cH71M5KhVMob55LSLjoft"
API_URL = "https://api.getgoapi.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

# ================= 安全配置 =================
MIN_WAIT = 10
MAX_WAIT = 45

# ================= 视觉分析函数 =================
def screenshot_base64():
    """截屏并返回base64"""
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def ask_ai_where_to_click(prompt):
    """让AI看图，返回点击坐标"""
    b64 = screenshot_base64()
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }
        ],
        "max_tokens": 300
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                print(f"  API错误({r.status_code}), 重试{attempt+1}...")
                time.sleep(2)
        except Exception as e:
            print(f"  请求异常: {e}, 重试{attempt+1}...")
            time.sleep(2)
    return None

def parse_coordinates(ai_response):
    """从AI回复中提取坐标"""
    import re
    # 支持格式: (500, 300) 或 x=500 y=300 或 500,300
    patterns = [
        r'[\(（]\s*(\d{1,4})\s*[,，]\s*(\d{1,4})\s*[\)）]',
        r'[xX]\s*[=:]\s*(\d{1,4}).*?[yY]\s*[=:]\s*(\d{1,4})',
        r'(\d{3,4})\s*[,，]\s*(\d{3,4})',
    ]
    for pat in patterns:
        m = re.search(pat, ai_response)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    return None

# ================= 真人行为模拟 =================
def human_move_click(x, y):
    pyautogui.moveTo(x, y, duration=random.uniform(0.4, 1.2))
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.click()
    time.sleep(random.uniform(0.5, 1.5))

def human_type(text):
    """真人打字前先强制切英文"""
    pyautogui.keyDown("shift")
    pyautogui.keyDown("ctrl")
    pyautogui.press("space")
    pyautogui.keyUp("ctrl")
    pyautogui.keyUp("shift")
    time.sleep(0.3)
    for char in text:
        if random.random() < 0.05:
            pyautogui.typewrite(char + random.choice('qwzx'))
            time.sleep(0.15)
            pyautogui.press('backspace')
        pyautogui.typewrite(char)
        time.sleep(random.uniform(0.04, 0.2))

def random_disturb():
    print("[伪装] 随机活动...")
    for _ in range(random.randint(2, 5)):
        rx = random.randint(300, 1500)
        ry = random.randint(200, 700)
        pyautogui.moveTo(rx, ry, duration=random.uniform(0.3, 0.8))
        time.sleep(random.uniform(0.3, 1))
    pyautogui.hotkey('alt', 'tab')
    time.sleep(random.uniform(1, 3))
    pyautogui.hotkey('alt', 'tab')
    time.sleep(1)

# ================= 找输入框并发送 =================
def find_and_click_input():
    """让AI在截图中找WhatsApp输入框"""
    print("[视觉] 正在分析屏幕，寻找输入框...")
    resp = ask_ai_where_to_click(
        "你看到的是一个WhatsApp Web或桌面端的界面。"
        "请找到聊天输入框（通常在最底部，写着'Type a message'或'输入消息'）。"
        "回复格式: (x, y)，x和y是输入框中央的像素坐标。"
        "只回复坐标，不要其他内容。"
    )
    if not resp:
        print("[视觉] AI无响应，使用备用坐标")
        return (800, 950)
    coord = parse_coordinates(resp)
    if coord:
        print(f"[视觉] 输入框坐标: {coord}")
        return coord
    else:
        print(f"[视觉] 坐标解析失败，AI回复: {resp[:50]}")
        return (800, 950)

# ================= 主流程 =================
def run(messages):
    print("=" * 60)
    print("  WhatsApp 视觉驱动机器人 V2")
    print("  眼睛: GPT-4o-mini | 手: pyautogui")
    print("=" * 60)
    
    for i, msg in enumerate(messages, 1):
        print(f"\n--- 第{i}/{len(messages)}条 ---")
        
        # 1. 视觉定位输入框
        input_pos = find_and_click_input()
        
        # 2. 点过去
        human_move_click(*input_pos)
        time.sleep(random.uniform(1, 3))
        
        # 3. 打字
        print(f"[打字] {msg[:40]}...")
        human_type(msg)
        time.sleep(random.uniform(0.5, 1.5))
        
        # 4. 发送
        pyautogui.press('enter')
        print("[OK] 发送完成")
        
        # 5. 等待
        if i < len(messages):
            wait = random.randint(MIN_WAIT, MAX_WAIT)
            print(f"[等待] {wait}秒...")
            time.sleep(wait)
        
        # 6. 伪装
        if i % 3 == 0:
            random_disturb()
    
    print(f"\n✅ 全部{len(messages)}条发送完成！")

# ================= 测试 =================
if __name__ == "__main__":
    messages = [
        "Hi there — Philip from Bohui, Zhongshan. We specialize in GLOWFORGE dual-channel illuminated signage. Quick question: what's the approximate letter height on your current project?",
        "If it's over 400mm we can do the full independent outline + fill control setup. Below that we recommend our single-channel chroma — same great quality, lower cost.",
        "Also — all our signs ship pre-wired with Raceway mounting. Your crew just hangs and plugs. 15 minutes vs 3 hours. Saves roughly $1k in installation per job.",
    ]
    print("将向 3 个客户发送消息")
    print("请确保 WhatsApp 窗口已打开并可见")
    print("5秒后开始...")
    time.sleep(5)
    run(messages)
