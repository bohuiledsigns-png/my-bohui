#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp 视觉防封机器人 —— 真人行为模拟 · 超慢模式
保存路径: D:\Bohui_Global_Push\OpenClaw\whatsapp_visual_bot.py
"""

import pyautogui
import random
import time
import sys

# ================= 安全核心配置（超慢模式） =================
MIN_WAIT = 10
MAX_WAIT = 60
RANDOM_DISTURB = True
HUMAN_TYPING = True

# ================= 真人行为模拟 =================
def human_mouse_move(x, y):
    pyautogui.moveTo(x, y, duration=random.uniform(0.5, 1.5))

def random_disturb():
    print("[安全伪装] 随机乱点晃鼠标...")
    for _ in range(random.randint(3, 7)):
        rx = random.randint(200, 1600)
        ry = random.randint(200, 800)
        human_mouse_move(rx, ry)
        if random.random() < 0.3:
            pyautogui.click()
        time.sleep(random.uniform(0.5, 2))
    pyautogui.hotkey('alt', 'tab')
    time.sleep(random.uniform(2, 5))
    pyautogui.hotkey('alt', 'tab')

def human_type(text):
    for char in text:
        if random.random() < 0.06:
            pyautogui.typewrite(char + 'q')
            time.sleep(0.2)
            pyautogui.press('backspace')
        pyautogui.typewrite(char)
        time.sleep(random.uniform(0.05, 0.25))

def send_whatsapp_message(msg):
    print(f"\n  [发送] {msg[:40]}...")
    time.sleep(random.uniform(2, 6))
    if HUMAN_TYPING:
        human_type(msg)
    else:
        pyautogui.typewrite(msg)
    time.sleep(1)
    pyautogui.press('enter')
    print("  [OK] 发送完成")

def run_whatsapp_bot(messages):
    count = 0
    total = len(messages)
    print(f"\n=== WhatsApp 防封机器人 | 共 {total} 条消息 ===")
    for i, msg in enumerate(messages, 1):
        print(f"\n--- 第 {i}/{total} 条 ---")
        send_whatsapp_message(msg)
        count += 1
        if i < total:
            wait = random.randint(MIN_WAIT, MAX_WAIT)
            print(f"  等待 {wait} 秒...")
            time.sleep(wait)
        if count % 3 == 0 and RANDOM_DISTURB:
            random_disturb()
    print(f"\n✅ 全部 {total} 条发送完成！")

if __name__ == "__main__":
    # 从命令行参数读取消息文件，或使用默认测试内容
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            messages = [line.strip() for line in f if line.strip()]
    else:
        messages = [
            "Hi there! Just checking in — have you seen our latest GLOWFORGE dual-channel illuminated signage? We've been getting great feedback from sign shops in Sydney.",
            "Quick question — what's the approximate height of your project letters? If they're over 400mm we can spec the full dual-channel system with independent outline and fill control.",
            "Also worth mentioning — all our signs ship with pre-wired Raceway mounting. Your crew just hangs and plugs. 15 minutes vs 3 hours. Thought you'd want to know.",
        ]

    print("⚠️  请先点击 WhatsApp 输入框，让光标闪烁！")
    print(" 5秒后开始自动运行... Press Ctrl+C to abort.")
    time.sleep(5)
    run_whatsapp_bot(messages)
