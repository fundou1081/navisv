# query/service.py - Query Layer 原子查询服务
# navisv 架构 v0.8 - Query Layer

"""
QueryService: 原子查询接口。

铁律约束：
- [铁律12] 只返回结构化数据，不返回带 summary 的对象
- [铁律13] 是 App Layer 的唯一数据通道

接口：
- get_drivers(signal) -> List[DriverInfo]
- get_loads(signal) -> List[LoadInfo]
- find_path(src, dst) -> List[str]
- fanin_cone(signal, max_depth=5) -> List[str]
- fanout_cone(signal, max_depth=5) -> List[str]
- scc_analysis() -> List[List[str]]
- search_signals(name_pattern='', tags=None) -> List[str]
"""

from typing import List, Optional

import networkx as nx

from .models import DriverInfo, LoadInfo


class QueryService:
    """
    原子查询接口。
    所有方法返回纯结构化数据，不包含 summary。
    App 层负责生成自然语言摘要。
    """

    def __init__(self, graph: 'DesignGraph'):
        # 铁律13：QueryService 持有 Graph 引用，App 不直接访问
        self._graph = graph
        # PathFinder 在需要时创建
        self._pf = None

    def get_drivers(self, signal: str) -> List[DriverInfo]:
        """
        返回驱动这个信号的所有源。
        
        Args:
            signal: 信号路径，如 "i2c_core.scl_i"
            
        Returns:
            List[DriverInfo]: 驱动源列表
        """
        drivers = []
        for src in self._graph.predecessors(signal):
            attr = self._graph.edge_attr(src, signal)
            drivers.append(DriverInfo(
                id=src,
                relation=attr.get('relation', 'drives'),
                timing=attr.get('timing', 'unknown'),
                qualifier=attr.get('qualifier'),
                bounds=attr.get('bounds'),
                source_location=attr.get('source_location'),
                source=attr.get('source', 'slang'),
                is_partial=attr.get('is_partial', False),
                confidence=attr.get('confidence', 'high')
            ))
        return drivers

    def get_loads(self, signal: str) -> List[LoadInfo]:
        """
        返回这个信号驱动的所有目标。
        
        Args:
            signal: 信号路径
            
        Returns:
            List[LoadInfo]: 负载列表
        """
        loads = []
        for dst in self._graph.successors(signal):
            attr = self._graph.edge_attr(signal, dst)
            loads.append(LoadInfo(
                id=dst,
                relation=attr.get('relation', 'drives'),
                timing=attr.get('timing', 'unknown'),
                qualifier=attr.get('qualifier'),
                bounds=attr.get('bounds'),
                source_location=attr.get('source_location'),
                source=attr.get('source', 'slang'),
                is_partial=attr.get('is_partial', False),
                confidence=attr.get('confidence', 'high')
            ))
        return loads

    def find_path(self, src: str, dst: str) -> List[str]:
        """
        返回从 src 到 dst 的节点路径列表（包含 src 和 dst）。
        如果无路径，返回空列表。
        
        优先用 slang PathFinder，回退到 networkx。
        
        Args:
            src: 起点信号路径
            dst: 终点信号路径
            
        Returns:
            List[str]: 节点路径，如 [src, ..., dst]
        """
        # 延迟导入 slang PathFinder
        import sys
        sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
        sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')
        import pyslang_netlist as nl

        # 尝试用 slang PathFinder
        try:
            src_node = self._graph._slang_graph.lookup(src) if self._graph._slang_graph else None
            dst_node = self._graph._slang_graph.lookup(dst) if self._graph._slang_graph else None
            if src_node and dst_node:
                pf = nl.PathFinder()
                path = pf.find(src_node, dst_node)
                if path and not path.empty():
                    return [n.hierarchicalPath if hasattr(n, 'hierarchicalPath') else str(n) for n in path]
        except Exception:
            pass

        # fallback 到 networkx shortest_path
        try:
            return nx.shortest_path(self._graph.graph, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def fanin_cone(self, signal: str, max_depth: int = 5) -> List[str]:
        """
        BFS 向上追踪，最多 max_depth 层。
        
        Args:
            signal: 信号路径
            max_depth: 最大深度，默认 5
            
        Returns:
            List[str]: 上游节点列表
        """
        visited = {signal}  # 包含起始节点
        queue = [(signal, 0)]
        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for pred in self._graph.predecessors(curr):
                if pred not in visited:
                    visited.add(pred)
                    queue.append((pred, depth + 1))
        return list(visited)

    def fanout_cone(self, signal: str, max_depth: int = 5) -> List[str]:
        """
        BFS 向下追踪，最多 max_depth 层。
        
        Args:
            signal: 信号路径
            max_depth: 最大深度，默认 5
            
        Returns:
            List[str]: 下游节点列表
        """
        visited = {signal}  # 包含起始节点
        queue = [(signal, 0)]
        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for succ in self._graph.successors(curr):
                if succ not in visited:
                    visited.add(succ)
                    queue.append((succ, depth + 1))
        return list(visited)

    def scc_analysis(self) -> List[List[str]]:
        """
        返回所有强连通分量。
        
        Returns:
            List[List[str]]: SCC 列表
        """
        return [list(scc) for scc in nx.strongly_connected_components(self._graph.graph)]

    def search_signals(self, name_pattern: str = '', tags: List[str] = None) -> List[str]:
        """
        按名称模式或 tags 搜索信号。
        
        Args:
            name_pattern: 信号名包含的子串（不区分大小写）
            tags: 需同时满足的 tags 列表
            
        Returns:
            List[str]: 匹配的信号路径列表
        """
        results = []
        for node_id in self._graph.nodes():
            attr = self._graph.node_attr(node_id)
            # 名称匹配
            if name_pattern:
                node_name = attr.get('name', '').lower()
                if name_pattern.lower() not in node_name:
                    continue
            # tags 匹配
            if tags:
                node_tags = attr.get('tags', set())
                if not any(t in node_tags for t in tags):
                    continue
            results.append(node_id)
        return results