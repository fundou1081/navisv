"""
Netlist Parser - 解析 slang-netlist --save-netlist 输出

功能：
- 解析 netlist JSON 构建节点和边
- 提取 Port, State, Assignment, Conditional, Case, Merge, Constant
- 支持边属性（timing, bounds, edgeKind）
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class EdgeKind(Enum):
    """边类型"""
    NONE = "None"
    POS_EDGE = "PosEdge"
    NEG_EDGE = "NegEdge"


class NodeKind(Enum):
    """节点类型"""
    PORT = "Port"
    STATE = "State"
    ASSIGNMENT = "Assignment"
    CONDITIONAL = "Conditional"
    CASE = "Case"
    MERGE = "Merge"
    CONSTANT = "Constant"


@dataclass
class NetlistNode:
    """Netlist 节点"""
    id: int
    name: str
    kind: str
    path: str = ""
    bounds: Tuple[int, int] = (0, 0)
    direction: str = ""  # In, Out for Port
    location: Optional[Dict[str, Any]] = None
    value: Optional[str] = None  # For Constant
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'kind': self.kind,
            'path': self.path,
            'bounds': self.bounds,
            'direction': self.direction,
            'location': self.location,
            'value': self.value,
        }
    
    @property
    def is_port(self) -> bool:
        return self.kind == 'Port'
    
    @property
    def is_state(self) -> bool:
        return self.kind == 'State'
    
    @property
    def is_register(self) -> bool:
        """State 节点是寄存器"""
        return self.kind == 'State'


@dataclass
class NetlistEdge:
    """Netlist 边"""
    source: int
    target: int
    edge_kind: str = "None"
    bounds: Tuple[int, int] = (0, 0)
    disabled: bool = False
    symbol: Optional[Dict[str, Any]] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source,
            'target': self.target,
            'edge_kind': self.edge_kind,
            'bounds': self.bounds,
            'disabled': self.disabled,
            'symbol': self.symbol,
        }
    
    @property
    def is_clock_edge(self) -> bool:
        """是否为时钟边"""
        return self.edge_kind in ('PosEdge', 'NegEdge')
    
    @property
    def is_combinational(self) -> bool:
        """是否为组合逻辑边"""
        return self.edge_kind == 'None'


class NetlistParser:
    """解析 slang-netlist --save-netlist 输出"""
    
    def __init__(self, netlist_json_path: str):
        """
        Args:
            netlist_json_path: slang-netlist 生成的 netlist.json 文件路径
        """
        self.netlist_json_path = netlist_json_path
        self.data: Dict[str, Any] = {}
        self.nodes: List[NetlistNode] = []
        self.edges: List[NetlistEdge] = []
        self.node_map: Dict[int, NetlistNode] = {}  # id -> node
        self.path_map: Dict[str, NetlistNode] = {}  # path -> node (named nodes)
        # (Stage 2.6) 文件表: fileIndex -> 文件路径
        self.file_table: List[str] = []
    
    def parse(self) -> 'NetlistParser':
        """解析 JSON 文件"""
        with open(self.netlist_json_path) as f:
            self.data = json.load(f)

        self.file_table = self.data.get('fileTable', [])

        self._parse_nodes()
        self._parse_edges()
        self._build_maps()
        return self
    
    def _parse_nodes(self):
        """解析节点"""
        nodes_data = self.data.get('nodes', [])
        for n in nodes_data:
            node = NetlistNode(
                id=n.get('id', 0),
                name=n.get('name', ''),
                kind=n.get('kind', 'Unknown'),
                path=n.get('path', ''),
                bounds=tuple(n.get('bounds', [0, 0])),
                direction=n.get('direction', ''),
                location=n.get('location'),
                value=n.get('value'),
                attributes={k: v for k, v in n.items()
                           if k not in ('id', 'name', 'kind', 'path', 'bounds', 'direction', 'location', 'value')}
            )
            self.nodes.append(node)
    
    def _parse_edges(self):
        """解析边"""
        edges_data = self.data.get('edges', [])
        for e in edges_data:
            edge = NetlistEdge(
                source=e.get('source', 0),
                target=e.get('target', 0),
                edge_kind=e.get('edgeKind', 'None'),
                bounds=tuple(e.get('bounds', [0, 0])),
                disabled=e.get('disabled', False),
                symbol=e.get('symbol'),
                attributes={k: v for k, v in e.items()
                           if k not in ('source', 'target', 'edgeKind', 'bounds', 'disabled', 'symbol')}
            )
            self.edges.append(edge)
    
    def _build_maps(self):
        """构建索引"""
        self.node_map = {n.id: n for n in self.nodes}
        self.path_map = {n.path: n for n in self.nodes if n.path}
    
    def get_node_by_id(self, node_id: int) -> Optional[NetlistNode]:
        """通过 ID 获取节点"""
        return self.node_map.get(node_id)
    
    def get_node_by_path(self, path: str) -> Optional[NetlistNode]:
        """通过路径获取节点"""
        return self.path_map.get(path)
    
    def get_ports(self) -> List[NetlistNode]:
        """获取所有端口"""
        return [n for n in self.nodes if n.kind == 'Port']
    
    def get_input_ports(self) -> List[NetlistNode]:
        """获取输入端口"""
        return [n for n in self.nodes if n.kind == 'Port' and n.direction == 'In']
    
    def get_output_ports(self) -> List[NetlistNode]:
        """获取输出端口"""
        return [n for n in self.nodes if n.kind == 'Port' and n.direction == 'Out']
    
    def get_registers(self) -> List[NetlistNode]:
        """获取所有寄存器（State 节点）"""
        return [n for n in self.nodes if n.kind == 'State']
    
    def get_edges_from(self, node_id: int) -> List[NetlistEdge]:
        """获取从指定节点出发的所有边"""
        return [e for e in self.edges if e.source == node_id]
    
    def get_edges_to(self, node_id: int) -> List[NetlistEdge]:
        """获取指向指定节点的所有边"""
        return [e for e in self.edges if e.target == node_id]
    
    def get_clock_edges(self) -> List[NetlistEdge]:
        """获取所有时钟边（寄存器时钟输入）"""
        return [e for e in self.edges if e.is_clock_edge]
    
    def get_combinational_edges(self) -> List[NetlistEdge]:
        """获取所有组合逻辑边"""
        return [e for e in self.edges if e.is_combinational]
    
    def find_nodes(self, pattern: str) -> List[NetlistNode]:
        """
        通配符查找节点 (*, ?)
        例: find_nodes("top.alu.*")
        """
        import fnmatch
        return [n for n in self.nodes if fnmatch.fnmatch(n.path, pattern)]
    
    def summary(self) -> Dict[str, Any]:
        """返回摘要"""
        kind_counts = {}
        for n in self.nodes:
            kind_counts[n.kind] = kind_counts.get(n.kind, 0) + 1
        
        direction_counts = {}
        for p in self.get_ports():
            direction_counts[p.direction] = direction_counts.get(p.direction, 0) + 1
        
        return {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
            'node_kinds': kind_counts,
            'port_directions': direction_counts,
            'clock_edges': len(self.get_clock_edges()),
            'registers': len(self.get_registers()),
            'file_count': len(self.data.get('fileTable', [])),
        }


if __name__ == '__main__':
    # 测试
    parser = NetlistParser('/tmp/navisv_netlist/netlist.json').parse()
    
    print("=== Netlist Parser 测试 ===")
    print(f"Summary: {parser.summary()}")
    
    print("\nRegisters:")
    for reg in parser.get_registers():
        print(f"  {reg.path}")
    
    print("\nInput ports:")
    for p in parser.get_input_ports():
        print(f"  {p.path} [{p.bounds[0]}:{p.bounds[1]}]")
    
    print("\nOutput ports:")
    for p in parser.get_output_ports():
        print(f"  {p.path} [{p.bounds[0]}:{p.bounds[1]}]")
    
    print("\nClock edges:")
    for e in parser.get_clock_edges():
        src = parser.get_node_by_id(e.source)
        tgt = parser.get_node_by_id(e.target)
        print(f"  {src.path if src else e.source} -> {tgt.path if tgt else e.target} ({e.edge_kind})")
    
    print("\nFind top.alu.*:")
    for n in parser.find_nodes("top.alu_inst.*"):
        print(f"  {n.path} ({n.kind})")