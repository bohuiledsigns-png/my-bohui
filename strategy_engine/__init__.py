"""V3.0 Strategy Engine — 商业决策系统

从「怎么卖」到「卖什么最赚钱 + 卖给谁最赚钱」。
独立于 ai_overlay/，只读访问 crm_data.db，不改一行现有代码。

运行方式:
  python -m strategy_engine.run_daily          # 完整分析
  python -m strategy_engine.run_daily --dry-run # 预览模式
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("strategy_engine")
