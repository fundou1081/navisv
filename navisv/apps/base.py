# apps/base.py - App Layer 基类和响应格式
# navisv 架构 v0.8 - App Layer

"""
BaseApp: App Layer 基类。
AppResponse: App 对外返回格式。

铁律约束：
- [铁律17] App Layer 是唯一生成自然语言的层
- [铁律18] App 原子化，一个文件一个 App
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AppResponse:
    """App 对外返回格式"""
    structured: Any       # 结构化数据
    summary: str          # 自然语言摘要，始终非空
    confidence: str       # "high" | "medium" | "uncertain"
    experimental: bool = False  # 实验性标记


class BaseApp(ABC):
    """
    App 基类。
    所有 App 必须实现 run() 方法。
    """

    def __init__(self, query: 'QueryService'):
        """
        Args:
            query: QueryService 实例（铁律13：App 通过 QueryService 获取数据）
        """
        self.query = query

    @abstractmethod
    def run(self, *args, **kwargs) -> AppResponse:
        """
        执行 App 场景。
        返回 AppResponse，必须包含非空的 summary。
        """
        pass

    def _check_signal_exists(self, signal: str) -> bool:
        """检查信号是否存在"""
        return self.query._graph.has_node(signal)

    def _confidence_from_queries(self, *query_results) -> str:
        """
        根据查询结果推断置信度。
        
        Args:
            query_results: 任意数量的查询结果
            
        Returns:
            confidence: "high" | "medium" | "uncertain"
        """
        # 如果所有结果都 high，返回 high
        if all(getattr(r, 'confidence', 'high') == 'high' for r in query_results if hasattr(r, 'confidence') or True):
            # 检查是否有 uncertain
            if any(getattr(r, 'confidence', 'high') == 'uncertain' for r in query_results if hasattr(r, 'confidence')):
                return 'uncertain'
            return 'high'
        elif any(getattr(r, 'confidence', 'high') == 'uncertain' for r in query_results if hasattr(r, 'confidence')):
            return 'uncertain'
        return 'medium'