"""
DesignGraph - 最终用户接口

Layer 3: 封装 MultiDiGraph,提供查询接口
"""

import networkx as nx
from typing import List, Dict, Any, Optional, Set, Tuple


class DesignGraph:
    """
    Layer 3: 最终用户接口

    封装 MultiDiGraph,提供语义查询接口。
    """

    def __init__(self, graph: nx.MultiDiGraph,
                 signal_conditions: Optional[Dict[str, List[Dict]]] = None,
                 netlist_driver=None):
        """
        Args:
            graph: 由 GraphBuilder 构建的 MultiDiGraph
            signal_conditions: {signal_path: [{condition, kind, source, location}]}
            netlist_driver: NetlistDriver 实例(用于 fan-in/fan-out 查询)
        """
        self.graph = graph
        self._signal_conditions = signal_conditions or {}
        self._netlist_driver = netlist_driver

    def __repr__(self) -> str:
        return f"DesignGraph(nodes={self.graph.number_of_nodes()}, edges={self.graph.number_of_edges()})"

    # ============================================
    # 基本查询
    # ============================================

    def nodes(self) -> List[str]:
        """返回所有节点路径"""
        return list(self.graph.nodes())

    def edges(self) -> List[Tuple[str, str]]:
        """返回所有边(去重)"""
        return list(self.graph.edges())

    def node_attr(self, path: str) -> Dict[str, Any]:
        """获取节点属性"""
        return dict(self.graph.nodes[path])

    def edge_attr(self, src: str, dst: str, key: Optional[int] = None) -> Dict[str, Any]:
        """获取边属性"""
        if key is not None:
            return dict(self.graph.edges[src, dst, key])
        return dict(self.graph.edges[src, dst])

    def has_node(self, path: str) -> bool:
        """检查节点是否存在"""
        return self.graph.has_node(path)

    def has_edge(self, src: str, dst: str) -> bool:
        """检查边是否存在"""
        return self.graph.has_edge(src, dst)

    # ============================================
    # 驱动/负载查询
    # ============================================

    def get_drivers(self, signal: str) -> List[str]:
        """
        获取驱动该信号的源节点列表

        Args:
            signal: 信号路径 (如 'top.cpu.alu.result')

        Returns:
            驱动该信号的源节点列表
        """
        if not self.graph.has_node(signal):
            return []

        drivers = []
        for src, dst, data in self.graph.in_edges(signal, data=True):
            drivers.append(src)

        return drivers

    def get_loads(self, signal: str) -> List[str]:
        """
        获取该信号驱动的负载节点列表

        Args:
            signal: 信号路径

        Returns:
            被该信号驱动的节点列表
        """
        if not self.graph.has_node(signal):
            return []

        loads = []
        for src, dst, data in self.graph.out_edges(signal, data=True):
            loads.append(dst)

        return loads

    def get_loads_with_timing(self, signal: str) -> List[Dict[str, Any]]:
        """
        获取该信号驱动的所有负载及其时序属性

        Args:
            signal: 信号路径

        Returns:
            [
                {
                    'signal': 'load_name',
                    'timing': {
                        'clock_domain': 'clk',
                        'reset_kind': 'async',
                        'target_kind': 'register_output'
                    },
                    'relation': 'drives',
                    'cross_clock': False,
                    'async_path': False
                },
                ...
            ]
        """
        if not self.graph.has_node(signal):
            return []

        # 获取驱动源的时钟域
        source_clock = None
        if signal in self._signal_conditions:
            conds = self._signal_conditions[signal]
            if conds:
                source_clock = conds[0].get('clock_domain')

        loads = []
        for src, dst, data in self.graph.out_edges(signal, data=True):
            timing = {'clock_domain': None, 'reset_kind': None, 'target_kind': None}
            is_register = False

            if dst in self._signal_conditions:
                conds = self._signal_conditions[dst]
                if conds:
                    c = conds[0]
                    timing['clock_domain'] = c.get('clock_domain')
                    timing['reset_kind'] = c.get('reset_kind')
                    timing['target_kind'] = c.get('target_kind')
                    is_register = c.get('target_kind') == 'register_output'

            cross_clock = bool(source_clock and timing['clock_domain'] and source_clock != timing['clock_domain'])
            async_path = is_register and timing['reset_kind'] == 'async'

            loads.append({
                'signal': dst,
                'timing': timing,
                'relation': data.get('relation', 'drives'),
                'condition': data.get('condition'),
                'cross_clock': cross_clock,
                'async_path': async_path
            })

        return loads

    def get_fanout_analysis(self, signal: str) -> Dict[str, Any]:
        """
        获取信号的完整 fan-out 分析

        Args:
            signal: 信号路径

        Returns:
            {
                'signal': signal,
                'loads': [...],
                'summary': {
                    'total': int,
                    'registers': int,
                    'combinational': int,
                    'cross_clock': int,
                    'async_paths': int,
                    'clocks': [clocks...]
                }
            }
        """
        loads = self.get_loads_with_timing(signal)

        total = len(loads)
        registers = sum(1 for l in loads if l['timing']['target_kind'] == 'register_output')
        combinational = sum(1 for l in loads if l['timing']['target_kind'] == 'combinational')
        cross_clock_count = sum(1 for l in loads if l['cross_clock'])
        async_paths = sum(1 for l in loads if l['async_path'])
        clocks = list(set(l['timing']['clock_domain'] for l in loads if l['timing']['clock_domain']))

        return {
            'signal': signal,
            'loads': loads,
            'summary': {
                'total': total,
                'registers': registers,
                'combinational': combinational,
                'cross_clock': cross_clock_count,
                'async_paths': async_paths,
                'clocks': clocks
            }
        }

    # ============================================
    # Fan-in / Fan-out 锥
    # ============================================

    def get_fanin_cone(self, signal: str, depth: int = 5, timing: Optional[str] = None) -> Set[str]:
        """
        获取 fan-in 锥(该信号的所有祖先)

        Args:
            signal: 起始信号
            depth: 最大深度
            timing: 过滤时序类型 ('combinational', 'sequential')

        Returns:
            fan-in 锥中的所有节点集合
        """
        if not self.graph.has_node(signal):
            return set()

        cone = set()
        queue = [(signal, 0)]
        visited = {signal}

        while queue:
            node, d = queue.pop(0)
            if d >= depth:
                continue

            for src, _, data in self.graph.in_edges(node, data=True):
                if src in visited:
                    continue

                # 时序过滤
                if timing and data.get('timing') != timing:
                    continue

                cone.add(src)
                visited.add(src)
                queue.append((src, d + 1))

        return cone

    def get_fanout_cone(self, signal: str, depth: int = 5, timing: Optional[str] = None) -> Set[str]:
        """
        获取 fan-out 锥(该信号驱动的所有节点)

        Args:
            signal: 起始信号
            depth: 最大深度
            timing: 过滤时序类型

        Returns:
            fan-out 锥中的所有节点集合
        """
        if not self.graph.has_node(signal):
            return set()

        cone = set()
        queue = [(signal, 0)]
        visited = {signal}

        while queue:
            node, d = queue.pop(0)
            if d >= depth:
                continue

            for _, dst, data in self.graph.out_edges(node, data=True):
                if dst in visited:
                    continue

                if timing and data.get('timing') != timing:
                    continue

                cone.add(dst)
                visited.add(dst)
                queue.append((dst, d + 1))

        return cone

    # ============================================
    # 寄存器查询
    # ============================================

    def get_registers(self) -> List[str]:
        """获取所有寄存器(State 节点)"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == 'State']

    def get_input_ports(self) -> List[str]:
        """获取所有输入端口"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == 'Port'
                and self.graph.nodes[n].get('direction') == 'In']

    def get_output_ports(self) -> List[str]:
        """获取所有输出端口"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == 'Port'
                and self.graph.nodes[n].get('direction') == 'Out']

    # ============================================
    # 查找
    # ============================================

    def find_nodes(self, pattern: str) -> List[str]:
        """
        通配符查找节点

        Args:
            pattern: 通配符模式 (*, ?)

        Returns:
            匹配的节点列表
        """
        import fnmatch
        return [n for n in self.graph.nodes() if fnmatch.fnmatch(n, pattern)]

    def find_by_kind(self, kind: str) -> List[str]:
        """按 kind 查找节点"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == kind]

    # ============================================
    # 路径查询
    # ============================================

    def get_path(self, src: str, dst: str) -> List[str]:
        """
        查找两点间的路径

        Args:
            src: 起始节点
            dst: 目标节点

        Returns:
            路径节点列表,如果不存在则返回空列表
        """
        if not self.graph.has_node(src) or not self.graph.has_node(dst):
            return []

        try:
            return nx.shortest_path(self.graph, src, dst)
        except nx.NetworkXNoPath:
            return []

    # ============================================
    # 条件查询 (Option B)
    # ============================================

    def get_condition_pairs(self, signal: str) -> List[Dict[str, Any]]:
        """
        获取信号的"条件-语句"一一对应关系

        Args:
            signal: 信号路径 (如 'top.alu_inst.result')

        Returns:
            [
                {
                    'condition': 'op_sel == 3'b0',
                    'statement': 'result = a + b',
                    'kind': 'case',
                    'location': {'file': 'design.sv', 'line': 12, 'column': 19}
                },
                ...
            ]
        """
        if signal not in self._signal_conditions:
            return []

        results = []
        for cond_info in self._signal_conditions[signal]:
            loc = cond_info.get('location', {})
            # 清理文件路径(取文件名部分)
            file_name = loc.get('file', 'unknown')
            if '/' in file_name:
                file_name = file_name.split('/')[-1]

            line = loc.get('line', 0)
            column = loc.get('column', 0)

            # 构建完整输出
            statement = cond_info.get('statement') or f"{file_name}:{line}:{column}"
            if_expr = cond_info.get('if_expression') or f"if ({cond_info.get('condition', '')}) {statement}"

            results.append({
                'condition': cond_info['condition'],
                'statement': statement,
                'if_expression': if_expr,  # 完整的 if 表达式
                'kind': cond_info['kind'],
                'location': f"{file_name}:{line}:{column}"
            })

        return results

    def _find_condition_key(self, signal: str) -> str:
        """查找 signal 在 _signal_conditions 中的键"""
        if signal in self._signal_conditions:
            return signal

        # 尝试去掉前缀
        if '.' in signal:
            unprefixed = signal.split('.')[-1]
            if unprefixed in self._signal_conditions:
                return unprefixed

        return None

    def get_all_conditions(self, signal: str) -> List[Dict[str, Any]]:
        """
        获取信号的所有条件(不带边)

        Args:
            signal: 信号路径

        Returns:
            [{condition, kind, location, edges}, ...]
        """
        condition_key = self._find_condition_key(signal)
        if not condition_key:
            return []

        # 获取该信号的边 (使用原始 signal 路径)
        edges = []
        if self.graph.has_node(signal):
            for src, dst, data in self.graph.in_edges(signal, data=True):
                edges.append({
                    'from': src,
                    'edge_kind': data.get('edge_kind'),
                    'timing': data.get('timing'),
                })

        results = []
        for cond_info in self._signal_conditions[condition_key]:
            result = {
                'condition': cond_info['condition'],
                'statement': cond_info.get('statement', ''),
                'if_expression': cond_info.get('if_expression', ''),
                'kind': cond_info['kind'],
                'location': cond_info.get('location'),
                'edges': edges if edges else None
            }

            # 添加时序属性 (如果有)
            if cond_info.get('target_kind'):
                result['target_kind'] = cond_info['target_kind']
            if cond_info.get('clock_domain'):
                result['clock_domain'] = cond_info['clock_domain']
            if cond_info.get('edge_type'):
                result['edge_type'] = cond_info['edge_type']
            if cond_info.get('reset_signal'):
                result['reset_signal'] = cond_info['reset_signal']
            if cond_info.get('reset_kind'):
                result['reset_kind'] = cond_info['reset_kind']

            results.append(result)

        return results

    # ============================================
    # 统计
    # ============================================

    def summary(self) -> Dict[str, Any]:
        """返回摘要"""
        # 节点统计
        node_kinds = {}
        for n in self.graph.nodes():
            kind = self.graph.nodes[n].get('kind', 'unknown')
            node_kinds[kind] = node_kinds.get(kind, 0) + 1

        # 边统计
        edge_kinds = {}
        timing_stats = {}
        for u, v, d in self.graph.edges(data=True):
            ek = d.get('edge_kind', 'None')
            edge_kinds[ek] = edge_kinds.get(ek, 0) + 1
            t = d.get('timing', 'unknown')
            timing_stats[t] = timing_stats.get(t, 0) + 1

        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'node_kinds': node_kinds,
            'edge_kinds': edge_kinds,
            'timing_stats': timing_stats,
        }


    def get_signal_info(self, signal: str, source: str = 'both') -> Dict[str, Any]:
        """
        获取信号的完整信息(data flow + conditions)

        Args:
            signal: 信号路径
            source: 数据源
                - 'netlist': 只用 slang-netlist fan-in/fan-out
                - 'ast': 只用 AST 条件分析
                - 'both': 合并两者,用 AST 条件增强 netlist 数据

        Returns:
            {
                'signal': 信号路径,
                'drivers': [..netlist fan-in..],
                'loads': [..netlist fan-out..],
                'conditions': [..AST condition分析..],
            }
        """
        result = {
            'signal': signal,
            'drivers': [],
            'loads': [],
            'conditions': []
        }

        # 处理 netlist fan-in/fan-out
        if source in ('netlist', 'both'):
            if hasattr(self, '_netlist_driver') and self._netlist_driver:
                fan_in = self._netlist_driver.run_fan_in(signal)
                fan_out = self._netlist_driver.run_fan_out(signal)

                # 解析 fan-in 结果
                for item in fan_in.get('fan_in', []):
                    path, loc = self._parse_fan_item(item)
                    result['drivers'].append({
                        'path': path,
                        'location': loc
                    })

                # 解析 fan-out 结果
                for item in fan_out.get('fan_out', []):
                    path, loc = self._parse_fan_item(item)
                    result['loads'].append({
                        'path': path,
                        'location': loc
                    })

        # 处理 AST conditions
        if source in ('ast', 'both'):
            conds = self.get_all_conditions(signal)
            result['conditions'] = conds

        # 用 conditions 增强 drivers
        if source == 'both' and result['conditions']:
            # 建立 path -> condition 映射
            for d in result['drivers']:
                # 查找这个 driver 相关的 condition
                for c in result['conditions']:
                    cond_sig = c.get('condition', '')
                    if d['path'].split('.')[-1] in cond_sig:
                        d['condition'] = c['condition']
                        d['statement'] = c.get('statement', '')
                        d['condition_kind'] = c['kind']
                        break

        return result

    def _parse_fan_item(self, item: str) -> Tuple[str, str]:
        """解析 fan-in/fan-out 输出的一行: 'path  location'"""
        parts = item.strip().split()
        if len(parts) >= 2:
            # 最后两部分是 path 和 location
            path = parts[0]
            loc = parts[1]
            return path, loc
        return item.strip(), ''

    def trace_path(self, from_signal: str, to_signal: str, enrich: bool = True) -> Dict[str, Any]:
        """
        追踪两点间的路径(带完整信息)

        Args:
            from_signal: 起始信号
            to_signal: 目标信号
            enrich: 是否用 AST 条件信息增强路径节点(只增强终点)

        Returns:
            {
                'from': from_signal,
                'to': to_signal,
                'path': [{path, location, condition?, statement?}],
                'success': bool
            }
        """
        if not hasattr(self, '_netlist_driver') or not self._netlist_driver:
            return {'from': from_signal, 'to': to_signal, 'path': [], 'success': False}

        result = self._netlist_driver.run_path_trace(from_signal, to_signal)

        # 解析路径
        path_nodes = self._parse_path_trace(result['stdout'])

        # 用 AST conditions 增强(只增强终点,即 to_signal)
        if enrich and to_signal in self._signal_conditions:
            # 找到 to_signal 对应的节点并附加条件
            for node in path_nodes:
                if node['path'] == to_signal:
                    conds = self._signal_conditions[to_signal]
                    if conds:
                        # 取第一个条件及其信息
                        c = conds[0]
                        node['condition'] = c.get('condition')
                        node['statement'] = c.get('statement')
                        node['condition_kind'] = c.get('kind')
                    break

        return {
            'from': from_signal,
            'to': to_signal,
            'path': path_nodes,
            'success': result['success']
        }

    def trace_full_path(self, src: str, dst: str) -> Dict[str, Any]:
        """
        完整路径追踪 - 包含所有时序和条件信息

        结合 slang-netlist 的 path trace 和 AST 的条件/时序信息，
        返回两点间路径的完整视图。

        Args:
            src: 起始信号
            dst: 目标信号

        Returns:
            {
                'from': src,
                'to': dst,
                'success': bool,
                'path': [
                    {
                        'signal': signal_name,
                        'location': 'file:line:col',
                        'timing': {
                            'clock_domain': 'clk',
                            'reset_kind': 'async',
                            'target_kind': 'register_output'
                        },
                        'is_register': bool,
                        'driving_condition': None,  # 驱动这个节点的条件
                        'driving_kind': None,        # 条件类型 (if/case/ternary/plain)
                        'edge': {
                            'from': upstream_signal,
                            'relation': 'drives',
                            'timing': 'sequential_input',
                            'edge_kind': 'PosEdge'
                        }
                    }
                ],
                'summary': {
                    'reset_safe': bool,
                    'cross_clock': bool,
                    'register_count': int,
                    'clocks': [list],
                    'path_length': int
                }
            }
        """
        # 1. 尝试 networkx shortest_path (时序边: clk/rst_n → register)
        try:
            nx_path = nx.shortest_path(self.graph, src, dst)
            return self._build_trace_result(nx_path, src, dst)
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            pass

        # 2. Fallback: 使用 netlist path trace (包含完整数据流路径)
        if self._netlist_driver:
            result = self._netlist_driver.run_path_trace(src, dst)
            if result['success']:
                return self._build_trace_from_netlist(result['stdout'], src, dst)

        # 3. 路径不存在
        return {
            'from': src,
            'to': dst,
            'success': False,
            'path': [],
            'summary': {
                'reset_safe': False,
                'cross_clock': False,
                'register_count': 0,
                'clocks': [],
                'path_length': 0
            }
        }

    def _build_trace_result(self, path: List[str], src: str, dst: str) -> Dict[str, Any]:

        path_info = []
        clocks_seen = set()
        register_count = 0

        for i, signal in enumerate(path):
            # 获取节点时序属性
            timing = {'clock_domain': None, 'reset_kind': None, 'target_kind': None}
            is_register = False

            if signal in self._signal_conditions:
                conds = self._signal_conditions[signal]
                if conds:
                    c = conds[0]
                    timing['clock_domain'] = c.get('clock_domain')
                    timing['reset_kind'] = c.get('reset_kind')
                    timing['target_kind'] = c.get('target_kind')
                    if c.get('target_kind') == 'register_output':
                        is_register = True
                        register_count += 1
                    if c.get('clock_domain'):
                        clocks_seen.add(c['clock_domain'])

            # 获取位置信息
            location = ''
            if signal in self._signal_conditions and self._signal_conditions[signal]:
                loc = self._signal_conditions[signal][0].get('location', {})
                if loc:
                    file_name = loc.get('file', '')
                    if '/' in file_name:
                        file_name = file_name.split('/')[-1]
                    line = loc.get('line', 0)
                    col = loc.get('column', 0)
                    if line:
                        location = f"{file_name}:{line}:{col}"

            # 获取边的信息 (从上一个节点到这个节点)
            edge_info = {'from': None, 'relation': None, 'timing': None, 'edge_kind': None}
            driving_condition = None
            driving_kind = None

            if i > 0:
                prev_signal = path[i - 1]
                if self.graph.has_edge(prev_signal, signal):
                    edge_data = self.graph.get_edge_data(prev_signal, signal)
                    # 获取第一条边的属性 (MultiDiGraph 可能有多个边)
                    if edge_data:
                        first_key = next(iter(edge_data))
                        edge_attrs = edge_data[first_key]
                        edge_info = {
                            'from': prev_signal,
                            'relation': edge_attrs.get('relation'),
                            'timing': edge_attrs.get('timing'),
                            'edge_kind': edge_attrs.get('edge_kind')
                        }
                        driving_condition = edge_attrs.get('condition')
                        driving_kind = edge_attrs.get('condition_kind')

            path_info.append({
                'signal': signal,
                'location': location,
                'timing': timing,
                'is_register': is_register,
                'driving_condition': driving_condition,
                'driving_kind': driving_kind,
                'edge': edge_info
            })

        # 判断路径安全性
        cross_clock = len(clocks_seen) > 1
        reset_safe = all(
            node.get('timing', {}).get('reset_kind') in (None, 'sync', 'none')
            for node in path_info
        )

        # 计算路径置信度评分 (0-1)
        path_confidence = self._calculate_path_confidence(path_info, path, src, dst)

        return {
            'from': src,
            'to': dst,
            'success': True,
            'path': path_info,
            'summary': {
                'reset_safe': reset_safe,
                'cross_clock': cross_clock,
                'register_count': register_count,
                'clocks': list(clocks_seen),
                'path_length': len(path_info),
                'path_confidence': path_confidence
            }
        }

    def _calculate_path_confidence(self, path_info: List[Dict], path: List[str], src: str, dst: str) -> Dict[str, Any]:
        """
        计算路径置信度评分 (0-1)

        评分维度:
        1. 节点匹配度: 路径中有多少节点有时序信息 (权重 40%)
        2. 边完整性: 边是否有完整的属性 (condition, timing) (权重 30%)
        3. 模块边界损失: 跨模块路径可能损失信息 (权重 15%)
        4. 时钟域一致性: 单一时钟域更可靠 (权重 15%)
        """
        if not path:
            return {'score': 0.0, 'details': {}}

        # 1. 节点匹配度 (40%)
        nodes_with_timing = sum(1 for node in path_info if node.get('timing', {}).get('clock_domain'))
        node_match_score = nodes_with_timing / len(path_info) if path_info else 0

        # 2. 边完整性 (30%)
        edges_with_condition = 0
        edges_with_timing = 0
        total_edges = len(path_info) - 1  # 边数 = 节点数 - 1

        if total_edges > 0:
            for node in path_info:
                edge = node.get('edge', {})
                if edge.get('condition'):
                    edges_with_condition += 1
                if edge.get('timing'):
                    edges_with_timing += 1

        edge_condition_score = edges_with_condition / total_edges if total_edges > 0 else 0
        edge_timing_score = edges_with_timing / total_edges if total_edges > 0 else 0
        edge_completeness_score = (edge_condition_score + edge_timing_score) / 2

        # 3. 模块边界损失 (15%)
        # 计算路径中的模块边界数
        module_boundaries = 0
        for i in range(1, len(path)):
            prev_parts = path[i-1].split('.')
            curr_parts = path[i].split('.')
            # 如果两个节点的模块数量不同或模块名不同,算一个边界
            if len(prev_parts) != len(curr_parts):
                module_boundaries += 1
            elif len(prev_parts) >= 2 and prev_parts[1] != curr_parts[1]:
                module_boundaries += 1

        # 边界越多,置信度越低 (最多扣 15%)
        boundary_penalty = min(module_boundaries * 0.03, 0.15)
        module_boundary_score = 1.0 - boundary_penalty

        # 4. 时钟域一致性 (15%)
        clocks = set()
        for node in path_info:
            clk = node.get('timing', {}).get('clock_domain')
            if clk:
                clocks.add(clk)

        if len(clocks) <= 1:
            clock_consistency_score = 1.0  # 单一时钟域
        elif len(clocks) == 2:
            clock_consistency_score = 0.7  # 轻微跨时钟域
        else:
            clock_consistency_score = 0.4  # 多时钟域

        # 综合评分
        final_score = (
            node_match_score * 0.40 +
            edge_completeness_score * 0.30 +
            module_boundary_score * 0.15 +
            clock_consistency_score * 0.15
        )

        return {
            'score': round(final_score, 3),
            'details': {
                'node_match_score': round(node_match_score, 3),
                'edge_completeness_score': round(edge_completeness_score, 3),
                'module_boundary_score': round(module_boundary_score, 3),
                'clock_consistency_score': round(clock_consistency_score, 3),
                'nodes_with_timing': nodes_with_timing,
                'total_nodes': len(path_info),
                'module_boundaries': module_boundaries,
                'clock_domains': len(clocks)
            }
        }

    def _parse_path_trace(self, stdout: str) -> List[Dict[str, str]]:
        """解析 path_trace 输出,提取路径节点"""
        import re
        ansi_pattern = re.compile(r'\[[0-9;]*m')
        clean = ansi_pattern.sub('', stdout)

        nodes = []
        current_loc = ''
        for line in clean.splitlines():
            loc_match = re.search(r'^(\S+:)(\d+):(\d+):', line)
            if loc_match:
                loc_path = loc_match.group(1).replace('../chipsonar/slang_test/', '')
                current_loc = f"{loc_path}{loc_match.group(2)}:{loc_match.group(3)}"

            match = re.search(r'value\s+(\S+)\[', line)
            if match:
                path = match.group(1)
                nodes.append({'path': path, 'location': current_loc})
                current_loc = ''

        return nodes

    def _build_trace_from_netlist(self, stdout: str, src: str, dst: str) -> Dict[str, Any]:
        """
        从 netlist path trace 输出构建 trace 结果

        解析 slang-netlist 的 --from --to 输出，获取完整路径节点序列，
        并用 AST 条件信息增强。
        """
        import re

        # 解析 netlist path trace 输出
        ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
        clean = ansi_pattern.sub('', stdout)

        # 提取路径节点 (去重，保持顺序)
        path_signals = []
        seen = set()

        for line in clean.splitlines():
            match = re.search(r'value\s+(\S+)\[', line)
            if match:
                signal = match.group(1)
                if signal not in seen:
                    seen.add(signal)
                    path_signals.append(signal)

        if not path_signals:
            return {
                'from': src, 'to': dst, 'success': False,
                'path': [],
                'summary': {'reset_safe': False, 'cross_clock': False, 'register_count': 0, 'clocks': [], 'path_length': 0}
            }

        # 构建路径信息
        path_info = []
        clocks_seen = set()
        register_count = 0

        for i, signal in enumerate(path_signals):
            timing = {'clock_domain': None, 'reset_kind': None, 'target_kind': None}
            is_register = False

            # 优先从 _signal_conditions 获取 (AST 分析结果)
            if signal in self._signal_conditions:
                conds = self._signal_conditions[signal]
                if conds:
                    c = conds[0]
                    timing['clock_domain'] = c.get('clock_domain')
                    timing['reset_kind'] = c.get('reset_kind')
                    timing['target_kind'] = c.get('target_kind')
                    if c.get('target_kind') == 'register_output':
                        is_register = True
                        register_count += 1
                    if c.get('clock_domain'):
                        clocks_seen.add(c['clock_domain'])
            else:
                # Fallback: 从 graph edges 推断时序属性
                # 检查是否有 clk -> signal (PosEdge) 和 rst_n -> signal (NegEdge)
                clock_domain = None
                reset_kind = None
                target_kind = 'register_output'

                for src, dst, edge_data in self.graph.edges(data=True):
                    if dst != signal:
                        continue
                    src_short = src.split('.')[-1] if '.' in src else src
                    if src_short == 'clk' and edge_data.get('edge_kind') == 'PosEdge':
                        clock_domain = 'clk'
                    if src_short == 'rst_n' and edge_data.get('edge_kind') == 'NegEdge':
                        reset_kind = 'async'

                if clock_domain:
                    timing['clock_domain'] = clock_domain
                    timing['reset_kind'] = reset_kind
                    timing['target_kind'] = target_kind
                    is_register = True
                    register_count += 1
                    clocks_seen.add(clock_domain)

            location = ''
            if signal in self._signal_conditions and self._signal_conditions[signal]:
                loc = self._signal_conditions[signal][0].get('location', {})
                if loc:
                    file_name = loc.get('file', '')
                    if '/' in file_name:
                        file_name = file_name.split('/')[-1]
                    line_num = loc.get('line', 0)
                    col = loc.get('column', 0)
                    if line_num:
                        location = f"{file_name}:{line_num}:{col}"

            edge_info = {'from': None, 'relation': 'drives', 'timing': None, 'edge_kind': None}
            driving_condition = None
            driving_kind = None

            if i > 0:
                prev_signal = path_signals[i - 1]
                edge_info['from'] = prev_signal
                edge_info['timing'] = 'sequential_input' if is_register else 'combinational'
                if is_register:
                    if timing['reset_kind'] == 'async':
                        edge_info['edge_kind'] = 'NegEdge'
                    elif timing['clock_domain']:
                        edge_info['edge_kind'] = 'PosEdge'

            path_info.append({
                'signal': signal, 'location': location, 'timing': timing,
                'is_register': is_register, 'driving_condition': driving_condition,
                'driving_kind': driving_kind, 'edge': edge_info
            })

        cross_clock = len(clocks_seen) > 1
        reset_safe = all(node.get('timing', {}).get('reset_kind') in (None, 'sync', 'none') for node in path_info)

        return {
            'from': src, 'to': dst, 'success': True,
            'path': path_info,
            'summary': {
                'reset_safe': reset_safe, 'cross_clock': cross_clock,
                'register_count': register_count, 'clocks': list(clocks_seen),
                'path_length': len(path_info)
            }
        }

    def get_path_timing(self, src: str, dst: str) -> Dict[str, Any]:
        """
        增强的路径分析 - 结合时序属性

        追踪两点间的路径,返回每个节点的 timing 属性:
        - clock_domain: 时钟域
        - reset_kind: reset 类型 (async/sync/none)
        - target_kind: 目标类型 (register_output/combinational)

        Args:
            src: 起始信号
            dst: 目标信号

        Returns:
            {
                'from': src,
                'to': dst,
                'path': [
                    {
                        'signal': signal_name,
                        'location': file:line:col,
                        'timing': {
                            'clock_domain': clk,
                            'reset_kind': async,
                            'target_kind': register_output
                        },
                        'is_register': bool
                    }
                ],
                'success': bool,
                'summary': {
                    'reset_safe': bool,  # 路径是否全部同步 reset
                    'cross_clock': bool,  # 是否有跨时钟域
                    'register_count': int
                }
            }
        """
        path = self.get_path(src, dst)
        if not path:
            return {
                'from': src,
                'to': dst,
                'path': [],
                'success': False,
                'summary': {'reset_safe': False, 'cross_clock': False, 'register_count': 0}
            }

        path_info = []
        clocks_seen = set()
        register_count = 0

        for signal in path:
            # 获取该信号的时序属性
            timing_info = {'clock_domain': None, 'reset_kind': None, 'target_kind': None}
            is_register = False

            if signal in self._signal_conditions:
                conds = self._signal_conditions[signal]
                if conds:
                    # 从第一个条件获取时序属性
                    c = conds[0]
                    timing_info['clock_domain'] = c.get('clock_domain')
                    timing_info['reset_kind'] = c.get('reset_kind')
                    timing_info['target_kind'] = c.get('target_kind')

                    if c.get('target_kind') == 'register_output':
                        is_register = True
                        register_count += 1

                    if c.get('clock_domain'):
                        clocks_seen.add(c['clock_domain'])

            # 获取位置信息
            location = ''
            if signal in self._signal_conditions and self._signal_conditions[signal]:
                loc = self._signal_conditions[signal][0].get('location', {})
                if loc:
                    file_name = loc.get('file', '')
                    if '/' in file_name:
                        file_name = file_name.split('/')[-1]
                    line = loc.get('line', 0)
                    col = loc.get('column', 0)
                    if line:
                        location = f"{file_name}:{line}:{col}"

            path_info.append({
                'signal': signal,
                'location': location,
                'timing': timing_info,
                'is_register': is_register
            })

        # 判断路径安全性
        cross_clock = len(clocks_seen) > 1
        reset_safe = all(
            node.get('timing', {}).get('reset_kind') in (None, 'sync', 'none')
            for node in path_info
        )

        return {
            'from': src,
            'to': dst,
            'path': path_info,
            'success': True,
            'summary': {
                'reset_safe': reset_safe,
                'cross_clock': cross_clock,
                'register_count': register_count,
                'clocks': list(clocks_seen)
            }
        }

if __name__ == '__main__':
    from navisv.parsers import ASTParser, NetlistParser
    from navisv.graph.graph_builder import GraphBuilder

    # 测试
    ast = ASTParser('/tmp/navisv_slang/ast.json').parse()
    netlist = NetlistParser('/tmp/navisv_netlist/netlist.json').parse()

    builder = GraphBuilder(ast, netlist)
    graph = builder.build()

    dg = DesignGraph(graph)

    print("=== DesignGraph 测试 ===")
    print(dg)
    print(f"\nSummary: {dg.summary()}")

    print(f"\nRegisters: {dg.get_registers()}")
    print(f"Input ports: {dg.get_input_ports()}")
    print(f"Output ports: {dg.get_output_ports()}")

    print(f"\nDrivers of 'top.cnt_inst.count': {dg.get_drivers('top.cnt_inst.count')}")
    print(f"Fan-in cone of 'top.cnt_inst.count': {dg.get_fanin_cone('top.cnt_inst.count')}")
    print(f"Fan-out cone of 'top.cnt_inst.clk': {dg.get_fanout_cone('top.cnt_inst.clk')}")

    print(f"\nFind '*.count': {dg.find_nodes('*.count')}")