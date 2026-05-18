# query/service.py - Query Layer 原子查询服务
# navisv 架构 v0.9 - Query Layer

"""
QueryService: 原子查询接口。

铁律约束：
- [铁律12] 只返回结构化数据，不返回带 summary 的对象
- [铁律13] 是 App Layer 的唯一数据通道

接口（v0.9 新增）：
- get_drivers(signal) -> List[DriverInfo]
- get_loads(signal) -> List[LoadInfo]
- find_path(src, dst) -> List[str]
- find_comb_path(src, dst) -> List[str]  # 新增：纯组合路径
- get_comb_fan_in(signal) -> List[str]  # 新增：组合扇入
- get_comb_fan_out(signal) -> List[str]  # 新增：组合扇出
- fanin_cone(signal, max_depth=5) -> List[str]
- fanout_cone(signal, max_depth=5) -> List[str]
- scc_analysis() -> List[List[str]]
- search_signals(name_pattern='', tags=None) -> List[str]
- is_driven(signal) -> bool  # 新增：检查信号是否被驱动

参考: docs/SLANG_NETLIST_USER_GUIDE.md
"""

from typing import List, Optional, Set

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
        # 延迟加载 slang PathFinder
        self._nl = None
        self._finder = None

    def _get_pathfinder(self):
        """延迟加载 PathFinder"""
        if self._finder is None:
            import sys
            sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
            sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')
            import pyslang_netlist
            self._nl = pyslang_netlist
            self._finder = pyslang_netlist.PathFinder()
        return self._finder

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
        
        使用 slang PathFinder（可穿过 State 节点）。
        这是全路径查找，适合时序路径分析。
        
        Args:
            src: 起点信号路径
            dst: 终点信号路径
            
        Returns:
            List[str]: 节点路径，如 [src, ..., dst]
        """
        # 尝试用 slang PathFinder
        try:
            sl_graph = self._graph._slang_graph
            if sl_graph:
                src_node = sl_graph.lookup(src)
                dst_node = sl_graph.lookup(dst)
                if src_node and dst_node:
                    pf = self._get_pathfinder()
                    path = pf.find(src_node, dst_node)
                    if path and not path.empty():
                        result = []
                        for n in path:
                            p = getattr(n, 'path', None)
                            if p:
                                result.append(p)
                            elif hasattr(n, 'ID'):
                                result.append(f'Assignment:{n.ID}')
                            else:
                                result.append(str(n))
                        return result
        except Exception:
            pass

        # fallback 到 networkx shortest_path
        try:
            return nx.shortest_path(self._graph.graph, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_comb_path(self, src: str, dst: str) -> List[str]:
        """
        返回从 src 到 dst 的纯组合逻辑路径。
        遇到 State 节点（FF）立即停止。
        
        适用于：
        - 组合环检测
        - 组合逻辑时序分析
        
        Args:
            src: 起点信号路径
            dst: 终点信号路径（不能是 State 节点）
            
        Returns:
            List[str]: 组合逻辑路径
        """
        try:
            sl_graph = self._graph._slang_graph
            if sl_graph:
                src_node = sl_graph.lookup(src)
                dst_node = sl_graph.lookup(dst)
                if src_node and dst_node:
                    pf = self._get_pathfinder()
                    path = pf.find_comb(src_node, dst_node)
                    if path and not path.empty():
                        return [n.path if hasattr(n, 'path') else str(n) for n in path]
        except Exception:
            pass

        # networkx 不支持 find_comb，回退到 find_path
        # 注意：这可能包含 State 节点，不是纯组合路径
        return self.find_path(src, dst)

    def get_comb_fan_in(self, signal: str) -> List[str]:
        """
        向上游追踪组合逻辑的所有源节点（State 或 Port），遇到 State 停止。
        
        与 get_drivers() 的区别：
        - get_drivers(): 返回直接驱动源（通常是 Assignment 节点）
        - get_comb_fan_in(): 返回组合逻辑上游的所有 Named Nodes
        
        Args:
            signal: 信号路径
            
        Returns:
            List[str]: 组合逻辑上游的 Named Nodes
        """
        try:
            sl_graph = self._graph._slang_graph
            if sl_graph:
                node = sl_graph.lookup(signal)
                if node:
                    fan_in = sl_graph.get_comb_fan_in(node)
                    # 过滤出 Named Nodes（有 path 属性）
                    named = []
                    for n in fan_in:
                        path = getattr(n, 'path', None)
                        if path:
                            named.append(path)
                    # 去重
                    seen = set()
                    result = []
                    for p in named:
                        if p not in seen:
                            seen.add(p)
                            result.append(p)
                    return result
        except Exception:
            pass

        # fallback: BFS 上游
        return self._bfs_fan_in(signal, max_depth=20)

    def get_comb_fan_out(self, signal: str) -> List[str]:
        """
        向下游追踪组合逻辑的所有受影响节点，遇到 State 节点停止。
        
        Args:
            signal: 信号路径
            
        Returns:
            List[str]: 组合逻辑下游的 Named Nodes
        """
        try:
            sl_graph = self._graph._slang_graph
            if sl_graph:
                node = sl_graph.lookup(signal)
                if node:
                    fan_out = sl_graph.get_comb_fan_out(node)
                    # 过滤出 Named Nodes
                    named = []
                    for n in fan_out:
                        path = getattr(n, 'path', None)
                        if path:
                            named.append(path)
                    # 去重
                    seen = set()
                    result = []
                    for p in named:
                        if p not in seen:
                            seen.add(p)
                            result.append(p)
                    return result
        except Exception:
            pass

        # fallback: BFS 下游
        return self._bfs_fan_out(signal, max_depth=20)

    def is_driven(self, signal: str) -> bool:
        """
        检查信号是否被驱动（用于检测未连接输出端口）。
        
        Args:
            signal: 信号路径（通常是 Output Port）
            
        Returns:
            bool: True 如果被驱动，False 如果悬浮
        """
        # 方法1：检查是否有 predecessors
        if list(self._graph.predecessors(signal)):
            return True

        # 方法2：通过 slang graph 检查
        try:
            sl_graph = self._graph._slang_graph
            if sl_graph:
                node = sl_graph.lookup(signal)
                if node and hasattr(node, 'is_driven'):
                    return node.is_driven()
        except Exception:
            pass

        return False

    def _bfs_fan_in(self, signal: str, max_depth: int = 20) -> List[str]:
        """BFS 上游追踪（直到 State 节点）"""
        visited: Set[str] = set()
        queue: List[tuple] = [(signal, 0)]
        result: List[str] = []
        signal_kind = self._graph.get_node_kind(signal)
        is_state_start = signal_kind == 'State'

        while queue:
            curr, depth = queue.pop(0)
            if curr in visited:
                continue
            if depth > max_depth:
                continue
            visited.add(curr)

            # 如果遇到 State 节点，停止追踪
            curr_kind = self._graph.get_node_kind(curr)
            if curr_kind == 'State' and curr != signal:
                continue

            for pred in self._graph.predecessors(curr):
                if pred not in visited:
                    pred_kind = self._graph.get_node_kind(pred)
                    # 收集 Named Node
                    if pred_kind in ('Port', 'State'):
                        result.append(pred)
                    # State 停止，Port 继续
                    if pred_kind != 'State':
                        queue.append((pred, depth + 1))

        return result

    def _bfs_fan_out(self, signal: str, max_depth: int = 20) -> List[str]:
        """BFS 下游追踪（遇到 State 节点停止）"""
        visited: Set[str] = set()
        queue: List[tuple] = [(signal, 0)]
        result: List[str] = []

        while queue:
            curr, depth = queue.pop(0)
            if curr in visited:
                continue
            if depth > max_depth:
                continue
            visited.add(curr)

            # State 节点停止
            curr_kind = self._graph.get_node_kind(curr)
            if curr_kind == 'State' and curr != signal:
                continue

            for succ in self._graph.successors(curr):
                if succ not in visited:
                    succ_kind = self._graph.get_node_kind(succ)
                    if succ_kind in ('Port', 'State'):
                        result.append(succ)
                    if succ_kind != 'State':
                        queue.append((succ, depth + 1))

        return result

    def fanin_cone(self, signal: str, max_depth: int = 5) -> List[str]:
        """
        BFS 向上追踪，最多 max_depth 层。
        
        Args:
            signal: 信号路径
            max_depth: 最大深度，默认 5
            
        Returns:
            List[str]: 上游节点列表
        """
        visited = {signal}
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
        visited = {signal}
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

    def get_state_nodes(self) -> List[str]:
        """
        返回所有 State 节点（寄存器/FF）。
        
        Returns:
            List[str]: State 节点路径列表
        """
        return [n for n in self._graph.nodes() if self._graph.get_node_kind(n) == 'State']

    def get_input_ports(self) -> List[str]:
        """
        返回所有输入端口。
        
        Returns:
            List[str]: 输入端口路径列表
        """
        return [n for n in self._graph.nodes() if self._graph.get_node_kind(n) == 'Port'
                and 'clock' not in n.lower() and 'reset' not in n.lower()]

    def get_output_ports(self) -> List[str]:
        """
        返回所有输出端口。
        
        Returns:
            List[str]: 输出端口路径列表
        """
        return [n for n in self._graph.nodes() if 'output' in self._graph.node_attr(n).get('tags', set())]