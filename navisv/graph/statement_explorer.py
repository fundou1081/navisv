# graph/statement_explorer.py - 边属性注释器
# navisv 架构 v0.8 - Graph Layer

"""
StatementExplorer: 遍历 always/assign 语句，为已存在的边补充属性。

角色约束（铁律15）：StatementExplorer 是边注释者，不是边构建者。
不调用 graph.add_edge()，只更新已有边的属性。

铁律检查：
- [A] StatementExplorer 不调用 add_edge
"""

from typing import Iterator, Tuple, Optional, Any


class StatementExplorer:
    """
    遍历 always/assign 语句，为已存在的边补充 timing/qualifier/source_location。
    不创建新边，边已由 slang getDrivers() 创建。
    """

    # 已知需要检查 timing 的 procedural block kinds
    PROCEDURAL_BLOCK_KINDS = {
        'AlwaysFF', 'AlwaysComb', 'AlwaysLatch', 'Always',
        'Initial', 'Final'
    }

    def __init__(self, comp, mgr):
        self.comp = comp
        self.mgr = mgr

    def annotate(self, graph: 'DesignGraph') -> None:
        """
        遍历设计中的所有 procedural block，
        为已存在的边补充 timing/qualifier/source_location。
        
        Args:
            graph: DesignGraph 实例
        """
        root = self.comp.getRoot()
        inst = list(root)[1]
        body = inst.body

        for item in body:
            kind_name = item.kind.name if hasattr(item.kind, 'name') else ''
            if kind_name in self.PROCEDURAL_BLOCK_KINDS:
                for src, dst, timing, qualifier, location in self._explore_block(item):
                    # 只更新已存在的边（铁律：StatementExplorer 不创建边）
                    if graph.graph.has_edge(src, dst):
                        edge_attrs = graph.graph.edges[src, dst]
                        # slang 拓扑优先，只补充属性
                        if timing != 'unknown' and edge_attrs.get('timing') == 'unknown':
                            edge_attrs['timing'] = timing
                        if qualifier and not edge_attrs.get('qualifier'):
                            edge_attrs['qualifier'] = qualifier
                        if location and not edge_attrs.get('source_location'):
                            edge_attrs['source_location'] = location
                        # 标记 merged
                        if edge_attrs.get('source') == 'slang':
                            if timing != 'unknown' or qualifier or location:
                                edge_attrs['source'] = 'merged'

    def _explore_block(self, block) -> Iterator[Tuple[str, str, str, Optional[str], Optional[str]]]:
        """遍历单个 procedural block"""
        block_body = getattr(block, 'body', None)
        if not block_body:
            return

        for stmt in self._walk_statements(block_body):
            result = self._extract_driver_info(stmt)
            if result:
                yield result

    def _extract_driver_info(self, stmt) -> Optional[Tuple[str, str, str, Optional[str], Optional[str]]]:
        """从赋值语句提取 (src, dst, timing, qualifier, location)"""
        stmt_kind = getattr(stmt, 'kind', None)
        if not stmt_kind:
            return None
        kind_name = stmt_kind.name if hasattr(stmt_kind, 'name') else ''

        lhs = getattr(stmt, 'expression', None) or getattr(stmt, 'left', None)
        if not lhs:
            return None

        # 提取 LHS（被驱动信号）
        lhs_name = self._resolve_signal_name(lhs)
        if not lhs_name:
            return None

        # 提取 timing
        if kind_name == 'ExpressionStatement':
            timing = 'blocking'
        elif kind_name == 'NonblockingBlockingSubprogramStatement':
            timing = 'non_blocking'
        elif kind_name == 'ContinuousAssign':
            timing = 'continuous'
        else:
            return None

        # qualifier（从上层 if 语句继承，暂不处理）
        qualifier = None

        # RHS 提取
        rhs = getattr(stmt, 'rhs', None) or getattr(stmt, 'right', None) or getattr(lhs, 'right', None)
        src_name = self._extract_rhs_driver(rhs)

        # source_location
        location = self._get_location(lhs)

        if not src_name:
            return None

        return (src_name, lhs_name, timing, qualifier, location)

    def _extract_rhs_driver(self, expr) -> Optional[str]:
        """提取 RHS 主驱动源"""
        if not expr:
            return None

        ev = ExpressionVisitor()
        ev.visit(expr)

        if ev.is_constant:
            return None
        if ev.is_simple_signal:
            return ev.signal_name
        return ev.signal_name  # partial 情况，timing 会在调用方处理

    def _resolve_signal_name(self, expr) -> Optional[str]:
        """从 LHS 提取信号名，复用 pyslang 符号表"""
        sym = getattr(expr, 'symbol', None)
        if sym:
            return sym.hierarchicalPath
        return getattr(expr, 'name', None) or str(expr)

    def _walk_statements(self, stmt) -> Iterator:
        """递归遍历 statement tree"""
        yield stmt
        for child in getattr(stmt, 'children', []):
            yield from self._walk_statements(child)

    def _get_location(self, node) -> Optional[str]:
        """获取源码位置"""
        syn = getattr(node, 'syntax', None) or getattr(node, 'getSyntax', lambda: None)()
        if syn:
            sr = getattr(syn, 'sourceRange', None)
            if sr:
                return f"{sr.start.file}:{sr.start.line}"
        return None


class ExpressionVisitor:
    """
    遍历表达式，提取驱动源信号。
    不尝试在 Python 层重建位精确性，只提取足够的语义。
    """

    def __init__(self):
        self.signal_name: Optional[str] = None
        self.is_constant: bool = False
        self.is_simple_signal: bool = False

    def visit(self, expr) -> None:
        """遍历表达式"""
        if not expr:
            return

        kind_name = getattr(expr, 'kind', None)
        kind_name = kind_name.name if kind_name and hasattr(kind_name, 'name') else ''

        # 常数
        if 'Integral' in kind_name or 'Literal' in kind_name:
            self.is_constant = True
            return

        # 简单信号
        if 'Identifier' in kind_name or 'Named' in kind_name:
            sym = getattr(expr, 'symbol', None)
            self.signal_name = sym.hierarchicalPath if sym else str(expr)
            self.is_simple_signal = True
            return

        # 拼接 {a, b} → 取第一个元素
        if 'Concatenation' in kind_name:
            parts = getattr(expr, 'expressions', [])
            if parts:
                self.visit(parts[0])
            return

        # 其他 fallback
        self.signal_name = str(expr)