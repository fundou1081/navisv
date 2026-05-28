"""
PathTracer - 信号路径追踪

从 DesignGraph 提取的路径追踪逻辑:
- trace_path: 单路径追踪
- trace_full_path: 完整路径追踪 (含中间节点)
- trace_paths_batch: 批量路径追踪
- get_path_timing: 路径时序分析
- generate_timing_report: 时序报告生成
"""

import subprocess
import os
import tempfile
from typing import Dict, List, Any, Optional, Tuple


class PathTracer:
    """信号路径追踪"""

    def __init__(self, graph, netlist_driver=None):
        """
        Args:
            graph: DesignGraph 实例
            netlist_driver: NetlistDriver 实例
        """
        self.graph = graph
        self.netlist_driver = netlist_driver

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
        if not self.netlist_driver:
            return {'from': from_signal, 'to': to_signal, 'path': [], 'success': False}

        result = self.netlist_driver.run_path_trace(from_signal, to_signal)

        # 解析路径
        path_nodes = self._parse_path_trace(result['stdout'])

        # 用 AST conditions 增强(只增强终点,即 to_signal)
        if enrich and to_signal in self.__signal_conditions:
            # 找到 to_signal 对应的节点并附加条件
            for node in path_nodes:
                if node['path'] == to_signal:
                    conds = self.__signal_conditions[to_signal]
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
        if self.netlist_driver:
            result = self.netlist_driver.run_path_trace(src, dst)
            if result['success']:
                return self._build_trace_from_netlist(result['stdout'], src, dst)

        # 3. 路径不存在 - 检查原因
        src_exists = src in self.graph
        dst_exists = dst in self.graph
        
        if not src_exists and not dst_exists:
            status = 'not_found'
            error = f'source "{src}" and target "{dst}" not found in graph'
        elif not src_exists:
            status = 'not_found'
            error = f'source "{src}" not found in graph'
        elif not dst_exists:
            status = 'not_found'
            error = f'target "{dst}" not found in graph'
        else:
            # 两个节点都存在但无路径 - 可能是图不完整
            status = 'uncertain'
            error = 'no path found (graph may be incomplete due to slang-netlist limitations)'
        
        return {
            'from': src,
            'to': dst,
            'success': False,
            'status': status,
            'error': error,
            'path': [],
            'summary': {
                'reset_safe': False,
                'cross_clock': False,
                'register_count': 0,
                'clocks': [],
                'path_length': 0,
                'path_confidence': {'score': 0.0, 'details': {}}
            }
        }

    def trace_paths_batch(self, path_specs: List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        批量追踪多个路径

        Args:
            path_specs: 路径规格列表,每个元素为 (src, dst) 元组

        Returns:
            {
                'paths': [
                    {'from': src, 'to': dst, 'success': bool, 'path': [...], 'summary': {...}}
                ],
                'summary': {
                    'total_paths': int,
                    'successful_paths': int,
                    'failed_paths': int
                }
            }
        """
        results = []
        successful = 0
        failed = 0

        for src, dst in path_specs:
            result = self.trace_full_path(src, dst)
            results.append(result)
            if result['success']:
                successful += 1
            else:
                failed += 1

        return {
            'paths': results,
            'summary': {
                'total_paths': len(path_specs),
                'successful_paths': successful,
                'failed_paths': failed
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

            if signal in self.__signal_conditions:
                conds = self.__signal_conditions[signal]
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
            if signal in self.__signal_conditions and self.__signal_conditions[signal]:
                loc = self.__signal_conditions[signal][0].get('location', {})
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
            'status': 'found',
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
            if signal in self.__signal_conditions:
                conds = self.__signal_conditions[signal]
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
            if signal in self.__signal_conditions and self.__signal_conditions[signal]:
                loc = self.__signal_conditions[signal][0].get('location', {})
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
            'status': 'found',
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

            if signal in self.__signal_conditions:
                conds = self.__signal_conditions[signal]
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
            if signal in self.__signal_conditions and self.__signal_conditions[signal]:
                loc = self.__signal_conditions[signal][0].get('location', {})
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
            'status': 'found',
            'summary': {
                'reset_safe': reset_safe,
                'cross_clock': cross_clock,
                'register_count': register_count,
                'clocks': list(clocks_seen),
                'path_length': len(path_info)
            }
        }

    def generate_timing_report(self, format: str = 'text') -> Dict[str, Any]:
        """
        生成完整的时序分析报告

        Args:
            format: 输出格式 ('text', 'markdown', 'json')

        Returns:
            {
                'summary': {...},
                'clock_domains': {...},
                'registers': [...],
                'async_paths': [...],
                'cross_clock_paths': [...],
                'report_text': str  (format='text'时)
            }
        """
        clock_domains_data = {}
        all_registers = []
        async_paths = []
        cross_clock_paths = []

        # 按时钟域分组
        for sig, conds in self.__signal_conditions.items():
            if not conds:
                continue
            clk = conds[0].get('clock_domain')
            reset_kind = conds[0].get('reset_kind', 'sync')
            target_kind = conds[0].get('target_kind')
            if not clk:
                continue
            clk_short = clk.split('.')[-1] if '.' in clk else clk

            if clk_short not in clock_domains_data:
                clock_domains_data[clk_short] = {
                    'full_name': clk,
                    'signals': [],
                    'registers': [],
                    'reset_kind': reset_kind
                }
            if target_kind == 'register_output':
                clock_domains_data[clk_short]['registers'].append(sig)
                all_registers.append({'signal': sig, 'clock': clk_short, 'reset_kind': reset_kind})
            else:
                clock_domains_data[clk_short]['signals'].append(sig)

        # 收集跨时钟域和异步路径
        for sig in self.graph.nodes():
            loads = self.get_loads_with_timing(sig)
            for l in loads:
                if l.get('cross_clock'):
                    cross_clock_paths.append({
                        'source': sig,
                        'target': l['signal'],
                        'source_clock': l['timing'].get('clock_domain', '').split('.')[-1],
                        'target_clock': next((c['clock_domain'].split('.')[-1] for c in self.__signal_conditions.get(sig, []) if c.get('clock_domain')), '')
                    })
                if l.get('async_path'):
                    async_paths.append({'source': sig, 'target': l['signal']})

        # 生成文本报告
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("                        TIMING REPORT")
        report_lines.append("=" * 70)
        report_lines.append("")
        report_lines.append("SUMMARY")
        report_lines.append("-" * 70)
        total_signals = len(self.graph.nodes())
        signals_with_timing = sum(1 for s, c in self.__signal_conditions.items() if c)
        report_lines.append(f"  Total signals:          {total_signals}")
        report_lines.append(f"  Signals with timing:    {signals_with_timing}")
        report_lines.append(f"  Clock domains:          {len(clock_domains_data)}")
        report_lines.append(f"  Registers:              {len(all_registers)}")
        report_lines.append(f"  Async paths:            {len(async_paths)}")
        report_lines.append(f"  Cross-clock paths:      {len(cross_clock_paths)}")
        report_lines.append("")

        report_lines.append("CLOCK DOMAINS")
        report_lines.append("-" * 70)
        for clk, data in sorted(clock_domains_data.items()):
            report_lines.append(f"\n  [{clk}] reset={data['reset_kind']}")
            report_lines.append(f"    Registers: {len(data['registers'])}")
            report_lines.append(f"    Combinational: {len(data['signals'])}")
            if data['registers']:
                report_lines.append(f"    Examples: {', '.join([s.split('.')[-1] for s in data['registers'][:3]])}")
        report_lines.append("")

        if cross_clock_paths:
            report_lines.append("CROSS-CLOCK DOMAIN PATHS (CDC RISKS)")
            report_lines.append("-" * 70)
            for path in cross_clock_paths[:10]:
                report_lines.append(f"  {path['source'].split('.')[-1]} [{path['source_clock']}] -> {path['target'].split('.')[-1]} [{path['target_clock']}]")
            if len(cross_clock_paths) > 10:
                report_lines.append(f"  ... and {len(cross_clock_paths) - 10} more")
            report_lines.append("")

        if async_paths:
            report_lines.append("ASYNC PATHS (RESET RISKS)")
            report_lines.append("-" * 70)
            for path in async_paths[:10]:
                report_lines.append(f"  {path['source'].split('.')[-1]} -> {path['target'].split('.')[-1]}")
            if len(async_paths) > 10:
                report_lines.append(f"  ... and {len(async_paths) - 10} more")
            report_lines.append("")

        report_lines.append("=" * 70)
        report_text = '\n'.join(report_lines)

        result = {
            'summary': {
                'total_signals': total_signals,
                'signals_with_timing': signals_with_timing,
                'clock_domains': len(clock_domains_data),
                'registers': len(all_registers),
                'async_paths': len(async_paths),
                'cross_clock_paths': len(cross_clock_paths)
            },
            'clock_domains': clock_domains_data,
            'registers': all_registers,
            'async_paths': async_paths,
            'cross_clock_paths': cross_clock_paths,
            'report_text': report_text
        }

        return result

