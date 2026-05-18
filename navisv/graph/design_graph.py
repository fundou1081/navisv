# graph/design_graph.py - 核心图存储
# navisv 架构 v0.9 - Graph Layer

"""
DesignGraph: 持有 networkx DiGraph，是 navisv 的唯一数据存储。

铁律约束：
- [铁律2] networkx DiGraph 是唯一查询接口，不维护自定义索引字典
- [铁律3] slang 是拓扑权威，Python 只做属性补充
- [铁律14] DesignGraph 禁止暴露内部 DiGraph

构建流程（v0.9 基于用户指南的重构）：
1. 从 slang-netlist 添加节点
2. 调用 graph.get_drivers() 创建边（slang 拓扑权威）
3. StatementExplorer 补充边属性（不创建新边）
4. ClassExplorer 补充 class 内 method 调用边（唯一在 Python 创建边的场景）

参考: docs/SLANG_NETLIST_USER_GUIDE.md
"""

from typing import List, Tuple, Optional, Any, Iterator
import os

import networkx as nx

from .schema import bit_width_from_bounds


# 已知需要检查 timing 的 procedural block kinds
PROCEDURAL_BLOCK_KINDS = {
    'AlwaysFF', 'AlwaysComb', 'AlwaysLatch', 'Always',
    'Initial', 'Final'
}


def _get_slang_modules():
    """延迟加载 slang-netlist 模块"""
    import sys
    sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
    sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')
    import pyslang
    import pyslang_netlist
    return pyslang, pyslang_netlist


class DesignGraph:
    """
    持有 networkx DiGraph，是 navisv 的唯一数据存储。
    
    构建流程（v0.9 重构）：
    1. 从 slang-netlist 添加节点（SignalNode 属性）
    2. 调用 graph.get_drivers() 创建边（拓扑权威）
    3. StatementExplorer 补充边属性（不创建新边）
    4. ClassExplorer 补充 method 边
    """

    def __init__(self, sv_files: List[str], enable_annotators: bool = True):
        # 铁律2：self.graph 是唯一存储，不维护额外的自定义索引
        self.graph = nx.DiGraph()
        self._sv_files = sv_files
        self._enable_annotators = enable_annotators
        self._comp = None
        self._mgr = None
        self._slang_graph = None  # slang NetlistGraph
        self._module_name = None
        self._build()

    def _build(self) -> None:
        """主构建流程（v0.9 基于用户指南重构）"""
        pyslang, pyslang_netlist = _get_slang_modules()

        # 1. 解析语法树
        trees = []
        for f in self._sv_files:
            if not os.path.exists(f):
                raise FileNotFoundError(f"File not found: {f}")
            tree = pyslang.syntax.SyntaxTree.fromFile(f)
            trees.append(tree)

        # 2. 编译（语义分析）
        self._comp = pyslang.ast.Compilation()
        for tree in trees:
            self._comp.addSyntaxTree(tree)

        # 检查编译错误
        diagnostics = self._comp.getAllDiagnostics()
        if len(diagnostics) > 0:
            print("Compilation errors:")
            for d in diagnostics:
                print(f"  {d}")

        # 3. 激发 elaboration（新版 slang 必须调用，否则无法分析）
        self._comp.getSemanticDiagnostics()

        # 4. 强制冻结 AST (为多线程安全)
        pyslang_netlist.VisitAll().run(self._comp)

        # 5. 冻结编译，运行数据流分析
        self._comp.freeze()
        self._mgr = pyslang.analysis.AnalysisManager()
        self._mgr.analyze(self._comp)

        # 6. 解冻 (netlist builder 需要继续 elaborate AST)
        self._comp.unfreeze()

        # 7. 构建 netlist 图
        self._slang_graph = pyslang_netlist.NetlistGraph()
        self._slang_graph.build(self._comp, self._mgr)

        # 获取模块名
        root = self._comp.getRoot()
        inst = list(root)[1] if len(list(root)) > 1 else None
        self._module_name = inst.name if inst else 'top'

        # 8. 从 slang-netlist 添加节点
        self._add_nodes_from_slang(pyslang_netlist)

        # 8.5 从 compilation 添加 Instance 节点（slang-netlist 不提供 Instance 节点）
        self._add_instances_from_comp()

        # 9. graph.get_drivers() 创建边（拓扑权威）
        self._add_edges_from_slang_get_drivers()

        # 10. 使用 PathFinder 补充遗漏的边
        self._add_edges_from_pathfinder()

        # 11. StatementExplorer 注释边属性
        if self._enable_annotators:
            self._annotate_edges_from_statements()

        # 12. ClassExplorer 补充 method 边
        if self._enable_annotators:
            self._add_method_edges()

    def _add_nodes_from_slang(self, nl) -> None:
        """从 slang-netlist 遍历设计，添加所有信号节点（Named Nodes: Port + State）"""
        sl_graph = self._slang_graph
        module_name = self._module_name

        # Named nodes: Port 和 State 可通过 lookup 查询
        # 组合逻辑中间信号（wire/assign）是透明节点，无法 lookup
        for node in sl_graph:
            kind_name = str(node.kind).replace('NodeKind.', '')

            if kind_name not in ('Port', 'State'):
                continue

            # 获取路径
            path = getattr(node, 'path', None) or getattr(node, 'hierarchicalPath', None)
            if not path:
                continue

            # Port 节点有 direction，可以判断是否为 clock
            name = getattr(node, 'name', '') or path.rsplit('.', 1)[-1]
            is_port = kind_name == 'Port'

            # 自动标记 clk/rst 信号
            tags = set()
            if is_port:
                direction = getattr(node, 'direction', None)
                if direction:
                    if 'In' in direction.name or direction.name == 'In':
                        if 'clk' in name.lower() or 'clock' in name.lower():
                            tags.add('clock')
                        elif 'rst' in name.lower() or 'reset' in name.lower():
                            tags.add('reset')
                    if 'Out' in direction.name or direction.name == 'Out':
                        tags.add('output')
                    else:
                        tags.add('input')

            # 添加节点
            self.graph.add_node(path,
                name=name,
                module=path.rsplit('.', 1)[0] if '.' in path else module_name,
                bit_width=bit_width_from_bounds(getattr(node, 'bounds', None)),
                tags=tags,
                node_kind=kind_name,
                meta={})

    def _add_instances_from_comp(self) -> None:
        """
        从 compilation 的 Instance hierarchy 中添加 Instance 节点。

        slang-netlist 只提供 Port/State/Assignment 等信号节点，
        不包含 Instance（模块实例）节点。需要从 pyslang Compilation 中提取。

        处理的 SymbolKind：
        - Instance: 已实例化并 elaborator 的模块
        - UninstantiatedDef: 引用但未 elaborator 的模块定义（如 bs_mult_slice I0）

        节点属性：
        - kind: 'Instance'
        - tags: {'instance'} 或 {'instance', 'uninstantiated'}
        - definition: 模块定义名
        """
        if not self._comp:
            return

        root = self._comp.getRoot()
        visited = set()

        def add_instance(path, name, definition, is_instantiated, parameters=None) -> None:
            """添加一个 Instance 节点"""
            if path in visited:
                return
            visited.add(path)

            tags = {'instance'}
            if not is_instantiated:
                tags.add('uninstantiated')

            self.graph.add_node(path,
                name=name,
                module=path.rsplit('.', 1)[0] if '.' in path else path,
                bit_width=(0, 0),
                tags=tags,
                node_kind='Instance',
                definition=definition,
                parameters=parameters or {},
                meta={})

        def traverse_scope(scope, prefix='') -> None:
            """递归遍历 scope 中的所有 Instance / UninstantiatedDef"""
            for sym in scope:
                kind_str = str(sym.kind)

                if kind_str == 'SymbolKind.Instance':
                    inst = sym
                    inst_name = getattr(inst, 'name', '')
                    path = f'{prefix}.{inst_name}' if prefix else inst_name

                    defn_name = ''
                    if hasattr(inst, 'body') and hasattr(inst.body, 'definition'):
                        defn_name = getattr(inst.body.definition, 'name', '')

                    # 提取参数值
                    params = {}
                    if hasattr(inst, 'body') and hasattr(inst.body, 'parameters'):
                        for p in inst.body.parameters:
                            p_name = getattr(p, 'name', '')
                            p_value = str(getattr(p, 'value', ''))
                            params[p_name] = p_value

                    add_instance(path, inst_name, defn_name, is_instantiated=True, parameters=params)

                    # 递归遍历 body 中的子 instances
                    if hasattr(inst, 'body'):
                        traverse_scope(inst.body, path)

                elif kind_str == 'SymbolKind.UninstantiatedDef':
                    # 未实例化的定义（如 bs_mult_slice I0）
                    def_name = getattr(sym, 'name', '')
                    path = f'{prefix}.{def_name}' if prefix else def_name

                    # 获取引用的定义名
                    defn_name = ''
                    if hasattr(sym, 'definition'):
                        defn_name = getattr(sym.definition, 'name', '')

                    add_instance(path, def_name, defn_name, is_instantiated=False)

        traverse_scope(root)

    def _add_edges_from_slang_get_drivers(self) -> None:
        """
        从 slang graph.get_drivers() 添加边（拓扑权威）。
        
        graph.get_drivers(name, lower, upper) 返回直接驱动该信号的节点列表。
        如果 driver 是 Assignment 节点（没有 path），追踪其 fan_in 链找到 Named Nodes。
        """
        sl_graph = self._slang_graph
        module_name = self._module_name

        for node_id in list(self.graph.nodes()):
            bounds = self.graph.nodes[node_id].get('bit_width', (0, 0))

            # 使用 get_drivers() 查找驱动节点
            drivers = sl_graph.get_drivers(node_id, bounds[0], bounds[1])


            for drv in drivers:
                drv_path = self._resolve_driver_path(drv)
                if not drv_path:
                    continue

                # 跳过 self-loop
                if drv_path == node_id:
                    continue

                # 确保驱动节点存在
                if drv_path not in self.graph.nodes():
                    self.graph.add_node(drv_path,
                        name=drv_path.rsplit('.', 1)[-1],
                        module=drv_path.rsplit('.', 1)[0] if '.' in drv_path else module_name,
                        bit_width=(0, 0),
                        tags=set(),
                        node_kind=str(getattr(drv, 'kind', 'Unknown')).replace('NodeKind.', ''),
                        meta={})

                # 添加边
                if not self.graph.has_edge(drv_path, node_id):
                    self.graph.add_edge(drv_path, node_id,
                        relation='drives',
                        timing='unknown',
                        qualifier=None,
                        bounds=bounds,
                        source_location=None,
                        source='slang_get_drivers',
                        is_partial=False,
                        confidence='high',
                        meta={})

    def _resolve_driver_path(self, drv) -> Optional[str]:
        """
        从 driver 节点解析路径。
        
        如果 driver 是 Named Node（Port/State），直接返回 path。
        如果 driver 是 Assignment 节点，追踪 fan_in 链找到 Named Nodes。
        """
        # 直接有 path 的节点
        path = getattr(drv, 'path', None) or getattr(drv, 'hierarchicalPath', None)
        if path:
            return path

        # Assignment 节点：追踪 fan_in 链
        if str(getattr(drv, 'kind', '')) == 'NodeKind.Assignment':
            named_sources = self._trace_assignment_fan_in(drv)
            # 返回第一个 Named Node
            return named_sources[0] if named_sources else None

        return None

    def _trace_assignment_fan_in(self, assign_node, max_depth=10) -> List[str]:
        """
        追踪 Assignment 节点的 fan_in 链，找到所有 Named Nodes。
        
        当 Assignment 节点驱动一个信号时，它的 fan_in 包含其他 Assignment 或 Named Nodes。
        递归追踪直到找到 Port 或 State 节点。
        """
        sl_graph = self._slang_graph
        visited = set()
        result = []
        stack = [assign_node]

        while stack and len(visited) < max_depth:
            node = stack.pop()
            node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)

            # 获取 fan_in
            fan_in = list(sl_graph.get_comb_fan_in(node))

            for n in fan_in:
                # 检查是否是 Named Node
                n_path = getattr(n, 'path', None)
                if n_path and n_path != getattr(assign_node, 'path', None):
                    result.append(n_path)
                    continue

                # 如果是 Assignment，继续追踪
                if str(getattr(n, 'kind', '')) == 'NodeKind.Assignment':
                    if id(n) not in visited:
                        stack.append(n)

        return result

    def _add_edges_from_pathfinder(self) -> None:
        """
        使用 PathFinder 补充 get_drivers() 遗漏的边。
        
        原理：对每对 Input Port -> Output Port，使用 PathFinder.find() 查找路径。
        如果路径非空，说明该 Input Port 驱动该 Output Port。
        
        适用场景：
        - 一个信号在多个 always block 中赋值（导致 get_drivers 链断裂）
        - 复杂的数据流需要 PathFinder 才能正确追踪
        """
        sl_graph = self._slang_graph
        finder = _get_slang_modules()[1].PathFinder()
        module_name = self._module_name

        # 获取所有端口
        port_nodes = [n for n in sl_graph if str(n.kind) == 'NodeKind.Port']
        output_ports = [n for n in port_nodes if n.direction.name == 'Out']
        input_ports = [n for n in port_nodes if n.direction.name == 'In']

        # 对每个 Output Port，查找所有 Input Port 到它的路径
        for out_node in output_ports:
            dst_path = f'{module_name}.{out_node.name}'
            if dst_path not in self.graph.nodes():
                continue

            for in_node in input_ports:
                src_path = f'{module_name}.{in_node.name}'
                if src_path not in self.graph.nodes():
                    continue

                # 跳过 self-loop
                if src_path == dst_path:
                    continue

                # 跳过已存在的边
                if self.graph.has_edge(src_path, dst_path):
                    continue

                # 使用 PathFinder 查找路径
                path = finder.find(in_node, out_node)
                if path.empty():
                    continue

                # 添加边
                self.graph.add_edge(src_path, dst_path,
                    relation='drives',
                    timing='unknown',
                    qualifier=None,
                    bounds=None,
                    source_location=None,
                    source='pathfinder',
                    is_partial=False,
                    confidence='high',
                    meta={})

    def _annotate_edges_from_statements(self) -> None:
        """StatementExplorer 补充边属性"""
        from .statement_explorer import StatementExplorer

        explorer = StatementExplorer(self._comp, self._mgr)
        explorer.annotate(self)

    def _add_method_edges(self) -> None:
        """ClassExplorer 补充 class method 调用边"""
        from .class_explorer import ClassExplorer

        explorer = ClassExplorer()
        explorer.merge_method_edges(self)

    # ---- 最小公开接口（铁律14：禁止暴露内部 DiGraph）----

    def nodes(self) -> List[str]:
        """返回所有节点 ID"""
        return list(self.graph.nodes())

    def edges(self) -> List[Tuple[str, str]]:
        """返回所有边的 (src, dst) 元组"""
        return list(self.graph.edges())

    def predecessors(self, node_id: str) -> List[str]:
        """返回驱动这个节点的所有源节点"""
        return list(self.graph.predecessors(node_id))

    def successors(self, node_id: str) -> List[str]:
        """返回这个节点驱动的所有目标节点"""
        return list(self.graph.successors(node_id))

    def edge_attr(self, src: str, dst: str) -> dict:
        """返回边的属性字典"""
        try:
            return dict(self.graph.edges[src, dst])
        except KeyError:
            return {}

    def node_attr(self, node_id: str) -> dict:
        """返回节点的属性字典"""
        try:
            return dict(self.graph.nodes[node_id])
        except KeyError:
            return {}

    def subgraph(self, node_ids: List[str]) -> nx.DiGraph:
        """返回指定节点的子图（内部用于算法）"""
        return self.graph.subgraph(node_ids)

    def has_node(self, node_id: str) -> bool:
        """检查节点是否存在"""
        return self.graph.has_node(node_id)

    def has_edge(self, src: str, dst: str) -> bool:
        """检查边是否存在"""
        return self.graph.has_edge(src, dst)

    def get_node_kind(self, node_id: str) -> Optional[str]:
        """返回节点的种类（Port/State/Variable）"""
        try:
            return self.graph.nodes[node_id].get('node_kind')
        except KeyError:
            return None

    def find_nodes(self, pattern: str) -> List[str]:
        """
        通配符搜索节点。
        
        Args:
            pattern: 通配符模式，如 "module.*" 或 "*.clk"
            
        Returns:
            匹配的节点 ID 列表
        """
        import fnmatch
        return [n for n in self.graph.nodes() if fnmatch.fnmatch(n, pattern)]

    def find_nodes_regex(self, pattern: str) -> List[str]:
        """
        正则表达式搜索节点。
        
        Args:
            pattern: 正则表达式，如 r"top\.s[0-9]+_.*"
            
        Returns:
            匹配的节点 ID 列表
        """
        import re
        return [n for n in self.graph.nodes() if re.match(pattern, n)]

    def __repr__(self) -> str:
        return f"DesignGraph({len(self.graph.nodes())} nodes, {len(self.graph.edges())} edges)"