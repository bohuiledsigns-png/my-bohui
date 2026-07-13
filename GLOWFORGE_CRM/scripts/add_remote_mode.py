"""Add remote mode support to whatsapp_engine.py"""
import re

path = r'D:\Bohui_Global_Push\GLOWFORGE_CRM\whatsapp_engine.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ===== 1. Add remote mode code before the public functions section =====
remote_code = '''
# ==================== 远程模式（独立服务器） ====================
# 启用后所有函数通过 HTTP 转发到独立 whatsapp_server.py
# 好处：Chrome 永不重启，CRM 重启不影响 WhatsApp 登录状态
_REMOTE_SERVER = None

def _is_remote():
    return _REMOTE_SERVER is not None

def set_remote_server(url):
    """切换到远程模式，后续所有调用转发到独立服务器"""
    global _REMOTE_SERVER
    _REMOTE_SERVER = url

def unset_remote_server():
    """切回本地模式"""
    global _REMOTE_SERVER
    _REMOTE_SERVER = None

def _remote_get(endpoint, timeout=30):
    import urllib.request, json as _json
    url = f"{_REMOTE_SERVER}/{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return _json.loads(r.read().decode())
    except Exception as e:
        raise Exception(f"[WA远程] {e}")

def _remote_post(endpoint, data, timeout=60):
    import urllib.request, json as _json
    url = f"{_REMOTE_SERVER}/{endpoint}"
    body = _json.dumps(data).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _json.loads(r.read().decode())
    except Exception as e:
        raise Exception(f"[WA远程] {e}")


'''

# Find the public functions section marker
marker = '# ==================== 对外接口 (同步) ===================='
idx = content.find(marker)
if idx < 0:
    print('FAIL: marker not found')
    exit(1)

# Insert remote mode code before the marker
content = content[:idx] + remote_code + content[idx:]

# ===== 2. Update the marker line (it shifted) =====
# Now the remote code is before the marker. Adjust.

# ===== 3. Modify each public function =====
# We need to modify:
# - send_text
# - send_image_clipboard
# - send_media_file
# - read_messages
# - get_unread_chats
# - is_logged_in
# - get_monitor_status
# - refresh_whatsapp_page
# - start_monitor
# - stop_monitor
# - close

# Pattern: add remote check at the beginning of each function
# def func_name(...):
#     if _is_remote():
#         ...

modifications = [
    ('send_text', """def send_text(text, contact_name=None):
    if _is_remote():
        return _remote_post("send", {"text": text, "contact_name": contact_name or ""})
    _check_engine_alive()"""),

    ('send_image_clipboard', """def send_image_clipboard(image_path, contact_name=None):
    if _is_remote():
        return _remote_post("send-image", {"path": image_path, "contact_name": contact_name or ""})
    _check_engine_alive()"""),

    ('send_media_file', """def send_media_file(file_path, contact_name=None):
    if _is_remote():
        return _remote_post("send-file", {"path": file_path, "contact_name": contact_name or ""})
    _check_engine_alive()"""),

    ('read_messages', """def read_messages():
    if _is_remote():
        return _remote_get("read").get("text", "读取失败")
    _page_ready.wait(timeout=30)"""),

    ('get_unread_chats', """def get_unread_chats():
    if _is_remote():
        return _remote_get("unread").get("unread", [])
    _page_ready.wait(timeout=30)"""),

    ('is_logged_in', """def is_logged_in():
    if _is_remote():
        try:
            return _remote_get("logged-in", timeout=10).get("logged_in", False)
        except:
            return False
    try:
        _page_ready.wait(timeout=30)"""),

    ('get_monitor_status', """def get_monitor_status():
    if _is_remote():
        try:
            return _remote_get("status", timeout=10)
        except:
            return {"running": False, "logged_in": False}
    try:
        _page_ready.wait(timeout=5)"""),

    ('refresh_whatsapp_page', """def refresh_whatsapp_page():
    if _is_remote():
        try:
            return _remote_post("refresh", {}).get("ok", False)
        except:
            return False
    try:
        _page_ready.wait(timeout=30)"""),

    ('start_monitor', """def start_monitor(callback=None):
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎启动")
        return
    global _on_message_callback, _loop_thread, _running"""),

    ('stop_monitor', """def stop_monitor():
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎停止")
        return
    global _running"""),

    ('close', """def close():
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎关闭")
        return
    stop_monitor()"""),
]

# Verify all function definitions exist
for func_name, new_def in modifications:
    # Find the original function definition
    pattern = f'def {func_name}\('
    matches = list(re.finditer(pattern, content))
    if len(matches) == 0:
        print(f'WARNING: {func_name} not found')
        continue
    elif len(matches) > 1:
        print(f'WARNING: {func_name} has {len(matches)} matches, using first')

    m = matches[0]
    old_start = m.start()

    # Find where the function body starts (after the def line and docstring)
    # Find the end of the def line
    def_line_end = content.find('\n', old_start)
    remaining = content[def_line_end+1:]

    # Find the first non-empty, non-comment, non-decorator line in the function body
    # This is where we insert the remote check
    lines = remaining.split('\n')
    first_body_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
            first_body_line = i
            break

    # Build the new function with remote check added right after def line
    # Find how the original function starts
    old_def_line = content[old_start:def_line_end]
    # Find the first line of the body (could be docstring)

    # Simple approach: replace the entire function start
    # from "def func_name(...):\n    existing_first_line"
    # to "def func_name(...):\n    if _is_remote():\n        ...\n    existing_first_line"

    # Actually, let me just do simple string replacements for the function start
    pass

# Let me use a simpler approach - find each function start and insert the remote check
for func_name, new_def in modifications:
    # Find original def line
    pattern = f'def {func_name}'
    start_idx = content.find(pattern)
    if start_idx < 0:
        print(f'WARNING: {func_name} not found')
        continue

    # Find the end of the line
    end_of_line = content.find('\n', start_idx)

    # Find the body start (skip blank lines and docstring)
    pos = end_of_line + 1
    while pos < len(content) and content[pos] in ('\n', '\r', ' '):
        pos += 1

    # Check for docstring
    if content[pos:pos+3] == '"""':
        # Skip docstring
        doc_end = content.find('"""', pos+3)
        if doc_end > 0:
            pos = doc_end + 3
            # Skip more blank lines
            while pos < len(content) and content[pos] in ('\n', '\r', ' '):
                pos += 1

    # Now pos should be at the first real line of the function body
    # Find end of that line
    first_body_line_end = content.find('\n', pos)
    first_body_line = content[pos:first_body_line_end] if first_body_line_end > 0 else content[pos:]

    # Check if already modified (has remote check)
    if 'if _is_remote():' in first_body_line:
        print(f'SKIP: {func_name} already has remote check')
        continue

    # Insert remote check before the first body line
    indent = first_body_line[:len(first_body_line) - len(first_body_line.lstrip())]
    remote_check = f'{indent}if _is_remote():\n'

    # Determine what the remote call should be
    if func_name == 'send_text':
        remote_call = f'{indent}    return _remote_post("send", {{"text": text, "contact_name": contact_name or ""}})\n'
    elif func_name == 'send_image_clipboard':
        remote_call = f'{indent}    return _remote_post("send-image", {{"path": image_path, "contact_name": contact_name or ""}})\n'
    elif func_name == 'send_media_file':
        remote_call = f'{indent}    return _remote_post("send-file", {{"path": file_path, "contact_name": contact_name or ""}})\n'
    elif func_name == 'read_messages':
        remote_call = f'{indent}    return _remote_get("read").get("text", "读取失败")\n'
    elif func_name == 'get_unread_chats':
        remote_call = f'{indent}    return _remote_get("unread").get("unread", [])\n'
    elif func_name == 'is_logged_in':
        remote_call = f'{indent}    try:\n{indent}        return _remote_get("logged-in", timeout=10).get("logged_in", False)\n{indent}    except:\n{indent}        return False\n{indent}\n'
    elif func_name == 'get_monitor_status':
        remote_call = f'{indent}    try:\n{indent}        return _remote_get("status", timeout=10)\n{indent}    except:\n{indent}        return {{"running": False, "logged_in": False}}\n{indent}\n'
    elif func_name == 'refresh_whatsapp_page':
        remote_call = f'{indent}    try:\n{indent}        return _remote_post("refresh", {{}}).get("ok", False)\n{indent}    except:\n{indent}        return False\n{indent}\n'
    elif func_name == 'start_monitor':
        remote_call = f'{indent}    if _is_remote():\n{indent}        _log("[Engine] 远程模式，忽略本地引擎启动")\n{indent}        return\n{indent}\n'
        # For start_monitor, we need to wrap the whole thing, not just first line
    elif func_name == 'stop_monitor':
        remote_call = f'{indent}    if _is_remote():\n{indent}        _log("[Engine] 远程模式，忽略本地引擎停止")\n{indent}        return\n{indent}\n'
    elif func_name == 'close':
        remote_call = f'{indent}    if _is_remote():\n{indent}        _log("[Engine] 远程模式，忽略本地引擎关闭")\n{indent}        return\n{indent}\n'
    else:
        continue

    # Handle special cases differently
    if func_name in ('start_monitor', 'stop_monitor', 'close'):
        # Insert the check right after the def line
        content = content[:end_of_line+1] + remote_check + content[end_of_line+1:]
    elif func_name in ('is_logged_in', 'get_monitor_status', 'refresh_whatsapp_page'):
        # Replace the first body line content
        # First, get the original first body line
        original_first_body = content[pos:first_body_line_end]
        # Replace "    try:" with our remote check + try
        content = content[:pos] + remote_call + content[pos:]
    else:
        # Insert remote check before the first actual line
        content = content[:pos] + remote_check + remote_call + content[pos:]

    print(f'OK: {func_name} modified')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('\\nDone!')
