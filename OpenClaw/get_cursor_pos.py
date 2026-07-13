#!/usr/bin/env python3
"""鼠标坐标查看器 — 把鼠标放到目标位置，看终端输出坐标"""
import pyautogui, time

print("鼠标坐标查看器")
print("把鼠标移到你想获取坐标的位置")
print("每2秒显示一次当前坐标")
print("按 Ctrl+C 退出")
print()

try:
    while True:
        x, y = pyautogui.position()
        print(f"  当前坐标: ({x}, {y})", end="\r")
        time.sleep(0.5)
except KeyboardInterrupt:
    print(f"\n\n最后坐标: ({x}, {y})")
    print("记录这个数字，发给我")
