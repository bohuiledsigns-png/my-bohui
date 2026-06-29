"""Strategy Rollback Manager — 策略回滚机制

在每次策略状态更新前自动创建版本化备份。
提供列出、对比和回滚功能。

用法:
    python -m strategy_engine.rollback_manager list           # 列出所有备份
    python -m strategy_engine.rollback_manager show <file>    # 显示备份内容
    python -m strategy_engine.rollback_manager restore <file> # 回滚指定备份
"""
import argparse
import glob
import json
import os
import shutil
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # strategy_engine/
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_before_save(state_path):
    """在写入 state 文件前创建备份（由 save 函数自动调用）

    参数:
        state_path: state 文件的绝对路径（如 strategy_state.json 或 growth_state.json）

    返回:
        backup_path 或 None
    """
    if not os.path.exists(state_path):
        return None

    try:
        name = os.path.basename(state_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{name}.{timestamp}.bak"
        backup_path = os.path.join(BACKUP_DIR, backup_name)

        shutil.copy2(state_path, backup_path)
        return backup_path
    except OSError as e:
        import logging
        logging.getLogger("rollback").warning(f"Backup failed: {e}")
        return None


def list_backups(state_name=None):
    """列出所有备份

    参数:
        state_name: 可选过滤，如 "strategy_state.json" 或 "growth_state.json"

    返回:
        list of dict
    """
    pattern = "*.bak" if not state_name else f"{state_name}.*.bak"
    backup_files = sorted(
        glob.glob(os.path.join(BACKUP_DIR, pattern)),
        reverse=True,
    )
    result = []
    for path in backup_files:
        name = os.path.basename(path)
        parts = name.split(".")
        state_file = f"{parts[0]}.json"
        timestamp_str = parts[1] + "_" + parts[2] if len(parts) >= 3 else "unknown"
        size = os.path.getsize(path)
        result.append({
            "backup_file": name,
            "state_file": state_file,
            "timestamp": timestamp_str,
            "size": size,
            "path": path,
        })
    return result


def show_backup(backup_name):
    """显示备份文件内容"""
    path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(path):
        # Try as full path
        path = backup_name
        if not os.path.exists(path):
            return {"error": f"Backup not found: {backup_name}"}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "backup_file": os.path.basename(path),
        "size": os.path.getsize(path),
        "content": data,
    }


def restore_backup(backup_name, dry_run=True):
    """从备份恢复 state 文件

    参数:
        backup_name: 备份文件名 (如 "strategy_state.json.20250629_120000.bak")
        dry_run: 预览模式

    返回:
        dict: { restored, state_file, backup_path, state_path }
    """
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        return {"error": f"Backup not found: {backup_name}"}

    parts = backup_name.split(".")
    state_file = f"{parts[0]}.json"
    state_path = os.path.join(DATA_DIR, state_file)

    result = {
        "state_file": state_file,
        "backup_path": backup_path,
        "state_path": state_path,
        "backup_timestamp": parts[1] + "_" + parts[2] if len(parts) >= 3 else "unknown",
    }

    if dry_run:
        result["restored"] = False
        result["note"] = "dry run — use --no-dry-run to restore"
        return result

    if not os.path.exists(state_path):
        result["error"] = f"State file not found: {state_path}"
        return result

    # 回滚前先备份当前状态
    current_backup = backup_before_save(state_path)
    if current_backup:
        result["pre_restore_backup"] = current_backup

    shutil.copy2(backup_path, state_path)
    result["restored"] = True
    return result


# ── 自动注入钩子 ──

def patch_save_functions():
    """猴子补丁 _save_state 函数，自动创建备份"""
    try:
        from strategy_engine.growth.self_learning_loop import SelfLearningLoop

        original_save = SelfLearningLoop._save_state

        def patched_save(state):
            state_path = os.path.join(DATA_DIR, "growth_state.json")
            backup_before_save(state_path)
            return original_save(state)

        SelfLearningLoop._save_state = staticmethod(patched_save)
    except ImportError:
        pass

    try:
        from strategy_engine.learning.feedback_loop import _save_state as fb_save

        original_fb_save = fb_save

        def patched_fb_save(state):
            state_path = os.path.join(DATA_DIR, "strategy_state.json")
            backup_before_save(state_path)
            return original_fb_save(state)

        import strategy_engine.learning.feedback_loop as fb_module
        fb_module._save_state = patched_fb_save
    except ImportError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy Rollback Manager")
    parser.add_argument("action", choices=["list", "show", "restore"],
                        help="操作：列出/查看/恢复")
    parser.add_argument("name", nargs="?", default=None,
                        help="备份文件名（show/restore 需要）")
    parser.add_argument("--no-dry-run", action="store_true",
                        help="restore 的实际执行模式")
    parser.add_argument("--state", default=None,
                        help="list 过滤：strategy_state 或 growth_state")

    args = parser.parse_args()

    if args.action == "list":
        backups = list_backups(state_name=args.state)
        if not backups:
            print("No backups found.")
        else:
            print(f"{'Backup File':<50} {'State':<20} {'Size':<10}")
            print("-" * 80)
            for b in backups:
                print(f"{b['backup_file']:<50} {b['state_file']:<20} {b['size']:<10}")

    elif args.action == "show":
        if not args.name:
            print("Error: 'show' requires a backup filename")
            sys.exit(1)
        result = show_backup(args.name)
        if "error" in result:
            print(f"Error: {result['error']}")
            sys.exit(1)
        print(f"Backup: {result['backup_file']} ({result['size']} bytes)")
        print(f"Content (cycle #{result['content'].get('cycle_number', '?')}):")
        print(json.dumps(result['content'], indent=2, ensure_ascii=False)[:2000])

    elif args.action == "restore":
        if not args.name:
            print("Error: 'restore' requires a backup filename")
            sys.exit(1)
        result = restore_backup(args.name, dry_run=not args.no_dry_run)
        if "error" in result:
            print(f"Error: {result['error']}")
            sys.exit(1)
        print(f"Restore from: {result['backup_timestamp']}")
        print(f"State file: {result['state_file']}")
        print(f"Path: {result['state_path']}")
        if not result.get("restored"):
            print("Dry run — use --no-dry-run to actually restore")
        else:
            print("✓ Restored successfully")
            if result.get("pre_restore_backup"):
                print(f"  Pre-restore backup: {result['pre_restore_backup']}")
