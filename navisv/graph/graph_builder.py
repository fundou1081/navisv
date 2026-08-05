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


# (Stage 2.6) slang AST op 枚举 → 人类可读符号
# 来源: slang AST schema (Expression op field)
AST_OP_TO_SYMBOL: Dict[str, str] = {
    # Assignment
    'Assignment': '<=',

    # Conditional
    'Conditional': 'if',
    'ConditionalOp': '?:',

    # BinaryOp - 算术
    'Add': '+',
    'Subtract': '-',
    'Multiply': '*',
    'Divide': '/',
    'Mod': '%',
    'Power': '**',
    # BinaryOp - 位运算
    'BitwiseAnd': '&',
    'BitwiseOr': '|',
    'BitwiseXor': '^',
    'BitwiseNand': '~&',
    'BitwiseNor': '~|',
    'BitwiseXnor': '~^',
    'ShiftLeft': '<<',
    'ShiftRight': '>>',
    'ArithmeticShiftLeft': '<<<',
    'ArithmeticShiftRight': '>>>',
    # BinaryOp - 逻辑
    'LogicalAnd': '&&',
    'LogicalOr': '||',
    'LogicalImplication': '->',
    'LogicalEquivalence': '<->',
    # BinaryOp - 比较
    'Equality': '==',
    'Inequality': '!=',
    'CaseEquality': '===',
    'CaseInequality': '!==',
    'GreaterThan': '>',
    'GreaterThanEqual': '>=',
    'LessThan': '<',
    'LessThanEqual': '<=',
    'WildcardEquality': '==?',
    'WildcardInequality': '!=?',

    # UnaryOp
    'Plus': '+',
    'Minus': '-',
    'LogicalNot': '!',
    'BitwiseNot': '~',
    'PreIncrement': '++',
    'PreDecrement': '--',
    'PostIncrement': '++',
    'PostDecrement': '--',

    # Other
    'Replication': '{n{}}',
    'StreamingConcat': '{<<{}}',
}

# Netlist 中间节点 kind → AST Kind (供精确匹配使用)
NETLIST_INTERMEDIATE_TO_AST: Dict[str, str] = {
    'Conditional': 'Conditional',
    'Assignment': 'Assignment',
    # 'Merge' 无 AST 对应 (slang 内部 multi-way merge)
    # 'Case'   等同 Conditional (slang --netlist 不区分)
}


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
                 ast_json_path: str = None, source_files: list = None,
                 preserve_operators: bool = False):
        """构造 GraphBuilder

        Args:
            ast_parser: 已解析的 ASTParser
            netlist_parser: 已解析的 NetlistParser
            ast_json_path: slang --ast-json 输出路径 (可选, 用于提取源码片段)
            source_files: 源文件路径列表 (用于读取源码)
            preserve_operators: 是否保留中间节点 (Conditional/Assignment/Merge/Constant) 作为图节点。
                False (默认) - 保留现有行为, 中间节点 collapse 成 source→target 边
                True - 中间节点作为 Operator/Literal kind 保留, 数据流可见
        """
        self.ast = ast_parser
        self.netlist = netlist_parser
        self.ast_json_path = ast_json_path
        self.source_files = source_files or []
        self.preserve_operators = preserve_operators
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

        # 1.5 (Stage 2.5) 添加 Operator/Literal 中间节点 (仅 preserve_operators=True)
        self._add_intermediate_nodes()

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

    def _add_intermediate_nodes(self):
        """(Stage 2.5/2.6) 为中间节点 (Operator/Literal) 创建图节点

        仅在 preserve_operators=True 时生效。
        - Assignment / Conditional / Case / Merge -> kind='Operator'
        - Constant -> kind='Literal' (使用 netlist node.value)

        (Stage 2.6) 优先用 AST 表达式 (op / value) 生成具体符号
                    匹配不上时 fallback 到 netlist kind label

        生成的图节点 path 格式: 'op_<id>' 或 'const_<id>'
        """
        if not self.preserve_operators:
            return

        # (Stage 2.6) 建立 AST 表达式索引: (file, line, col) -> Expression info
        #   file 来自 ast_json_path
        #   line, col 来自 ASTNode attributes (source_line_start, source_column_start)
        ast_index = self._build_ast_expression_index()

        # Operator kind -> 默认 label (fallback)
        operator_label_fallback = {
            'Assignment': '<=',
            'Conditional': 'if',
            'Case': 'case',
            'Merge': 'merge',
        }

        for node in self.netlist.nodes:
            if node.kind in ('Assignment', 'Conditional', 'Case', 'Merge') and not node.path:
                op_path = f"op_{node.id}"
                if op_path in self._node_attrs:
                    continue

                # (Stage 2.6) 从 AST 拿具体 op 符号
                ast_match = self._match_netlist_to_ast(node, ast_index)
                if ast_match and ast_match.get('symbol'):
                    label = ast_match['symbol']
                    op_attrs = {
                        'operator_kind': node.kind,
                        'netlist_id': node.id,
                        'ast_kind': ast_match.get('ast_kind', ''),
                        'ast_op': ast_match.get('op', ''),
                    }
                else:
                    label = operator_label_fallback.get(node.kind, node.kind.lower())
                    op_attrs = {'operator_kind': node.kind, 'netlist_id': node.id}

                attr = NodeAttr(
                    name=label,
                    path=op_path,
                    kind='Operator',
                    bit_width=node.bounds,
                    timing='combinational',
                    module='',
                    location=node.location,
                    attributes=op_attrs,
                )
                self._add_node(op_path, attr)

            elif node.kind == 'Constant' and not node.path:
                const_path = f"const_{node.id}"
                if const_path in self._node_attrs:
                    continue
                # (Stage 2.6) 优先用 AST IntegerLiteral.value, fallback 到 netlist
                ast_match = self._match_netlist_to_ast(node, ast_index)
                if ast_match and ast_match.get('value'):
                    value_str = ast_match['value']
                else:
                    value_str = str(node.value) if node.value is not None else '?'
                attr = NodeAttr(
                    name=value_str,
                    path=const_path,
                    kind='Literal',
                    bit_width=node.bounds,
                    timing='combinational',
                    module='',
                    location=node.location,
                    attributes={
                        'value': value_str,
                        'netlist_id': node.id,
                        'ast_kind': ast_match.get('ast_kind', '') if ast_match else '',
                    },
                )
                self._add_node(const_path, attr)

    # ------------------------------------------------------------------
    # (Stage 2.6) AST 表达式提取 + 位置匹配
    # ------------------------------------------------------------------

    def _build_ast_expression_index(self) -> Dict[Tuple[str, int], List[Dict]]:
        """Walk AST 收集所有 expression 节点, 按 (file, line) 索引

        Returns:
            {(file_key, line): [{ast_kind, op, value, col, location}, ...]}
            - 同一行可能有多个表达式, 按 col 排序
            - file_key 用 netlist fileTable 中的 basename, 以跟 netlist.location 对齐
        """
        index: Dict[Tuple[str, int], List[Dict]] = {}

        if not self.ast or not self.ast.root:
            return index

        # 定位源文件: 第一个非 $root 的 source_file
        ast_source_file = ''
        try:
            defn = self.ast.data.get('definitions', [{}])[0] if hasattr(self.ast, 'data') else {}
            ast_source_file = defn.get('source_file', '')
        except Exception:
            pass
        if not ast_source_file:
            ast_source_file = os.path.basename(self.source_files[0]) if self.source_files else ''

        def walk(node):
            # ASTParser 节点的 attributes dict 是从原始 JSON 拷过来的,
            # source_line_start / source_column_start 在那里
            attrs = node.attributes or {}
            kind = node.kind
            line_start = attrs.get('source_line_start', 0)
            col_start = attrs.get('source_column_start', 0)

            if line_start > 0 and kind in (
                'Assignment', 'Conditional', 'BinaryOp', 'UnaryOp',
                'ConditionalOp', 'IntegerLiteral', 'Conversion',
            ):
                key = (ast_source_file, line_start)
                if key not in index:
                    index[key] = []
                index[key].append({
                    'ast_kind': kind,
                    'op': attrs.get('op', ''),
                    'value': attrs.get('value', ''),
                    'constant': attrs.get('constant', ''),
                    'col': col_start,
                    'isNonBlocking': attrs.get('isNonBlocking', False),
                    'node': node,
                })

            for child in node.children:
                walk(child)

        walk(self.ast.root)

        # 按 col 排序, 方便 binary search
        for key in index:
            index[key].sort(key=lambda x: x['col'])

        return index

    def _match_netlist_to_ast(self, netlist_node, ast_index: Dict[Tuple[str, int], List[Dict]]) -> Optional[Dict]:
        """按 (file, line) + 临近 col 在 ast_index 找最佳匹配

        策略:
        1. file_key 使用 ast_source_file 的 basename (跟 netlist fileTable index 一致)
        2. line 完全匹配
        3. 同一行多表达式时, 取 col 最接近 netlist.column 的
        4. kind 匹配优先 (Assignment ↔ Assignment, Constant ↔ Conversion/IntegerLiteral)
        """
        loc = netlist_node.location or {}
        line = loc.get('line', 0)
        col = loc.get('column', 0)
        file_index = loc.get('fileIndex', 0)

        # 拿到 ast_index 所有 keys, 用 file basename 匹配
        # netlist 用 fileTable, ast 直接用 source_file 路径
        # 我们用 ast_index 的第一个 key 的 file 部分
        ast_file_key = None
        for (f, l) in ast_index.keys():
            ast_file_key = f
            break

        # 计算 netlist 的 file basename
        netlist_file = ''
        if self.netlist.file_table:
            netlist_file = self.netlist.file_table[file_index]
        netlist_file_base = os.path.basename(netlist_file) if netlist_file else ''
        ast_file_base = os.path.basename(ast_file_key) if ast_file_key else ''

        # line 必须匹配
        if not line:
            return None

        # 尝试两种 file_key
        candidates = None
        for key in [(ast_file_base, line), (ast_file_key, line)]:
            if key in ast_index:
                candidates = ast_index[key]
                break

        if not candidates:
            return None

        # kind 过滤: netlist Assignment -> AST Assignment, Constant -> Conversion/IntegerLiteral
        if netlist_node.kind == 'Assignment':
            filtered = [c for c in candidates if c['ast_kind'] == 'Assignment']
        elif netlist_node.kind == 'Conditional':
            filtered = [c for c in candidates if c['ast_kind'] == 'Conditional']
        elif netlist_node.kind == 'Case':
            filtered = [c for c in candidates if c['ast_kind'] == 'Conditional']  # slang 把 case 映射成 Conditional
        elif netlist_node.kind == 'Constant':
            filtered = [c for c in candidates if c['ast_kind'] in ('Conversion', 'IntegerLiteral')]
        else:
            filtered = candidates

        if not filtered:
            filtered = candidates  # fallback 用所有

        # col 最近
        best = min(filtered, key=lambda c: abs(c['col'] - col))
        return self._ast_match_to_info(netlist_node.kind, best)

    def _ast_match_to_info(self, netlist_kind: str, ast_entry: Dict) -> Dict:
        """把 AST 表达式 entry 转成 Operator/Literal 需要的 info dict

        Returns:
            {symbol, value, ast_kind, op}

        (Stage 2.6) Assignment 节点如果 RHS 是单一 BinaryOp/UnaryOp/ConditionalOp,
                     用具体 op symbol 覆盖 <= / = label
        """
        ast_kind = ast_entry['ast_kind']
        op = ast_entry['op']
        value = ast_entry['value']
        constant = ast_entry['constant']
        is_nb = ast_entry.get('isNonBlocking', False)
        ast_node = ast_entry.get('node')

        if netlist_kind == 'Constant':
            # 优先用 Conversion.constant, fallback IntegerLiteral.value
            lit = constant or value or '?'
            return {'symbol': lit, 'value': lit, 'ast_kind': ast_kind, 'op': op}

        # Operator
        if ast_kind == 'Assignment':
            # (Stage 2.6) 探查 RHS 是否有具体 operator
            rhs_op = self._find_first_operator(ast_node, skip_named_value=True)
            if rhs_op and rhs_op in AST_OP_TO_SYMBOL:
                sym = AST_OP_TO_SYMBOL[rhs_op]
                return {'symbol': sym, 'ast_kind': ast_kind, 'op': rhs_op}
            # fallback to assignment symbol
            sym = '<=' if is_nb else '='
            return {'symbol': sym, 'ast_kind': ast_kind, 'op': op or sym}

        if ast_kind == 'Conditional':
            # (Stage 2.6) 探查 condition 是否有具体 operator
            cond_op = self._find_first_operator(ast_node, skip_named_value=True,
                                                 skip_conditional=True)
            if cond_op and cond_op in AST_OP_TO_SYMBOL:
                sym = AST_OP_TO_SYMBOL[cond_op]
                return {'symbol': sym, 'ast_kind': ast_kind, 'op': cond_op}
            return {'symbol': 'if', 'ast_kind': ast_kind, 'op': op or 'if'}

        if ast_kind == 'ConditionalOp':
            return {'symbol': '?:', 'ast_kind': ast_kind, 'op': op or '?:'}

        # BinaryOp / UnaryOp -> AST_OP_TO_SYMBOL
        sym = AST_OP_TO_SYMBOL.get(op, op or ast_kind.lower())
        return {'symbol': sym, 'ast_kind': ast_kind, 'op': op}

    def _find_first_operator(self, ast_node, skip_named_value: bool = True,
                              skip_conditional: bool = False) -> Optional[str]:
        """从 AST 节点往下走, 找第一个真正的 operator (BinaryOp/UnaryOp/ConditionalOp)

        (Stage 2.6 bugfix) 严格限制 walk 范围:
          - Conditional 只看 conditions[*].expr (不看 ifTrue/ifFalse 避免跳到嵌套语句)
          - Assignment 只看 right (不看 left 是 NamedValue)
          - Conversion 看 operand

        Args:
            ast_node: 起点 AST 节点 (Conditional/Assignment 等)
            skip_named_value: 跳过 NamedValue (不加)
            skip_conditional: 跳过 Conditional (避免多层 if 套娃)
        """
        target_kinds = ('BinaryOp', 'UnaryOp', 'ConditionalOp')

        attrs = ast_node.attributes or {}
        kind = ast_node.kind

        if kind == 'Conditional':
            # 只 walk conditions[*].expr
            conds = attrs.get('conditions', [])
            for cond in conds:
                if not isinstance(cond, dict): continue
                expr = cond.get('expr')
                if isinstance(expr, dict):
                    r = self._walk_for_op(expr, target_kinds, skip_named_value, depth=0)
                    if r: return r
            return None

        if kind == 'Assignment':
            # 只 walk right
            right = attrs.get('right')
            if isinstance(right, dict):
                return self._walk_for_op(right, target_kinds, skip_named_value, depth=0)
            return None

        # fallback: walk children
        for child in ast_node.children:
            r = self._walk_for_op(child, target_kinds, skip_named_value, depth=0)
            if r: return r
        return None

    def _walk_for_op(self, node, target_kinds, skip_named_value: bool, depth: int) -> Optional[str]:
        """递归 walk dict AST 节点找 operator (不走 ASTNode.children, 直接用 attributes)"""
        if depth > 10: return None
        if not isinstance(node, dict): return None
        kind = node.get('kind', '')
        if kind in target_kinds:
            return node.get('op', '')
        if skip_named_value and kind == 'NamedValue':
            return None
        # Conversion 看 operand
        if kind == 'Conversion':
            op = node.get('operand')
            if isinstance(op, dict):
                return self._walk_for_op(op, target_kinds, skip_named_value, depth+1)
            return None
        # 递归子表达式: left/right/operand/expr/conditions[*].expr
        for key in ('left', 'right', 'operand', 'expr'):
            v = node.get(key)
            if isinstance(v, dict):
                r = self._walk_for_op(v, target_kinds, skip_named_value, depth+1)
                if r: return r
        conds = node.get('conditions', [])
        if isinstance(conds, list):
            for c in conds:
                if isinstance(c, dict):
                    e = c.get('expr')
                    if isinstance(e, dict):
                        r = self._walk_for_op(e, target_kinds, skip_named_value, depth+1)
                        if r: return r
        return None

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

            # (Stage 2.5) preserve_operators=True: 中间节点用 op_<id> / const_<id> 作为图节点路径
            if self.preserve_operators:
                if not src_path:
                    if src_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge'):
                        src_path = f"op_{src_node.id}"
                    elif src_node.kind == 'Constant':
                        src_path = f"const_{src_node.id}"
                if not tgt_path:
                    if tgt_node.kind in ('Assignment', 'Conditional', 'Case', 'Merge'):
                        tgt_path = f"op_{tgt_node.id}"
                    elif tgt_node.kind == 'Constant':
                        tgt_path = f"const_{tgt_node.id}"

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