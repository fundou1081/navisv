"""
condition_annotator.py - 条件标注器

从 AST 提取条件信息并标注到图的边上:
- true_condition 标注
- always_comb 条件边
- 拼接表达式边
"""

import os
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx


class ConditionAnnotator:
    """
    从 AST 提取条件信息并标注到图的边上
    """

    def __init__(self, graph: nx.MultiDiGraph, edge_attrs: dict, ast_json_path: str):
        self.graph = graph
        self.edge_attrs = edge_attrs
        self.ast_json_path = ast_json_path

    def annotate_all(self):
        """执行所有条件标注"""
        if not self.ast_json_path or not os.path.exists(self.ast_json_path):
            return
        import json
        try:
            with open(self.ast_json_path) as f:
                ast_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        self._annotate_true_conditions(ast_data)
        self._extract_comb_cond_edges(ast_data)
        self._extract_concat_edges(ast_data)

    # ================================================================
    # true_condition 标注
    # ================================================================

    def _annotate_true_conditions(self, ast_data: dict):
        """从 AST 提取 true_condition 并标注到图的边上"""
        self._walk_for_true_cond(ast_data, [], [])

    def _walk_for_true_cond(self, node: Any, cond_stack: list, neg_stack: list, current_expr_str: str = ''):
        """遍历 AST 提取 true_condition"""
        if isinstance(node, dict):
            kind = node.get('kind', '')

            if kind == 'ProceduralBlock':
                self._walk_for_true_cond(node.get('body', {}), [], [])
                return

            elif kind == 'Conditional':
                conditions = node.get('conditions', [])
                cond_signals = []
                for cond in conditions:
                    expr = cond.get('expr', {})
                    cond_str = self._ast_expr_to_string(expr)
                    if cond_str:
                        cond_signals.append(cond_str)

                self._walk_for_true_cond(node.get('predicate', {}), cond_stack, neg_stack, current_expr_str)

                if_body = node.get('ifBody', {})
                if_body_str = self._constraint_to_string(if_body)
                if_tc = f"if ({cond_signals[0] if cond_signals else ''}) {{ {if_body_str} }}"
                full_tc = f"{''.join(neg_stack)}{''.join(cond_stack)}{if_tc}"

                if_true = node.get('ifTrue', {})
                self._walk_for_true_cond(if_true, cond_stack + cond_signals, neg_stack, current_expr_str)
                self._annotate_block(if_true, full_tc)

                if_false = node.get('ifFalse', {})
                if if_false:
                    neg_cond = '!' + cond_signals[-1] if cond_signals else ''
                    else_neg = list(neg_stack) + list(cond_stack)
                    if neg_cond:
                        else_neg.append(neg_cond)

                    if if_false.get('kind') == 'Conditional':
                        self._walk_for_true_cond(if_false, [], else_neg, current_expr_str)
                    else:
                        else_tc = f"{{ {self._constraint_to_string(if_false)} }}"
                        full_else_tc = f"{''.join(else_neg)}{else_tc}"
                        self._annotate_block(if_false, full_else_tc)
                        self._walk_for_true_cond(if_false, [], else_neg, current_expr_str)
                return

            elif kind == 'Case':
                case_expr = node.get('expr', {})
                case_str = self._ast_expr_to_string(case_expr)
                items = node.get('items', [])
                default_case = node.get('defaultCase', {})

                for item in items:
                    item_exprs = item.get('expressions', item.get('exprs', []))
                    stmt = item.get('stmt', {})
                    for ie in item_exprs:
                        ie_str = self._ast_expr_to_string(ie)
                        tc_parts = list(neg_stack)
                        if ie_str:
                            tc_parts.append(f'{case_str} == {ie_str}')
                        tc = ' && '.join(tc_parts) if tc_parts else ''
                        self._annotate_block(stmt, tc)
                    self._walk_for_true_cond(stmt, [], neg_stack, current_expr_str)

                if default_case:
                    default_negs = list(neg_stack)
                    for other_item in items:
                        for oe in other_item.get('expressions', other_item.get('exprs', [])):
                            oe_str = self._ast_expr_to_string(oe)
                            if oe_str:
                                default_negs.append(f'{case_str} != {oe_str}')
                    default_tc = ' && '.join(default_negs) if default_negs else ''
                    self._annotate_block(default_case, default_tc)
                    self._walk_for_true_cond(default_case, [], neg_stack, current_expr_str)
                return

            elif kind == 'ConditionalOp':
                conditions = node.get('conditions', [])
                cond_str = ''
                for cond in conditions:
                    expr = cond.get('expr', {})
                    cond_str = self._ast_expr_to_string(expr)
                    break
                if cond_str:
                    true_expr = node.get('left', {})
                    false_expr = node.get('right', {})
                    self._annotate_ternary_target(true_expr, cond_str, neg_stack)
                    self._annotate_ternary_target(false_expr, '!' + cond_str, neg_stack)
                return

            elif kind == 'ContinuousAssign':
                assigns = node.get('assignments', node.get('assignment', []))
                if isinstance(assigns, dict):
                    assigns = [assigns]
                for assign in assigns:
                    left = assign.get('left', {})
                    right = assign.get('right', {})
                    if right.get('kind') == 'ConditionalOp':
                        self._process_continuous_ternary(left, right)

            for v in node.values():
                self._walk_for_true_cond(v, cond_stack, neg_stack, current_expr_str)

        elif isinstance(node, list):
            for item in node:
                self._walk_for_true_cond(item, cond_stack, neg_stack, current_expr_str)

    def _annotate_block(self, block_node: dict, true_condition: str):
        """标注 block 内所有直接赋值的 true_condition"""
        if not true_condition:
            return
        if isinstance(block_node, dict):
            kind = block_node.get('kind', '')
            if kind == 'ExpressionStatement':
                expr = block_node.get('expr', {})
                if expr.get('kind') == 'Assignment':
                    left = expr.get('left', {})
                    right = expr.get('right', {})
                    if right.get('kind') == 'Conversion':
                        right = right.get('operand', {})
                    target_sym = left.get('symbol', '')
                    _, target_name = self._parse_ast_symbol(target_sym)
                    source_name = ''
                    source_in_graph = False
                    if right.get('kind') == 'NamedValue':
                        _, source_name = self._parse_ast_symbol(right.get('symbol', ''))
                        if source_name:
                            source_in_graph = any(
                                path.endswith(f'.{source_name}') or path == source_name
                                for path in self.graph.nodes
                            )
                    elif right.get('kind') == 'IntegerLiteral':
                        source_name = right.get('constant', right.get('value', ''))
                        source_in_graph = False
                    if target_name:
                        self._set_true_condition_on_edge(
                            source_name if source_in_graph else '',
                            target_name, true_condition
                        )
            elif kind == 'Block':
                body = block_node.get('body', {})
                self._annotate_block(body, true_condition)
            elif kind == 'List':
                for item in block_node.get('list', []):
                    self._annotate_block(item, true_condition)
            else:
                for v in block_node.values():
                    if isinstance(v, (dict, list)):
                        self._annotate_block(v, true_condition)
        elif isinstance(block_node, list):
            for item in block_node:
                self._annotate_block(item, true_condition)

    def _annotate_ternary_target(self, expr_node: dict, true_condition: str, neg_stack: list):
        """标注三元运算符的目标"""
        if not expr_node or not true_condition:
            return
        kind = expr_node.get('kind', '')
        if kind == 'NamedValue':
            sym = expr_node.get('symbol', '')
            _, name = self._parse_ast_symbol(sym)
            if name:
                full_tc = ' && '.join(neg_stack + [true_condition]) if neg_stack else true_condition
                self._set_true_condition_on_edge('', name, full_tc)
        elif kind == 'Conversion':
            self._annotate_ternary_target(expr_node.get('operand', {}), true_condition, neg_stack)

    def _process_continuous_ternary(self, left: dict, right: dict):
        """处理连续赋值中的三元运算符"""
        target_sym = left.get('symbol', '')
        _, target_name = self._parse_ast_symbol(target_sym)
        if not target_name:
            return

        conditions = right.get('conditions', [])
        cond_str = ''
        for cond in conditions:
            expr = cond.get('expr', {})
            cond_str = self._ast_expr_to_string(expr)
            break
        if not cond_str:
            return

        target_path = None
        for path in self.graph.nodes:
            if path.endswith(f'.{target_name}') or path == target_name:
                target_path = path
                break
        if not target_path:
            return

        true_expr = right.get('left', {})
        false_expr = right.get('right', {})
        self._annotate_ternary_edge(true_expr, target_path, cond_str)
        self._annotate_ternary_edge(false_expr, target_path, '!' + cond_str)

    def _annotate_ternary_edge(self, expr_node: dict, target_path: str, true_condition: str):
        """标注三元运算符分支的具体边"""
        if not expr_node:
            return
        kind = expr_node.get('kind', '')
        source_name = ''
        if kind == 'NamedValue':
            _, source_name = self._parse_ast_symbol(expr_node.get('symbol', ''))
        elif kind == 'Conversion':
            self._annotate_ternary_edge(expr_node.get('operand', {}), target_path, true_condition)
            return
        elif kind == 'IntegerLiteral':
            source_name = expr_node.get('constant', expr_node.get('value', ''))

        if source_name:
            for src, dst, key, data in self.graph.in_edges(target_path, data=True, keys=True):
                if data.get('true_condition'):
                    continue
                src_short = src.split('.')[-1]
                if src_short == source_name or src.endswith(f'.{source_name}'):
                    data['true_condition'] = true_condition
                    break

    def _set_true_condition_on_edge(self, source_name: str, target_name: str, true_condition: str):
        """给匹配的边设置 true_condition (支持多条件叠加)"""
        target_path = None
        for path in self.graph.nodes:
            if path.endswith(f'.{target_name}') or path == target_name:
                target_path = path
                break
        if not target_path:
            return
        for src, dst, key, data in self.graph.in_edges(target_path, data=True, keys=True):
            if source_name:
                src_short = src.split('.')[-1]
                if src_short != source_name and not src.endswith(f'.{source_name}'):
                    continue
            existing = data.get('true_condition', '')
            if existing:
                data['true_condition'] = existing + ' | ' + true_condition
            else:
                data['true_condition'] = true_condition

    # ================================================================
    # always_comb 条件边
    # ================================================================

    def _extract_comb_cond_edges(self, ast_data: dict):
        """从 AST 提取 always_comb 块中的条件信号边"""
        self._walk_for_comb_cond(ast_data, [])

    def _walk_for_comb_cond(self, node: Any, cond_stack: list):
        """遍历 AST 提取 always_comb 中的条件赋值关系"""
        if isinstance(node, dict):
            kind = node.get('kind', '')

            if kind == 'ProceduralBlock' and node.get('procedureKind') == 'AlwaysComb':
                self._walk_for_comb_cond(node.get('body', {}), [])
                return

            if kind == 'Conditional':
                conditions = node.get('conditions', [])
                cond_signals = []
                for cond in conditions:
                    expr = cond.get('expr', {})
                    self._collect_cond_signals(expr, cond_signals)

                new_stack = cond_stack + cond_signals
                self._walk_for_comb_cond(node.get('ifTrue', {}), new_stack)
                self._walk_for_comb_cond(node.get('ifFalse', {}), new_stack)
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
                                    import networkx as nx
                                    attr = {'edge_kind': 'None', 'bounds': (0, 0)}
                                    self.graph.add_edge(cond_sig, target_path, **attr)
                return

            for v in node.values():
                self._walk_for_comb_cond(v, cond_stack)

        elif isinstance(node, list):
            for item in node:
                self._walk_for_comb_cond(item, cond_stack)

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

    # ================================================================
    # 拼接表达式边
    # ================================================================

    def _extract_concat_edges(self, ast_data: dict):
        """从 AST 提取拼接表达式的数据依赖边"""
        self._walk_for_concat(ast_data)

    def _walk_for_concat(self, node: Any):
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
                self._walk_for_concat(v)
        elif isinstance(node, list):
            for item in node:
                self._walk_for_concat(item)

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
                        import networkx as nx
                        attr = {'edge_kind': 'None', 'bounds': (0, 0)}
                        self.graph.add_edge(op_path, target_path, **attr)

    # ================================================================
    # 工具方法
    # ================================================================

    def _constraint_to_string(self, node: Any) -> str:
        """将约束表达式子树转换为可读字符串"""
        if not node:
            return ''
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'List':
                items = [self._constraint_to_string(item) for item in node.get('list', [])]
                return '; '.join(items)
            elif kind == 'Expression':
                expr = node.get('expr', {})
                return self._ast_expr_to_string(expr)
            elif kind == 'Conditional':
                pred = self._ast_expr_to_string(node.get('predicate', {}))
                if_body = self._constraint_to_string(node.get('ifBody', {}))
                else_body = self._constraint_to_string(node.get('elseBody', {}))
                result = f"if ({pred}) {{ {if_body} }}"
                if else_body:
                    result += f" else {{ {else_body} }}"
                return result
            else:
                return self._ast_expr_to_string(node)
        elif isinstance(node, list):
            return '; '.join(self._constraint_to_string(item) for item in node)
        return ''

    def _ast_expr_to_string(self, node: dict) -> str:
        """将 AST 表达式节点转为字符串"""
        if not node:
            return ''
        kind = node.get('kind', '')

        if kind == 'NamedValue':
            sym = node.get('symbol', '')
            _, name = self._parse_ast_symbol(sym)
            return name
        if kind == 'IntegerLiteral':
            return node.get('constant', node.get('value', ''))
        if kind == 'BinaryOp':
            left = self._ast_expr_to_string(node.get('left', {}))
            right = self._ast_expr_to_string(node.get('right', {}))
            op = node.get('op', '?')
            op_map = {
                'Equality': '==', 'Inequality': '!=',
                'LessThan': '<', 'LessThanEqual': '<=',
                'GreaterThan': '>', 'GreaterThanEqual': '>=',
                'LogicalAnd': '&&', 'LogicalOr': '||',
                'BinaryAnd': '&', 'BinaryOr': '|',
                'Add': '+', 'Subtract': '-', 'Multiply': '*', 'Divide': '/',
            }
            return f'{left} {op_map.get(op, op)} {right}'
        if kind == 'UnaryOp':
            operand = self._ast_expr_to_string(node.get('operand', {}))
            op = node.get('op', '')
            op_map = {'LogicalNot': '!'}
            return f'{op_map.get(op, op)}{operand}'
        if kind == 'ElementSelect':
            value = self._ast_expr_to_string(node.get('value', {}))
            idx = self._ast_expr_to_string(node.get('selector', {}))
            return f'{value}[{idx}]'
        if kind == 'RangeSelect':
            value = self._ast_expr_to_string(node.get('value', {}))
            left = self._ast_expr_to_string(node.get('left', {}))
            right = self._ast_expr_to_string(node.get('right', {}))
            return f'{value}[{left}:{right}]'
        if kind == 'Conversion':
            return self._ast_expr_to_string(node.get('operand', {}))
        if kind == 'Concatenation':
            operands = node.get('operands', [])
            parts = [self._ast_expr_to_string(op) for op in operands]
            return '{' + ', '.join(parts) + '}'
        return f'<{kind}>'

    def _parse_ast_symbol(self, symbol: str) -> tuple:
        """解析 AST symbol: 'addr name' -> (addr, name)"""
        if not symbol:
            return '', ''
        parts = symbol.strip().split(' ', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return '', symbol
