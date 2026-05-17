# graph/class_explorer.py - Class 内 method 驱动关系补充
# navisv 架构 v0.8 - Graph Layer

"""
ClassExplorer: 补充 class 内的 method 驱动关系。

角色约束：
- slang 不处理 class，这是唯一在 Python 层创建边的场景
- source="python"，confidence="medium"
- slang 拓扑优先，不覆盖已有边（铁律3）
"""

from typing import Iterator, Tuple, Any


class ClassExplorer:
    """
    补充 class 内 method 驱动关系。
    slang 不处理 class，这是唯一在 Python 层创建边的场景。
    """

    def merge_method_edges(self, graph: 'DesignGraph') -> None:
        """
        合并 class method 调用边。
        
        合并原则（铁律3）：
        - 如果边已存在（source="slang"）：只补充 Python 独有的字段，不覆盖拓扑
        - 如果边不存在：创建新边，标记 source="python"
        """
        for src, dst, info in self._extract_method_drives():
            if graph.graph.has_edge(src, dst):
                # 边已存在，slang 拓扑优先，只补充属性
                existing = graph.graph.edges[src, dst]
                if existing.get('source') == 'slang':
                    # 只补充 source_location
                    if not existing.get('source_location') and info.get('source_location'):
                        existing['source_location'] = info['source_location']
                    # 记录 Python 发现的额外关系
                    if existing.get('relation') == 'drives' and info.get('relation') == 'calls':
                        existing.setdefault('meta', {})['python_relation'] = 'calls'
            else:
                # 新边，slang 完全不知道
                graph.graph.add_edge(src, dst,
                    relation=info.get('relation', 'calls'),
                    timing=info.get('timing', 'unknown'),
                    qualifier=info.get('qualifier'),
                    bounds=info.get('bounds'),
                    source_location=info.get('source_location'),
                    source='python',
                    is_partial=info.get('is_partial', True),
                    confidence='medium',
                    meta={})

    def _extract_method_drives(self) -> Iterator[Tuple[str, str, dict]]:
        """
        提取 class 内的 method 驱动关系。
        Yields: (src, dst, edge_info)
        
        注意：这是占位实现。class method 提取需要完整的 class 遍历逻辑。
        当前返回空迭代器，待后续实现完整逻辑。
        """
        # TODO: 实现完整的 class 方法遍历
        # 需要遍历 ClassDeclarationSyntax，提取 ClassMethodDeclarationSyntax
        # 对每个 method call，找到 target property 和 method 本身
        return
        yield  # 使函数成为 generator