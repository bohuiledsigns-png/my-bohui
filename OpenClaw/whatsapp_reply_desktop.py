#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp 中译英回复助手 v2 — 桌面版
博汇 GLOWFORGE — 发光字 · 炫彩字 · 亚克力工艺 · 亚克力家具
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import os.path
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

# ================= 配置 =================
# --- 阿里云 DashScope（翻译 + 生图） ---
ALI_KEY = "sk-468fb68eaf4d4097abaa48327716ccc0"
ALI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
TRANSLATE_MODEL = "qwen3.7-max"
IMAGE_MODEL = "wan2.7-image-pro"

# --- 旧中转站（仅用于WhatsApp视觉定位，GPT-4o-mini看图更准） ---
VISION_KEY = "sk-ym9wY6TMotRVF8K4JnaEUt2mnK5cH71M5KhVMob55LSLjoft"
VISION_URL = "https://api.getgoapi.com/v1/chat/completions"
VISION_MODEL = "gpt-4o-mini"

# ================= 翻译提示词 =================
TRANSLATE_PROMPT = """你是一个专业的中译英翻译，专精于广告标识与亚克力制品行业。用户给你中文，你输出地道英文。

公司背景：Bohui（博汇），中国GLOWFORGE工厂，产品出口美国、英国、德国、法国、西班牙、俄罗斯、日本、意大利等全球市场。

产品线：
- 招牌广告发光字 / 炫彩发光字 → illuminated signage, channel letters, GLOWFORGE chromatic LED signs
- 亚克力工艺制品 → acrylic fabrication, acrylic display, acrylic signage
- 亚克力家具 → acrylic furniture (tables, chairs, shelves, display cases, retail fixtures)
- AI宣传片 → promotional video (15s free, 60s $119, 120s $239)

材质：304不锈钢 / 201不锈钢 / 镀锌板
发光类型：RGB炫彩围边 / 单面发光 / 双面发光

规则：
- 扮演博汇销售Philip，语气专业、友好、B2B
- 保留品牌名: Bohui, GLOWFORGE, Raceway
- 术语准确: channel letters, LED modules, raceway mounting, faceplate, trim cap, IP65, CE
- 英文简洁地道，不要中式英语
- 直接输出翻译结果，不要解释

直接翻译以下中文到英文："""

QUICK_REPLIES = [
    ("📷 要门头照片", "Could you send me a photo of your storefront? I'll give you a free 3D design rendering based on it."),
    ("🎨 要Logo文件", "Please share your logo file (AI/PDF/SVG). We'll create a free mockup for you."),
    ("💰 报价引导", "Our GLOWFORGE pricing depends on letter height, font style, and finish. Could you tell me the size and quantity?"),
    ("🔧 Raceway安装", "All signs ship pre-wired with Raceway mounting. Your installer just hangs and plugs — saves ~$1k per job."),
    ("🎁 免费3D设计", "We provide free 3D rendering — send your artwork and we'll show you how the finished sign will look."),
    ("🚚 发货/物流", "We ship worldwide via DHL/FedEx. Lead time 7-15 days. We handle all export documentation."),
    ("🔩 材质选项", "304 stainless steel, 201 stainless steel, or galvanized. Outdoor? I recommend 304 — rust-proof."),
    ("🌈 发光类型", "3 options: RGB chromatic edge-lit, single-face, or double-face illumination. Which suits your project?"),
    ("🎬 宣传片服务", "We make AI promo videos: 15s free teaser, 60s $119, 120s $239. Local talent matched to your country."),
    ("🌍 多国市场", "We export to US, UK, DE, FR, ES, RU, JP, IT and more. Multi-language support available."),
    ("📅 生产周期", "Standard 7-10 days for channel letters, 10-15 days for custom. We send photos before shipping."),
    ("🪑 亚克力家具", "We custom-make acrylic furniture — tables, chairs, display cases, shelves. Factory direct, worldwide shipping."),
]

READ_PROMPT = """你看到的是WhatsApp聊天窗口。找出最新消息，把对方发的翻译成中文，按格式输出：
【客户】翻译后的中文
[原文]英文原文

只显示最近3-5条消息，你的消息标注【我】，对方标注【客户】。图片标注[图片]。"""

# ================= 核心函数 =================

def ask_ali_text(prompt, text):
    """用阿里云Qwen翻译"""
    payload = {
        "model": TRANSLATE_MODEL,
        "messages": [{"role": "user", "content": prompt + "\n\n" + text}],
        "max_tokens": 1500
    }
    headers = {"Authorization": f"Bearer {ALI_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(f"{ALI_BASE}/chat/completions", headers=headers, json=payload, timeout=60)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            time.sleep(2)
        except:
            time.sleep(2)
    return None

def ask_gpt_vision(prompt):
    """用旧API做视觉定位（GPT-4o-mini看图比Qwen更稳）"""
    b64 = screenshot_base64()
    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}],
        "max_tokens": 500
    }
    headers = {"Authorization": f"Bearer {VISION_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(VISION_URL, headers=headers, json=payload, timeout=45)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            time.sleep(2)
        except:
            time.sleep(2)
    return None

def screenshot_base64():
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def find_input_box():
    resp = ask_gpt_vision("你看到的是WhatsApp界面。找到底部聊天输入框('Type a message')，回复中心坐标，格式: (x, y)。只回复坐标。")
    if resp:
        m = re.search(r'[\(（]\s*(\d{1,4})\s*[,，]\s*(\d{1,4})\s*[\)）]', resp)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    return (800, 950)

def paste_text(text):
    import subprocess
    escaped = text.replace('"', '\\"').replace('\n', '\\n')
    subprocess.run(f'powershell -command "Set-Clipboard -Value \\\"{escaped}\\""', shell=True, capture_output=True)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

def send_whatsapp(text):
    pos = find_input_box()
    pyautogui.moveTo(pos[0], pos[1], duration=random.uniform(0.3, 0.8))
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.click()
    time.sleep(random.uniform(1, 2))
    paste_text(text)
    time.sleep(random.uniform(0.3, 0.8))
    pyautogui.press("enter")
    time.sleep(1)

def translate_chinese(text):
    return ask_ali_text(TRANSLATE_PROMPT, text)

# ================= AI 生图（通义万相） =================

def generate_image(prompt):
    """用阿里云通义万相生成效果图，返回图片URL"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
    payload = {
        "model": IMAGE_MODEL,
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": prompt}]}
            ]
        },
        "parameters": {"n": 1, "size": "1024*1024"}
    }
    headers = {
        "Authorization": f"Bearer {ALI_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable"
    }

    # 提交任务
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    if r.status_code != 200:
        return None, f"提交失败: {r.text[:200]}"
    task_id = r.json().get("output", {}).get("task_id", "")
    if not task_id:
        return None, "获取task_id失败"

    # 轮询结果
    status_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    for _ in range(30):
        time.sleep(3)
        r2 = requests.get(status_url, headers={"Authorization": f"Bearer {ALI_KEY}"}, timeout=15)
        data = r2.json()
        status = data.get("output", {}).get("task_status", "")
        if status == "SUCCEEDED":
            choices = data.get("output", {}).get("choices", [])
            if choices:
                content_list = choices[0].get("message", {}).get("content", [])
                for item in content_list:
                    if "image" in item:
                        return item["image"], None
                return None, "未找到图片URL"
            return None, "结果为空"
        elif status == "FAILED":
            msg = data.get("output", {}).get("message", "未知错误")
            return None, f"生成失败: {msg}"
    return None, "生成超时"

def read_whatsapp():
    return ask_gpt_vision(READ_PROMPT)


# ================= 文件发送 =================

def human_click(pos, delay=1):
    pyautogui.moveTo(pos[0], pos[1], duration=random.uniform(0.3, 0.8))
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.click()
    time.sleep(delay)

def find_element(prompt, fallback=None):
    resp = ask_gpt_vision(prompt)
    if resp:
        m = re.search(r'[\(（]\s*(\d{1,4})\s*[,，]\s*(\d{1,4})\s*[\)）]', resp)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    return fallback

def send_media_file(file_path):
    """
    WhatsApp Web 发送文件流程:
    1. 点附件按钮(📎)
    2. 点"Photos & Videos"
    3. 文件对话框 → 粘贴路径 → 回车
    4. 等待上传 → 发送
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # Step 1: 点附件按钮
    print("[1/5] 找附件按钮...")
    clip = find_element(
        "你看到的是WhatsApp界面。找到底部输入框左边的附件按钮(📎回形针图标)，回复中心坐标，格式: (x, y)。只回复坐标。",
        fallback=(100, 920)
    )
    human_click(clip, delay=1.5)

    # Step 2: 选"Photos & Videos"或"Document"
    is_image = ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    if is_image:
        print("[2/5] 选 Photos & Videos...")
        pv = find_element(
            "WhatsApp的附件菜单已打开(回形针点击后的弹出菜单)。找到'Photos & Videos'或'照片和视频'选项，回复中心坐标。",
            fallback=None
        )
        if not pv:
            pv = find_element(
                "找到选项'Photos & Videos'，回复中心坐标。",
                fallback=None
            )
    else:
        print("[2/5] 选 Document...")
        pv = find_element(
            "WhatsApp的附件菜单已打开。找到'Document'或'文件'选项，回复中心坐标。",
            fallback=None
        )

    if not pv:
        print("  附件菜单没找到，尝试用快捷键Ctrl+O...")
        pyautogui.hotkey('ctrl', 'o')
        time.sleep(2)
    else:
        human_click(pv, delay=2.5)

    # Step 3: Windows文件对话框 → 输入路径
    print("[3/5] 文件对话框已打开，输入路径...")
    time.sleep(1.5)

    # 尝试多种方式输入文件路径
    path_quoted = f'"{file_path}"' if ' ' in file_path else file_path

    # 方式1: 直接写入路径
    pyautogui.write(path_quoted, interval=0.02)
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(1)

    # 如果没有成功，试试Ctrl+V
    if not os.path.isfile(file_path):
        # Try clipboard paste approach
        subprocess.run(
            f'powershell -command "Set-Clipboard -Value \\\"{file_path}\\\""',
            shell=True, capture_output=True
        )
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        pyautogui.press('enter')

    # Step 4: 等待上传
    print("[4/5] 上传中...")
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    upload_wait = max(5, min(int(file_size_mb * 2), 60))  # 5秒~60秒，按文件大小
    print(f"  文件大小: {file_size_mb:.1f}MB, 等待约{upload_wait}秒...")
    time.sleep(upload_wait)

    # Step 5: 发送
    print("[5/5] 发送...")
    pyautogui.press('enter')
    time.sleep(2)
    print("✅ 发送完成!")


# ================= 效果图发送（直接Ctrl+V） =================

def send_image_clipboard(image_path):
    """把图片加载到剪贴板，Ctrl+V发送到WhatsApp（绕过附件菜单）"""
    print("[方法B] 剪贴板粘贴图片...")
    # 用PowerShell加载图片到剪贴板
    ps_script = f'''
    Add-Type -AssemblyName System.Windows.Forms
    $img = [System.Drawing.Image]::FromFile("{image_path}")
    [System.Windows.Forms.Clipboard]::SetImage($img)
    $img.Dispose()
    '''
    subprocess.run(['powershell', '-command', ps_script], shell=True, capture_output=True)
    time.sleep(0.5)

    # 点一下输入框
    pos = find_input_box()
    human_click(pos, delay=0.5)

    # Ctrl+V
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(2)  # 等图片加载

    # Enter发送
    pyautogui.press('enter')
    time.sleep(1)
    print("✅ 图片已发送!")


# ================= 桌面GUI =================

class ReplyApp:
    def __init__(self, root):
        self.root = root
        root.title("WhatsApp 中译英回复助手 v2")
        root.geometry("820x680")
        root.minsize(700, 600)
        root.configure(bg="#0f121c")

        # 设置样式
        self.setup_styles()
        self.build_ui()

        self.last_translation = ""

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TFrame", background="#0f121c")
        style.configure("Card.TFrame", background="#1a1d2e", relief="flat")
        style.configure("Status.TLabel", background="#0f121c", foreground="#888")
        style.configure("Title.TLabel", background="#0f121c", foreground="#00f2ff", font=("Inter", 10, "bold"))
        style.configure("Action.TButton", font=("Inter", 9, "bold"), padding=6)

    def build_ui(self):
        # === 标题栏 ===
        title_frame = tk.Frame(self.root, bg="#0f121c", pady=12)
        title_frame.pack(fill="x")

        tk.Label(title_frame, text="WhatsApp 中译英回复助手", fg="#00f2ff", bg="#0f121c",
                 font=("Inter", 16, "bold")).pack()
        tk.Label(title_frame, text="博汇 — 发光字 · 炫彩字 · 亚克力工艺 · 亚克力家具",
                 fg="#D4AF37", bg="#0f121c", font=("Inter", 9)).pack()

        # === 主内容 ===
        main_frame = tk.Frame(self.root, bg="#0f121c")
        main_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # -- 左: 会话记录 --
        left = tk.Frame(main_frame, bg="#0f121c")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(left, text="📋 会话记录", fg="#00f2ff", bg="#0f121c",
                 font=("Inter", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 4))

        self.chat_log = scrolledtext.ScrolledText(
            left, wrap="word", state="disabled",
            bg="#1a1d2e", fg="#e0e0e0", insertbackground="#00f2ff",
            font=("Consolas", 10), relief="flat", borderwidth=0,
            padx=12, pady=8, height=18
        )
        self.chat_log.pack(fill="both", expand=True)

        # -- 右: 输入区 --
        right = tk.Frame(main_frame, bg="#0f121c", width=320)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)

        # 输入
        tk.Label(right, text="✏️ 你的回复（打中文）", fg="#00f2ff", bg="#0f121c",
                 font=("Inter", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 4))

        self.input_text = scrolledtext.ScrolledText(
            right, wrap="word", height=6,
            bg="#1a1d2e", fg="#fff", insertbackground="#00f2ff",
            font=("Microsoft YaHei", 11), relief="flat", borderwidth=0,
            padx=10, pady=8
        )
        self.input_text.pack(fill="x", pady=(0, 8))
        self.input_text.bind("<Control-Return>", lambda e: self.do_translate())

        # 翻译按钮行
        btn_row = tk.Frame(right, bg="#0f121c")
        btn_row.pack(fill="x", pady=(0, 4))

        self.translate_btn = tk.Button(
            btn_row, text="🌐 翻译", command=self.do_translate,
            bg="#00f2ff", fg="#000", font=("Inter", 10, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2"
        )
        self.translate_btn.pack(side="left", padx=(0, 6))

        self.send_btn = tk.Button(
            btn_row, text="📤 发送", command=self.do_send,
            bg="#ff0050", fg="#fff", font=("Inter", 10, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2", state="disabled"
        )
        self.send_btn.pack(side="left")

        # 英文预览
        tk.Label(right, text="📝 英文预览", fg="#D4AF37", bg="#0f121c",
                 font=("Inter", 10, "bold"), anchor="w").pack(fill="x", pady=(8, 4))

        self.preview_text = scrolledtext.ScrolledText(
            right, wrap="word", height=5,
            bg="#1a1d2e", fg="#D4AF37", insertbackground="#D4AF37",
            font=("Consolas", 10), relief="flat", borderwidth=0,
            padx=10, pady=8
        )
        self.preview_text.pack(fill="x", pady=(0, 4))

        # === 工具栏 ===
        tool_frame = tk.Frame(self.root, bg="#0f121c", pady=6)
        tool_frame.pack(fill="x", padx=16)

        self.read_btn = tk.Button(
            tool_frame, text="📖 阅读消息", command=self.do_read,
            bg="#2a2d3e", fg="#fff", font=("Inter", 9),
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.read_btn.pack(side="left", padx=(0, 6))

        self.quick_btn = tk.Button(
            tool_frame, text="⚡ 快捷回复", command=self.show_quick_replies,
            bg="#2a2d3e", fg="#fff", font=("Inter", 9),
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.quick_btn.pack(side="left", padx=(0, 6))

        self.image_btn = tk.Button(
            tool_frame, text="🎨 生成效果图", command=self.do_generate_image,
            bg="#2a2d3e", fg="#D4AF37", font=("Inter", 9),
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.image_btn.pack(side="left", padx=(0, 6))

        self.file_btn = tk.Button(
            tool_frame, text="📎 发送文件", command=self.do_send_file,
            bg="#2a2d3e", fg="#fff", font=("Inter", 9),
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.file_btn.pack(side="left", padx=(0, 6))

        # === 快捷回复按钮行（可滚动） ===
        self.qr_frame = tk.Frame(self.root, bg="#161926")
        self.qr_frame.pack(fill="x", padx=16, pady=(0, 4))
        self.qr_visible = False

        # === 状态栏 ===
        self.status_bar = tk.Frame(self.root, bg="#0a0c14", height=28)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(
            self.status_bar, text="✅ 就绪 | 阿里云Qwen翻译 + 通义万相生图",
            fg="#888", bg="#0a0c14", font=("Inter", 9), anchor="w"
        )
        self.status_label.pack(side="left", padx=16, pady=4)

        self.add_log("ℹ️ 机器人已启动。打开WhatsApp Web后使用。")
        self.add_log("💡 打中文 → 点翻译 → 确认英文 → 发送\n")

    def set_status(self, msg):
        self.status_label.config(text=msg)
        self.root.update_idletasks()

    def add_log(self, msg):
        self.chat_log.config(state="normal")
        self.chat_log.insert("end", msg + "\n")
        self.chat_log.see("end")
        self.chat_log.config(state="disabled")

    # ---------- 翻译 ----------
    def do_translate(self):
        chinese = self.input_text.get("1.0", "end-1c").strip()
        if not chinese:
            messagebox.showinfo("提示", "请先输入中文")
            return

        self.set_status("⏳ 翻译中...")
        self.translate_btn.config(state="disabled")

        def work():
            result = translate_chinese(chinese)
            self.root.after(0, lambda: self._on_translated(result, chinese))

        threading.Thread(target=work, daemon=True).start()

    def _on_translated(self, result, original):
        self.translate_btn.config(state="normal")
        if result:
            self.last_translation = result
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", result)
            self.send_btn.config(state="normal")
            self.add_log(f"🀄 你: {original}")
            self.add_log(f"🌐 EN: {result}\n")
            self.set_status("✅ 翻译完成，可发送")
        else:
            self.set_status("❌ 翻译失败，请重试")

    # ---------- 发送 ----------
    def do_send(self):
        if not self.last_translation:
            messagebox.showinfo("提示", "请先翻译")
            return

        if not messagebox.askyesno("确认发送", "即将发送到WhatsApp，请确保窗口可见。\n继续吗？"):
            return

        self.set_status("⏳ 正在发送...")
        self.send_btn.config(state="disabled")

        def work():
            try:
                send_whatsapp(self.last_translation)
                self.root.after(0, lambda: self._on_sent())
            except Exception as e:
                self.root.after(0, lambda: self._on_send_error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _on_sent(self):
        self.send_btn.config(state="normal")
        self.add_log("✅ 已发送\n")
        self.set_status("✅ 发送成功")
        self.input_text.delete("1.0", "end")
        self.preview_text.delete("1.0", "end")
        self.last_translation = ""

    def _on_send_error(self, err):
        self.send_btn.config(state="normal")
        self.add_log(f"❌ 发送失败: {err}")
        self.set_status("❌ 发送失败")

    # ---------- 阅读消息 ----------
    def do_read(self):
        self.set_status("⏳ 正在截屏分析...")
        self.read_btn.config(state="disabled")

        def work():
            result = read_whatsapp()
            self.root.after(0, lambda: self._on_read(result))

        threading.Thread(target=work, daemon=True).start()

    def _on_read(self, result):
        self.read_btn.config(state="normal")
        if result:
            self.add_log("📖 === 最新消息 ===")
            for line in result.strip().split("\n"):
                self.add_log(f"  {line}")
            self.add_log("")
            self.set_status("✅ 消息已读取")
        else:
            self.set_status("❌ 读取失败，确保WhatsApp窗口可见")

    # ---------- 快捷回复 ----------
    def show_quick_replies(self):
        if self.qr_visible:
            for w in self.qr_frame.winfo_children():
                w.destroy()
            self.qr_visible = False
            return

        self.qr_visible = True
        for i, (label, text) in enumerate(QUICK_REPLIES):
            row = i // 4
            col = i % 4
            btn = tk.Button(
                self.qr_frame, text=label,
                command=lambda t=text, l=label: self.use_quick_reply(t, l),
                bg="#2a2d3e", fg="#fff", font=("Inter", 8),
                relief="flat", padx=8, pady=4, cursor="hand2",
                width=18
            )
            btn.grid(row=row, column=col, padx=3, pady=2, sticky="w")

    def use_quick_reply(self, text, label):
        self.last_translation = text
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.send_btn.config(state="normal")
        self.add_log(f"⚡ 快捷回复: {label}")
        self.add_log(f"🌐 EN: {text[:60]}...\n")
        self.set_status("✅ 已加载快捷回复，点击发送")
        self.show_quick_replies()  # 收起

    # ---------- AI生图 ----------
    def do_generate_image(self):
        # 弹窗输入描述
        dialog = tk.Toplevel(self.root)
        dialog.title("AI 生成效果图")
        dialog.geometry("450x350")
        dialog.configure(bg="#0f121c")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="描述你想要的效果图（中文）", fg="#00f2ff",
                 bg="#0f121c", font=("Inter", 11, "bold")).pack(pady=(16, 4))
        tk.Label(dialog, text="例如：双通道炫彩发光字 'GLOWFORGE'，不锈钢底壳，夜晚门头效果",
                 fg="#666", bg="#0f121c", font=("Inter", 9)).pack()

        text_widget = scrolledtext.ScrolledText(
            dialog, wrap="word", height=6,
            bg="#1a1d2e", fg="#fff", insertbackground="#00f2ff",
            font=("Microsoft YaHei", 11), relief="flat", borderwidth=0,
            padx=10, pady=8
        )
        text_widget.pack(fill="both", expand=True, padx=16, pady=8)

        result_frame = tk.Frame(dialog, bg="#0f121c")
        result_frame.pack(fill="x", padx=16, pady=(0, 8))
        result_label = tk.Label(result_frame, text="", fg="#D4AF37",
                                bg="#0f121c", font=("Inter", 9), wraplength=400)
        result_label.pack()

        def on_generate():
            prompt = text_widget.get("1.0", "end-1c").strip()
            if not prompt:
                return
            # 翻译成英文再生图（通义万相用英文prompt更准）
            result_label.config(text="⏳ 翻译描述...")
            dialog.update()

            def work():
                en_prompt = ask_ali_text("把以下中文翻译成英文，用于AI生图描述：", prompt)
                if not en_prompt:
                    self.root.after(0, lambda: result_label.config(text="❌ 翻译失败"))
                    return

                self.root.after(0, lambda: result_label.config(
                    text=f"⏳ 正在生成图片... (prompt: {en_prompt[:60]}...)"))
                img_url, error = generate_image(en_prompt)

                self.root.after(0, lambda: self._on_image_result(
                    result_label, img_url, error, en_prompt, dialog))

            threading.Thread(target=work, daemon=True).start()

        btn_frame = tk.Frame(dialog, bg="#0f121c")
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))

        tk.Button(btn_frame, text="🎨 生成", command=on_generate,
                  bg="#00f2ff", fg="#000", font=("Inter", 10, "bold"),
                  relief="flat", padx=20, pady=6, cursor="hand2").pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="取消", command=dialog.destroy,
                  bg="#2a2d3e", fg="#fff", font=("Inter", 10),
                  relief="flat", padx=20, pady=6, cursor="hand2").pack(side="left")

    def _on_image_result(self, label, img_url, error, en_prompt, dialog):
        if error:
            label.config(text=f"❌ {error}")
            return

        label.config(text="✅ 效果图生成成功！")
        self.add_log(f"🎨 AI生成效果图: {en_prompt[:80]}")
        self.add_log(f"   🖼 {img_url[:100]}\n")
        self.set_status("✅ 效果图已生成")

        # 询问是否下载+发送
        if messagebox.askyesno("发送给客户？",
                               "效果图已生成！\n\n要下载并发送给当前WhatsApp客户吗？"):
            self.set_status("⏳ 下载图片并发送...")
            def work():
                try:
                    # 下载图片
                    r = requests.get(img_url, timeout=30)
                    save_dir = os.path.expanduser("~/Desktop")
                    save_path = os.path.join(save_dir, f"glowforge_ai_{int(time.time())}.png")
                    with open(save_path, "wb") as f:
                        f.write(r.content)

                    self.root.after(0, lambda: self.add_log(f"  💾 已保存: {save_path}"))
                    self.root.after(0, lambda: self.set_status("📤 正在发送到WhatsApp..."))

                    # 发送
                    send_image_clipboard(save_path)

                    self.root.after(0, lambda: self.add_log("✅ 效果图已发送给客户\n"))
                    self.root.after(0, lambda: self.set_status("✅ 效果图已发送"))
                except Exception as e:
                    self.root.after(0, lambda: self.set_status(f"❌ 发送失败: {e}"))

            threading.Thread(target=work, daemon=True).start()

        dialog.destroy()

    # ---------- 发送文件 ----------
    def do_send_file(self):
        file_path = filedialog.askopenfilename(
            title="选择要发送给客户的图片或视频",
            filetypes=[
                ("图片和视频", "*.jpg *.jpeg *.png *.gif *.bmp *.webp *.mp4 *.mov *.avi *.wmv"),
                ("图片", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"),
                ("视频", "*.mp4 *.mov *.avi *.wmv"),
            ]
        )
        if not file_path:
            return

        self.add_log(f"📎 选择文件: {os.path.basename(file_path)}")
        self.set_status("⏳ 正在发送文件...")
        self.file_btn.config(state="disabled")

        _, ext = os.path.splitext(file_path)
        is_image = ext.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

        choice = messagebox.askyesno("发送方式",
            f"文件: {os.path.basename(file_path)} ({file_size_mb:.1f}MB)\n\n"
            f"图片可用剪贴板粘贴方式（更快），视频走附件菜单。\n\n"
            + ("是 = 剪贴板粘贴（推荐，速度快）\n否 = 附件菜单上传" if is_image else
               "是 = 继续发送视频\n否 = 取消"))

        if not choice and is_image:
            # Cancel
            self.file_btn.config(state="normal")
            return

        def work():
            try:
                if is_image and choice:
                    # 尝试剪贴板方式（更快）
                    self.root.after(0, lambda: self.add_log("  📋 剪贴板粘贴方式..."))
                    send_image_clipboard(file_path)
                else:
                    # 附件菜单上传
                    self.root.after(0, lambda: self.add_log("  📎 附件菜单上传方式..."))
                    send_media_file(file_path)

                self.root.after(0, lambda: self._on_file_sent())
            except Exception as e:
                self.root.after(0, lambda: self._on_file_error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _on_file_sent(self):
        self.file_btn.config(state="normal")
        self.add_log("✅ 文件已发送\n")
        self.set_status("✅ 文件发送成功")

    def _on_file_error(self, err):
        self.file_btn.config(state="normal")
        self.add_log(f"❌ 文件发送失败: {err}")
        self.set_status("❌ 发送失败")


# ================= 启动 =================
def main():
    root = tk.Tk()
    app = ReplyApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
