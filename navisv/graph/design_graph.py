"""
DesignGraph - 最终用户接口

Layer 3: 封装 MultiDiGraph,提供查询接口
"""

import copy
import warnings
import networkx as nx
from typing import List, Dict, Any, Optional, Set, Tuple
from navisv.graph.path_tracer import PathTracer
from navisv.graph.coverage_analyzer import CoverageAnalyzer


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
        # 内部存储使用 name mangling，外部无法直接访问
        self.__signal_conditions = signal_conditions or {}
        self._netlist_driver = netlist_driver

    def __repr__(self) -> str:
        return f"DesignGraph(nodes={self.graph.number_of_nodes()}, edges={self.graph.number_of_edges()})"

    # ============================================
    # 条件查询（公开 API）
    # ============================================
    
    def get_signal_conditions(self, signal: str) -> List[Dict[str, Any]]:
        """获取信号的条件列表
        
        Args:
            signal: 信号路径
            
        Returns:
            条件字典列表的副本（修改不影响内部状态）
        """
        raw = self.__signal_conditions.get(signal, [])
        return [dict(c) for c in raw]
    
    @property
    def _signal_conditions(self) -> Dict[str, List[Dict[str, Any]]]:
        """内部数据访问（向后兼容，建议使用 get_signal_conditions）"""
        warnings.warn(
            "直接访问 _signal_conditions 已废弃，请使用 get_signal_conditions(signal) 方法",
            DeprecationWarning,
            stacklevel=2
        )
        return {k: [dict(c) for c in v] 
                for k, v in self.__signal_conditions.items()}
    
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
            signal: 信号路径或通配符模式 (如 'top.cpu.*')

        Returns:
            驱动该信号的源节点列表
        """
        import fnmatch
        
        if '*' in signal or '?' in signal:
            # 通配符模式: 合并所有匹配节点的驱动
            drivers = set()
            for n in self.graph.nodes():
                if fnmatch.fnmatch(n, signal):
                    for src, _, _ in self.graph.in_edges(n, data=True):
                        drivers.add(src)
            return list(drivers)
        
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
            signal: 信号路径或通配符模式 (如 'top.cpu.*')

        Returns:
            被该信号驱动的节点列表
        """
        import fnmatch
        
        if '*' in signal or '?' in signal:
            # 通配符模式: 合并所有匹配节点的负载
            loads = set()
            for n in self.graph.nodes():
                if fnmatch.fnmatch(n, signal):
                    for _, dst, _ in self.graph.out_edges(n, data=True):
                        loads.add(dst)
            return list(loads)
        
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

        # 获取驱动源的时钟域 (如果驱动源是寄存器)
        source_clock = None
        if signal in self.__signal_conditions:
            conds = self.__signal_conditions[signal]
            if conds:
                source_clock = conds[0].get('clock_domain')

        # 推断负载的时钟域
        # 如果一个负载被某个时钟域的寄存器消费，则它属于该时钟域
        def infer_load_clock_domain(load_sig):
            """推断负载信号属于哪个时钟域"""
            # 如果负载本身是寄存器，直接返回其时钟域
            if load_sig in self.__signal_conditions:
                conds = self.__signal_conditions[load_sig]
                if conds and conds[0].get('clock_domain'):
                    return conds[0].get('clock_domain')
            
            # 否则查看哪些寄存器的时钟输入来自这个信号
            # 或者哪些寄存器的数据输入来自这个信号
            candidate_clocks = set()
            
            # 方法1: 检查哪些寄存器的时钟端口连接到这个信号
            for src, dst in self.graph.out_edges(load_sig):
                if dst in self.__signal_conditions:
                    dst_conds = self.__signal_conditions[dst]
                    if dst_conds and dst_conds[0].get('clock_domain'):
                        candidate_clocks.add(dst_conds[0].get('clock_domain'))
            
            # 方法2: 检查哪些寄存器的数据输入来自这个信号
            for src, dst in self.graph.in_edges(load_sig):
                if dst in self.__signal_conditions:
                    dst_conds = self.__signal_conditions[dst]
                    if dst_conds and dst_conds[0].get('clock_domain'):
                        candidate_clocks.add(dst_conds[0].get('clock_domain'))
            
            if len(candidate_clocks) == 1:
                return list(candidate_clocks)[0]
            elif len(candidate_clocks) > 1:
                # 多个时钟域，返回第一个
                return list(candidate_clocks)[0]
            return None

        loads = []
        for src, dst, data in self.graph.out_edges(signal, data=True):
            timing = {'clock_domain': None, 'reset_kind': None, 'target_kind': None}
            is_register = False

            # 尝试从 _signal_conditions 获取时序信息
            if dst in self.__signal_conditions:
                conds = self.__signal_conditions[dst]
                if conds:
                    c = conds[0]
                    timing['clock_domain'] = c.get('clock_domain')
                    timing['reset_kind'] = c.get('reset_kind')
                    timing['target_kind'] = c.get('target_kind')
                    is_register = c.get('target_kind') == 'register_output'
            
            # 如果没有时序信息，尝试推断
            if not timing['clock_domain']:
                inferred_clk = infer_load_clock_domain(dst)
                if inferred_clk:
                    timing['clock_domain'] = inferred_clk
                    # 如果目标被某个时钟域的寄存器消费，推断它可能是组合逻辑
                    if not timing['target_kind']:
                        timing['target_kind'] = 'combinational'

            # 判断跨时钟域和异步路径
            # 如果源信号本身有时钟域，才谈跨时钟域
            cross_clock = False
            async_path = False
            
            if source_clock and timing['clock_domain'] and source_clock != timing['clock_domain']:
                cross_clock = True
            
            if is_register and timing['reset_kind'] == 'async':
                async_path = True

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
        if signal not in self.__signal_conditions:
            return []

        results = []
        for cond_info in self.__signal_conditions[signal]:
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

    def _find_condition_key(self, signal: str) -> Optional[str]:
        """查找 signal 在 _signal_conditions 中的键（精确优先，前缀/短名称回退）
        
        注意：建议使用 resolve_signal_path() 获取完整路径列表，
        此方法仅在确定只有一个匹配时使用。
        """
        if signal in self.__signal_conditions:
            return signal

        # 前缀匹配: signal = 'test_signal_attributes', 匹配 'test_signal_attributes.result'
        prefix_matches = [k for k in self.__signal_conditions if k.startswith(signal + '.')]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        elif len(prefix_matches) > 1:
            return min(prefix_matches, key=len)

        # 短名称匹配: signal = 'result', 匹配 'test_signal_attributes.result'
        short_name = signal.split('.')[-1]
        if short_name != signal or not prefix_matches:
            short_matches = [k for k in self.__signal_conditions if k.split('.')[-1] == short_name]
            if len(short_matches) == 1:
                return short_matches[0]
            elif len(short_matches) > 1:
                return min(short_matches, key=len)

        return None

    def resolve_signal_path(self, signal: str) -> List[str]:
        """解析信号路径，支持精确、前缀、短名称、通配符匹配
        
        Args:
            signal: 信号路径（可以是完整路径、前缀、短名称或通配符模式）
            
        Returns:
            匹配的完整路径列表（可能多个）
        """
        import fnmatch
        matches = []
        
        # 1. 精确匹配
        if signal in self.__signal_conditions:
            return [signal]
        
        # 2. 通配符匹配
        if '*' in signal or '?' in signal:
            wildcard_matches = [k for k in self.__signal_conditions 
                              if fnmatch.fnmatch(k, signal)]
            if wildcard_matches:
                return wildcard_matches
        
        # 3. 前缀匹配
        prefix_matches = [k for k in self.__signal_conditions if k.startswith(signal + '.')]
        if prefix_matches:
            matches.extend(prefix_matches)
        
        # 4. 短名称匹配
        short_name = signal.split('.')[-1]
        if not prefix_matches or '.' not in signal:
            short_matches = [k for k in self.__signal_conditions 
                          if k.split('.')[-1] == short_name]
            for m in short_matches:
                if m not in matches:
                    matches.append(m)
        
        return matches

    def _get_conditions(self, signal: str) -> List[Dict[str, Any]]:
        """获取信号的条件列表，使用路径解析辅助方法"""
        key = self._find_condition_key(signal)
        if key:
            return self.__signal_conditions.get(key, [])
        return []

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
        for cond_info in self.__signal_conditions[condition_key]:
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

    def get_signals_info_batch(self, signals: List[str], source: str = 'both') -> Dict[str, Any]:
        """
        批量获取多个信号的完整信息

        Args:
            signals: 信号路径列表
            source: 数据源 ('netlist', 'ast', 'both')

        Returns:
            {
                'signals': [信号路径列表],
                'results': {
                    signal_path: {
                        'signal': signal_path,
                        'drivers': [...],
                        'loads': [...],
                        'conditions': [...]
                    }
                },
                'summary': {
                    'total_signals': int,
                    'signals_with_fan_in': int,
                    'signals_with_fan_out': int,
                    'signals_with_conditions': int
                }
            }
        """
        results = {}
        signals_with_fan_in = 0
        signals_with_fan_out = 0
        signals_with_conditions = 0

        for signal in signals:
            if not self.graph.has_node(signal):
                results[signal] = {
                    'signal': signal,
                    'error': 'signal not found',
                    'drivers': [],
                    'loads': [],
                    'conditions': []
                }
                continue

            info = self.get_signal_info(signal, source)
            results[signal] = info

            if info.get('drivers'):
                signals_with_fan_in += 1
            if info.get('loads'):
                signals_with_fan_out += 1
            if info.get('conditions'):
                signals_with_conditions += 1

        return {
            'signals': signals,
            'results': results,
            'summary': {
                'total_signals': len(signals),
                'signals_with_fan_in': signals_with_fan_in,
                'signals_with_fan_out': signals_with_fan_out,
                'signals_with_conditions': signals_with_conditions
            }
        }

    def _parse_fan_item(self, item: str) -> Tuple[str, str]:
        """解析 fan-in/fan-out 输出的一行: 'path  location'"""
        parts = item.strip().split()
        if len(parts) >= 2:
            # 最后两部分是 path 和 location
            path = parts[0]
            loc = parts[1]
            return path, loc
        return item.strip(), ''

    # ================================================================
    # 路径追踪 (委托给 PathTracer)
    # ================================================================

    def trace_path(self, from_signal: str, to_signal: str, enrich: bool = True) -> Dict[str, Any]:
        """追踪两个信号之间的路径"""
        tracer = PathTracer(self, self._netlist_driver)
        return tracer.trace_path(from_signal, to_signal, enrich)

    def trace_full_path(self, src: str, dst: str) -> Dict[str, Any]:
        """完整路径追踪 (含中间节点)"""
        tracer = PathTracer(self, self._netlist_driver)
        return tracer.trace_full_path(src, dst)

    def trace_paths_batch(self, path_specs: List[Tuple[str, str]]) -> Dict[str, Any]:
        """批量路径追踪"""
        tracer = PathTracer(self, self._netlist_driver)
        return tracer.trace_paths_batch(path_specs)

    def get_path_timing(self, src: str, dst: str) -> Dict[str, Any]:
        """获取路径时序信息"""
        tracer = PathTracer(self, self._netlist_driver)
        return tracer.get_path_timing(src, dst)

    def generate_timing_report(self, format: str = 'text') -> Dict[str, Any]:
        """生成时序报告"""
        tracer = PathTracer(self, self._netlist_driver)
        return tracer.generate_timing_report(format)

    # ================================================================
    # 条件覆盖率 (委托给 CoverageAnalyzer)
    # ================================================================

    def get_condition_coverage(self, signal: str) -> Dict[str, Any]:
        """获取信号条件覆盖率"""
        analyzer = CoverageAnalyzer(self)
        return analyzer.get_condition_coverage(signal)

    def analyze_condition_coverage(self, signals: Optional[List[str]] = None) -> Dict[str, Any]:
        """分析条件覆盖率"""
        analyzer = CoverageAnalyzer(self)
        return analyzer.analyze_condition_coverage(signals)

    def export_to_dot(self, file_path: str = None, subgraph: str = None, 
                       include_timing: bool = True, include_conditions: bool = True) -> str:
        """
        导出图到 DOT 格式

        Args:
            file_path: 输出文件路径, None 表示返回 DOT 字符串
            subgraph: 子图范围, None 表示导出完整图
                       支持格式: 'module.signal' 或 glob pattern 'module.*'
            include_timing: 是否包含时序信息(时钟域、reset 类型)
            include_conditions: 是否包含条件信息

        Returns:
            DOT 格式字符串 (如果 file_path 为 None)
        """
        # 获取要导出的节点
        if subgraph:
            nodes = self._filter_nodes_by_pattern(subgraph)
        else:
            nodes = list(self.graph.nodes())

        # 构建 DOT 内容
        lines = []
        lines.append('digraph design_graph {')
        lines.append('    # Graph attributes')
        lines.append('    rankdir=LR;')
        lines.append('    splines=ortho;')
        lines.append('    nodesep=0.5;')
        lines.append('    ranksep=0.8;')
        lines.append('')

        # 添加节点定义
        lines.append('    # Nodes')
        for node in nodes:
            attrs = self.graph.nodes[node]
            node_label = node.split('.')[-1]  # 简短名称
            
            # 节点样式
            kind = attrs.get('kind', 'unknown')
            timing = attrs.get('timing', 'unknown')
            
            # 根据类型设置形状和颜色
            shape = 'box'
            color = '#333333'
            fillcolor = 'white'
            
            if kind == 'Port':
                shape = 'oval'
                color = '#0066cc'
            elif kind == 'State':
                shape = 'box'
                color = '#009966'
            elif kind == 'Net':
                shape = 'ellipse'
            
            # 时序信息颜色
            if include_timing:
                if timing == 'sequential':
                    fillcolor = '#e6f3ff'
                elif timing == 'combinational':
                    fillcolor = '#fff9e6'
            
            # 构建节点属性
            tooltip_parts = [f"{node_label}", f"kind: {kind}", f"timing: {timing}"]
            
            # 添加时钟域信息
            if include_timing and node in self.__signal_conditions and self.__signal_conditions[node]:
                c = self.__signal_conditions[node][0]
                clk = c.get('clock_domain', '')
                reset = c.get('reset_kind', '')
                if clk:
                    tooltip_parts.append(f"clock: {clk.split('.')[-1]}")
                if reset:
                    tooltip_parts.append(f"reset: {reset}")
            
            tooltip = '\\n'.join(tooltip_parts)
            
            lines.append(f'    "{node}" [')
            lines.append(f'        label="{node_label}"')
            lines.append(f'        shape={shape}')
            lines.append(f'        style=filled')
            lines.append(f'        fillcolor="{fillcolor}"')
            lines.append(f'        color="{color}"')
            lines.append(f'        fontname="Helvetica"')
            lines.append(f'        fontsize=10')
            lines.append(f'        tooltip="{tooltip}"')
            lines.append('    ];')

        lines.append('')

        # 添加边定义
        lines.append('    # Edges')
        for src, dst, data in self.graph.edges(nodes, data=True):
            edge_label_parts = []
            
            # 关系类型
            relation = data.get('relation', '')
            if relation:
                edge_label_parts.append(relation)
            
            # 时序类型
            if include_timing:
                timing = data.get('timing', '')
                if timing:
                    edge_label_parts.append(f"[{timing}]")
            
            # 条件信息
            if include_conditions:
                condition = data.get('condition', '')
                if condition:
                    edge_label_parts.append(f"({condition[:30]}...)" if len(condition) > 30 else f"({condition})")
            
            edge_label = ', '.join(edge_label_parts) if edge_label_parts else ''
            
            # 边样式
            color = '#666666'
            penwidth = '1.0'
            
            if relation == 'controls':
                color = '#cc6600'
                penwidth = '1.5'
            elif data.get('cross_clock'):
                color = '#ff0000'
                penwidth = '2.0'
            elif timing == 'sequential' or timing == 'sequential_input':
                color = '#0066cc'
            elif timing == 'combinational':
                color = '#999900'
            
            lines.append(f'    "{src}" -> "{dst}" [')
            if edge_label:
                lines.append(f'        label="{edge_label}"')
            lines.append(f'        color="{color}"')
            lines.append(f'        penwidth="{penwidth}"')
            lines.append(f'        fontname="Helvetica"')
            lines.append(f'        fontsize=9')
            lines.append('    ];')

        lines.append('}')

        dot_content = '\n'.join(lines)

        # 写入文件或返回
        if file_path:
            with open(file_path, 'w') as f:
                f.write(dot_content)
            return None
        else:
            return dot_content

    def export_to_svg(self, file_path: str, subgraph: str = None,
                       include_timing: bool = True, include_conditions: bool = True) -> bool:
        """
        导出图到 SVG 格式

        需要 graphviz 安装

        Args:
            file_path: 输出 SVG 文件路径
            subgraph: 子图范围
            include_timing: 是否包含时序信息
            include_conditions: 是否包含条件信息

        Returns:
            是否成功
        """
        try:
            import subprocess
            dot_content = self.export_to_dot(subgraph=subgraph, 
                                              include_timing=include_timing,
                                              include_conditions=include_conditions)
            
            # 调用 dot 生成 SVG
            result = subprocess.run(
                ['dot', '-Tsvg', '-o', file_path],
                input=dot_content,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            return result.returncode == 0
        except Exception as e:
            print(f"Error generating SVG: {e}")
            return False

    def _filter_nodes_by_pattern(self, pattern: str) -> List[str]:
        """
        根据模式过滤节点

        Args:
            pattern: 模块路径或 glob 模式, 如 'uart_tx.*' 或 'uart_controller.uart_tx.data'

        Returns:
            匹配的节点列表
        """
        import fnmatch

        # 如果是完整路径且节点存在
        if pattern in self.graph.nodes():
            return [pattern]

        # 如果是 glob 模式
        nodes = []
        pattern_parts = pattern.split('.')
        
        for node in self.graph.nodes():
            node_parts = node.split('.')
            
            # 检查是否匹配
            match = True
            for i, part in enumerate(pattern_parts):
                if i >= len(node_parts):
                    match = False
                    break
                if part == '*':
                    continue
                if part != node_parts[i] and part != '*':
                    match = False
                    break
            
            if match:
                nodes.append(node)

        return nodes

    def _generate_markdown_report(self, data: Dict) -> str:
        """生成 Markdown 格式的报告"""
        lines = ["# Timing Report\n", "## Summary\n"]
        s = data['summary']
        lines.extend([f"| Metric | Value |", f"|---------|-------|",
                      f"| Total Signals | {s['total_signals']} |",
                      f"| Signals with Timing | {s['signals_with_timing']} |",
                      f"| Clock Domains | {s['clock_domains']} |",
                      f"| Registers | {s['registers']} |",
                      f"| Async Paths | {s['async_paths']} |",
                      f"| Cross-Clock Paths | {s['cross_clock_paths']} |", ""])
        lines.append("## Clock Domains\n")
        for clk, info in data['clock_domains'].items():
            lines.append(f"### {clk} (reset={info['reset_kind']})\n")
            lines.append(f"- Registers: {len(info['registers'])}")
            lines.append(f"- Combinational: {len(info['signals'])}")
            if info['registers']:
                lines.append(f"- Examples: `{'`, `'.join([s.split('.')[-1] for s in info['registers'][:5]])}`")
            lines.append("")
        if data['cross_clock_paths']:
            lines.append("## CDC Risks\n")
            lines.extend([f"| Source | Target | Source Clock | Target Clock |",
                          f"|--------|--------|--------------|---------------|"])
            for p in data['cross_clock_paths'][:10]:
                lines.append(f"| {p['source'].split('.')[-1]} | {p['target'].split('.')[-1]} | {p['source_clock']} | {p['target_clock']} |")
            lines.append("")
        return '\n'.join(lines)


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