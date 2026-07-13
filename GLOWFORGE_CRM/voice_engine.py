"""Voice Engine — 阿里云 Qwen-TTS 多语言语音合成

基于阿里云百炼 Qwen-TTS 模型，支持多语言、多音色语音合成。
用于：
  - 宣传视频多语言配音（英语 / 阿拉伯语 / 中文等）
  - WhatsApp 语音回复消息
  - 获客内容配音（TikTok / Instagram 视频旁白）

使用说明：
    from voice_engine import synthesize

    # 英语配音，保存到文件
    url, path = synthesize("Hello world!", lang="English", voice="Cherry")

    # 阿拉伯语配音
    url, path = synthesize("مرحبا بالعالم", lang="Auto", voice="Cherry")

依赖：requests (已安装)
"""

import os
import requests
import json
import uuid
import time
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────
# 复用 ai_engine.py 里的阿里云 Key
from ai_engine import ALI_KEY as _ali_key
ALI_KEY = _ali_key

TTS_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# 项目目录（存音频文件）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "uploads", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# ── 可用音色 ──────────────────────────────────────────
VOICES = {
    "Cherry":   {"name": "Cherry",   "gender": "female", "lang": ["en", "ar", "zh", "auto"]},
    "Chelsie":  {"name": "Chelsie",  "gender": "female", "lang": ["en", "auto"]},
    "Stella":   {"name": "Stella",   "gender": "female", "lang": ["en", "auto"]},
    # 男性音色（多角色语音用）
    "Andre":    {"name": "Andre",    "gender": "male",   "lang": ["en", "auto"]},
    "Ethan":    {"name": "Ethan",    "gender": "male",   "lang": ["en", "auto"]},
    "Vincent":  {"name": "Vincent",  "gender": "male",   "lang": ["en", "auto"]},
}

# ── 多角色语音映射 ────────────────────────────────────
VOICE_ROLE_MAP = {
    "Customer": "Cherry",   # 欧美女声，疑惑/震惊/好奇
    "Factory":  "Andre",    # 沉稳磁性男声，专业自信
    "Wisdom":   "Ethan",    # 低沉温暖男声，悬疑厚重感
}

def get_role_voice(role: str) -> str:
    """返回角色对应的 TTS 音色名称"""
    return VOICE_ROLE_MAP.get(role, DEFAULT_VOICE)

# ── 语言映射 ──────────────────────────────────────────
LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
    "ar": "Auto",
    "auto": "Auto",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
}

DEFAULT_VOICE = "Cherry"
DEFAULT_LANG = "Auto"

# ── 核心函数 ──────────────────────────────────────────


def list_voices():
    """返回可用音色列表"""
    return list(VOICES.keys())


def synthesize(text: str, lang: str = "Auto", voice: str = "Cherry",
               response_format: str = "wav", sample_rate: int = 24000,
               filename: str = None) -> tuple:
    """文字转语音，返回 (audio_url, local_path)

    Args:
        text: 要合成的文字
        lang: 语言 (English / Chinese / Auto / Arabic / ...)
        voice: 音色 (Cherry / Chelsie / Stella)
        response_format: 音频格式 (wav / mp3 / pcm / opus)
        sample_rate: 采样率 (8000 / 16000 / 24000)
        filename: 自定义文件名（不含扩展名），默认自动生成

    Returns:
        (audio_url, local_path) — audio_url 有效期24小时
        失败返回 (None, None)
    """
    if not text or not text.strip():
        return None, None

    payload = {
        "model": "qwen3-tts-flash",
        "input": {
            "text": text.strip(),
            "voice": voice,
            "language_type": lang,
        },
        "parameters": {
            "response_format": response_format,
            "sample_rate": sample_rate,
        },
    }

    headers = {
        "Authorization": f"Bearer {ALI_KEY}",
        "Content-Type": "application/json",
    }

    _no_proxy = {"http": None, "https": None}
    for attempt in range(3):
        try:
            r = requests.post(TTS_ENDPOINT, headers=headers, json=payload, timeout=120, proxies=_no_proxy)
            if r.status_code == 200:
                data = r.json()
                audio_url = data.get("output", {}).get("audio", {}).get("url", "")
                if not audio_url:
                    print(f"[Voice] 返回中没有音频URL: {data}")
                    time.sleep(1)
                    continue

                # 下载音频
                audio_r = requests.get(audio_url, timeout=60, proxies=_no_proxy)
                if audio_r.status_code != 200:
                    print(f"[Voice] 下载音频失败: {audio_r.status_code}")
                    time.sleep(1)
                    continue

                # 存本地文件
                if not filename:
                    filename = f"voice_{uuid.uuid4().hex[:8]}"
                ext = f".{response_format}" if response_format != "pcm" else ".pcm"
                local_path = os.path.join(AUDIO_DIR, f"{filename}{ext}")
                with open(local_path, "wb") as f:
                    f.write(audio_r.content)

                print(f"[Voice] 合成成功: {len(audio_r.content)} bytes → {local_path}")
                return audio_url, local_path

            elif r.status_code == 400:
                err = r.json()
                msg = err.get("message", err.get("code", ""))
                print(f"[Voice] 参数错误: {msg}")
                # 如果是音色不存在，尝试用默认音色
                if "voice" in str(msg).lower():
                    payload["input"]["voice"] = DEFAULT_VOICE
                    continue
                return None, None
            else:
                print(f"[Voice] API错误 ({r.status_code}): {r.text[:200]}")
                time.sleep(2)
        except requests.exceptions.Timeout:
            print(f"[Voice] 请求超时 (尝试 {attempt+1}/3)")
            time.sleep(2)
        except Exception as e:
            print(f"[Voice] 异常: {e}")
            time.sleep(2)

    return None, None


def synthesize_to_file(text: str, output_path: str, lang: str = "Auto",
                       voice: str = "Cherry", response_format: str = "wav",
                       sample_rate: int = 24000) -> bool:
    """合成语音到指定路径，成功返回 True"""
    url, path = synthesize(text, lang=lang, voice=voice,
                           response_format=response_format,
                           sample_rate=sample_rate)
    if path and path != output_path:
        import shutil
        shutil.move(path, output_path)
        return True
    return path is not None


def get_audio_duration(wav_path: str) -> float:
    """简单获取 WAV 音频时长（秒）"""
    try:
        with open(wav_path, "rb") as f:
            header = f.read(44)
            if len(header) < 44:
                return 0
            import struct
            channels = struct.unpack("<H", header[22:24])[0]
            sample_rate = struct.unpack("<I", header[24:28])[0]
            bits_per_sample = struct.unpack("<H", header[34:36])[0]
            data_size = os.path.getsize(wav_path) - 44
            if data_size <= 0:
                return 0
            bytes_per_sec = sample_rate * channels * (bits_per_sample // 8)
            return data_size / bytes_per_sec if bytes_per_sec > 0 else 0
    except Exception as e:
        print(f"[Voice] 读取时长失败: {e}")
        return 0


# ── 快捷函数 ──────────────────────────────────────────


def text_to_speech(text: str, lang: str = "en", voice: str = "Cherry") -> str:
    """最简单的调用：给文字返回本地音频路径"""
    lang_code = LANGUAGES.get(lang, lang)
    _, path = synthesize(text, lang=lang_code, voice=voice)
    return path


def make_video_voiceover(script: str, lang: str = "en", voice: str = "Cherry",
                         project_name: str = "video") -> str:
    """为视频生成配音，返回音频文件路径

    Args:
        script: 配音文案
        lang: 语言代码
        voice: 音色
        project_name: 项目名称（用于文件命名）
    Returns:
        音频文件路径，失败返回 None
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"voiceover_{project_name}_{ts}"
    _, path = synthesize(script, lang=LANGUAGES.get(lang, lang),
                         voice=voice, filename=filename)
    return path


# ── 自测 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("Voice Engine 自测")
    print("=" * 60)

    # 英语
    print("\n--- 英语 ---")
    url, path = synthesize(
        "Hello! Welcome to GLOWFORGE. We manufacture premium custom LED signs "
        "for businesses worldwide. Our products are exported to UAE, Saudi Arabia, "
        "USA, Europe and beyond.",
        lang="English", voice="Cherry"
    )
    if path:
        duration = get_audio_duration(path)
        print(f"  时长: {duration:.1f}s, 文件: {path}")

    # 阿拉伯语
    print("\n--- 阿拉伯语 ---")
    url, path = synthesize(
        "مرحبا! أهلا وسهلا في مصنع GLOWFORGE. نحن نصنع اللوحات الإعلانية المضيئة "
        "الفاخرة للشركات في جميع أنحاء العالم.",
        lang="Auto", voice="Cherry"
    )
    if path:
        duration = get_audio_duration(path)
        print(f"  时长: {duration:.1f}s, 文件: {path}")

    print("\n✅ 自测完成")
