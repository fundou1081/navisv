import os
"""
GraphBuilder - 构建 enriched MultiDiGraph

Layer 2: 组合 Parser 结果 + 分析逻辑
- 添加 Named Nodes (Port + State)
- 添加边(带完整属性)
- 从 AST 提取条件信息
- 推断时序分类
- 计算 bit_mapping
"""

import networkx as nx
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

from navisv.parsers import ASTParser, NetlistParser, NetlistNode, NetlistEdge
from navisv.graph.condition_annotator import ConditionAnnotator
from navisv.graph.ast_analyzer import ASTAnalyzer


@dataclass
class NodeAttr:
    """节点属性"""
    name: str
    path: str
    kind: str
    bit_width: Tuple[int, int] = (0, 0)
    direction: str = ''
    timing: str = 'unknown'
    module: str = ''
    location: Optional[Dict[str, Any]] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def bit_width_str(self) -> str:
        msb, lsb = self.bit_width
        if msb == lsb:
            return f"[{msb}]"
        return f"[{msb}:{lsb}]"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'path': self.path,
            'kind': self.kind,
            'bit_width': self.bit_width,
            'direction': self.direction,
            'timing': self.timing,
            'module': self.module,
            'location': self.location,
            'attributes': self.attributes,
        }


@dataclass
class EdgeAttr:
    """边属性"""
    relation: str = 'drives'

    # 时序
    timing: str = 'unknown'
    edge_kind: str = 'None'

    # 位精确
    bounds: Tuple[int, int] = (0, 0)
    bit_mapping: Optional[Dict[int, int]] = None

    # 条件
    condition: str = ''
    condition_kind: str = ''  # 'if', 'case', 'ternary'
    condition_signals: List[str] = field(default_factory=list)  # 控制信号列表

    # 位置
    location: Optional[Dict[str, Any]] = None

    # 统计
    path_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'relation': self.relation,
            'timing': self.timing,
            'edge_kind': self.edge_kind,
            'bounds': self.bounds,
            'bit_mapping': self.bit_mapping,
            'condition': self.condition,
            'condition_kind': self.condition_kind,
            'condition_signals': self.condition_signals,
            'location': self.location,
            'path_count': self.path_count,
        }


class GraphBuilder:
    """
    Layer 2: 构建 enriched MultiDiGraph

    组合 ASTParser + NetlistParser 的结果,
    推断时序分类,提取条件信息。
    """

    def __init__(self, ast_parser: ASTParser, netlist_parser: NetlistParser,
                 ast_json_path: str = None, source_files: list = None):
        self.ast = ast_parser
        self.netlist = netlist_parser
        self.ast_json_path = ast_json_path
        self.source_files = source_files or []
        self.graph: nx.MultiDiGraph = None

        # 缓存
        self._node_attrs: Dict[str, NodeAttr] = {}
        self._edge_attrs: Dict[Tuple[str, str, Any], EdgeAttr] = {}

        # 符号映射: symbol_id -> (name, ast_path)
        self._symbol_to_path: Dict[str, Tuple[str, str]] = {}
        # 符号映射: netlist addr -> path
        self._symbol_to_netlist_path: Dict[str, str] = {}

        # AST 分析结果: result_path -> [conditions]
        self._signal_conditions: Dict[str, List[Dict]] = {}
        self._procedural_timing: Dict[int, Dict] = {}  # line -> timing info  # signal -> [{condition, kind, location}]


        self._build_symbol_map()

    def _read_source_line(self, file: str, line: int, col_start: int, col_end: int) -> str:
        """从源文件读取指定范围的文本"""
        if not file or line <= 0:
            return ''

        # 优先从 source_files 中查找(传入的是绝对路径)
        if self.source_files:
            for src in self.source_files:
                if os.path.isabs(src) and os.path.exists(src):
                    if file in src or src.endswith(file):
                        return self._extract_from_file(src, line, col_start, col_end)

        # 尝试从 ast_json_path 构建路径
        if self.ast_json_path:
            ast_dir = os.path.dirname(self.ast_json_path)
            for rel in ['', '..', '../..']:
                path = os.path.join(ast_dir, rel, file)
                if os.path.exists(path):
                    return self._extract_from_file(path, line, col_start, col_end)

        # 尝试当前工作目录
        if os.path.exists(file):
            return self._extract_from_file(file, line, col_start, col_end)
        return ''

    def _extract_from_file(self, filepath: str, line: int, col_start: int, col_end: int) -> str:
        """从文件提取指定行和列范围的文本(AST column 是 1-indexed)"""
        try:
            with open(filepath) as f:
                lines = f.readlines()
            if 0 < line <= len(lines):
                src_line = lines[line - 1]
                col_start = max(0, col_start - 1)  # 1-indexed → 0-indexed
                col_end = max(0, col_end - 1)
                if col_end > len(src_line):
                    col_end = len(src_line)
                if col_start < len(src_line):
                    return src_line[col_start:col_end].strip()
        except Exception:
            pass
        return ''

    def _build_symbol_map(self):
        """构建符号映射表

        从 AST NamedValue: symbol="id name" 提取 name
        从 Netlist 建立 name -> path 映射
        """
        self._symbol_to_path = {}  # sym_id -> (name, ast_path)
        self._name_to_path = {}    # signal_name -> full_path

        if not self.ast or not self.ast.root:
            return

        # 从 AST 收集 symbol_id -> (name, module_path)
        def traverse(node):
            if node.kind == 'NamedValue':
                sym = node.attributes.get('symbol', '')
                if sym and ' ' in sym:
                    sym_id, name = sym.split(' ', 1)
                    if sym_id not in self._symbol_to_path:
                        self._symbol_to_path[sym_id] = (name, node.path)
            for child in node.children:
                traverse(child)

        traverse(self.ast.root)

        # 从 Netlist 的 named nodes 建立 name -> path 映射
        for node in self.netlist.nodes:
            if node.path:
                # 使用完整路径作为 key
                self._name_to_path[node.path] = node.path
                # 也用简化的 name 作为 key(如果有重复会用第一个)
                name = node.name
                if name and name not in self._name_to_path:
                    self._name_to_path[name] = node.path

        # 处理边的 symbol.path 中引用但没有对应节点的情况
        # 例如模块实例端口连接的中间信号
        existing_paths = set(n.path for n in self.netlist.nodes)
        for edge in self.netlist.edges:
            if edge.symbol and edge.symbol.get('path'):
                symbol_path = edge.symbol['path']
                # 如果 symbol.path 不存在于节点中，创建一个占位符 Net 节点
                if symbol_path and symbol_path not in existing_paths:
                    # 解析模块路径和信号名
                    parts = symbol_path.rsplit('.', 1)
                    if len(parts) == 2:
                        module_path, signal_name = parts
                        # 创建占位符节点
                        placeholder_node = NetlistNode(
                            id=-1,  # 占位符用负数 ID
                            name=signal_name,
                            kind='Net',
                            path=symbol_path,
                            bounds=edge.bounds if edge.bounds != (0, 0) else (0, 0),
                            direction='',
                            location=edge.symbol.get('location'),
                            value=None,
                            attributes={'placeholder': True, 'from_edge': True}
                        )
                        self.netlist.nodes.append(placeholder_node)
                        existing_paths.add(symbol_path)
                        # 添加到 path_map
                        self.netlist.path_map[symbol_path] = placeholder_node



    def build(self) -> nx.MultiDiGraph:
        """构建完整的 MultiDiGraph"""
        self.graph = nx.MultiDiGraph()

        # 1. 添加 Named Nodes (Port + State)
        self._add_named_nodes()

        # 2. 分析 AST 获取条件信息
        self._ast_analyzer = ASTAnalyzer(self.ast, {path: path for path in self.graph.nodes}, self._node_attrs, self.graph, self.source_files)
        self._ast_analyzer.analyze()
        self._signal_conditions = self._ast_analyzer._signal_conditions

        # 3. 从 Netlist 添加边
        self._add_edges()

        # 4. 丰富边的条件属性
        self._enrich_edges_with_conditions()

        # 5. 推断时序分类
        self._classify_timing()

        # 6. 标注 true_condition + always_comb + 拼接表达式
        annotator = ConditionAnnotator(self.graph, self._edge_attrs, self.ast_json_path)
        annotator.annotate_all()

        # 7. 提取 interface 信息
        self._extract_interface_info()

        # 8. 计算 bit_mapping
        self._calculate_bit_mapping()

        return self.graph

    def _add_named_nodes(self):
        """添加 Named Nodes (Port + State + Net)"""
        # 先添加 State 节点(更高优先级)
        for state in self.netlist.get_registers():
            attr = NodeAttr(
                name=state.name,
                path=state.path,
                kind='State',
                bit_width=state.bounds,
                timing='sequential',
                module=self._extract_module(state.path),
                location=state.location,
            )
            self._add_node(state.path, attr)

        # 再添加 Port 节点(如果不存在同名节点)
        for port in self.netlist.get_ports():
            if port.path in self._node_attrs:
                continue

            attr = NodeAttr(
                name=port.name,
                path=port.path,
                kind='Port',
                bit_width=port.bounds,
                direction=port.direction,
                timing='combinational',
                module=self._extract_module(port.path),
                location=port.location,
            )
            self._add_node(port.path, attr)

        # 添加 Net 类型的 placeholder 节点(模块实例端口连接信号)
        for node in self.netlist.nodes:
            if node.kind == 'Net' and node.attributes.get('placeholder') and node.path not in self._node_attrs:
                attr = NodeAttr(
                    name=node.name,
                    path=node.path,
                    kind='Net',
                    bit_width=node.bounds,
                    timing='combinational',
                    module=self._extract_module(node.path),
                    location=node.location,
                    attributes=node.attributes,
                )
                self._add_node(node.path, attr)

    def _add_node(self, path: str, attr: NodeAttr):
        """添加节点到图中"""
        if path in self.graph:
            return

        self.graph.add_node(path, **attr.to_dict())
        self._node_attrs[path] = attr

    def _add_edges(self):
        """从 Netlist 添加边"""
        # 收集所有无 path 的 Assignment/Conditional 节点的入边和出边信息
        # 用于跳过中间节点，直接连接源信号到目标信号
        intermediate_info = {}  # node_id -> {'in': [(src_path, symbol)], 'out': [(tgt_path, symbol)]}
        
        for edge in self.netlist.edges:
            src_node = self.netlist.get_node_by_id(edge.source)
            tgt_node = self.netlist.get_node_by_id(edge.target)

            if not src_node or not tgt_node:
                continue

            # 收集无 path 的 Assignment/Conditional 节点信息
            if tgt_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge') and not tgt_node.path:
                if tgt_node.id not in intermediate_info:
                    intermediate_info[tgt_node.id] = {'in': [], 'out': [], 'kind': tgt_node.kind}
                src_path = src_node.path if src_node.path else ''
                if not src_path and edge.symbol and edge.symbol.get('path'):
                    src_path = edge.symbol['path']
                if src_path:
                    intermediate_info[tgt_node.id]['in'].append((src_path, edge.symbol))
            
            if src_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge') and not src_node.path:
                if src_node.id not in intermediate_info:
                    intermediate_info[src_node.id] = {'in': [], 'out': [], 'kind': src_node.kind}
                tgt_path = tgt_node.path if tgt_node.path else ''
                if not tgt_path and edge.symbol and edge.symbol.get('path'):
                    tgt_path = edge.symbol['path']
                if tgt_path:
                    intermediate_info[src_node.id]['out'].append((tgt_path, edge.symbol))

        # 传播: 中间节点的入边路径 → 出边目标
        # 当 Conditional → Assignment 边没有 symbol 时，从入边继承路径
        for _ in range(3):  # 多轮传播处理嵌套
            for nid, info in intermediate_info.items():
                if info['out'] and info['in']:
                    continue  # 已有信息
                # 如果有入边但没有出边，从入边传播到出边节点
                if info['in'] and not info['out']:
                    # 找这个节点的出边
                    for edge in self.netlist.edges:
                        if edge.source == nid:
                            tgt = self.netlist.get_node_by_id(edge.target)
                            if tgt and tgt.kind in ('Assignment', 'Conditional', 'Case', 'Merge') and not tgt.path:
                                tgt_info = intermediate_info.get(tgt.id)
                                if tgt_info and not tgt_info['in']:
                                    # 从源节点继承入边路径
                                    for src_path, sym in info['in']:
                                        tgt_info['in'].append((src_path, sym))

        # 处理边
        for edge in self.netlist.edges:
            src_node = self.netlist.get_node_by_id(edge.source)
            tgt_node = self.netlist.get_node_by_id(edge.target)

            if not src_node or not tgt_node:
                continue

            src_path = src_node.path if src_node.path else ''
            tgt_path = tgt_node.path if tgt_node.path else ''

            # 如果 source 没有 path 但有 symbol.path 且不等于 tgt_path,使用 symbol.path
            if not src_path and edge.symbol and edge.symbol.get('path'):
                symbol_path = edge.symbol['path']
                if symbol_path and symbol_path != tgt_path:
                    src_path = symbol_path

            # 如果 target 没有 path 但有 symbol.path 且不等于 src_path,使用 symbol.path
            if not tgt_path and edge.symbol and edge.symbol.get('path'):
                symbol_path = edge.symbol['path']
                if symbol_path and symbol_path != src_path:
                    tgt_path = symbol_path

            # 如果 target 是中间节点且没有有效 path，递归从出边获取目标路径
            if not tgt_path and tgt_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge'):
                tgt_path = self._resolve_intermediate_path(tgt_node.id, intermediate_info, 'out')

            # 如果 source 是中间节点且没有有效 path，递归从入边获取源路径
            if not src_path and src_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge'):
                src_path = self._resolve_intermediate_path(src_node.id, intermediate_info, 'in')

            # 跳过没有有效路径的边
            if not src_path or not tgt_path:
                continue

            # 跳过 self-loop
            if src_path == tgt_path:
                continue

            attr = EdgeAttr(
                edge_kind=edge.edge_kind,
                bounds=edge.bounds,
                location=edge.symbol.get('location') if edge.symbol else None,
            )

            key = self.graph.add_edge(
                src_path,
                tgt_path,
                **attr.to_dict()
            )

            self._edge_attrs[(src_path, tgt_path, key)] = attr

            # 如果 target 是中间节点，为每条出边创建从 source 到 target 的边
            if tgt_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge') and not tgt_node.path:
                info = intermediate_info.get(tgt_node.id)
                if info and len(info['out']) > 1:
                    for out_tgt_path, out_symbol in info['out'][1:]:
                        if out_tgt_path and out_tgt_path != src_path:
                            out_attr = EdgeAttr(
                                edge_kind=edge.edge_kind,
                                bounds=edge.bounds,
                                location=out_symbol.get('location') if out_symbol else None,
                            )
                            out_key = self.graph.add_edge(
                                src_path,
                                out_tgt_path,
                                **out_attr.to_dict()
                            )
                            self._edge_attrs[(src_path, out_tgt_path, out_key)] = out_attr

    def _extract_module(self, path: str) -> str:
        """从路径提取模块名"""
        parts = path.rsplit('.', 1)
        return parts[0] if len(parts) > 1 else 'top'

    def _resolve_intermediate_path(self, node_id: int, intermediate_info: dict, direction: str = 'out', depth: int = 0) -> str:
        """递归解析中间节点到有 path 的节点"""
        if depth > 10:
            return ''
        info = intermediate_info.get(node_id)
        if not info:
            return ''
        targets = info.get(direction, [])
        if not targets:
            return ''
        for path, _ in targets:
            if path:
                node = self.netlist.get_node_by_path(path)
                if node and node.kind in ('Assignment', 'Conditional', 'Case', 'Merge'):
                    result = self._resolve_intermediate_path(node.id, intermediate_info, direction, depth + 1)
                    if result:
                        return result
                return path
        return ''

    def _classify_timing(self):
        """
        推断时序分类
        """
        # 标记 State 节点
        for node_path in self.graph.nodes():
            node_attr = self._node_attrs.get(node_path)
            if node_attr and node_attr.kind == 'State':
                node_attr.timing = 'sequential'
                self.graph.nodes[node_path]['timing'] = 'sequential'

        # 分类边
        for src, dst, data in self.graph.edges(data=True):
            src_attr = self._node_attrs.get(src)
            dst_attr = self._node_attrs.get(dst)

            if not src_attr or not dst_attr:
                data['timing'] = 'combinational'
                continue

            if data.get('edge_kind') in ('PosEdge', 'NegEdge'):
                data['timing'] = 'sequential_input'
            elif data.get('timing') == 'combinational':
                # 保持已设置的组合逻辑 timing 不变
                pass
            elif src_attr.kind == 'State' and dst_attr.kind == 'State':
                # State -> State 边通常是 sequential_output (寄存器到寄存器)
                data['timing'] = 'sequential_output'
            elif dst_attr.kind == 'State' and data.get('edge_kind') == 'None':
                data['timing'] = 'sequential_input'
            else:
                data['timing'] = 'combinational'

    def _calculate_bit_mapping(self):
        """计算 bit_mapping"""
        for src, dst, data in self.graph.edges(data=True):
            bounds = data.get('bounds', (0, 0))
            msb, lsb = bounds

            if msb >= lsb:
                bit_mapping = {i: i for i in range(lsb, msb + 1)}
            else:
                bit_mapping = {}

            data['bit_mapping'] = bit_mapping

    def _enrich_edges_with_conditions(self):
        """丰富边的条件属性"""
        for target_path, conditions in self._signal_conditions.items():
            if not conditions:
                continue

            for (src, dst, key), attr in self._edge_attrs.items():
                if dst == target_path and not attr.condition:
                    cond_info = conditions[0]
                    attr.condition = cond_info['condition']
                    attr.condition_kind = cond_info['kind']
                    attr.condition_signals = [c['condition'] for c in conditions]

                    if self.graph.has_edge(src, dst, key):
                        self.graph[src][dst][key]['condition'] = attr.condition
                        self.graph[src][dst][key]['condition_kind'] = attr.condition_kind
                        self.graph[src][dst][key]['condition_signals'] = attr.condition_signals

        for target_path, conditions in self._signal_conditions.items():
            if target_path not in self.graph:
                continue
            for cond_info in conditions:
                cond_signal = cond_info.get('condition', '')
                if cond_signal and cond_signal in self.graph:
                    if not self.graph.has_edge(cond_signal, target_path):
                        attr = EdgeAttr(
                            edge_kind='None', bounds=(0, 0),
                            condition=cond_signal,
                            condition_kind=cond_info.get('kind', ''),
                            condition_signals=[cond_signal],
                        )
                        key = self.graph.add_edge(cond_signal, target_path, **attr.to_dict())
                        self._edge_attrs[(cond_signal, target_path, key)] = attr

    def _extract_interface_info(self):
        """从图节点推断 interface/modport 信息"""
        if not self.ast_json_path or not os.path.exists(self.ast_json_path):
            return
        import json as json_mod
        try:
            with open(self.ast_json_path) as f:
                ast_data = json_mod.load(f)
        except (json_mod.JSONDecodeError, IOError):
            return

        modport_defs = self._collect_modport_defs(ast_data)
        if not modport_defs:
            return

        for path, data in self.graph.nodes(data=True):
            kind = data.get('kind', '')
            if kind in ('', '?'):
                data['is_interface_signal'] = True
                for addr, modports in modport_defs.items():
                    if modports:
                        data.setdefault('modports', modports)
                        break

    def _collect_modport_defs(self, ast_data: dict) -> dict:
        """从 AST 收集所有 modport 定义"""
        result = {}

        def walk(node):
            if isinstance(node, dict):
                if node.get('kind') == 'InstanceBody':
                    members = node.get('members', [])
                    modports = {}
                    for m in members:
                        if m.get('kind') == 'Modport':
                            mp_name = m.get('name', '')
                            ports = []
                            for mp in m.get('members', []):
                                if mp.get('kind') == 'ModportPort':
                                    ports.append({
                                        'name': mp.get('name', ''),
                                        'direction': mp.get('direction', ''),
                                    })
                            if mp_name:
                                modports[mp_name] = ports
                    if modports:
                        result[str(node.get('addr', ''))] = modports
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(ast_data)
        return result

    def summary(self) -> Dict[str, Any]:
        """返回摘要"""
        if not self.graph:
            return {}

        node_kinds = {}
        timing_stats = {}
        for n in self.graph.nodes():
            kind = self.graph.nodes[n].get('kind', 'unknown')
            node_kinds[kind] = node_kinds.get(kind, 0) + 1
            t = self.graph.nodes[n].get('timing', 'unknown')
            timing_stats[t] = timing_stats.get(t, 0) + 1

        edge_kinds = {}
        cond_stats = {'with_condition': 0, 'without_condition': 0}
        for u, v, d in self.graph.edges(data=True):
            ek = d.get('edge_kind', 'None')
            edge_kinds[ek] = edge_kinds.get(ek, 0) + 1
            if d.get('condition'):
                cond_stats['with_condition'] += 1
            else:
                cond_stats['without_condition'] += 1

        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'node_kinds': node_kinds,
            'edge_kinds': edge_kinds,
            'timing_stats': timing_stats,
            'condition_stats': cond_stats,
        }


if __name__ == '__main__':
    from navisv.parsers import ASTParser, NetlistParser

    ast = ASTParser('/tmp/navisv_slang/ast.json').parse()
    netlist = NetlistParser('/tmp/navisv_netlist/netlist.json').parse()

    builder = GraphBuilder(ast, netlist)
    graph = builder.build()

    print("=== GraphBuilder 测试 ===")
    print(f"Summary: {builder.summary()}")

    print(f"\n=== Signal conditions ===")
    print(f"Signals with conditions: {list(builder._signal_conditions.keys())}")
    for sig, conds in builder._signal_conditions.items():
        print(f"  {sig}: {conds}")

    print(f"\n=== Edges with conditions ===")
    for u, v, d in graph.edges(data=True):
        if d.get('condition'):
            print(f"  {u} -> {v}: condition='{d.get('condition')}'")

    print(f"\n=== All edges ===")
    for u, v, d in graph.edges(data=True):
        print(f"  {u} -> {v}: timing={d.get('timing')}, condition='{d.get('condition', '')}'")