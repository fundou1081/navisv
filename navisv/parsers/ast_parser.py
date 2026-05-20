"""
AST Parser - 解析 slang --ast-json 输出

功能：
- 解析 AST JSON 构建节点树
- 提取模块、端口、变量、实例信息
- 支持 scope 过滤
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ASTNode:
    """AST 节点"""
    name: str
    kind: str
    path: str = ""
    depth: int = 0
    children: List['ASTNode'] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    location: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'kind': self.kind,
            'path': self.path,
            'depth': self.depth,
            'children': [c.to_dict() for c in self.children],
            'attributes': self.attributes,
            'location': self.location
        }


class ASTParser:
    """解析 slang --ast-json 输出"""
    
    def __init__(self, ast_json_path: str):
        """
        Args:
            ast_json_path: slang 生成的 ast.json 文件路径
        """
        self.ast_json_path = ast_json_path
        self.data: Dict[str, Any] = {}
        self.nodes: List[ASTNode] = []
        self.root: Optional[ASTNode] = None
    
    def parse(self) -> 'ASTParser':
        """解析 JSON 文件"""
        with open(self.ast_json_path) as f:
            self.data = json.load(f)
        
        self._build_tree()
        return self
    
    def _build_tree(self):
        """从 JSON 构建树结构"""
        design = self.data.get('design', {})
        self.root = self._parse_node(design, '', 0)
    
    def _parse_node(self, obj: Dict[str, Any], parent_path: str, depth: int) -> ASTNode:
        """递归解析节点"""
        name = obj.get('name', '') or ''
        kind = obj.get('kind', 'Unknown')
        
        # 构建路径
        if parent_path:
            path = f"{parent_path}.{name}" if name else parent_path
        else:
            path = name
        
        node = ASTNode(
            name=name,
            kind=kind,
            path=path,
            depth=depth,
            attributes={k: v for k, v in obj.items() 
                       if k not in ('name', 'kind', 'body', 'members', 'addr')},
            location=obj.get('sourceLocation') or obj.get('location')
        )
        
        # 递归处理 body
        if 'body' in obj:
            body = obj['body']
            if isinstance(body, dict):
                node.children.append(self._parse_node(body, path, depth + 1))
            elif isinstance(body, list):
                for item in body:
                    if isinstance(item, dict):
                        node.children.append(self._parse_node(item, path, depth + 1))
        
        # 递归处理 members
        if 'members' in obj:
            for member in obj['members']:
                if isinstance(member, dict):
                    # ContinuousAssign has 'assignment' instead of recursively visiting
                    if member.get('kind') == 'ContinuousAssign' and 'assignment' in member:
                        member_with_assignment = dict(member)
                        member_with_assignment['assignment'] = member['assignment']
                    node.children.append(self._parse_node(member, path, depth + 1))
        
        # 递归处理 ContinuousAssign 的 assignment 字段
        if obj.get('kind') == 'ContinuousAssign' and 'assignment' in obj:
            assignment = obj['assignment']
            if isinstance(assignment, dict):
                node.children.append(self._parse_node(assignment, path, depth + 1))
        
        # 递归处理 Net 的 initializer 字段 (wire 赋值，如 ternary)
        if obj.get('kind') == 'Net' and 'initializer' in obj:
            initializer = obj['initializer']
            if isinstance(initializer, dict):
                node.children.append(self._parse_node(initializer, path, depth + 1))
        
        # 递归处理 stmt (Timed 节点中的语句)
        if 'stmt' in obj:
            stmt = obj['stmt']
            if isinstance(stmt, dict):
                node.children.append(self._parse_node(stmt, path, depth + 1))
        
        # 递归处理 expr (ExpressionStatement, Conditional 等的表达式)
        if 'expr' in obj and isinstance(obj['expr'], dict):
            node.children.append(self._parse_node(obj['expr'], path, depth + 1))
        
        # 递归处理 case items
        if 'items' in obj and isinstance(obj['items'], list):
            for item in obj['items']:
                if isinstance(item, dict):
                    node.children.append(self._parse_node(item, path, depth + 1))
        
        # 递归处理 defaultCase
        if 'defaultCase' in obj and isinstance(obj['defaultCase'], dict):
            node.children.append(self._parse_node(obj['defaultCase'], path, depth + 1))
        
        # 递归处理 Conditional (?:) 的 true/false expression
        if 'trueExpression' in obj and isinstance(obj['trueExpression'], dict):
            node.children.append(self._parse_node(obj['trueExpression'], path, depth + 1))
        if 'falseExpression' in obj and isinstance(obj['falseExpression'], dict):
            node.children.append(self._parse_node(obj['falseExpression'], path, depth + 1))
        
        # 递归处理 ConditionalOp (链式三元运算符) 的 conditions/left/right
        if kind == 'ConditionalOp':
            # conditions
            if 'conditions' in obj and isinstance(obj['conditions'], list):
                for cond_item in obj['conditions']:
                    if isinstance(cond_item, dict) and 'expr' in cond_item:
                        node.children.append(self._parse_node(cond_item['expr'], path, depth + 1))
            # left/right (ternary true/false branches)
            if 'left' in obj and isinstance(obj['left'], dict):
                node.children.append(self._parse_node(obj['left'], path, depth + 1))
            if 'right' in obj and isinstance(obj['right'], dict):
                node.children.append(self._parse_node(obj['right'], path, depth + 1))
        
        # 递归处理 expressions (case item 的条件表达式)
        if 'expressions' in obj and isinstance(obj['expressions'], list):
            for expr in obj['expressions']:
                if isinstance(expr, dict):
                    node.children.append(self._parse_node(expr, path, depth + 1))
        
        # 递归处理 Assignment 的 left/right (赋值的两边)
        if 'left' in obj and isinstance(obj['left'], dict):
            node.children.append(self._parse_node(obj['left'], path, depth + 1))
        if 'right' in obj and isinstance(obj['right'], dict):
            node.children.append(self._parse_node(obj['right'], path, depth + 1))
        
        # 递归处理 operand (一元操作符的操作数)
        if 'operand' in obj and isinstance(obj['operand'], dict):
            node.children.append(self._parse_node(obj['operand'], path, depth + 1))
        
        # 递归处理 condition (if/conditional 的条件)
        if 'condition' in obj and isinstance(obj['condition'], dict):
            node.children.append(self._parse_node(obj['condition'], path, depth + 1))
        
        # 递归处理 ifTrue/ifFalse (Conditional 的分支)
        if 'ifTrue' in obj and isinstance(obj['ifTrue'], dict):
            node.children.append(self._parse_node(obj['ifTrue'], path, depth + 1))
        if 'ifFalse' in obj and isinstance(obj['ifFalse'], dict):
            node.children.append(self._parse_node(obj['ifFalse'], path, depth + 1))
        
        # 递归处理 true_branch/false_branch (if 语句的分支)
        if 'true_branch' in obj and isinstance(obj['true_branch'], dict):
            node.children.append(self._parse_node(obj['true_branch'], path, depth + 1))
        if 'false_branch' in obj and isinstance(obj['false_branch'], dict):
            node.children.append(self._parse_node(obj['false_branch'], path, depth + 1))
        
        return node
    
    def get_modules(self) -> List[ASTNode]:
        """获取所有模块定义"""
        modules = []
        for node in self._traverse(self.root):
            if node.kind == 'InstanceBody':
                modules.append(node)
        return modules
    
    def get_ports(self, module_path: str = '') -> List[ASTNode]:
        """获取端口"""
        ports = []
        for node in self._traverse(self.root):
            if node.kind == 'Port':
                if not module_path or module_path in node.path:
                    ports.append(node)
        return ports
    
    def get_variables(self, module_path: str = '') -> List[ASTNode]:
        """获取变量"""
        variables = []
        for node in self._traverse(self.root):
            if node.kind == 'Variable':
                if not module_path or module_path in node.path:
                    variables.append(node)
        return variables
    
    def get_instances(self, module_path: str = '') -> List[ASTNode]:
        """获取实例"""
        instances = []
        for node in self._traverse(self.root):
            if node.kind == 'Instance':
                if not module_path or module_path in node.path:
                    instances.append(node)
        return instances
    
    def find_by_kind(self, kind: str) -> List[ASTNode]:
        """按 kind 查找节点"""
        results = []
        for node in self._traverse(self.root):
            if node.kind == kind:
                results.append(node)
        return results
    
    def find_by_name(self, name: str) -> List[ASTNode]:
        """按名称查找节点"""
        results = []
        for node in self._traverse(self.root):
            if node.name == name:
                results.append(node)
        return results
    
    def _traverse(self, node: Optional[ASTNode]):
        """遍历所有节点"""
        if node is None:
            return
        
        yield node
        for child in node.children:
            yield from self._traverse(child)
    
    def summary(self) -> Dict[str, Any]:
        """返回摘要"""
        kind_counts = {}
        for node in self._traverse(self.root):
            kind_counts[node.kind] = kind_counts.get(node.kind, 0) + 1
        
        return {
            'total_nodes': sum(kind_counts.values()),
            'kind_counts': kind_counts,
            'modules': len(self.get_modules()),
            'ports': len(self.get_ports()),
            'variables': len(self.get_variables()),
            'instances': len(self.get_instances()),
        }


if __name__ == '__main__':
    # 测试
    parser = ASTParser('/tmp/navisv_slang/ast.json').parse()
    
    print("=== AST Parser 测试 ===")
    print(f"Summary: {parser.summary()}")
    
    print("\nModules:")
    for m in parser.get_modules():
        print(f"  {m.path}")
    
    print("\nPorts:")
    for p in parser.get_ports():
        print(f"  {p.path} ({p.attributes.get('direction', 'unknown')})")
    
    print("\nInstances:")
    for i in parser.get_instances():
        print(f"  {i.path}")