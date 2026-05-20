"""
DesignGraph - 最终用户接口

Layer 3: 封装 MultiDiGraph，提供查询接口
"""

import networkx as nx
from typing import List, Dict, Any, Optional, Set, Tuple


class DesignGraph:
    """
    Layer 3: 最终用户接口
    
    封装 MultiDiGraph，提供语义查询接口。
    """
    
    def __init__(self, graph: nx.MultiDiGraph, signal_conditions: Optional[Dict[str, List[Dict]]] = None):
        """
        Args:
            graph: 由 GraphBuilder 构建的 MultiDiGraph
            signal_conditions: {signal_path: [{condition, kind, source, location}]}
        """
        self.graph = graph
        self._signal_conditions = signal_conditions or {}
    
    def __repr__(self) -> str:
        return f"DesignGraph(nodes={self.graph.number_of_nodes()}, edges={self.graph.number_of_edges()})"
    
    # ============================================
    # 基本查询
    # ============================================
    
    def nodes(self) -> List[str]:
        """返回所有节点路径"""
        return list(self.graph.nodes())
    
    def edges(self) -> List[Tuple[str, str]]:
        """返回所有边（去重）"""
        return list(self.graph.edges())
    
    def node_attr(self, path: str) -> Dict[str, Any]:
        """获取节点属性"""
        return dict(self.graph.nodes[path])
    
    def edge_attr(self, src: str, dst: str, key: Optional[int] = None) -> Dict[str, Any]:
        """获取边属性"""
        if key is not None:
            return dict(self.graph.edges[src, dst, key])
        return dict(self.graph.edges[src, dst])
    
    def has_node(self, path: str) -> bool:
        """检查节点是否存在"""
        return self.graph.has_node(path)
    
    def has_edge(self, src: str, dst: str) -> bool:
        """检查边是否存在"""
        return self.graph.has_edge(src, dst)
    
    # ============================================
    # 驱动/负载查询
    # ============================================
    
    def get_drivers(self, signal: str) -> List[str]:
        """
        获取驱动该信号的源节点列表
        
        Args:
            signal: 信号路径 (如 'top.cpu.alu.result')
        
        Returns:
            驱动该信号的源节点列表
        """
        if not self.graph.has_node(signal):
            return []
        
        drivers = []
        for src, dst, data in self.graph.in_edges(signal, data=True):
            drivers.append(src)
        
        return drivers
    
    def get_loads(self, signal: str) -> List[str]:
        """
        获取该信号驱动的负载节点列表
        
        Args:
            signal: 信号路径
        
        Returns:
            被该信号驱动的节点列表
        """
        if not self.graph.has_node(signal):
            return []
        
        loads = []
        for src, dst, data in self.graph.out_edges(signal, data=True):
            loads.append(dst)
        
        return loads
    
    # ============================================
    # Fan-in / Fan-out 锥
    # ============================================
    
    def get_fanin_cone(self, signal: str, depth: int = 5, timing: Optional[str] = None) -> Set[str]:
        """
        获取 fan-in 锥（该信号的所有祖先）
        
        Args:
            signal: 起始信号
            depth: 最大深度
            timing: 过滤时序类型 ('combinational', 'sequential')
        
        Returns:
            fan-in 锥中的所有节点集合
        """
        if not self.graph.has_node(signal):
            return set()
        
        cone = set()
        queue = [(signal, 0)]
        visited = {signal}
        
        while queue:
            node, d = queue.pop(0)
            if d >= depth:
                continue
            
            for src, _, data in self.graph.in_edges(node, data=True):
                if src in visited:
                    continue
                
                # 时序过滤
                if timing and data.get('timing') != timing:
                    continue
                
                cone.add(src)
                visited.add(src)
                queue.append((src, d + 1))
        
        return cone
    
    def get_fanout_cone(self, signal: str, depth: int = 5, timing: Optional[str] = None) -> Set[str]:
        """
        获取 fan-out 锥（该信号驱动的所有节点）
        
        Args:
            signal: 起始信号
            depth: 最大深度
            timing: 过滤时序类型
        
        Returns:
            fan-out 锥中的所有节点集合
        """
        if not self.graph.has_node(signal):
            return set()
        
        cone = set()
        queue = [(signal, 0)]
        visited = {signal}
        
        while queue:
            node, d = queue.pop(0)
            if d >= depth:
                continue
            
            for _, dst, data in self.graph.out_edges(node, data=True):
                if dst in visited:
                    continue
                
                if timing and data.get('timing') != timing:
                    continue
                
                cone.add(dst)
                visited.add(dst)
                queue.append((dst, d + 1))
        
        return cone
    
    # ============================================
    # 寄存器查询
    # ============================================
    
    def get_registers(self) -> List[str]:
        """获取所有寄存器（State 节点）"""
        return [n for n in self.graph.nodes() 
                if self.graph.nodes[n].get('kind') == 'State']
    
    def get_input_ports(self) -> List[str]:
        """获取所有输入端口"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == 'Port' 
                and self.graph.nodes[n].get('direction') == 'In']
    
    def get_output_ports(self) -> List[str]:
        """获取所有输出端口"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == 'Port'
                and self.graph.nodes[n].get('direction') == 'Out']
    
    # ============================================
    # 查找
    # ============================================
    
    def find_nodes(self, pattern: str) -> List[str]:
        """
        通配符查找节点
        
        Args:
            pattern: 通配符模式 (*, ?)
        
        Returns:
            匹配的节点列表
        """
        import fnmatch
        return [n for n in self.graph.nodes() if fnmatch.fnmatch(n, pattern)]
    
    def find_by_kind(self, kind: str) -> List[str]:
        """按 kind 查找节点"""
        return [n for n in self.graph.nodes()
                if self.graph.nodes[n].get('kind') == kind]
    
    # ============================================
    # 路径查询
    # ============================================
    
    def get_path(self, src: str, dst: str) -> List[str]:
        """
        查找两点间的路径
        
        Args:
            src: 起始节点
            dst: 目标节点
        
        Returns:
            路径节点列表，如果不存在则返回空列表
        """
        if not self.graph.has_node(src) or not self.graph.has_node(dst):
            return []
        
        try:
            return nx.shortest_path(self.graph, src, dst)
        except nx.NetworkXNoPath:
            return []
    
    # ============================================
    # 条件查询 (Option B)
    # ============================================
    
    def get_condition_pairs(self, signal: str) -> List[Dict[str, Any]]:
        """
        获取信号的"条件-语句"一一对应关系
        
        Args:
            signal: 信号路径 (如 'top.alu_inst.result')
        
        Returns:
            [
                {
                    'condition': 'op_sel == 3'b0',
                    'statement': 'result = a + b',
                    'kind': 'case',
                    'location': {'file': 'design.sv', 'line': 12, 'column': 19}
                },
                ...
            ]
        """
        if signal not in self._signal_conditions:
            return []
        
        results = []
        for cond_info in self._signal_conditions[signal]:
            loc = cond_info.get('location', {})
            # 清理文件路径（取文件名部分）
            file_name = loc.get('file', 'unknown')
            if '/' in file_name:
                file_name = file_name.split('/')[-1]
            
            line = loc.get('line', 0)
            column = loc.get('column', 0)
            
            # 优先使用从源码提取的 statement，否则用 location
            statement = cond_info.get('statement') or f"{file_name}:{line}:{column}"
            
            results.append({
                'condition': cond_info['condition'],
                'statement': statement,
                'kind': cond_info['kind'],
                'location': f"{file_name}:{line}:{column}"
            })
        
        return results
    
    def get_all_conditions(self, signal: str) -> List[Dict[str, Any]]:
        """
        获取信号的所有条件（不带边）
        
        Args:
            signal: 信号路径
        
        Returns:
            [{condition, kind, location, edges}, ...]
        """
        if signal not in self._signal_conditions:
            return []
        
        # 获取该信号的边
        edges = []
        for src, dst, data in self.graph.in_edges(signal, data=True):
            edges.append({
                'from': src,
                'edge_kind': data.get('edge_kind'),
                'timing': data.get('timing'),
            })
        
        results = []
        for cond_info in self._signal_conditions[signal]:
            results.append({
                'condition': cond_info['condition'],
                'kind': cond_info['kind'],
                'location': cond_info.get('location'),
                'edges': edges if edges else None  # None 表示无 named 边
            })
        
        return results
    
    # ============================================
    # 统计
    # ============================================
    
    def summary(self) -> Dict[str, Any]:
        """返回摘要"""
        # 节点统计
        node_kinds = {}
        for n in self.graph.nodes():
            kind = self.graph.nodes[n].get('kind', 'unknown')
            node_kinds[kind] = node_kinds.get(kind, 0) + 1
        
        # 边统计
        edge_kinds = {}
        timing_stats = {}
        for u, v, d in self.graph.edges(data=True):
            ek = d.get('edge_kind', 'None')
            edge_kinds[ek] = edge_kinds.get(ek, 0) + 1
            t = d.get('timing', 'unknown')
            timing_stats[t] = timing_stats.get(t, 0) + 1
        
        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'node_kinds': node_kinds,
            'edge_kinds': edge_kinds,
            'timing_stats': timing_stats,
        }


if __name__ == '__main__':
    from navisv.parsers import ASTParser, NetlistParser
    from navisv.graph.graph_builder import GraphBuilder
    
    # 测试
    ast = ASTParser('/tmp/navisv_slang/ast.json').parse()
    netlist = NetlistParser('/tmp/navisv_netlist/netlist.json').parse()
    
    builder = GraphBuilder(ast, netlist)
    graph = builder.build()
    
    dg = DesignGraph(graph)
    
    print("=== DesignGraph 测试 ===")
    print(dg)
    print(f"\nSummary: {dg.summary()}")
    
    print(f"\nRegisters: {dg.get_registers()}")
    print(f"Input ports: {dg.get_input_ports()}")
    print(f"Output ports: {dg.get_output_ports()}")
    
    print(f"\nDrivers of 'top.cnt_inst.count': {dg.get_drivers('top.cnt_inst.count')}")
    print(f"Fan-in cone of 'top.cnt_inst.count': {dg.get_fanin_cone('top.cnt_inst.count')}")
    print(f"Fan-out cone of 'top.cnt_inst.clk': {dg.get_fanout_cone('top.cnt_inst.clk')}")
    
    print(f"\nFind '*.count': {dg.find_nodes('*.count')}")