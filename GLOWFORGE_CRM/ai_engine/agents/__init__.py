"""V5 Multi-Agent Competition System — 并行Agent竞争系统

5个Agent类型：
  - Hunter: 激进报价+逼单
  - Consultant: 顾问式需求分析
  - Soft Seller: 温和建立信任
  - Technical: 参数技术流
  - Closer: 紧迫感成交

核心流程：
  1. Agent Router: 客户→Agent池分配
  2. Agent Competition: 多个Agent并行生成回复
  3. Winner Selector: 评分选出最优 + 学习
  4. Agent Manager: 每日调度
"""

from .hunter_agent import HunterAgent
from .consultant_agent import ConsultantAgent
from .soft_seller_agent import SoftSellerAgent
from .technical_agent import TechnicalAgent
from .closer_agent import CloserAgent
from .agent_competition import AgentCompetition
from .winner_selector import WinnerSelector
from .agent_manager import AgentManager
from .agent_router import AgentRouter

__all__ = [
    "HunterAgent",
    "ConsultantAgent",
    "SoftSellerAgent",
    "TechnicalAgent",
    "CloserAgent",
    "AgentCompetition",
    "WinnerSelector",
    "AgentManager",
    "AgentRouter",
]
