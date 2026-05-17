# graph/schema.py - 数据模型
# navisv 架构 v0.8 - Graph Layer

"""
数据模型定义。

节点属性存在 networkx DiGraph 的 node attributes 中：
    graph.add_node(node_id,
        name=str,
        module=str,
        bit_width=tuple,
        tags=set,
        meta=dict)

边属性存在 networkx DiGraph 的 edge attributes 中：
    graph.add_edge(src, dst,
        relation=str,
        timing=str,
        qualifier=str,
        bounds=tuple,
        source_location=str,
        source=str,
        is_partial=bool,
        confidence=str,
        meta=dict)
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Any


@dataclass
class DriverInfo:
    """Query Layer get_drivers() 返回的驱动源信息"""
    id: str                       # 驱动端节点 ID
    relation: str = "drives"      # "drives" | "controls" | "calls"
    timing: str = "unknown"       # "blocking" | "non_blocking" | "continuous" | "unknown"
    qualifier: Optional[str] = None  # 门控条件，如 "if (valid)"
    bounds: Optional[Tuple[int, int]] = None  # 位选 (15, 8)
    source_location: Optional[str] = None  # "file.sv:42"
    source: str = "slang"         # "slang" | "python" | "merged"
    is_partial: bool = False      # RHS 解析不完整
    confidence: str = "high"      # "high" | "medium" | "uncertain"


@dataclass
class LoadInfo:
    """Query Layer get_loads() 返回的负载信息"""
    id: str                       # 负载端节点 ID
    relation: str = "drives"      # "drives" | "controls" | "calls"
    timing: str = "unknown"
    qualifier: Optional[str] = None
    bounds: Optional[Tuple[int, int]] = None
    source_location: Optional[str] = None
    source: str = "slang"
    is_partial: bool = False
    confidence: str = "high"


@dataclass
class AppResponse:
    """App Layer 对外返回格式"""
    structured: Any       # 结构化数据
    summary: str          # 自然语言摘要，始终非空
    confidence: str       # "high" | "medium" | "uncertain"
    experimental: bool = False  # 实验性标记


@dataclass
class PathResult:
    """Query Layer find_path() 返回格式"""
    nodes: List[str]      # 节点路径列表 [src, ..., dst]
    edges: List[dict] = field(default_factory=list)  # 每条边的属性
    confidence: str = "high"


def bit_width_from_bounds(bounds) -> Tuple[int, int]:
    """从 slang bounds 转换为 (msb, lsb) 元组"""
    if bounds is None:
        return (0, 0)
    if hasattr(bounds, 'upper') and hasattr(bounds, 'lower'):
        return (int(bounds.upper), int(bounds.lower))
    if isinstance(bounds, tuple) and len(bounds) == 2:
        return (int(bounds[0]), int(bounds[1]))
    return (0, 0)


def timing_from_stmt_kind(kind_name: str) -> str:
    """从 statement kind 推断 timing"""
    if kind_name == 'ExpressionStatement':
        return 'blocking'
    elif kind_name == 'NonblockingBlockingSubprogramStatement':
        return 'non_blocking'
    elif kind_name == 'ContinuousAssign':
        return 'continuous'
    return 'unknown'