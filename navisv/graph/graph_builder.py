import os
"""
GraphBuilder - 构建 enriched MultiDiGraph

Layer 2: 组合 Parser 结果 + 分析逻辑
- 添加 Named Nodes (Port + State)
- 添加边（带完整属性）
- 从 AST 提取条件信息
- 推断时序分类
- 计算 bit_mapping
"""

import networkx as nx
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

from navisv.parsers import ASTParser, NetlistParser, NetlistNode, NetlistEdge


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
    
    组合 ASTParser + NetlistParser 的结果，
    推断时序分类，提取条件信息。
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
        self._signal_conditions: Dict[str, List[Dict]] = {}  # signal -> [{condition, kind, location}]

        
        self._build_symbol_map()
    
    def _read_source_line(self, file: str, line: int, col_start: int, col_end: int) -> str:
        """从源文件读取指定范围的文本"""
        if not file or line <= 0:
            return ''
        
        # 优先从 source_files 中查找（传入的是绝对路径）
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
        """从文件提取指定行和列范围的文本（AST column 是 1-indexed）"""
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
                # 也用简化的 name 作为 key（如果有重复会用第一个）
                name = node.name
                if name and name not in self._name_to_path:
                    self._name_to_path[name] = node.path
    
    
    
    def build(self) -> nx.MultiDiGraph:
        """构建完整的 MultiDiGraph"""
        self.graph = nx.MultiDiGraph()
        
        # 1. 添加 Named Nodes (Port + State) - 必须先添加，因为条件分析依赖 node paths
        self._add_named_nodes()
        
        # 2. 分析 AST 获取条件信息
        self._analyze_ast_conditions()
        
        # 3. 从 Netlist 添加边
        self._add_edges()
        
        # 4. 丰富边的条件属性
        self._enrich_edges_with_conditions()
        
        # 5. 推断时序分类
        self._classify_timing()
        
        # 6. 计算 bit_mapping
        self._calculate_bit_mapping()
        
        return self.graph
    
    def _add_named_nodes(self):
        """添加 Named Nodes (Port + State)"""
        # 先添加 State 节点（更高优先级）
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
        
        # 再添加 Port 节点（如果不存在同名节点）
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
    
    def _add_node(self, path: str, attr: NodeAttr):
        """添加节点到图中"""
        if path in self.graph:
            return
        
        self.graph.add_node(path, **attr.to_dict())
        self._node_attrs[path] = attr
    
    def _add_edges(self):
        """从 Netlist 添加边"""
        for edge in self.netlist.edges:
            src_node = self.netlist.get_node_by_id(edge.source)
            tgt_node = self.netlist.get_node_by_id(edge.target)
            
            if not src_node or not tgt_node:
                continue
            
            # 只添加 named → named 边
            if not src_node.path or not tgt_node.path:
                continue
            
            # 跳过 self-loop
            if src_node.path == tgt_node.path:
                continue
            
            attr = EdgeAttr(
                edge_kind=edge.edge_kind,
                bounds=edge.bounds,
                location=edge.symbol.get('location') if edge.symbol else None,
            )
            
            key = self.graph.add_edge(
                src_node.path, 
                tgt_node.path,
                **attr.to_dict()
            )
            
            self._edge_attrs[(src_node.path, tgt_node.path, key)] = attr
    
    def _extract_module(self, path: str) -> str:
        """从路径提取模块名"""
        parts = path.rsplit('.', 1)
        return parts[0] if len(parts) > 1 else 'top'
    
    def _analyze_ast_conditions(self):
        """
        分析 AST，提取所有信号的条件赋值信息
        
        建立映射: signal_path -> [{condition, kind, location}]
        """
        self._signal_conditions = {}
        
        if not self.ast or not self.ast.root:
            return
        
        # 遍历所有模块
        for module in self.ast.get_modules():
            self._analyze_module_conditions(module)
    
    def _analyze_module_conditions(self, module_node):
        """分析模块内的条件语句"""
        for node in self._traverse_ast(module_node):
            if node.kind == 'Case':
                self._analyze_case(node)
            elif node.kind == 'Conditional':
                self._analyze_conditional(node)
    
    def _analyze_case(self, case_node):
        """
        分析 case 语句，建立 目标信号 -> 条件 的映射
        
        Case 结构:
        {
            "kind": "Case",
            "expr": {symbol: "id name"},  # 选择变量
            "items": [
                {
                    "expressions": [{constant: "3'b0"}],  # case 值
                    "stmt": {kind: "ExpressionStatement", expr: {Assignment}}
                },
                ...
            ]
        }
        """
        # 提取 case 选择变量
        case_var = self._extract_expr_path(case_node.attributes.get('expr', {}))
        
        if not case_var:
            return
        
        # 遍历每个 case item
        for item in case_node.attributes.get('items', []):
            # 提取 case 值
            case_value = self._extract_case_value(item)
            
            # 构建完整条件
            condition = f"{case_var} == {case_value}" if case_value else case_var
            
            # 分析 item 内的赋值
            stmt = item.get('stmt', {})
            self._extract_assignments_from_stmt(condition, 'case', stmt)
        
        # 处理 default case
        default_stmt = case_node.attributes.get('defaultCase', {})
        if default_stmt:
            self._extract_assignments_from_stmt(case_var, 'case', default_stmt)
    
    def _analyze_conditional(self, cond_node_or_dict):
        """
        分析 if/else 语句
        
        cond_node_or_dict 可以是 ASTNode 或 dict (递归调用时传入 dict)
        
        if/else 结构:
        {
            "kind": "Conditional",
            "conditions": [{"expr": {...}}],
            "check": "None",
            "ifTrue": {...},
            "ifFalse": {...}
        }
        
        三元运算符结构:
        {
            "kind": "Conditional",
            "condition": {...},
            "trueExpression": {...},
            "falseExpression": {...}
        }
        """
        # 统一获取 attributes
        if hasattr(cond_node_or_dict, 'attributes'):
            attrs = cond_node_or_dict.attributes
        else:
            attrs = cond_node_or_dict
        
        # 处理 if/else 结构 (conditions, ifTrue, ifFalse)
        conditions = attrs.get('conditions', [])
        if conditions:
            # 这是 if/else 结构
            for i, cond_item in enumerate(conditions):
                cond_expr = cond_item.get('expr', {})
                condition = self._extract_expr_path(cond_expr)
                
                if not condition:
                    continue
                
                if_true = attrs.get('ifTrue')
                if if_true:
                    self._extract_assignments_from_stmt(f"{condition}", 'if', if_true)
            
            if_false = attrs.get('ifFalse')
            if if_false and isinstance(if_false, dict):
                if if_false.get('kind') == 'Conditional':
                    self._analyze_conditional(if_false)
                else:
                    if conditions:
                        last_cond_expr = conditions[-1].get('expr', {})
                        last_cond = self._extract_expr_path(last_cond_expr)
                        if last_cond:
                            self._extract_assignments_from_stmt(f"!{last_cond}", 'if', if_false)
                        else:
                            self._extract_assignments_from_stmt('', 'else', if_false)
        
        # 处理三元运算符结构 (condition, trueExpression, falseExpression)
        condition = self._extract_expr_path(attrs.get('condition', {}))
        if condition:
            true_expr = attrs.get('trueExpression', {})
            self._extract_assignments_from_expr(f"{condition}", 'ternary', true_expr)
            
            false_expr = attrs.get('falseExpression', {})
            self._extract_assignments_from_expr(f"!{condition}", 'ternary', false_expr)
    
    def _extract_case_value(self, item: Dict) -> str:
        """从 case item 提取 case 值"""
        expressions = item.get('expressions', [])
        for expr in expressions:
            if isinstance(expr, dict):
                # 直接返回 constant 值
                constant = expr.get('constant', '')
                if constant:
                    return constant
        return ''
    
    def _extract_expr_path(self, expr: Dict) -> str:
        """
        从表达式中提取路径
        
        支持 NamedValue: symbol="id name"
        匹配到 _node_attrs 中的路径
        """
        if not isinstance(expr, dict):
            return ''
        
        kind = expr.get('kind', '')
        
        if kind == 'NamedValue':
            sym = expr.get('symbol', '')
            if ' ' in sym:
                sym_id, name = sym.split(' ', 1)
                
                # 先从 _symbol_to_path 获取 AST path
                if sym_id in self._symbol_to_path:
                    stored_name, ast_path = self._symbol_to_path[sym_id]
                    
                    # 直接匹配 _node_attrs 中的路径
                    for node_path in self._node_attrs:
                        if node_path.endswith(f'.{stored_name}'):
                            return node_path
                    
                    # 如果找不到精确匹配，返回 name
                    return stored_name
                return name
            return sym
        
        # 递归处理
        for key in ('left', 'right', 'operand', 'operand1', 'operand2', 'expr'):
            if key in expr:
                result = self._extract_expr_path(expr[key])
                if result:
                    return result
        
        return ''
    
    def _extract_assignments_from_stmt(self, condition: str, cond_kind: str, stmt: Dict):
        """从语句中提取赋值目标"""
        if not isinstance(stmt, dict):
            return
        
        if stmt.get('kind') == 'ExpressionStatement':
            expr = stmt.get('expr', {})
            self._extract_assignments_from_expr(condition, cond_kind, expr)
        elif stmt.get('kind') == 'Block':
            for item in stmt.get('items', []):
                self._extract_assignments_from_stmt(condition, cond_kind, item)
    
    def _extract_assignments_from_expr(self, condition: str, cond_kind: str, expr: Dict):
        """从表达式中提取赋值并建立条件映射"""
        if not isinstance(expr, dict):
            return
        
        kind = expr.get('kind', '')
        
        if kind == 'Assignment':
            left = expr.get('left', {})
            target_path = self._extract_expr_path(left)
            
            # 提取位置信息
            location = {
                'file': expr.get('source_file_start', ''),
                'line': expr.get('source_line_start', 0),
                'column': expr.get('source_column_start', 0),
            }
            
            # 提取赋值语句文本 (e.g., "count <= 0")
            assignment_stmt = self._read_source_line(
                location['file'], location['line'],
                expr.get('source_column_start', 0), expr.get('source_column_end', 0)
            )
            
            # 构建完整的 if 表达式 (e.g., "if (rst_n) count <= 0;")
            if condition and assignment_stmt:
                if cond_kind == 'if':
                    if_expression = f"if ({condition}) {assignment_stmt};"
                elif cond_kind == 'case':
                    if_expression = f"case ({condition}) ... {assignment_stmt}"
                else:
                    if_expression = f"{condition} ? {assignment_stmt}"
            else:
                if_expression = assignment_stmt
            
            if target_path and target_path in self._node_attrs:
                if target_path not in self._signal_conditions:
                    self._signal_conditions[target_path] = []
                self._signal_conditions[target_path].append({
                    'condition': condition,
                    'kind': cond_kind,
                    'source': 'ast',
                    'location': location,
                    'statement': assignment_stmt,
                    'if_expression': if_expression  # 完整 if 表达式
                })
        
        elif kind == 'Block':
            for item in expr.get('items', []):
                self._extract_assignments_from_expr(condition, cond_kind, item)
    
    def _traverse_ast(self, node) -> List:
        """遍历 AST 节点"""
        results = [node]
        for child in node.children:
            results.extend(self._traverse_ast(child))
        return results
    
    def _enrich_edges_with_conditions(self):
        """
        丰富边的条件属性
        
        对于每个目标信号，检查是否有 AST 分析的条件信息，
        并更新对应的边。
        """
        for target_path, conditions in self._signal_conditions.items():
            if not conditions:
                continue
            
            # 查找所有以 target_path 为目标的边
            for (src, dst, key), attr in self._edge_attrs.items():
                if dst == target_path and not attr.condition:
                    # 使用第一个条件（可以扩展为多条件）
                    cond_info = conditions[0]
                    attr.condition = cond_info['condition']
                    attr.condition_kind = cond_info['kind']
                    attr.condition_signals = [c['condition'] for c in conditions]
                    
                    # 更新图中边的属性
                    if self.graph.has_edge(src, dst, key):
                        self.graph[src][dst][key]['condition'] = attr.condition
                        self.graph[src][dst][key]['condition_kind'] = attr.condition_kind
                        self.graph[src][dst][key]['condition_signals'] = attr.condition_signals
    
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
            elif src_attr.kind == 'State' and dst_attr.kind != 'State':
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