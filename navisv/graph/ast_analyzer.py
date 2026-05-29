"""
ASTAnalyzer - 从 AST 提取条件信息

Layer 1: AST 语义分析
- 分析 always_comb / always_ff 块
- 提取条件信号关系
- 提取三元运算符条件
"""

import os
import json
from typing import Dict, List, Any, Optional, Tuple, Set


class NodeAttr:
    """简单节点属性对象 (替代动态 type(), 支持 pickle)"""
    __slots__ = ('kind', 'name', 'direction', 'bit_width', 'timing', 'risk_level',
                    'func_complexity', 'timing_complexity', 'verify_status',
                    'func_factors', 'timing_factors')

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return f"NodeAttr({self.__dict__})"


class ASTAnalyzer:
    """
    从 AST 提取条件信息

    输出: self._signal_conditions: Dict[str, List[Dict]]
    key = target_path
    value = [{'condition': 'signal_name', 'kind': 'always_comb', ...}]
    """

    def __init__(self, ast_parser, node_paths: dict, node_attrs: dict = None, graph=None, source_files: list = None):
        self.ast = ast_parser
        self.node_paths = node_paths
        self._node_attrs = node_attrs or {}
        self.graph = graph
        self._source_files = {f: f for f in (source_files or [])}
        self._signal_conditions: Dict[str, List[Dict[str, Any]]] = {}
        self._timing_ctx: Dict[str, Any] = {}

    def analyze(self):
        """执行 AST 条件分析"""
        if not self.ast or not self.ast.root:
            return
        self._analyze_ast_conditions()

    def _read_source_line(self, file: str, line: int, col_start: int, col_end: int) -> str:
        """从源文件读取指定行的源码"""
        if file not in self._source_files:
            return ''
        try:
            with open(self._source_files[file]) as f:
                lines = f.readlines()
            if 0 < line <= len(lines):
                return lines[line - 1].rstrip('\n')
        except (IOError, IndexError):
            pass
        return ''

    def _analyze_ast_conditions(self):
        """
        分析 AST,提取所有信号的条件赋值信息

        建立映射: signal_path -> [{condition, kind, location}]
        """
        self._signal_conditions = {}

        if not self.ast or not self.ast.root:
            return

        # 遍历所有模块
        for module in self.ast.get_modules():
            self._analyze_module_conditions(module)

    def _analyze_module_conditions(self, module_node):
        """分析模块内的条件语句 (语义化递归遍历,携带 timing context)"""
        # 存储当前模块路径,用于 ContinuousAssign 等需要模块前缀的场景
        self._current_module_path = module_node.path
        self._traverse_with_timing(module_node, timing_ctx=None)
        self._current_module_path = None

    def _traverse_with_timing(self, node, timing_ctx):
        """递归遍历 AST,timing context 随遍历传递

        Args:
            node: AST node
            timing_ctx: timing context from enclosing ProceduralBlock, or None
        """
        kind = node.kind

        if kind == 'ProceduralBlock':
            # 提取这个 ProceduralBlock 的 timing 作为新的 context
            new_timing = self._extract_timing_from_block(node)
            for child in node.children:
                self._traverse_with_timing(child, timing_ctx=new_timing)
            return  # children 已处理,不需要继续

        elif kind == 'Case':
            # Case 语句内部是纯组合逻辑,但仍传递 timing context
            # 以便嵌套的赋值语句知道它们是否在 ProceduralBlock 内
            self._analyze_case(node, timing_ctx)
            # 继续遍历处理 case items
            for child in node.children:
                self._traverse_with_timing(child, timing_ctx)
            return

        elif kind == 'Conditional':
            # Conditional 可能被 Case 或 ProceduralBlock 包含
            # 如果在 ProceduralBlock 内,有 timing context
            self._analyze_conditional(node, timing_ctx)
            # 继续遍历 children,传递 timing context
            for child in node.children:
                self._traverse_with_timing(child, timing_ctx)
            return

        elif kind == 'ContinuousAssign':
            # ContinuousAssign 是纯组合逻辑
            self._analyze_continuous_assign_ternary(node)
            return

        elif kind == 'Net' and node.attributes.get('initializer'):
            self._analyze_net_initializer_ternary(node)
            return

        elif kind == 'Assignment':
            # 直接在 always 块中的赋值 (无 if 包装,如 no_reset_reg <= data_in)
            # node.attributes 缺少 kind 字段,需要从 node.kind 获取
            if timing_ctx and timing_ctx.get('clock'):
                # 创建带 kind 的 expr dict
                expr_dict = dict(node.attributes)
                expr_dict['kind'] = 'Assignment'
                self._extract_assignments_from_expr('', 'plain', expr_dict, timing_ctx)
            return

        else:
            # 其他节点,继续递归
            for child in node.children:
                self._traverse_with_timing(child, timing_ctx)

    def _analyze_case(self, case_node, timing_ctx=None):
        """
        分析 case 语句,建立 目标信号 -> 条件 的映射

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
            self._extract_assignments_from_stmt(condition, 'case', stmt, timing_ctx)

        # 处理 default case
        default_stmt = case_node.attributes.get('defaultCase', {})
        if default_stmt:
            self._extract_assignments_from_stmt(case_var, 'case', default_stmt, timing_ctx)

    def _analyze_conditional_op(self, cond_node_or_dict, timing_ctx=None):
        """分析三元运算符 ConditionalOp"""
        self._analyze_conditional(cond_node_or_dict)

    def _analyze_net_initializer_ternary(self, net_node):
        """处理 Net 的 initializer (如 wire [7:0] complex_result = enable ? a : b)"""
        initializer = net_node.attributes.get('initializer')
        if not isinstance(initializer, dict):
            return

        if initializer.get('kind') != 'ConditionalOp':
            return

        # 尝试多种可能的前缀来构建路径
        possible_paths = [
            net_node.name,  # complex_result
            f"complex_test.{net_node.name}",  # complex_test.complex_result
            f"$root.complex_test.complex_test.{net_node.name}",  # 完整路径
        ]

        target_path = None
        for path in possible_paths:
            if self.graph.has_node(path):
                target_path = path
                break

        if not target_path:
            # 节点不在 graph 中,但仍需处理条件信息
            # 从 net_node.path 推断路径
            # $root.complex_test.complex_test.complex_result -> complex_test.complex_result
            full_path = net_node.path
            if '$root.' in full_path:
                # 去掉 $root. 前缀,保留后面的部分
                clean_path = full_path.replace('$root.', '')
                # 取最后两部分作为路径
                parts = clean_path.split('.')
                if len(parts) >= 2:
                    target_path = f"{parts[-2]}.{net_node.name}"
                    # 如果这个路径也不在 graph 中,只使用名称
                    if not self.graph.has_node(target_path):
                        target_path = net_node.name
                else:
                    target_path = net_node.name
            else:
                target_path = net_node.name

        # 提取条件
        self._extract_ternary_conditions(target_path, initializer)


    def _find_sync_reset_in_block(self, timed_node):
        """检查 Timed 节点内是否有 sync reset (if (!rst_n) 在 always 块内)

        Returns:
            [{'signal': path, 'edge': 'NegEdge', 'kind': 'sync'}] or None
        """
        if not timed_node:
            return None

        for child in timed_node.children:
            if child.kind == 'Block':
                sync_reset = self._find_sync_reset_in_conditional(child)
                if sync_reset:
                    return sync_reset

        return None

    def _find_sync_reset_in_conditional(self, node):
        """递归查找 sync reset 条件: if (!reset_signal)"""
        if not node:
            return None

        # 处理 dict 类型的节点
        if isinstance(node, dict):
            if node.get('kind') == 'Conditional':
                conditions = node.get('conditions', [])

                if conditions and isinstance(conditions, list):
                    for cond_item in conditions:
                        if isinstance(cond_item, dict):
                            cond_expr = cond_item.get('expr', {})

                            if cond_expr.get('kind') == 'UnaryOp':
                                operand = cond_expr.get('operand', {})
                                operand_path = self._extract_expr_path(operand)

                                if operand_path and 'rst' in operand_path.lower():
                                    return [{
                                        'signal': operand_path,
                                        'edge': 'NegEdge',
                                        'kind': 'sync'
                                    }]

                if_false = node.get('ifFalse', {})
                if isinstance(if_false, dict):
                    result = self._find_sync_reset_in_conditional(if_false)
                    if result:
                        return result

            # 遍历 children
            for child in node.get('children', []):
                if isinstance(child, dict):
                    result = self._find_sync_reset_in_conditional(child)
                    if result:
                        return result

            return None

        # 处理 ASTNode 对象
        if node.kind == 'Conditional':
            attrs = node.attributes
            conditions = attrs.get('conditions', [])

            if conditions and isinstance(conditions, list):
                for cond_item in conditions:
                    if isinstance(cond_item, dict):
                        cond_expr = cond_item.get('expr', {})

                        if cond_expr.get('kind') == 'UnaryOp':
                            operand = cond_expr.get('operand', {})
                            operand_path = self._extract_expr_path(operand)

                            if operand_path and 'rst' in operand_path.lower():
                                return [{
                                    'signal': operand_path,
                                    'edge': 'NegEdge',
                                    'kind': 'sync'
                                }]

            if_false = attrs.get('ifFalse', {})
            if isinstance(if_false, dict):
                result = self._find_sync_reset_in_conditional(if_false)
                if result:
                    return result

        for child in node.children:
            result = self._find_sync_reset_in_conditional(child)
            if result:
                return result

        return None

    def _extract_timing_from_block(self, procedural_block):
        """从 ProceduralBlock 提取时钟和复位信息,返回 dict

        Returns:
            dict: {'clock': [{'signal': path, 'edge': 'PosEdge'}],
                   'reset': [{'signal': path, 'edge': 'NegEdge'}],
                   'is_register': True}
            如果没有 timing 信息,返回 None
        """
        # 从 children 中找到 Timed 节点
        timed_node = None
        for child in procedural_block.children:
            if child.kind == 'Timed':
                timed_node = child
                break

        # Fallback: 检查 body.timing (有些 AST 格式将 timing 放在 body 下而非单独的 Timed 节点)
        timing_attr = None
        if not timed_node:
            body = procedural_block.attributes.get('body', {})
            if isinstance(body, dict):
                timing_attr = body.get('timing')
        else:
            timing_attr = timed_node.attributes.get('timing', {})

        if not timing_attr:
            return None

        clock_events = []
        reset_events = []

        if isinstance(timing_attr, dict):
            if timing_attr.get('kind') == 'EventList':
                # Normal EventList with events array
                events = timing_attr.get('events', [])
            elif timing_attr.get('kind') == 'SignalEvent':
                # Single SignalEvent directly
                events = [timing_attr]
            else:
                events = []
        elif isinstance(timing_attr, list):
            events = timing_attr
        else:
            events = []

        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get('kind') == 'SignalEvent':
                edge = event.get('edge', 'PosEdge')
                expr = event.get('expr', {})
                signal_path = self._extract_expr_path(expr)

                if edge == 'NegEdge':
                    reset_events.append({
                        'signal': signal_path,
                        'edge': edge
                    })
                else:  # PosEdge
                    clock_events.append({
                        'signal': signal_path,
                        'edge': edge
                    })

        # 检查是否有 sync reset (if (!rst_n) 在 always 块内)
        sync_reset = self._find_sync_reset_in_block(timed_node)

        if clock_events or reset_events or sync_reset:
            return {
                'clock': clock_events if clock_events else None,
                'reset': reset_events if reset_events else sync_reset,
                'is_register': True,
                'procedureKind': procedural_block.attributes.get('procedureKind', 'Always')
            }

        return None

    def _extract_timing_info(self, procedural_block):
        """从 ProceduralBlock 提取时钟和复位信息 (旧接口,保留用于兼容)"""
        # 调用新方法,但不存储到 dict
        self._extract_timing_from_block(procedural_block)

    def _extract_ternary_conditions(self, target_path: str, cond_op: Dict):
        """从 ConditionalOp 提取条件并建立到目标信号的映射"""
        conditions = cond_op.get('conditions', [])
        if not conditions:
            return

        for cond_item in conditions:
            if not isinstance(cond_item, dict):
                continue

            expr = cond_item.get('expr', {})

            # 对于 BinaryOp/UnaryOp 等复杂表达式,使用源码文本
            if isinstance(expr, dict) and expr.get('kind') in ('BinaryOp', 'UnaryOp'):
                # 从源码提取完整条件表达式
                location = {
                    'file': expr.get('source_file_start', ''),
                    'line': expr.get('source_line_start', 0),
                    'column': expr.get('source_column_start', 0),
                }
                condition = self._read_source_line(
                    location['file'], location['line'],
                    expr.get('source_column_start', 0), expr.get('source_column_end', 0)
                )
            else:
                condition = self._extract_expr_path(expr)

            if not condition:
                continue

            # 提取位置信息
            location = {
                'file': cond_op.get('source_file_start', ''),
                'line': cond_op.get('source_line_start', 0),
                'column': cond_op.get('source_column_start', 0),
            }

            # 提取 true_val (left 分支)
            left = cond_op.get('left', {})
            true_val = self._read_source_line(
                location['file'], location['line'],
                left.get('source_column_start', 0), left.get('source_column_end', 0)
            ) if isinstance(left, dict) else ''

            # 构造语句: "condition ? true_val : ..."
            statement = f"{condition} ? {true_val} : ..."

            # 构建完整表达式
            # 对于嵌套 ternary,statement 已经是 "condition ? true_val : ..."
            # 直接使用
            if statement.startswith(condition):
                if_expression = statement
            else:
                if_expression = f"{condition} ? {statement}"

            # 确保目标路径有效 (即使不在 netlist 图中也要添加条件)
            if not target_path:
                return

            # 如果目标不在 graph 中,添加到图中
            if not self.graph.has_node(target_path):
                # 尝试添加带模块前缀的路径
                prefixed_path = f"complex_test.{target_path}"
                if self.graph.has_node(prefixed_path):
                    target_path = prefixed_path
                else:
                    self.graph.add_node(target_path, kind='Net', type='logic[7:0]')

            if target_path not in self._signal_conditions:
                self._signal_conditions[target_path] = []
            self._signal_conditions[target_path].append({
                'condition': condition,
                'kind': 'ternary',
                'source': 'ast',
                'location': location,
                'statement': statement,
                'if_expression': if_expression,
                'target_kind': 'combinational',  # ContinuousAssign is always combinational
                'clock_domain': None,
                'edge_type': None,
                'reset_signal': None,
                'reset_kind': None,
            })

            # 处理嵌套 ternary (right 分支可能是另一个 ConditionalOp)
            right = cond_op.get('right', {})
            if isinstance(right, dict) and right.get('kind') == 'ConditionalOp':
                self._extract_ternary_conditions(target_path, right)

    def _analyze_continuous_assign_ternary(self, continuous_assign_node):
        """处理 ContinuousAssign (如 assign x = y ? a : b)

        ContinuousAssign 结构:
        {
            "kind": "ContinuousAssign",
            "assignment": {
                "kind": "Assignment",
                "left": {symbol: "id name"},  # 目标信号
                "right": {kind: "ConditionalOp", conditions: [...], left: {...}, right: {...}}
            }
        }
        """
        assignment = continuous_assign_node.attributes.get('assignment', {})
        if not isinstance(assignment, dict):
            return

        # 提取目标信号路径
        left = assignment.get('left', {})
        target_path = self._extract_expr_path(left)

        if not target_path:
            return

        # 添加模块前缀(如果需要) - 构造完整路径而不是只取最后一部分
        full_target_path = target_path
        if self._current_module_path and not target_path.startswith(self._current_module_path):
            parts = self._current_module_path.split('.')
            if len(parts) >= 2:
                # 使用完整模块路径前缀，例如 $root.A.B -> A.B.signal
                module_prefix = '.'.join(parts[1:])  # 去掉 $root
                if not target_path.startswith(module_prefix + '.'):
                    full_target_path = f"{module_prefix}.{target_path}"

        # 如果目标不在图中,添加为组合逻辑节点
        if not self.graph.has_node(full_target_path):
            self.graph.add_node(full_target_path, kind='Net', type='logic[7:0]')
            self._node_attrs[full_target_path] = NodeAttr(
                kind='Net', name=full_target_path.split('.')[-1]
            )

        right = assignment.get('right', {})
        if not isinstance(right, dict):
            return

        # 如果右侧是 ConditionalOp,提取条件并添加边
        if right.get('kind') == 'ConditionalOp':
            self._extract_ternary_conditions(target_path, right)

            # 添加连续赋值边: 从驱动信号到目标信号
            self._add_combinational_edges(target_path, right)
        elif right.get('kind') == 'NamedValue':
            # 简单连续赋值: assign x = y;
            driver = self._extract_expr_path(right)
            if driver and self.graph.has_node(driver) and self.graph.has_node(target_path):
                if not self.graph.has_edge(driver, target_path):
                    self.graph.add_edge(driver, target_path,
                        relation='drives', timing='combinational',
                        edge_kind=None, condition='')
        elif right.get('kind') == 'ElementSelect':
            # 数组索引赋值: assign x = y[3];
            # 递归处理基础信号
            base_value = right.get('value', {})
            if isinstance(base_value, dict) and base_value.get('kind') == 'NamedValue':
                driver = self._extract_expr_path(right)
                if driver and self.graph.has_node(driver) and self.graph.has_node(target_path):
                    if not self.graph.has_edge(driver, target_path):
                        self.graph.add_edge(driver, target_path,
                            relation='drives', timing='combinational',
                            edge_kind=None, condition='')

    def _add_combinational_edges(self, target_path: str, expr: Dict):
        """为连续赋值表达式添加组合逻辑边"""
        if not isinstance(expr, dict):
            return

        # 确保目标节点在图中(使用完整路径)
        if not self.graph.has_node(target_path):
            self.graph.add_node(target_path, kind='Net', type='logic[7:0]')
            self._node_attrs[target_path] = NodeAttr(
                kind='Net', name=target_path.split('.')[-1]
            )

        kind = expr.get('kind', '')

        if kind == 'ConditionalOp':
            # 条件驱动: 添加条件信号边
            conditions = expr.get('conditions', [])
            for cond in conditions:
                if isinstance(cond, dict):
                    cond_expr = cond.get('expr', {})
                    if cond_expr.get('kind') == 'ElementSelect':
                        # sel[0] -> 获取 sel
                        value = cond_expr.get('value', {})
                        if value.get('kind') == 'NamedValue':
                            driver = self._extract_expr_path(value)
                            if driver and self.graph.has_node(driver):
                                self.graph.add_edge(driver, target_path,
                                    relation='drives', timing='combinational',
                                    edge_kind=None, condition=target_path.split('.')[-1] + '.sel')

            # 递归处理左右分支
            left = expr.get('left', {})
            right = expr.get('right', {})
            if isinstance(left, dict):
                self._add_combinational_edges(target_path, left)
            if isinstance(right, dict):
                self._add_combinational_edges(target_path, right)

        elif kind == 'NamedValue':
            # 简单信号赋值: 添加边
            driver = self._extract_expr_path(expr)
            # 添加模块前缀
            if self._current_module_path and driver and not any(d in driver for d in ['.', 'test_', 'u_']):
                module_short = self._current_module_path.split('.')[-1]
                if not driver.startswith(module_short + '.'):
                    driver = f"{module_short}.{driver}"
            if driver and self.graph.has_node(driver):
                if not self.graph.has_edge(driver, target_path):
                    self.graph.add_edge(driver, target_path,
                        relation='drives', timing='combinational',
                        edge_kind=None)

        elif kind == 'ElementSelect':
            # 数组/向量选择: 从基础信号添加边
            value = expr.get('value', {})
            if isinstance(value, dict):
                self._add_combinational_edges(target_path, value)

        elif kind == 'BinaryOp':
            # 二元操作: 递归处理左右操作数
            for key in ('left', 'right'):
                operand = expr.get(key, {})
                if isinstance(operand, dict):
                    self._add_combinational_edges(target_path, operand)

    def _analyze_conditional(self, cond_node_or_dict, timing_ctx=None):
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
                    self._extract_assignments_from_stmt(f"{condition}", 'if', if_true, timing_ctx)

            if_false = attrs.get('ifFalse')
            if if_false and isinstance(if_false, dict):
                if if_false.get('kind') == 'Conditional':
                    self._analyze_conditional(if_false, timing_ctx)
                elif if_false.get('kind') == 'ConditionalOp':
                    self._analyze_conditional_op(if_false)
                else:
                    if conditions:
                        last_cond_expr = conditions[-1].get('expr', {})
                        last_cond = self._extract_expr_path(last_cond_expr)
                        if last_cond:
                            self._extract_assignments_from_stmt(f"!{last_cond}", 'if', if_false, timing_ctx)
                        else:
                            self._extract_assignments_from_stmt('', 'else', if_false, timing_ctx)

        # 处理三元运算符结构 (condition, trueExpression, falseExpression)
        # ConditionalOp 使用 conditions/left/right 而非 condition/trueExpression/falseExpression
        condition = self._extract_expr_path(attrs.get('condition', {}))
        if not condition:
            # 尝试 ConditionalOp 格式
            conditions_list = attrs.get('conditions', [])
            if conditions_list and isinstance(conditions_list, list):
                cond_item = conditions_list[0]
                if isinstance(cond_item, dict) and 'expr' in cond_item:
                    condition = self._extract_expr_path(cond_item['expr'])

        if condition:
            # 真分支: trueExpression 或 left
            true_expr = attrs.get('trueExpression', {}) or attrs.get('left', {})
            if true_expr:
                self._extract_assignments_from_expr(f"{condition}", 'ternary', true_expr, timing_ctx)

            # 假分支: falseExpression 或 right
            false_expr = attrs.get('falseExpression', {}) or attrs.get('right', {})
            if false_expr:
                # 嵌套三元: right 可能是另一个 ConditionalOp
                if isinstance(false_expr, dict) and false_expr.get('kind') == 'ConditionalOp':
                    # 递归处理嵌套三元
                    self._analyze_conditional_op(false_expr, timing_ctx)
                else:
                    self._extract_assignments_from_expr(f"!{condition}", 'ternary', false_expr, timing_ctx)

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

                # 优先使用当前模块上下文来构建路径
                if self._current_module_path:
                    module_parts = self._current_module_path.split('.')

                    if len(module_parts) == 3 and module_parts[1] == module_parts[2]:
                        # $root.test_multi_clock_domain.test_multi_clock_domain 模式
                        # 信号存储为 test_multi_clock_domain.<name>
                        current_module_short = module_parts[-1]
                        candidate = f"{current_module_short}.{name}"
                        if candidate in self._node_attrs or self.graph.has_node(candidate):
                            return candidate
                    elif len(module_parts) >= 4:
                        # $root.A.A.u_inst.B 或类似模式
                        # 信号存储为 B.<name> (instance name 作为前缀)
                        current_module_short = module_parts[-1]
                        candidate = f"{current_module_short}.{name}"
                        if candidate in self._node_attrs or self.graph.has_node(candidate):
                            return candidate
                        # 也检查完整路径的情况
                        current_module_path = f"{module_parts[-2]}.{current_module_short}"
                        candidate = f"{current_module_path}.{name}"
                        if candidate in self._node_attrs or self.graph.has_node(candidate):
                            return candidate

                # Fallback: 遍历 _node_attrs,匹配 name
                for node_path in self._node_attrs:
                    if node_path.endswith(f'.{name}'):
                        return node_path

                # 如果找不到精确匹配,返回 name (可能只是模块内信号)
                return name
            return sym

        # 递归处理
        for key in ('left', 'right', 'operand', 'operand1', 'operand2', 'expr', 'value'):
            if key in expr:
                result = self._extract_expr_path(expr[key])
                if result:
                    return result

        return ''

    def _extract_assignments_from_stmt(self, condition: str, cond_kind: str, stmt: Dict, timing_ctx=None):
        """从语句中提取赋值目标"""
        if not isinstance(stmt, dict):
            return

        if stmt.get('kind') == 'ExpressionStatement':
            expr = stmt.get('expr', {})
            self._extract_assignments_from_expr(condition, cond_kind, expr, timing_ctx)
        elif stmt.get('kind') == 'Block':
            # Block 结构可能是:
            # 1. items: [{ExpressionStatement}, ...]
            # 2. body.list: [{ExpressionStatement}, ...]  (slang AST 格式)
            items = stmt.get('items', [])
            if not items:
                # 尝试 body.list 结构
                body = stmt.get('body', {})
                if isinstance(body, dict):
                    items = body.get('list', [])
            for item in items:
                self._extract_assignments_from_stmt(condition, cond_kind, item, timing_ctx)

    def _extract_assignments_from_expr(self, condition: str, cond_kind: str, expr: Dict, timing_ctx=None):
        """从表达式中提取赋值并建立条件映射"""
        if not isinstance(expr, dict):
            return

        kind = expr.get('kind', '')

        # 处理 ContinuousAssign (continuous assignments like assign x = y ? a : b)
        if kind == 'ContinuousAssign':
            # ContinuousAssign has 'assignment' field
            assignment = expr.get('assignment', {})
            if isinstance(assignment, dict):
                # 处理左侧目标
                left = assignment.get('left', {})
                target_path = self._extract_expr_path(left)

                # 添加目标模块前缀
                if self._current_module_path and target_path and not any(
                    target_path.startswith(p) for p in ['.', 'test_', 'u_']
                ):
                    module_parts = self._current_module_path.split('.')
                    if len(module_parts) == 3 and module_parts[1] == module_parts[2]:
                        current_module_short = module_parts[-1]
                        if not target_path.startswith(current_module_short + '.'):
                            target_path = f"{current_module_short}.{target_path}"

                # 处理右侧表达式 (可能是 ConditionalOp 或简单的 NamedValue)
                right = assignment.get('right', {})
                self._extract_assignments_from_expr(condition, cond_kind, right, timing_ctx)

                # 为 ContinuousAssign 添加边: driver -> target
                # 对于 assign x = y, 添加边: y -> x
                if target_path and isinstance(right, dict):
                    driver = self._extract_expr_path(right)
                    if driver and self._current_module_path and not any(
                        driver.startswith(p) for p in ['.', 'test_', 'u_']
                    ):
                        module_parts = self._current_module_path.split('.')
                        if len(module_parts) == 3 and module_parts[1] == module_parts[2]:
                            current_module_short = module_parts[-1]
                            if not driver.startswith(current_module_short + '.'):
                                driver = f"{current_module_short}.{driver}"
                    if driver and self.graph.has_node(driver) and self.graph.has_node(target_path):
                        if not self.graph.has_edge(driver, target_path):
                            self.graph.add_edge(driver, target_path,
                                relation='drives', timing='combinational',
                                edge_kind=None, condition='')
            return

        # 处理 ConditionalOp (三元运算符)
        if kind == 'ConditionalOp':
            conditions = expr.get('conditions', [])
            if conditions and isinstance(conditions, list):
                for cond_item in conditions:
                    if isinstance(cond_item, dict) and 'expr' in cond_item:
                        cond_expr = cond_item['expr']
                        cond = self._extract_expr_path(cond_expr)
                        if cond:
                            # 真分支 (left)
                            true_expr = expr.get('left', {})
                            self._extract_assignments_from_expr(f"{cond}", 'ternary', true_expr)
                            # 假分支 (right) - 可能是嵌套三元
                            false_expr = expr.get('right', {})
                            if isinstance(false_expr, dict):
                                if false_expr.get('kind') == 'ConditionalOp':
                                    self._extract_assignments_from_expr(f"!{cond}", 'ternary', false_expr)
                                else:
                                    self._extract_assignments_from_expr(f"!{cond}", 'ternary', false_expr)
            return

        if kind == 'Assignment':
            left = expr.get('left', {})
            target_path = self._extract_expr_path(left)

            # 添加模块前缀(如果 _current_module_path 可用)
            if self._current_module_path and target_path:
                module_parts = self._current_module_path.split('.')
                if len(module_parts) == 3 and module_parts[1] == module_parts[2]:
                    current_module_short = module_parts[-1]
                    if not target_path.startswith(current_module_short + '.'):
                        target_path = f"{current_module_short}.{target_path}"

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

            # 如果 target_path 不在 _node_attrs 中(中间变量如 selector_out),
            # 添加为节点并建立 _signal_conditions 条目
            if target_path and target_path not in self._signal_conditions:
                # 添加模块前缀(如果需要)
                if self._current_module_path and not any(target_path.startswith(p) for p in ['test_', 'u_']):
                    module_parts = self._current_module_path.split('.')
                    if len(module_parts) == 3 and module_parts[1] == module_parts[2]:
                        current_module_short = module_parts[-1]
                        if not target_path.startswith(current_module_short + '.'):
                            target_path = f"{current_module_short}.{target_path}"
                
                # 如果仍然不在 _node_attrs 中,添加为组合逻辑节点
                if target_path not in self._node_attrs:
                    self._node_attrs[target_path] = NodeAttr(
                        kind='Net', name=target_path.split('.')[-1]
                    )
                    self.graph.add_node(target_path, kind='Net', type='logic')
                
                self._signal_conditions[target_path] = []

            # 去重: 同一 target_path + condition + statement 只保留一个
            if not target_path or target_path not in self._signal_conditions:
                return  # target_path 无效或未初始化

            dedup_key = (condition, assignment_stmt)
            for i, existing in enumerate(self._signal_conditions[target_path]):
                if existing.get('condition') == condition and existing.get('statement') == assignment_stmt:
                    # 更新已有条目的 timing 信息
                    if timing_ctx and not existing.get('clock_domain'):
                        existing['target_kind'] = 'register_output'
                        existing['clock_domain'] = timing_ctx['clock'][0]['signal'] if timing_ctx['clock'] else None
                        existing['edge_type'] = timing_ctx['clock'][0]['edge'] if timing_ctx['clock'] else None
                        if timing_ctx['reset']:
                            existing['reset_signal'] = timing_ctx['reset'][0]['signal']
                            existing['reset_kind'] = timing_ctx['reset'][0].get('kind', 'async')
                    break
            else:
                condition_entry = {
                    'condition': condition,
                    'kind': cond_kind,
                    'source': 'ast',
                    'location': location,
                    'statement': assignment_stmt,
                    'if_expression': if_expression
                }

                if timing_ctx:
                    condition_entry['target_kind'] = 'register_output'
                    condition_entry['clock_domain'] = timing_ctx['clock'][0]['signal'] if timing_ctx['clock'] else None
                    condition_entry['edge_type'] = timing_ctx['clock'][0]['edge'] if timing_ctx['clock'] else None
                    if timing_ctx['reset']:
                        condition_entry['reset_signal'] = timing_ctx['reset'][0]['signal']
                        condition_entry['reset_kind'] = timing_ctx['reset'][0].get('kind', 'async')
                else:
                    condition_entry['target_kind'] = 'combinational'

                self._signal_conditions[target_path].append(condition_entry)

            # 如果在 case 上下文中,添加 case 选择变量 -> target 的边
            # 这允许追踪 FSM 状态对数据赋值的控制
            # 例如: case (curr_state) S_DATA: data = tx_fifo_data_i; -> curr_state -> data
            if cond_kind == 'case' and condition:
                # 从 condition 中提取 case 选择变量
                # condition 可能是: "curr_state == S_DATA" (有 case_value) 或 "curr_state" (无 case_value)
                case_var = condition.split('==')[0].strip() if '==' in condition else condition.strip()
                
                # 检查 case_var 是否是 FSM 状态变量
                # 状态变量通常在 _node_attrs 中且名称包含 'state'
                if case_var:
                    # 尝试找到完整的 case_var 路径
                    full_case_var = case_var
                    if case_var in self._node_attrs:
                        full_case_var = case_var
                    elif self._current_module_path:
                        # 尝试添加模块前缀
                        module_parts = self._current_module_path.split('.')
                        if len(module_parts) >= 2:
                            module_short = module_parts[-1]
                            if not case_var.startswith(module_short + '.'):
                                full_case_var = f"{module_short}.{case_var}"
                    
                    if full_case_var in self._node_attrs or full_case_var in self.graph:
                        if self.graph.has_node(full_case_var) and self.graph.has_node(target_path):
                            if not self.graph.has_edge(full_case_var, target_path):
                                self.graph.add_edge(full_case_var, target_path,
                                    relation='controls', timing='combinational',
                                    edge_kind=None, condition=condition)

            # 如果在 timing_ctx 中(ProceduralBlock),添加数据流边
            # 这处理 always 块中的赋值,例如: always @(posedge clk) enable_reg <= data_in;
            # 也处理 always @(*) 组合逻辑块(timing_ctx 为 None)
            if target_path in self._node_attrs:
                # 提取右侧表达式中的驱动信号
                right = expr.get('right', {})
                if isinstance(right, dict):
                    driver = self._extract_expr_path(right)
                    if self._current_module_path and driver and not any(d in driver for d in ['.', 'test_', 'u_']):
                        module_parts = self._current_module_path.split('.')
                        if len(module_parts) == 3 and module_parts[1] == module_parts[2]:
                            current_module_short = module_parts[-1]
                            if not driver.startswith(current_module_short + '.'):
                                driver = f"{current_module_short}.{driver}"
                    if driver and self.graph.has_node(driver):
                        if not self.graph.has_edge(driver, target_path):
                            # always @(*) 或 if (timing_ctx is None) 时为组合逻辑,否则为时序逻辑
                            timing_type = 'sequential' if (timing_ctx and timing_ctx.get('clock')) else 'combinational'
                            self.graph.add_edge(driver, target_path,
                                relation='drives', timing=timing_type,
                                edge_kind=None, condition=condition if condition else '')

        elif kind == 'Block':
            for item in expr.get('items', []):
                self._extract_assignments_from_expr(condition, cond_kind, item, timing_ctx)

    def _traverse_ast(self, node) -> List:
        """遍历 AST 节点"""
        results = [node]
        for child in node.children:
            results.extend(self._traverse_ast(child))
        return results

    def _enrich_edges_with_conditions(self):
        """
        丰富边的条件属性

        对于每个目标信号,检查是否有 AST 分析的条件信息,
        并更新对应的边。
        """
        for target_path, conditions in self._signal_conditions.items():
            if not conditions:
                continue

            # 查找所有以 target_path 为目标的边
            for (src, dst, key), attr in self._edge_attrs.items():
                if dst == target_path and not attr.condition:
                    # 使用第一个条件(可以扩展为多条件)
                    cond_info = conditions[0]
                    attr.condition = cond_info['condition']
                    attr.condition_kind = cond_info['kind']
                    attr.condition_signals = [c['condition'] for c in conditions]

                    # 更新图中边的属性
                    if self.graph.has_edge(src, dst, key):
                        self.graph[src][dst][key]['condition'] = attr.condition
                        self.graph[src][dst][key]['condition_kind'] = attr.condition_kind
                        self.graph[src][dst][key]['condition_signals'] = attr.condition_signals

        # 补充: 用 AST 条件信息创建缺失的边
        # 如果条件信号到目标信号之间没有边，创建一条
        for target_path, conditions in self._signal_conditions.items():
            if not target_path in self.graph:
                continue
            for cond_info in conditions:
                cond_signal = cond_info.get('condition', '')
                if cond_signal and cond_signal in self.graph:
                    if not self.graph.has_edge(cond_signal, target_path):
                        attr = EdgeAttr(
                            edge_kind='None',
                            bounds=(0, 0),
                            condition=cond_signal,
                            condition_kind=cond_info.get('kind', ''),
                            condition_signals=[cond_signal],
                        )
                        key = self.graph.add_edge(
                            cond_signal,
                            target_path,
                            **attr.to_dict()
                        )
                        self._edge_attrs[(cond_signal, target_path, key)] = attr

        # 补充: 从 AST 中提取拼接表达式的数据路径
        self._extract_concat_edges_from_ast()
        # 补充: 从 AST 中提取 always_comb 条件边
        self._extract_comb_cond_edges_from_ast()

    def _extract_comb_cond_edges_from_ast(self):
        """从 AST 提取 always_comb 块中的条件信号边"""
        if not self.ast_json_path or not os.path.exists(self.ast_json_path):
            return
        import json as json_mod
        try:
            with open(self.ast_json_path) as f:
                ast_data = json_mod.load(f)
        except (json_mod.JSONDecodeError, IOError):
            return
        self._walk_ast_for_comb_cond(ast_data, [])

    def _walk_ast_for_comb_cond(self, node: Any, cond_stack: list):
        """遍历 AST 提取 always_comb 中的条件赋值关系"""
        if isinstance(node, dict):
            kind = node.get('kind', '')

            if kind == 'ProceduralBlock' and node.get('procedureKind') == 'AlwaysComb':
                self._walk_ast_for_comb_cond(node.get('body', {}), [])
                return

            if kind == 'Conditional':
                # 提取条件信号
                conditions = node.get('conditions', [])
                cond_signals = []
                for cond in conditions:
                    expr = cond.get('expr', {})
                    self._collect_cond_signals(expr, cond_signals)

                new_stack = cond_stack + cond_signals

                # if 分支的赋值
                if_true = node.get('ifTrue', {})
                self._walk_ast_for_comb_cond(if_true, new_stack)

                # else 分支
                if_false = node.get('ifFalse', {})
                if if_false:
                    self._walk_ast_for_comb_cond(if_false, new_stack)
                return

            if kind == 'ExpressionStatement':
                expr = node.get('expr', {})
                if expr.get('kind') == 'Assignment' and not expr.get('isNonBlocking', False):
                    left = expr.get('left', {})
                    target_sym = left.get('symbol', '')
                    _, target_name = self._parse_ast_symbol(target_sym)
                    if target_name and cond_stack:
                        target_path = None
                        for path in self.graph.nodes:
                            if path.endswith(f'.{target_name}') or path == target_name:
                                target_path = path
                                break
                        if target_path:
                            for cond_sig in cond_stack:
                                if cond_sig in self.graph and not self.graph.has_edge(cond_sig, target_path):
                                    attr = EdgeAttr(edge_kind='None', bounds=(0, 0))
                                    key = self.graph.add_edge(cond_sig, target_path, **attr.to_dict())
                                    self._edge_attrs[(cond_sig, target_path, key)] = attr
                return

            for v in node.values():
                self._walk_ast_for_comb_cond(v, cond_stack)
        elif isinstance(node, list):
            for item in node:
                self._walk_ast_for_comb_cond(item, cond_stack)

    def _collect_cond_signals(self, expr: dict, signals: list):
        """从条件表达式中提取信号路径"""
        kind = expr.get('kind', '')
        if kind == 'NamedValue':
            sym = expr.get('symbol', '')
            _, name = self._parse_ast_symbol(sym)
            if name:
                for path in self.graph.nodes:
                    if path.endswith(f'.{name}') or path == name:
                        if path not in signals:
                            signals.append(path)
                        break
        elif kind == 'ElementSelect':
            self._collect_cond_signals(expr.get('value', {}), signals)
        elif kind == 'BinaryOp':
            self._collect_cond_signals(expr.get('left', {}), signals)
            self._collect_cond_signals(expr.get('right', {}), signals)
        elif kind == 'UnaryOp':
            self._collect_cond_signals(expr.get('operand', {}), signals)

    def _extract_concat_edges_from_ast(self):
        """从 AST 提取拼接表达式的数据依赖边"""
        if not self.ast_json_path or not os.path.exists(self.ast_json_path):
            return
        import json as json_mod
        try:
            with open(self.ast_json_path) as f:
                ast_data = json_mod.load(f)
        except (json_mod.JSONDecodeError, IOError):
            return
        self._walk_ast_for_concat(ast_data)

    def _walk_ast_for_concat(self, node: Any):
        """遍历 AST 找拼接赋值"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'ExpressionStatement':
                expr = node.get('expr', {})
                if expr.get('kind') == 'Assignment':
                    left = expr.get('left', {})
                    right = expr.get('right', {})
                    if right.get('kind') == 'Conversion':
                        right = right.get('operand', {})
                    if right.get('kind') == 'Concatenation':
                        self._process_concat_assignment(left, right)
            for v in node.values():
                self._walk_ast_for_concat(v)
        elif isinstance(node, list):
            for item in node:
                self._walk_ast_for_concat(item)

    def _process_concat_assignment(self, left: dict, right: dict):
        """处理拼接赋值: left <= {a, b, c}"""
        left_symbol = left.get('symbol', '')
        if not left_symbol:
            return
        _, target_name = self._parse_ast_symbol(left_symbol)
        if not target_name:
            return
        target_path = None
        for path in self.graph.nodes:
            if path.endswith(f'.{target_name}') or path == target_name:
                target_path = path
                break
        if not target_path:
            return
        operands = right.get('operands', [])
        for op in operands:
            if op.get('kind') == 'NamedValue':
                sym = op.get('symbol', '')
                _, op_name = self._parse_ast_symbol(sym)
                if op_name:
                    op_path = None
                    for path in self.graph.nodes:
                        if path.endswith(f'.{op_name}') or path == op_name:
                            op_path = path
                            break
                    if op_path and not self.graph.has_edge(op_path, target_path):
                        attr = EdgeAttr(edge_kind='None', bounds=(0, 0))
                        key = self.graph.add_edge(op_path, target_path, **attr.to_dict())
                        self._edge_attrs[(op_path, target_path, key)] = attr

