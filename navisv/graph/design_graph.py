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
        使用 slang-netlist NetlistGraph BFS 遍历添加边。
        
        原理：通过 get_comb_fan_in() BFS 追踪每个信号的驱动源，
        直到遇到 Input Port 为止（Input Port 是外部驱动，停止追踪）。
        
        优点：绕过 getDrivers() self-loop 问题，能找到真实驱动关系。
        """
        sl_graph = self._slang_graph
        root = self._comp.getRoot()
        inst = list(root)[1]
        module_name = inst.name  # e.g. 'serv_alu'
        
        def get_ultimate_drivers(signal_name: str) -> list:
            """BFS 找到 signal_name 的终极 Input Port 驱动源"""
            start_nodes = sl_graph.find_nodes(f'{module_name}.{signal_name}')
            if not start_nodes:
                return []
            
            visited_ids = set()
            queue = [(start_nodes[0], 0)]
            ultimate_drivers = []
            
            while queue:
                node, depth = queue.pop(0)
                node_id = id(node)
                if node_id in visited_ids:
                    continue
                visited_ids.add(node_id)
                
                kn = str(node.kind)
                nm = node.name if hasattr(node, 'name') else None
                if nm == signal_name:
                    # 跳过自己，但继续追踪其 fan_in
                    if depth < 10:
                        try:
                            for item in sl_graph.get_comb_fan_in(node):
                                queue.append((item, depth + 1))
                        except:
                            pass
                    continue
                
                # Input Port 是终极驱动源
                if kn == 'NodeKind.Port':
                    try:
                        if node.direction.name == 'In':
                            ultimate_drivers.append(nm)
                    except:
                        pass
                    continue  # Stop tracing from ports
                
                # State (时序元素) - 继续追踪
                if kn == 'NodeKind.State':
                    if depth < 10:
                        try:
                            for item in sl_graph.get_comb_fan_in(node):
                                queue.append((item, depth + 1))
                        except:
                            pass
                    continue
                
                # Max depth protection
                if depth >= 10:
                    continue
                
                # 尝试遍历 fan_in
                try:
                    for item in sl_graph.get_comb_fan_in(node):
                        queue.append((item, depth + 1))
                except:
                    pass
            
            return list(set(ultimate_drivers))
        
        # 对 body 中每个信号调用 BFS 建边
        body = inst.body
        for sym in body:
            kn = getattr(sym, 'kind', None)
            kn = kn.name if hasattr(kn, 'name') else str(kn) if kn else ''
            if kn not in ('Variable', 'Port', 'State', 'Net'):
                continue
            
            signal_name = getattr(sym, 'name', None)
            if not signal_name:
                continue
            
            signal_path = sym.hierarchicalPath
            drivers = get_ultimate_drivers(signal_name)
            
            for driver in drivers:
                driver_path = f'{module_name}.{driver}'
                if driver_path == signal_path:
                    continue
                
                # 确保 driver 节点存在
                if driver_path not in self.graph.nodes():
                    self.graph.add_node(driver_path,
                        name=driver,
                        module=module_name,
                        bit_width=(0, 0),
                        tags=set(),
                        meta={})
                
                # 添加边（source='netlist_graph' 标记来源）
                if not self.graph.has_edge(driver_path, signal_path):
                    self.graph.add_edge(driver_path, signal_path,
                        relation='drives',
                        timing='unknown',
                        qualifier=None,
                        bounds=None,
                        source_location=None,
                        source='netlist_graph',
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