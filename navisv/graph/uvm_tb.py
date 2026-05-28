"""
uvm_tb.py - UVM Testbench 静态结构查询 API
"""

from typing import Dict, List, Any, Optional
from navisv.parsers.uvm_tb_parser import UVMTestbenchParser


class UVMTestbench:
    """UVM Testbench 静态结构查询接口"""
    
    def __init__(self, parser: UVMTestbenchParser):
        self._parser = parser
    
    def get_components(self) -> List[Dict[str, Any]]:
        """获取所有 UVM 组件"""
        return [
            {
                'name': c.name,
                'full_path': c.full_path,
                'uvm_type': c.uvm_type,
                'base_class': c.base_class,
            }
            for c in self._parser.components.values()
        ]
    
    def get_sequences(self) -> List[Dict[str, Any]]:
        """获取所有 sequence"""
        return [
            {
                'name': s.name,
                'full_path': s.full_path,
                'base_class': s.base_class,
                'seq_item_type': s.seq_item_type,
            }
            for s in self._parser.sequences.values()
        ]
    
    def get_sequence_items(self) -> List[Dict[str, Any]]:
        """获取所有 sequence_item"""
        return [
            {
                'name': i.name,
                'full_path': i.full_path,
                'base_class': i.base_class,
            }
            for i in self._parser.sequence_items.values()
        ]
    
    def get_children(self, class_path: str) -> List[Dict[str, Any]]:
        """获取组件的子组件"""
        children = self._parser.children.get(class_path, [])
        return [
            {
                'parent': c.parent,
                'child': c.child,
                'child_type': c.child_type,
                'field_name': c.field_name,
            }
            for c in children
        ]
    
    def get_hierarchy(self, class_path: str) -> Dict[str, Any]:
        """获取组件层级树"""
        tree = {}
        children = self._parser.children.get(class_path, [])
        for c in children:
            child_name = c.child
            # 递归获取子组件的子组件
            child_path = None
            for path in self._parser.components:
                if path.endswith(f'.{child_name}'):
                    child_path = path
                    break
            if child_path:
                sub_children = self._parser.children.get(child_path, [])
                tree[child_name] = [sc.child for sc in sub_children]
            else:
                tree[child_name] = []
        return tree
    
    def get_phases(self, class_path: str) -> List[Dict[str, Any]]:
        """获取类的 phase 方法"""
        phases = self._parser.phases.get(class_path, [])
        return [{'name': p.name} for p in phases]
    
    def get_sequence_usages(self) -> List[Dict[str, Any]]:
        """获取 sequence 使用关系"""
        return [
            {
                'user': u.user,
                'sequence': u.sequence,
                'method': u.method,
            }
            for u in self._parser.sequence_usages
        ]
    
    def get_port_connections(self) -> List[Dict[str, Any]]:
        """获取端口连接关系"""
        return [
            {
                'source': c.source,
                'target': c.target,
                'source_class': c.source_class,
                'target_class': c.target_class,
            }
            for c in self._parser.port_connections
        ]
    
    def get_config_db_sets(self) -> List[Dict[str, Any]]:
        """获取 config_db::set 调用"""
        return [
            {
                'context': s.context,
                'inst_name': s.inst_name,
                'field': s.field,
                'value': s.value,
                'method': s.method,
            }
            for s in self._parser.config_db_sets
        ]
    
    def get_config_db_gets(self) -> List[Dict[str, Any]]:
        """获取 config_db::get 调用"""
        return [
            {
                'context': g.context,
                'inst_name': g.inst_name,
                'field': g.field,
                'method': g.method,
            }
            for g in self._parser.config_db_gets
        ]
    
    def get_config_flows(self) -> List[Dict[str, Any]]:
        """获取 set → get 配置流"""
        flows = []
        for s in self._parser.config_db_sets:
            # 找匹配的 get
            getter = None
            for g in self._parser.config_db_gets:
                if g.field == s.field:
                    getter = g.context
                    break
            flows.append({
                'field': s.field,
                'value': s.value,
                'setter': s.context,
                'getter': getter,
                'inst_name': s.inst_name,
            })
        return flows
    
    def get_plusargs(self) -> List[Dict[str, Any]]:
        """获取 plusargs"""
        return [
            {
                'name': p.name,
                'kind': p.kind,
                'context': p.context,
                'method': p.method,
                'variable': p.variable,
            }
            for p in self._parser.plusargs
        ]
    
    def get_plusargs_impacts(self) -> List[Dict[str, Any]]:
        """获取 plusargs 对 config_db 的影响"""
        impacts = []
        for p in self._parser.plusargs:
            if p.kind == 'value' and p.variable:
                # 查找同方法中的 config_db::set 使用了该变量
                for s in self._parser.config_db_sets:
                    if s.method == p.method and s.context == p.context:
                        impacts.append({
                            'plusarg': p.name,
                            'variable': p.variable,
                            'config_field': s.field,
                            'context': s.context,
                        })
        return impacts
    
    def to_dot(self, class_filter: str = '') -> str:
        """导出 DOT 格式"""
        lines = ['digraph UVMTestbench {', '  rankdir=TB;', '  node [shape=box];', '']
        
        # 组件节点
        for path, comp in self._parser.components.items():
            if class_filter and class_filter not in path:
                continue
            label = f'{comp.name}\\n({comp.uvm_type})'
            lines.append(f'  "{comp.name}" [label="{label}"];')
        
        # Sequence 节点
        for path, seq in self._parser.sequences.items():
            if class_filter and class_filter not in path:
                continue
            label = f'{seq.name}\\n(sequence)'
            lines.append(f'  "{seq.name}" [label="{label}", shape=ellipse, color=blue];')
        
        lines.append('')
        
        # 层级边 (contains)
        for parent_path, children in self._parser.children.items():
            parent_name = parent_path.split('.')[-1]
            if class_filter and class_filter not in parent_path:
                continue
            for c in children:
                lines.append(f'  "{parent_name}" -> "{c.child}" [label="contains"];')
        
        # Sequence 使用边
        for u in self._parser.sequence_usages:
            lines.append(f'  "{u.user}" -> "{u.sequence}" [label="uses", color=blue, style=dashed];')
        
        # Port 连接边
        for conn in self._parser.port_connections:
            if conn.source and conn.target:
                lines.append(f'  "{conn.source}" -> "{conn.target}" [label="connect", color=green];')
        
        # 继承边
        for path, comp in self._parser.components.items():
            if comp.base_class and comp.base_class not in self._parser.UVM_COMPONENT_BASES:
                base_name = comp.base_class.split('.')[-1]
                lines.append(f'  "{comp.name}" -> "{base_name}" [label="extends", style=dotted];')
        for path, seq in self._parser.sequences.items():
            if seq.base_class:
                base_name = seq.base_class.split('.')[-1]
                if base_name not in self._parser.UVM_SEQUENCE_BASES:
                    lines.append(f'  "{seq.name}" -> "{base_name}" [label="extends", style=dotted];')
        
        lines.append('}')
        return '\n'.join(lines)
    
    def to_mermaid(self, class_filter: str = '') -> str:
        """导出 Mermaid 格式"""
        lines = ['graph TB']
        
        # 组件节点
        for path, comp in self._parser.components.items():
            if class_filter and class_filter not in path:
                continue
            node_id = comp.name
            lines.append(f'  {node_id}["{comp.name}<br/>({comp.uvm_type})"]')
        
        # Sequence 节点
        for path, seq in self._parser.sequences.items():
            if class_filter and class_filter not in path:
                continue
            node_id = seq.name
            lines.append(f'  {node_id}("{seq.name}<br/>(sequence)")')
        
        # 层级边
        for parent_path, children in self._parser.children.items():
            parent_name = parent_path.split('.')[-1]
            if class_filter and class_filter not in parent_path:
                continue
            for c in children:
                lines.append(f'  {parent_name} --> {c.child}')
        
        # Sequence 使用边
        for u in self._parser.sequence_usages:
            lines.append(f'  {u.user} -.-> {u.sequence}')
        
        # Port 连接边
        for conn in self._parser.port_connections:
            if conn.source and conn.target:
                src = conn.source.replace('.', '_')
                tgt = conn.target.replace('.', '_')
                lines.append(f'  {src} ==> {tgt}')
        
        return '\n'.join(lines)
