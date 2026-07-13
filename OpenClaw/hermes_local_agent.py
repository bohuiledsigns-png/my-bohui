#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes 本地执行代理 — 在你的电脑上常驻运行
接收 Hermes 发来的鼠标指令，在本地执行
"""

import pyautogui
import random
import time
import json
import os
import subprocess

# 指令暂存文件（Hermes 写这里，代理读这里）
INBOX = r"D:\Bohui_Global_Push\_agent_commands.json"
OUTBOX = r"D:\Bohui_Global_Push\_agent_response.json"

pyautogui.FAILSAFE = True  # 鼠标移到左上角紧急停止

def execute_command(cmd):
    action = cmd.get("action", "")
    print(f"[执行] {action}")
    
    if action == "click":
        x, y = cmd["x"], cmd["y"]
        dur = random.uniform(0.3, 0.8)
        pyautogui.moveTo(x, y, duration=dur)
        time.sleep(random.uniform(0.1, 0.2))
        pyautogui.click()
        time.sleep(random.uniform(0.5, 1.5))
        return {"status": "ok", "action": "click", "at": (x, y)}
    
    elif action == "type":
        text = cmd["text"]
        for char in text:
            if random.random() < 0.05:
                pyautogui.typewrite(char + "q")
                time.sleep(0.1)
                pyautogui.press("backspace")
            pyautogui.typewrite(char)
            time.sleep(random.uniform(0.04, 0.12))
        return {"status": "ok", "action": "type", "chars": len(text)}
    
    elif action == "paste":
        text = cmd["text"].replace('"', '\\"')
        subprocess.run(
            f'powershell -command "Set-Clipboard -Value \\\"{text}\\\""',
            shell=True, capture_output=True
        )
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "v")
        return {"status": "ok", "action": "paste"}
    
    elif action == "hotkey":
        keys = cmd["keys"]
        pyautogui.hotkey(*keys)
        return {"status": "ok", "action": "hotkey", "keys": keys}
    
    elif action == "scroll":
        pyautogui.scroll(cmd.get("amount", -300))
        return {"status": "ok", "action": "scroll"}
    
    elif action == "wait":
        time.sleep(cmd.get("seconds", 1))
        return {"status": "ok", "action": "wait"}
    
    elif action == "screenshot":
        img = pyautogui.screenshot()
        path = cmd.get("path", r"D:\Bohui_Global_Push\_agent_screenshot.png")
        img.save(path)
        return {"status": "ok", "action": "screenshot", "path": path}
    
    else:
        return {"status": "error", "msg": f"未知动作: {action}"}


print("=" * 60)
print("  Hermes 本地执行代理")
print("  正在监听 D:\\_agent_commands.json ...")
print("  按 Ctrl+C 停止")
print("=" * 60)

while True:
    if os.path.exists(INBOX):
        with open(INBOX, "r", encoding="utf-8") as f:
            cmds = json.load(f)
        os.remove(INBOX)
        
        if not isinstance(cmds, list):
            cmds = [cmds]
        
        results = []
        for cmd in cmds:
            result = execute_command(cmd)
            results.append(result)
            
            # 随机延迟模仿真人
            delay = random.uniform(0.5, 2.0)
            time.sleep(delay)
        
        with open(OUTBOX, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"  ✅ 执行完毕, 响应已写入 {OUTBOX}")
    
    time.sleep(1)
