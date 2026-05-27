"""
sva_parser.py - 从 slang AST 提取 SVA (SystemVerilog Assertions)

直接从语义 AST 提取:
  - ConcurrentAssertion (assert/assume/cover/restrict)
  - Property 定义
  - Sequence 定义
  - AssertionInstance (property 引用)
  
不做图转换, 输出结构化原始数据供后续对比使用。
"""

import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class SVAAssertion:
    """一条 assertion"""
    kind: str                    # Assert / Assume / CoverProperty / Restrict
    clock: str = ''              # 时钟信号
    edge: str = ''               # PosEdge / NegEdge
    disable_condition: str = ''  # disable iff 条件
    expression: str = ''         # 属性表达式 (可读)
    signals: List[str] = field(default_factory=list)  # 涉及的信号
    property_name: str = ''      # 引用的 property 名 (如有)
    location: Optional[Dict] = None


@dataclass
class SVAProperty:
    """property 定义"""
    name: str
    full_path: str = ''
    clock: str = ''
    edge: str = ''
    disable_condition: str = ''
    expression: str = ''
    signals: List[str] = field(default_factory=list)


@dataclass
class SVASequence:
    """sequence 定义"""
    name: str
    full_path: str = ''
    expression: str = ''
    signals: List[str] = field(default_factory=list)
    local_vars: List[str] = field(default_factory=list)


class SVAParser:
    """
    从 slang AST JSON 提取 SVA 信息
    
    Usage:
        parser = SVAParser(ast_json_path)
        parser.parse()
        assertions = parser.assertions
        properties = parser.properties
        sequences = parser.sequences
    """
    
    def __init__(self, ast_json_path: str):
        self.ast_json_path = ast_json_path
        self.assertions: List[SVAAssertion] = []
        self.properties: Dict[str, SVAProperty] = {}   # name -> SVAProperty
        self.sequences: Dict[str, SVASequence] = {}     # name -> SVASequence
        
        # 地址 -> 名称映射
        self._addr_to_name: Dict[str, str] = {}
    
    def parse(self) -> 'SVAParser':
        with open(self.ast_json_path) as f:
            data = json.load(f)
        self._walk(data, '')
        return self
    
    def _walk(self, node: Any, location: str):
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind in ('Module', 'ClassType', 'Package'):
                location = node.get('name', location)
            
            if kind == 'Property':
                self._process_property(node, location)
            elif kind == 'Sequence':
                self._process_sequence(node, location)
            elif kind == 'ConcurrentAssertion':
                self._process_concurrent_assertion(node, location)
            
            for v in node.values():
                self._walk(v, location)
        elif isinstance(node, list):
            for item in node:
                self._walk(item, location)
    
    def _process_property(self, node: dict, location: str):
        name = node.get('name', '')
        if not name:
            return
        addr = str(node.get('addr', ''))
        full_path = f"{location}.{name}" if location else name
        self._addr_to_name[addr] = name
        
        prop = SVAProperty(name=name, full_path=full_path)
        self.properties[name] = prop
    
    def _process_sequence(self, node: dict, location: str):
        name = node.get('name', '')
        if not name:
            return
        addr = str(node.get('addr', ''))
        full_path = f"{location}.{name}" if location else name
        self._addr_to_name[addr] = name
        
        seq = SVASequence(name=name, full_path=full_path)
        self.sequences[name] = seq
    
    def _process_concurrent_assertion(self, node: dict, location: str):
        assertion_kind = node.get('assertionKind', '')
        prop_spec = node.get('propertySpec', {})
        
        assertion = SVAAssertion(kind=assertion_kind)
        
        # 解析 propertySpec
        self._parse_property_spec(prop_spec, assertion)
        
        self.assertions.append(assertion)
    
    def _parse_property_spec(self, prop_spec: dict, assertion: SVAAssertion):
        """解析 propertySpec 节点"""
        kind = prop_spec.get('kind', '')
        
        if kind == 'Clocking':
            # 提取时钟
            clocking = prop_spec.get('clocking', {})
            self._parse_clocking(clocking, assertion)
            # 提取表达式
            expr = prop_spec.get('expr', {})
            self._parse_sva_expr(expr, assertion)
        
        elif kind == 'DisableIff':
            # disable iff 条件
            condition = prop_spec.get('condition', {})
            assertion.disable_condition = self._expr_to_string(condition)
            # 继续解析内部表达式
            inner = prop_spec.get('expr', {})
            self._parse_property_spec(inner, assertion)
        
        elif kind == 'Binary':
            # 直接是二元表达式 (无时钟包装)
            assertion.expression = self._expr_to_string(prop_spec)
            self._collect_signals(prop_spec, assertion.signals)
        
        elif kind == 'Simple':
            # 引用命名 property
            expr = prop_spec.get('expr', {})
            self._parse_sva_expr(expr, assertion)
    
    def _parse_clocking(self, clocking: dict, assertion: SVAAssertion):
        """解析时钟事件"""
        kind = clocking.get('kind', '')
        if kind == 'SignalEvent':
            expr = clocking.get('expr', {})
            assertion.clock = self._get_signal_name(expr)
            assertion.edge = clocking.get('edge', '')
    
    def _parse_sva_expr(self, node: dict, assertion: SVAAssertion):
        """解析 SVA 表达式"""
        if not node:
            return
        
        kind = node.get('kind', '')
        
        if kind == 'Binary':
            op = node.get('op', '')
            left = node.get('left', {})
            right = node.get('right', {})
            left_str = self._sva_expr_to_string(left)
            right_str = self._sva_expr_to_string(right)
            op_map = {
                'OverlappedImplication': '|->',
                'NonOverlappedImplication': '|=>',
                'Until': 'until',
                'UntilWith': 'until_w',
            }
            assertion.expression = f"{left_str} {op_map.get(op, op)} {right_str}"
            self._collect_signals(node, assertion.signals)
        
        elif kind == 'SequenceConcat':
            elements = node.get('elements', [])
            parts = []
            for elem in elements:
                seq = elem.get('sequence', {})
                min_delay = elem.get('min', 0)
                max_delay = elem.get('max', 0)
                seq_str = self._sva_expr_to_string(seq)
                if min_delay == max_delay:
                    if min_delay > 0:
                        parts.append(f"##{min_delay} {seq_str}")
                    else:
                        parts.append(seq_str)
                else:
                    parts.append(f"##[{min_delay}:{max_delay}] {seq_str}")
            assertion.expression = ' '.join(parts)
            self._collect_signals(node, assertion.signals)
        
        elif kind == 'DisableIff':
            condition = node.get('condition', {})
            assertion.disable_condition = self._expr_to_string(condition)
            inner = node.get('expr', {})
            self._parse_sva_expr(inner, assertion)
        
        elif kind == 'Simple':
            expr = node.get('expr', {})
            assertion.expression = self._sva_expr_to_string(expr)
            self._collect_signals(expr, assertion.signals)
        
        elif kind == 'Clocking':
            self._parse_clocking(node.get('clocking', {}), assertion)
            expr = node.get('expr', {})
            self._parse_sva_expr(expr, assertion)
        
        elif kind == 'AssertionInstance':
            # 引用命名 property
            sym = node.get('symbol', '')
            if ' ' in sym:
                assertion.property_name = sym.split(' ')[-1]
            # 解析展开的 body
            body = node.get('body', {})
            if body:
                self._parse_sva_expr(body, assertion)
        
        else:
            assertion.expression = self._sva_expr_to_string(node)
            self._collect_signals(node, assertion.signals)
    
    def _sva_expr_to_string(self, node: dict) -> str:
        """将 SVA 表达式节点转为字符串"""
        if not node:
            return ''
        
        kind = node.get('kind', '')
        
        if kind == 'NamedValue':
            return self._get_signal_name(node)
        
        if kind == 'IntegerLiteral':
            return node.get('constant', node.get('value', ''))
        
        if kind == 'BinaryOp':
            left = self._sva_expr_to_string(node.get('left', {}))
            right = self._sva_expr_to_string(node.get('right', {}))
            op = node.get('op', '?')
            op_map = {
                'Equality': '==', 'Inequality': '!=',
                'LessThan': '<', 'LessThanEqual': '<=',
                'GreaterThan': '>', 'GreaterThanEqual': '>=',
                'LogicalAnd': '&&', 'LogicalOr': '||',
                'Add': '+', 'Subtract': '-',
            }
            return f'{left} {op_map.get(op, op)} {right}'
        
        if kind == 'UnaryOp':
            operand = self._sva_expr_to_string(node.get('operand', {}))
            op = node.get('op', '')
            op_map = {'LogicalNot': '!'}
            return f'{op_map.get(op, op)}{operand}'
        
        if kind == 'Simple':
            return self._sva_expr_to_string(node.get('expr', {}))
        
        if kind == 'Binary':
            op = node.get('op', '')
            left = self._sva_expr_to_string(node.get('left', {}))
            right = self._sva_expr_to_string(node.get('right', {}))
            op_map = {
                'OverlappedImplication': '|->',
                'NonOverlappedImplication': '|=>',
            }
            return f'{left} {op_map.get(op, op)} {right}'
        
        if kind == 'SequenceConcat':
            elements = node.get('elements', [])
            parts = []
            for elem in elements:
                seq = elem.get('sequence', {})
                min_d = elem.get('min', 0)
                max_d = elem.get('max', 0)
                seq_str = self._sva_expr_to_string(seq)
                if min_d == max_d:
                    if min_d > 0:
                        parts.append(f'##{min_d} {seq_str}')
                    else:
                        parts.append(seq_str)
                else:
                    parts.append(f'##[{min_d}:{max_d}] {seq_str}')
            return ' '.join(parts)
        
        if kind == 'Call':
            sub = node.get('subroutine', '')
            args = [self._sva_expr_to_string(a) for a in node.get('arguments', [])]
            return f'{sub}({", ".join(args)})'
        
        if kind == 'Conversion':
            return self._sva_expr_to_string(node.get('operand', {}))
        
        if kind == 'AssertionInstance':
            sym = node.get('symbol', '')
            name = sym.split(' ')[-1] if ' ' in sym else sym
            return f'({name})'
        
        if kind == 'DisableIff':
            cond = self._expr_to_string(node.get('condition', {}))
            inner = self._sva_expr_to_string(node.get('expr', {}))
            return f'disable iff ({cond}) {inner}'
        
        if kind == 'Clocking':
            return self._sva_expr_to_string(node.get('expr', {}))
        
        if kind == 'Empty':
            return ''
        
        return f'<{kind}>'
    
    def _expr_to_string(self, node: dict) -> str:
        """将普通表达式节点转为字符串"""
        if not node:
            return ''
        kind = node.get('kind', '')
        
        if kind == 'NamedValue':
            return self._get_signal_name(node)
        if kind == 'IntegerLiteral':
            return node.get('constant', node.get('value', ''))
        if kind == 'BinaryOp':
            left = self._expr_to_string(node.get('left', {}))
            right = self._expr_to_string(node.get('right', {}))
            op = node.get('op', '?')
            op_map = {
                'Equality': '==', 'Inequality': '!=',
                'LogicalAnd': '&&', 'LogicalOr': '||',
            }
            return f'{left} {op_map.get(op, op)} {right}'
        if kind == 'UnaryOp':
            operand = self._expr_to_string(node.get('operand', {}))
            op = node.get('op', '')
            op_map = {'LogicalNot': '!'}
            return f'{op_map.get(op, op)}{operand}'
        if kind == 'Conversion':
            return self._expr_to_string(node.get('operand', {}))
        return f'<{kind}>'
    
    def _get_signal_name(self, node: dict) -> str:
        """从 NamedValue 节点提取信号名"""
        sym = node.get('symbol', '')
        if sym:
            parts = sym.strip().split(' ', 1)
            return parts[1] if len(parts) == 2 else sym
        return node.get('name', '')
    
    def _collect_signals(self, node: Any, signals: list):
        """递归收集信号引用"""
        if isinstance(node, dict):
            if node.get('kind') == 'NamedValue':
                name = self._get_signal_name(node)
                if name and name not in signals:
                    signals.append(name)
            for v in node.values():
                self._collect_signals(v, signals)
        elif isinstance(node, list):
            for item in node:
                self._collect_signals(item, signals)
