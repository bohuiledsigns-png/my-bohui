"""
OpenClaw 自动化获客系统 — Hermes V4 联动入口
物理路径: D:\Bohui_Global_Push\OpenClaw
"""

import os, sys

OPENCLAW_ROOT = os.path.dirname(os.path.abspath(__file__))
WIKI_ROOT = r"D:\Bohui_Global_Push\Sign_Industry_Wiki"
CHECKING_CENTER = r"D:\Bohui_Global_Push\OpenClaw_Checking_Center"

def health_check():
    """检查所有核心路径是否就绪"""
    paths = [OPENCLAW_ROOT, WIKI_ROOT, CHECKING_CENTER]
    for p in paths:
        if not os.path.exists(p):
            print(f"[FAIL] {p} 不可达")
            return False
    print("[PASS] 所有核心路径就绪")
    return True

if __name__ == "__main__":
    print("OpenClaw Hermes V4 联动引擎启动...")
    health_check()
