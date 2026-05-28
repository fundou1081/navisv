"""
call_graph.py - 函数调用图查询 API
"""

from typing import Dict, List, Any, Optional
from navisv.parsers.call_graph_parser import CallGraphParser, CallInfo


class CallGraph:
    """函数调用图查询接口"""
    
    def __init__(self, parser: CallGraphParser):
        self._parser = parser
    
    def get_methods(self, class_path: str) -> List[Dict[str, Any]]:
        """获取类的所有方法（含继承）"""
        result = []
        seen = set()
        
        # 当前类的方法
        for path, m in self._parser.methods.items():
            if m.class_name == class_path and m.name not in seen:
                seen.add(m.name)
                result.append(self._method_to_dict(m))
        
        # 继承的方法
        cls_info = self._parser._class_info.get(class_path, {})
        base = cls_info.get('base_class')
        while base:
            for path, m in self._parser.methods.items():
                if m.class_name == base and m.name not in seen:
                    seen.add(m.name)
                    result.append(self._method_to_dict(m))
            base_info = self._parser._class_info.get(base, {})
            base = base_info.get('base_class')
        
        return result
    
    def get_calls_from(self, method_path: str) -> List[Dict[str, Any]]:
        """获取方法的所有调用"""
        calls = self._parser.calls.get(method_path, [])
        return [self._call_to_dict(c) for c in calls]
    
    def get_forks(self, class_path: str) -> List[Dict[str, Any]]:
        """获取类的所有 fork 块"""
        forks = self._parser.forks.get(class_path, [])
        return [self._fork_to_dict(f) for f in forks]
    
    def _method_to_dict(self, m) -> Dict[str, Any]:
        return {
            'name': m.name,
            'full_path': m.full_path,
            'class_name': m.class_name,
            'kind': m.kind,
            'is_virtual': m.is_virtual,
        }
    
    def _call_to_dict(self, c: CallInfo) -> Dict[str, Any]:
        return {
            'callee': c.callee,
            'callee_path': c.callee_path,
            'target_class': c.target_class,
            'is_super': c.is_super,
            'is_constructor': c.is_constructor,
            'is_randomize': c.is_randomize,
            'is_builtin': c.is_builtin,
            'arguments': c.arguments,
        }
    
    def _fork_to_dict(self, f) -> Dict[str, Any]:
        return {
            'name': f.name,
            'parent_method': f.parent_method,
            'join_type': f.join_type,
            'branches': [self._call_to_dict(b) for b in f.branches],
        }

    # ================================================================
    # 导出
    # ================================================================

    def to_dot(self, class_filter: str = '') -> str:
        """导出 DOT 格式"""
        lines = ['digraph CallGraph {', '  rankdir=LR;', '  node [shape=box];', '']

        # 收集所有方法
        for path, m in self._parser.methods.items():
            if class_filter and class_filter not in path:
                continue
            cls = m.class_name.split('.')[-1]
            label = f'{cls}.{m.name}'
            style = ''
            if m.is_virtual:
                style = ' [style=dashed]'
            lines.append(f'  "{path}" [label="{label}"]{style};')

        lines.append('')

        # 调用边
        for caller, calls in self._parser.calls.items():
            if class_filter and class_filter not in caller:
                continue
            for c in calls:
                if c.is_randomize:
                    lines.append(f'  "{caller}" -> "randomize" [label="randomize", color=red];')
                elif c.is_constructor:
                    target = c.target_class or 'new'
                    lines.append(f'  "{caller}" -> "{target}.new" [label="new", color=green];')
                elif c.callee_path:
                    style = ' [style=dashed]' if c.is_super else ''
                    label = 'super' if c.is_super else ''
                    lines.append(f'  "{caller}" -> "{c.callee_path}"{style} [label="{label}"];')

        # fork 节点
        for cls, forks in self._parser.forks.items():
            if class_filter and class_filter not in cls:
                continue
            for f in forks:
                fork_id = f'{cls}.{f.name}'
                lines.append(f'  "{fork_id}" [label="fork ({f.join_type})", shape=ellipse, color=blue];')
                # fork 入边
                lines.append(f'  "{f.parent_method}" -> "{fork_id}" [color=blue];')
                # fork 出边
                for b in f.branches:
                    if b.callee_path:
                        lines.append(f'  "{fork_id}" -> "{b.callee_path}" [color=blue];')

        lines.append('}')
        return '\n'.join(lines)

    def to_mermaid(self, class_filter: str = '') -> str:
        """导出 Mermaid 格式"""
        lines = ['graph LR']

        # 收集所有方法
        for path, m in self._parser.methods.items():
            if class_filter and class_filter not in path:
                continue
            cls = m.class_name.split('.')[-1]
            label = f'{cls}.{m.name}'
            node_id = path.replace('.', '_')
            style = '' if m.is_virtual else ''
            lines.append(f'  {node_id}["{label}"]')

        # 调用边
        for caller, calls in self._parser.calls.items():
            if class_filter and class_filter not in caller:
                continue
            caller_id = caller.replace('.', '_')
            for c in calls:
                if c.is_randomize:
                    lines.append(f'  {caller_id} -->|randomize| randomize_node')
                elif c.is_constructor:
                    target = (c.target_class or 'new').replace('.', '_')
                    lines.append(f'  {caller_id} -->|new| {target}_new')
                elif c.callee_path:
                    callee_id = c.callee_path.replace('.', '_')
                    label = '|super|' if c.is_super else '-->'
                    lines.append(f'  {caller_id} {label} {callee_id}')

        # fork 节点
        for cls, forks in self._parser.forks.items():
            if class_filter and class_filter not in cls:
                continue
            for f in forks:
                fork_id = f'{cls}.{f.name}'.replace('.', '_')
                parent_id = f.parent_method.replace('.', '_')
                lines.append(f'  {parent_id} --> {fork_id}{{"fork ({f.join_type})"}}')
                for b in f.branches:
                    if b.callee_path:
                        callee_id = b.callee_path.replace('.', '_')
                        lines.append(f'  {fork_id} --> {callee_id}')

        return '\n'.join(lines)
