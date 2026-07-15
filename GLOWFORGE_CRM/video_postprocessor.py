"""Video Post-Processor — 生成原始视频后加入配音/BGM/字幕/钩子标题

流程:
  1. 下载 Jimeng 生成的原始视频
  2. 调用 voice_engine 生成 TTS 英文旁白
  3. 混合 BGM（自动闪避人声）
  4. 生成 SRT 字幕（按旁白段落分配时间码）
  5. FFmpeg 合成最终视频（含钩子文字叠加）

使用:
  from video_postprocessor import compose_video

  path, err = compose_video(
      video_url="https://...",
      voiceover_text="Dull old signs lower your shop grade...",
      hook_text="Premium Store Sign",
      bgm_path="D:/Bohui_Global_Push/ambient_bg.mp3",
      output_path="D:/output/final.mp4"
  )
"""

import os
import json
import re
import uuid
import subprocess
import requests

import voice_engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_jimeng")
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_REGULAR = "C:/Windows/Fonts/calibri.ttf"

# ── 多角色语音标记 ────────────────────────────────────
ROLE_PATTERN = re.compile(r'【(Customer|Factory|Wisdom)】')
SILENCE_BETWEEN_ROLES = 0.3  # 角色切换间静音秒数


def _ensure_dirs():
    os.makedirs(TEMP_DIR, exist_ok=True)


def _download_video(url: str) -> tuple:
    """下载视频到本地临时文件，返回 (local_path, error)"""
    _ensure_dirs()
    ext = ".mp4"
    local = os.path.join(TEMP_DIR, f"raw_{uuid.uuid4().hex}{ext}")
    try:
        _no_proxy = {"http": None, "https": None}
        r = requests.get(url, timeout=120, proxies=_no_proxy)
        if r.status_code != 200:
            return None, f"下载失败 HTTP {r.status_code}"
        with open(local, "wb") as f:
            f.write(r.content)
        if os.path.getsize(local) < 1024:
            return None, "视频文件太小，可能无效"
        return local, None
    except Exception as e:
        return None, f"下载异常: {e}"


def _get_video_duration(video_path: str) -> float:
    """FFprobe 获取视频时长（秒）"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15
        )
        return float(r.stdout.strip())
    except Exception:
        return 15.0  # fallback


def _generate_voiceover(text: str, voice: str = "Cherry") -> tuple:
    """生成英文旁白，返回 (wav_path, error)"""
    _ensure_dirs()
    out = os.path.join(TEMP_DIR, f"voiceover_{uuid.uuid4().hex}.wav")
    ok = voice_engine.synthesize_to_file(text, out, lang="English", voice=voice)
    if not ok:
        return None, "TTS 合成失败"
    return out, None


def _parse_role_markers(text: str) -> list:
    """解析角色标记，返回 [(role, segment_text), ...]

    无角色标记时返回 [(None, text)] 以保持向后兼容。
    """
    if not text:
        return [(None, "")]
    parts = ROLE_PATTERN.split(text)
    parts = [p.strip() for p in parts if p.strip()]
    # parts 结构: ["前置文本", "Customer", "角色台词1", "Factory", "角色台词2", ...]
    result = []
    # 如果没有角色标记，整段作为无角色文本
    has_role = any(p in ("Customer", "Factory", "Wisdom") for p in parts)
    if not has_role:
        return [(None, text.strip())]
    # 如果文本以角色标记开头，前置文本为空
    current_role = None
    for p in parts:
        if p in ("Customer", "Factory", "Wisdom"):
            current_role = p
        else:
            result.append((current_role, p))
    return result


def _generate_multi_role_voiceover(role_segments: list, lang: str = "English") -> tuple:
    """多角色语音合成：每段分配不同音色，段间插入静音

    Args:
        role_segments: [(role, text), ...]  — from _parse_role_markers()
        lang: 语言

    Returns:
        (combined_wav_path, per_role_durations, error)
        per_role_durations: 每段时长（不含静音），用于字幕时间码
    """
    _ensure_dirs()
    if not role_segments:
        return None, [], "空文案"

    seg_wavs = []
    durations = []

    # 1. 逐段合成
    for role, text in role_segments:
        if not text.strip():
            seg_wavs.append(None)
            durations.append(0)
            continue
        voice = voice_engine.get_role_voice(role) if role else voice_engine.DEFAULT_VOICE
        out = os.path.join(TEMP_DIR, f"seg_{role or 'voice'}_{uuid.uuid4().hex}.wav")
        ok = voice_engine.synthesize_to_file(text, out, lang=lang, voice=voice)
        if not ok:
            # 单段失败：用静音占位
            silence_path = os.path.join(TEMP_DIR, f"silence_{uuid.uuid4().hex}.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                 "-t", "0.5", silence_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
            )
            seg_wavs.append(silence_path)
            durations.append(0.5)
        else:
            seg_wavs.append(out)
            durations.append(voice_engine.get_audio_duration(out))

    # 2. 构建 concat 列表（段间插入静音）
    silence_path = os.path.join(TEMP_DIR, f"silence_{uuid.uuid4().hex}.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
         "-t", str(SILENCE_BETWEEN_ROLES), silence_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
    )

    concat_list = os.path.join(TEMP_DIR, f"concat_{uuid.uuid4().hex}.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for i, wav in enumerate(seg_wavs):
            if wav and os.path.exists(wav):
                f.write(f"file '{wav}'\n")
                if i < len(seg_wavs) - 1:
                    f.write(f"file '{silence_path}'\n")

    combined = os.path.join(TEMP_DIR, f"multi_role_{uuid.uuid4().hex}.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", concat_list, "-c", "copy", combined],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
    )
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[:200]
        # fallback: 如果 concat 失败，返回第一段
        if seg_wavs[0] and os.path.exists(seg_wavs[0]):
            return seg_wavs[0], durations, f"concat 降级: {err}"
        return None, [], f"concat 失败: {err}"

    return combined, durations, None


def _make_role_srt(role_segments: list, durations: list,
                   total_duration: float) -> list:
    """生成带角色标签的字幕段

    Args:
        role_segments: [(role, text), ...]
        durations: 每段原始音频时长（秒，不含静音）
        total_duration: 视频总时长

    Returns:
        [(start_sec, end_sec, display_text), ...]  可直接用于 _make_srt
    """
    if not role_segments or not durations:
        return []

    # 计算总音频时长（含静音间隔）
    total_audio = sum(durations) + SILENCE_BETWEEN_ROLES * max(0, len(durations) - 1)
    scale = min(1.0, total_duration / total_audio) if total_audio > 0 else 1.0

    result = []
    current = 0.0
    for i, (role, text) in enumerate(role_segments):
        seg_dur = durations[i] * scale
        words = text.strip().split() if text else []
        if not words:
            current += seg_dur + SILENCE_BETWEEN_ROLES * scale
            continue

        label = f"【{role}】" if role else ""
        # 短文本：整段一条字幕
        if len(words) <= 8:
            result.append((current, current + seg_dur, f"{label}{text.strip()}"))
        else:
            # 长文本按词数分多条
            n_sub = max(2, (len(words) + 7) // 8)
            sub_dur = seg_dur / n_sub
            for j in range(n_sub):
                sidx = len(words) * j // n_sub
                eidx = len(words) * (j + 1) // n_sub
                sub_words = words[sidx:eidx]
                if sub_words:
                    result.append((
                        current + j * sub_dur,
                        current + (j + 1) * sub_dur,
                        f"{label}{' '.join(sub_words)}"
                    ))
        current += seg_dur + SILENCE_BETWEEN_ROLES * scale

    return result


def _make_srt(segments: list, total_duration: float) -> str:
    """生成 SRT 字幕文件，返回文件路径

    Args:
        segments: [(start_sec, end_sec, text), ...]
        total_duration: 视频总时长（秒）
    """
    _ensure_dirs()
    path = os.path.join(TEMP_DIR, f"subs_{uuid.uuid4().hex}.srt")
    lines = []
    for i, (start, end, text) in enumerate(segments, 1):
        def _fmt(sec):
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = sec % 60
            return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
        lines.append(str(i))
        lines.append(f"{_fmt(start)} --> {_fmt(end)}")
        lines.append(text)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def _auto_segment_subtitles(text: str, total_duration: float) -> list:
    """根据视频时长自动分段字幕

    短视频(<15s): 3段   中视频(15-30s): 4段
    长视频(30-60s): 6段   超长(60s+): 每10s一段，最多12段
    返回 [(start, end, text), ...]
    """
    words = text.strip().split()
    total_wc = len(words)
    if total_wc == 0 or total_duration <= 0:
        return []

    if total_duration <= 15:
        n = 3
    elif total_duration <= 30:
        n = 4
    elif total_duration <= 60:
        n = 6
    else:
        n = min(12, max(6, int(total_duration / 10)))

    n = max(1, min(n, total_wc))
    segments = []
    for i in range(n):
        start_idx = total_wc * i // n
        end_idx = total_wc * (i + 1) // n
        seg_words = words[start_idx:end_idx]
        if not seg_words:
            continue
        start_t = total_duration * i / n
        end_t = total_duration * (i + 1) / n
        segments.append((start_t, end_t, " ".join(seg_words)))
    return segments


def _mix_audio(video_path: str, voiceover_path: str, bgm_path: str = None,
               output_path: str = None,
               voiceover_delay: float = 0.0) -> tuple:
    """混合配音 + BGM + 视频，返回 (output_path, error)

    BGM 音量曲线（匹配 Skill 规则）:
      0-2s:   静音（纯环境音铺垫）
      2-3s:   渐入（0→0.15）
      3-13s:  0.6（-30% 闪避人声）
      13-15s: 渐出（0.6→0）

    voiceover_delay: 配音延迟开始秒数（用于长视频）
    """
    _ensure_dirs()
    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"mixed_{uuid.uuid4().hex}.mp4")

    # 先获取视频时长
    dur = _get_video_duration(video_path)

    delay_ms = int(voiceover_delay * 1000)
    bgm_fade_point = min(dur, 13)  # BGM 渐入曲线只在前 13s

    if bgm_path and os.path.exists(bgm_path):
        # BGM 音量曲线
        fade_point = min(bgm_fade_point, dur - 2)
        vol_expr = (
            f"if(lt(t\\,2)\\,0.001\\,"
            f"if(lt(t\\,3)\\,0.15*(t-2)\\,"
            f"if(lt(t\\,{fade_point})\\,0.6\\,"
            f"0.6*(1-(t-{fade_point})/2))))"
        )
        filter_complex = (
            f"[1:a]adelay={delay_ms}|{delay_ms}[a1];"
            f"[2:a]volume={vol_expr}:eval=frame[bgm_vol];"
            f"[a1][bgm_vol]amix=inputs=2:duration=first:weights=1 1[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", voiceover_path,
            "-i", bgm_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]
    else:
        # 无 BGM：直接混入配音
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", voiceover_path,
            "-filter_complex",
            f"[1:a]adelay={delay_ms}|{delay_ms}[a1]",
            "-map", "0:v",
            "-map", "[a1]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]

    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", errors="replace")[:300]
            return None, f"FFmpeg 混音失败: {err}"
        return output_path, None
    except subprocess.TimeoutExpired:
        return None, "FFmpeg 超时"
    except Exception as e:
        return None, f"混音异常: {e}"


def _add_subtitles_and_hook(video_path: str, srt_path: str,
                             hook_text: str = None,
                             output_path: str = None,
                             video_duration: float = 15.0) -> tuple:
    """叠加字幕 + 钩子文字，返回 (output_path, error)"""
    _ensure_dirs()
    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"final_{uuid.uuid4().hex}.mp4")

    if not os.path.exists(srt_path):
        # 无字幕直接拷贝
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, cwd=BASE_DIR
        )
        return output_path, None

    # 字幕 filter：硬编码到视频
    # Windows 路径中 : 会被 FFmpeg filter 解析为选项分隔符
    # 改用相对路径（不含盘符冒号）并指定 cwd=BASE_DIR
    rel_srt = os.path.relpath(srt_path, BASE_DIR).replace("\\", "/")
    filter_parts = [f"subtitles={rel_srt}"]

    # 钩子文字：开头 3 秒，底部居中
    if hook_text:
        # 在 Windows FFmpeg 中，: 在 filter 选项内用 \: 转义不可靠
        # 改用 font (fontconfig) 避免路径中的冒号问题
        hook_escaped = hook_text.replace("'", "'\\\\\\''").replace(":", "\\:")
        drawtext_filter = (
            f"drawtext=text='{hook_escaped}'"
            f":font=Arial"
            f":fontsize=36"
            f":fontcolor=white"
            f":box=1:boxcolor=black@0.5"
            f":x=(w-text_w)/2"
            f":y=h-text_h-120"
            f":enable='lt(t,3)'"
        )
        filter_parts.append(drawtext_filter)

    filter_str = ",".join(filter_parts) if len(filter_parts) == 1 else f"[0:v]{','.join(filter_parts)}[v]"

    if len(filter_parts) > 1:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            output_path
        ]

    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, cwd=BASE_DIR)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", errors="replace")[-2000:]
            return None, f"FFmpeg 字幕合成失败: {err}"
        return output_path, None
    except subprocess.TimeoutExpired:
        return None, "FFmpeg 超时"
    except Exception as e:
        return None, f"字幕合成异常: {e}"


def compose_video(video_url: str, voiceover_text: str,
                  hook_text: str = None,
                  bgm_path: str = None,
                  subtitle_segments: list = None,
                  output_path: str = None,
                  voice: str = "Cherry",
                  keep_original_audio: bool = False,
                  custom_voice_path: str = None,
                  multi_role: bool = False) -> tuple:
    """完整视频合成：配音 + BGM + 字幕 + 钩子标题

    Args:
        video_url: Jimeng 生成的原始视频 URL 或本地路径
        voiceover_text: 英文旁白全文（keep_original_audio=True 时忽略）
        hook_text: 钩子标题文字（开头 3 秒显示）
        bgm_path: BGM 文件路径，None=无背景音乐
        subtitle_segments: [(start_sec, end_sec, text), ...]
            默认按时长自动分段
        output_path: 输出 mp4 路径，None=自动生成
        voice: TTS 音色 (Cherry / Chelsie / Stella) 或 "custom"
        keep_original_audio: True=保留原声，不替换音频
        custom_voice_path: 自定义声音文件路径（voice="custom" 时使用）
        multi_role: True=解析【Customer】【Factory】【Wisdom】标记分角色配音
    Returns:
        (final_path, error)
    """
    print("[VideoPP] 开始合成...")

    # 1. 下载原始视频（或使用本地路径）
    print("[VideoPP] 获取视频...")
    if os.path.exists(video_url):
        video_local = video_url
        print(f"[VideoPP] 使用本地文件: {video_local}")
    else:
        video_local, err = _download_video(video_url)
        if err:
            return None, err
    dur = _get_video_duration(video_local)
    print(f"[VideoPP] 视频时长: {dur:.1f}s")

    # 2. 获取旁白音频（保留原声时跳过）
    voice_path = None
    role_durations = None
    role_segments = None
    if keep_original_audio:
        print("[VideoPP] 保留原声，跳过 TTS...")
    elif custom_voice_path and os.path.exists(custom_voice_path):
        print("[VideoPP] 使用自定义声音...")
        voice_path = custom_voice_path
    elif voiceover_text and multi_role:
        # 多角色语音：解析标记 → 分段合成
        role_segments = _parse_role_markers(voiceover_text)
        has_role = any(r is not None for r, _ in role_segments)
        if has_role:
            print(f"[VideoPP] 多角色语音 ({len(role_segments)} 段)...")
            voice_path, role_durations, err = _generate_multi_role_voiceover(role_segments)
            if err and "concat" not in err:
                return None, err
            if err:
                print(f"[VideoPP]  {err}")
        else:
            # 有 multi_role flag 但无角色标记，降级为单音色
            print("[VideoPP] 无角色标记，降级单音色...")
            voice_path, err = _generate_voiceover(voiceover_text, voice=voice)
            if err:
                return None, err
    elif voiceover_text:
        print("[VideoPP] 生成 TTS 旁白...")
        voice_path, err = _generate_voiceover(voiceover_text, voice=voice)
        if err:
            return None, err
    else:
        print("[VideoPP] 无旁白，仅背景音乐...")

    # 3. 混合音频（保留原声时跳过）
    if keep_original_audio:
        mixed_path = video_local
        print("[VideoPP] 保留原音轨...")
    elif voice_path and bgm_path and os.path.exists(bgm_path):
        # 旁白 + BGM
        print("[VideoPP] 混合配音 + BGM...")
        mixed_path, err = _mix_audio(video_local, voice_path, bgm_path)
        if err:
            return None, err
    elif voice_path:
        # 仅旁白，无 BGM
        print("[VideoPP] 混合配音（无 BGM）...")
        mixed_path, err = _mix_audio(video_local, voice_path, None)
        if err:
            return None, err
    elif bgm_path and os.path.exists(bgm_path):
        # 仅 BGM，无旁白
        print("[VideoPP] 仅添加 BGM...")
        # 创建一个静音音频作为占位，然后混入 BGM
        mixed_path, err = _mix_audio(video_local, voice_path or "", bgm_path)
        if err:
            return None, err
    else:
        mixed_path = video_local
        print("[VideoPP] 不修改音频...")

    # 4. 生成字幕
    srt_path = None
    if subtitle_segments is not None:
        # 外部传入的字幕段
        print(f"[VideoPP] 使用外部字幕 ({len(subtitle_segments)} 段)...")
        srt_path = _make_srt(subtitle_segments, dur)
    elif role_segments and role_durations and not keep_original_audio:
        # 多角色字幕（带说话人标签）
        role_sub_segments = _make_role_srt(role_segments, role_durations, dur)
        if role_sub_segments:
            print(f"[VideoPP] 生成角色字幕 ({len(role_sub_segments)} 段)...")
            srt_path = _make_srt(role_sub_segments, dur)
    elif voiceover_text and not keep_original_audio:
        # 普通自动分段
        segs = _auto_segment_subtitles(voiceover_text, dur)
        if segs:
            print(f"[VideoPP] 生成字幕 ({len(segs)} 段)...")
            srt_path = _make_srt(segs, dur)

    # 5. 叠加字幕 + 钩子文字
    print("[VideoPP] 叠加字幕和钩子文字...")
    final_path, err = _add_subtitles_and_hook(
        mixed_path, srt_path, hook_text=hook_text,
        output_path=output_path, video_duration=dur
    )
    if err:
        return None, err

    print(f"[VideoPP] 合成完成: {final_path}")
    return final_path, None


# ── 快捷测试 ──
if __name__ == "__main__":
    # 用刚刚生成的视频测试
    test_url = (
        "https://v3-aiop.aigc-cloud.com/c74e0bf3829dda0ea82b62e7c7312393/6a3da1e1/"
        "video/tos/cn/tos-cn-v-242bcc/b462fdf8683e4c63b153cf41a469b665/"
    )
    test_voiceover = (
        "A dull storefront never stops a passerby. "
        "Ordinary signs fade into the street background. "
        "Our acrylic luminous letters glow evenly day and night, "
        "make your store the street highlight."
    )
    path, err = compose_video(
        video_url=test_url,
        voiceover_text=test_voiceover,
        hook_text="Dual-Color LED Sign — Upgrade Your Storefront",
        bgm_path="D:/Bohui_Global_Push/background_music.mp3",
        output_path="D:/Bohui_Global_Push/test_final_composed.mp4"
    )
    print(f"\nFinal: path={path}, err={err}")
