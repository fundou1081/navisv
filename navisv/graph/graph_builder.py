"""
GraphBuilder - 构建 enriched MultiDiGraph

Layer 2: 组合 Parser 结果 + 分析逻辑
- 添加 Named Nodes (Port + State)
- 添加边（带完整属性）
- 从 AST 提取条件信息
- 推断时序分类
- 计算 bit_mapping
"""

import networkx as nx
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

from navisv.parsers import ASTParser, NetlistParser, NetlistNode, NetlistEdge


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
        }


@dataclass
class EdgeAttr:
    """边属性"""
    relation: str = 'drives'
    
    # 时序
    timing: str = 'unknown'  # combinational, sequential_input, sequential_output
    edge_kind: str = 'None'  # None, PosEdge, NegEdge
    
    # 位精确
    bounds: Tuple[int, int] = (0, 0)
    bit_mapping: Optional[Dict[int, int]] = None
    
    # 条件
    condition: str = ''
    condition_path: str = ''
    
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
            'condition_path': self.condition_path,
            'location': self.location,
            'path_count': self.path_count,
        }


class GraphBuilder:
    """
    Layer 2: 构建 enriched MultiDiGraph
    
    组合 ASTParser + NetlistParser 的结果，
    推断时序分类，提取条件信息。
    """
    
    def __init__(self, ast_parser: ASTParser, netlist_parser: NetlistParser):
        self.ast = ast_parser
        self.netlist = netlist_parser
        self.graph: nx.MultiDiGraph = None
        
        # 缓存
        self._node_attrs: Dict[str, NodeAttr] = {}
        self._edge_attrs: Dict[Tuple[int, int, str], EdgeAttr] = {}  # (src, dst, key)
    
    def build(self) -> nx.MultiDiGraph:
        """构建完整的 MultiDiGraph"""
        self.graph = nx.MultiDiGraph()
        
        # 1. 添加 Named Nodes (Port + State)
        self._add_named_nodes()
        
        # 2. 从 Netlist 添加边
        self._add_edges()
        
        # 3. 从 AST 提取条件信息
        self._enrich_edges_with_conditions()
        
        # 4. 推断时序分类
        self._classify_timing()
        
        # 5. 计算 bit_mapping
        self._calculate_bit_mapping()
        
        return self.graph
    
    def _add_named_nodes(self):
        """添加 Named Nodes (Port + State)
        
        注意：同一个路径可能同时有 Port 和 State 表示（如 register 输出）。
        State 节点的语义更丰富，应该优先添加。
        """
        # 先添加 State 节点（更高优先级）
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
        
        # 再添加 Port 节点（如果不存在同名节点）
        for port in self.netlist.get_ports():
            # 跳过已经是 State 的节点
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
    
    def _add_node(self, path: str, attr: NodeAttr):
        """添加节点到图中"""
        if path in self.graph:
            return
        
        self.graph.add_node(path, **attr.to_dict())
        self._node_attrs[path] = attr
    
    def _add_edges(self):
        """从 Netlist 添加边"""
        for edge in self.netlist.edges:
            src_node = self.netlist.get_node_by_id(edge.source)
            tgt_node = self.netlist.get_node_by_id(edge.target)
            
            if not src_node or not tgt_node:
                continue
            
            # 只添加 named → named 边
            if not src_node.path or not tgt_node.path:
                continue
            
            # 跳过 self-loop（寄存器反馈边）
            if src_node.path == tgt_node.path:
                continue
            
            # 获取或创建边属性
            attr = EdgeAttr(
                edge_kind=edge.edge_kind,
                bounds=edge.bounds,
                location=edge.symbol.get('location') if edge.symbol else None,
            )
            
            # 添加边（MultiDiGraph 支持多边）
            key = self.graph.add_edge(
                src_node.path, 
                tgt_node.path,
                **attr.to_dict()
            )
            
            # 记录边属性（用于后续丰富）
            self._edge_attrs[(src_node.path, tgt_node.path, key)] = attr
    
    def _extract_module(self, path: str) -> str:
        """从路径提取模块名"""
        parts = path.rsplit('.', 1)
        return parts[0] if len(parts) > 1 else 'top'
    
    def _enrich_edges_with_conditions(self):
        """
        从 AST 提取条件信息，丰富边属性
        
        遍历 AST 中的 if/case/always 块，
        找到对应的边并添加 condition 信息。
        """
        # 查找所有条件语句
        for node in self.ast._traverse(self.ast.root):
            if node.kind == 'IfStatement':
                self._process_if_statement(node)
            elif node.kind == 'CaseStatement':
                self._process_case_statement(node)
            elif node.kind == 'ProceduralBlock':
                self._process_procedural_block(node)
    
    def _process_if_statement(self, if_node):
        """处理 if 语句"""
        # 提取条件表达式
        condition_expr = self._extract_condition(if_node.attributes.get('condition'))
        
        # 处理 true branch 和 false branch
        for branch_name, branch in [('true', if_node.attributes.get('true_branch')),
                                   ('false', if_node.attributes.get('false_branch'))]:
            if branch:
                self._apply_condition_to_branch(condition_expr, branch, branch_name)
    
    def _process_case_statement(self, case_node):
        """处理 case 语句"""
        # 提取 case 表达式
        case_expr = self._extract_condition(case_node.attributes.get('condition'))
        
        # 处理每个 case item
        for item in case_node.attributes.get('items', []):
            item_expr = self._extract_condition(item.get('condition'))
            full_condition = f"{case_expr} == {item_expr}" if item_expr else case_expr
            
            if item.get('body'):
                self._apply_condition_to_branch(full_condition, item['body'], 'case')
    
    def _process_procedural_block(self, block_node):
        """处理过程块 (always_ff, always_comb 等)"""
        # 遍历块内的赋值语句
        for stmt in block_node.children:
            if stmt.kind == 'Assignment':
                self._process_assignment(stmt)
    
    def _extract_condition(self, condition_obj) -> str:
        """从条件对象提取条件字符串"""
        if not condition_obj:
            return ''
        
        # 简化处理：直接返回 kind 作为占位符
        # 完整实现需要遍历条件树
        if isinstance(condition_obj, dict):
            return condition_obj.get('kind', '')
        return str(condition_obj)
    
    def _apply_condition_to_branch(self, condition: str, body, branch_type: str):
        """应用条件到分支"""
        # 简化：只在有明确赋值目标时添加条件
        pass
    
    def _process_assignment(self, assign_node):
        """处理赋值语句"""
        # 简化：边已经通过 Netlist 添加
        pass
    
    def _classify_timing(self):
        """
        推断时序分类
        
        规则:
        - combinational: 所有 fan_in 边的 edge_kind 都是 None
        - sequential_input: 有 PosEdge/NegEdge 边指向 State
        - sequential_output: State 节点的输出
        """
        for node_id in self.graph.nodes():
            node_attr = self._node_attrs.get(node_id)
            if not node_attr:
                continue
            
            # 获取所有入边
            in_edges = list(self.graph.in_edges(node_id, data=True))
            
            if not in_edges:
                continue
            
            # 检查是否有时钟边
            has_clock = any(d.get('edge_kind') in ('PosEdge', 'NegEdge') 
                          for _, _, d in in_edges)
            
            if node_attr.kind == 'State':
                # State 节点是 sequential
                node_attr.timing = 'sequential'
            elif has_clock:
                # 有时钟边的是 sequential_input
                node_attr.timing = 'sequential_input'
            else:
                # 纯组合逻辑
                node_attr.timing = 'combinational'
            
            # 更新图中的属性
            self.graph.nodes[node_id]['timing'] = node_attr.timing
        
        # 更新边属性
        for src, dst, data in self.graph.edges(data=True):
            edge_key = self.graph[src][dst]
            # 时序逻辑输出给后续节点提供时钟
            src_timing = self._node_attrs.get(src, NodeAttr('', '', '')).timing
            if src_timing == 'sequential':
                data['timing'] = 'combinational'  # 寄存器输出是组合延迟
            elif data.get('edge_kind') in ('PosEdge', 'NegEdge'):
                data['timing'] = 'sequential_input'
            else:
                data['timing'] = 'combinational'
    
    def _calculate_bit_mapping(self):
        """
        计算 bit_mapping
        
        规则:
        - 如果 bounds 相同，bit 是一一对应
        - 如果不同，需要分析位选择操作
        """
        for src, dst, data in self.graph.edges(data=True):
            bounds = data.get('bounds', (0, 0))
            bit_mapping = {i: i for i in range(bounds[0], bounds[1] + 1)}
            data['bit_mapping'] = bit_mapping
    
    def summary(self) -> Dict[str, Any]:
        """返回摘要"""
        if not self.graph:
            return {}
        
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
    
    # 测试
    ast = ASTParser('/tmp/navisv_slang/ast.json').parse()
    netlist = NetlistParser('/tmp/navisv_netlist/netlist.json').parse()
    
    builder = GraphBuilder(ast, netlist)
    graph = builder.build()
    
    print("=== GraphBuilder 测试 ===")
    print(f"Summary: {builder.summary()}")
    print(f"\nNodes: {graph.number_of_nodes()}")
    print(f"Edges: {graph.number_of_edges()}")
    print("\nEdges with attributes:")
    for u, v, d in list(graph.edges(data=True))[:5]:
        print(f"  {u} -> {v}: timing={d.get('timing')}, edge_kind={d.get('edge_kind')}")