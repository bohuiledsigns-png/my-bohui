"""Business Graph — 利润路径图谱

Phase 3: 在现有 SQLite 上增加 3 张 graph 表，从现有数据自动推导
节点和边，提供利润路径发现 + 瓶颈检测能力。

优雅降级: 导入失败时 GraphEngine = None（safety/__init__.py 模式）
"""
try:
    from business_graph.engine import GraphEngine
except ImportError:
    GraphEngine = None
