# query/models.py - Query Layer 数据模型
# navisv 架构 v0.8 - Query Layer

"""
Query Layer 数据模型。
从 graph/schema.py 导入 DriverInfo / LoadInfo。
"""

from navisv.graph.schema import DriverInfo, LoadInfo, PathResult

__all__ = ['DriverInfo', 'LoadInfo', 'PathResult']