# graph/design_graph.py - 核心图存储
# navisv 架构 v0.8 - Graph Layer

"""
DesignGraph: 持有 networkx DiGraph，是 navisv 的唯一数据存储。

铁律约束：
- [铁律2] networkx DiGraph 是唯一查询接口，不维护自定义索引字典
- [铁律3] slang 是拓扑权威，Python 只做属性补充
- [铁律14] DesignGraph 禁止暴露内部 DiGraph

构建流程：
1. 从 slang-netlist 添加节点
2. 调用 slang AnalysisManager.getDrivers() 创建所有边
3. StatementExplorer 补充边属性（不创建新边）
4. ClassExplorer 补充 class 内 method 调用边（唯一在 Python 创建边的场景）
"""

from typing import List, Tuple, Optional, Any, Iterator

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
    import pyslang_netlist as nl
    from pyslang import driver as sl_driver
    return nl, sl_driver


class DesignGraph:
    """
    持有 networkx DiGraph，是 navisv 的唯一数据存储。
    
    构建流程：
    1. 从 slang-netlist 添加节点（SignalNode 属性）
    2. 调用 slang AnalysisManager.getDrivers() 创建所有边（source="slang"）
    3. StatementExplorer 补充边属性（不创建新边）
    4. ClassExplorer 补充 class 内 method 调用边
    """

    def __init__(self, sv_files: List[str], enable_annotators: bool = True):
        # 铁律2：self.graph 是唯一存储，不维护额外的自定义索引
        self.graph = nx.DiGraph()
        self._sv_files = sv_files
        self._enable_annotators = enable_annotators
        self._comp = None
        self._mgr = None
        self._slang_graph = None  # slang NetlistGraph
        self._build()

    def _build(self) -> None:
        """主构建流程"""
        nl, sl_driver = _get_slang_modules()

        # 1. 从 slang-netlist 添加节点
        self._add_nodes_from_slang(nl, sl_driver)

        # 2. slang getDrivers() 创建边（拓扑权威）
        self._add_edges_from_slang(nl)

        # 3. StatementExplorer 注释边属性
        self._annotate_edges_from_statements()

        # 4. ClassExplorer 补充 method 边
        self._add_method_edges()

    def _add_nodes_from_slang(self, nl, sl_driver) -> None:
        """从 slang-netlist 遍历设计，添加所有信号节点"""
        d = sl_driver.Driver()
        d.addStandardArgs()
        for f in self._sv_files:
            d.sourceLoader.addFiles(f)
        ok = d.parseAllSources()
        if not ok:
            raise RuntimeError(f"Failed to parse: {self._sv_files}")

        self._comp = d.createCompilation()
        self._mgr = d.runAnalysis(self._comp)
        self._slang_graph = nl.NetlistGraph()
        self._slang_graph.build(self._comp, self._mgr)

        root = self._comp.getRoot()
        inst = list(root)[1]
        body = inst.body

        # InstanceBodySymbol 有 __iter__，过滤信号类型
        for sym in body:
            kind_name = getattr(sym, 'kind', None)
            kind_name = kind_name.name if hasattr(kind_name, 'name') else str(kind_name) if kind_name else ''
            if kind_name not in ('Variable', 'Port', 'State', 'Net'):
                continue
            path = sym.hierarchicalPath
            self.graph.add_node(path,
                name=getattr(sym, 'name', '') or '',
                module=path.rsplit('.', 1)[0] if '.' in path else '',
                bit_width=(0, 0),
                tags=set(),
                meta={})

    def _add_edges_from_slang(self, nl) -> None:
        """从 slang AnalysisManager.getDrivers() 添加边（拓扑权威）"""
        root = self._comp.getRoot()
        inst = list(root)[1]
        body = inst.body

        for node_id in list(self.graph.nodes()):
            sym = body.find(node_id.rsplit('.', 1)[-1] if '.' in node_id else node_id)
            if not sym:
                continue
            drivers = list(self._mgr.getDrivers(sym))
            for drv in drivers:
                # driver 的 path.rootSymbol 包含源信号的完整路径
                src_path = drv.path.rootSymbol.hierarchicalPath if hasattr(drv, 'path') and drv.path else None
                if not src_path:
                    continue
                # self-loop 表示该信号有 slang driver 信息（即使是 self-loop）
                # 但查询时通常不需要 self-loop，所以仍跳过它
                if src_path == node_id:
                    continue
                # 确保 src 节点存在
                if src_path not in self.graph.nodes():
                    # 添加未在节点列表中的隐式节点
                    self.graph.add_node(src_path,
                        name=src_path.rsplit('.', 1)[-1],
                        module=src_path.rsplit('.', 1)[0],
                        bit_width=(0, 0),
                        tags=set(),
                        meta={})
                self.graph.add_edge(src_path, node_id,
                    relation='drives',
                    timing='unknown',
                    qualifier=None,
                    bounds=bit_width_from_bounds(drv.bounds) if hasattr(drv, 'bounds') else None,
                    source_location=None,
                    source='slang',
                    is_partial=False,
                    confidence='high',
                    meta={})

        # Fallback: 如果 getDrivers() 没有产生任何边，使用 NetlistGraph BFS
        if self.graph.number_of_edges() == 0:
            self._add_edges_from_netlist_graph_bfs(nl)

    def _add_edges_from_netlist_graph_bfs(self, nl) -> None:
        """
        使用 PathFinder 查找所有输入->输出路径。
        
        原理：对每个 Output Port，使用 PathFinder.find() 查找所有 Input Port 到它的路径。
        如果路径非空，说明该 Input Port 驱动该 Output Port。
        
        优点：
        - 比手动 BFS 更准确，能正确追踪通过 State 节点的路径
        - 使用 slang-netlist 图算法，自动处理中间节点
        - 比 BFS 找到更多边（如 i_en -> o_rd 而非只在 i_en -> cmp_r 停止）
        """
        sl_graph = self._slang_graph
        finder = nl.PathFinder()
        
        root = self._comp.getRoot()
        inst = list(root)[1]
        module_name = inst.name  # e.g. 'serv_alu'
        
        # 获取所有端口
        port_nodes = [n for n in sl_graph if str(n.kind) == 'NodeKind.Port']
        output_ports = [n for n in port_nodes if n.direction.name == 'Out']
        input_ports = [n for n in port_nodes if n.direction.name == 'In']
        
        # 对每个 Output Port，查找所有 Input Port 到它的路径
        for out_node in output_ports:
            for in_node in input_ports:
                path = finder.find(in_node, out_node)
                if path.empty():
                    continue
                
                src_path = f'{module_name}.{in_node.name}'
                dst_path = f'{module_name}.{out_node.name}'
                
                if src_path == dst_path:
                    continue
                
                # 确保节点存在
                if src_path not in self.graph.nodes():
                    self.graph.add_node(src_path,
                        name=in_node.name,
                        module=module_name,
                        bit_width=(0, 0),
                        tags=set(),
                        meta={})
                if dst_path not in self.graph.nodes():
                    self.graph.add_node(dst_path,
                        name=out_node.name,
                        module=module_name,
                        bit_width=(0, 0),
                        tags=set(),
                        meta={})
                
                # 添加边
                if not self.graph.has_edge(src_path, dst_path):
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

    def __repr__(self) -> str:
        return f"DesignGraph({len(self.graph.nodes())} nodes, {len(self.graph.edges())} edges)"