"""
constraint_graph.py - ConstraintGraph 查询 API

基于 ConstraintParser 的解析结果, 构建 NetworkX 有向图,
提供三个核心查询:
  Q1: 变量在哪些 constraint 中?
  Q2: constraint 影响哪些变量?
  Q3: 两个变量之间的约束关系
"""

import networkx as nx
from typing import Dict, List, Optional, Set, Any

from navisv.parsers.constraint_parser import (
    ConstraintParser, ClassInfo, VariableInfo, ConstraintInfo, VarRef
)


class ConstraintGraph:
    """
    SystemVerilog Class Constraint 图查询接口
    
    图结构:
      节点类型: Class, Variable, Constraint
      边类型:
        has_var        - Class → Variable
        has_constraint - Class → Constraint
        binds          - Constraint → Variable (带 access_path, bit_range 等)
        inherits       - Class → Class (父类)
        member_of      - Variable → Class (类型为 class instance)
    """
    
    def __init__(self, parser: ConstraintParser):
        self._parser = parser
        self._graph = nx.MultiDiGraph()
        self._build_graph()
    
    # ================================================================
    # 图构建
    # ================================================================
    
    def _build_graph(self):
        """构建 NetworkX 图"""
        self._add_class_nodes()
        self._add_variable_nodes()
        self._add_constraint_nodes()
        self._add_inheritance_edges()
        self._add_member_of_edges()
        self._add_has_var_edges()
        self._add_has_constraint_edges()
        self._add_binds_edges()
    
    def _add_class_nodes(self):
        for path, info in self._parser.classes.items():
            self._graph.add_node(path, kind='Class', name=info.name,
                                  is_abstract=info.is_abstract)
    
    def _add_variable_nodes(self):
        for path, info in self._parser.variables.items():
            self._graph.add_node(path, kind='Variable', name=info.name,
                                  type_str=info.type_str, rand_mode=info.rand_mode,
                                  msb=info.msb, lsb=info.lsb,
                                  bit_width=info.bit_width, is_dynamic=info.is_dynamic,
                                  type_class=info.type_class or '')
    
    def _add_constraint_nodes(self):
        for path, info in self._parser.constraints.items():
            self._graph.add_node(path, kind='Constraint', name=info.name,
                                  expr_count=info.expr_count,
                                  has_soft=info.has_soft,
                                  is_conditional=info.is_conditional)
    
    def _add_inheritance_edges(self):
        for path, info in self._parser.classes.items():
            if info.base_class and info.base_class in self._parser.classes:
                self._graph.add_edge(path, info.base_class, edge_kind='inherits')
    
    def _add_member_of_edges(self):
        for path, info in self._parser.variables.items():
            if info.type_class and info.type_class in self._parser.classes:
                self._graph.add_edge(path, info.type_class, edge_kind='member_of')
    
    def _add_has_var_edges(self):
        for path, info in self._parser.variables.items():
            if info.class_name in self._parser.classes:
                self._graph.add_edge(info.class_name, path, edge_kind='has_var')
    
    def _add_has_constraint_edges(self):
        for path, info in self._parser.constraints.items():
            if info.class_name in self._parser.classes:
                self._graph.add_edge(info.class_name, path, edge_kind='has_constraint')
    
    def _add_binds_edges(self):
        for cpath, cinfo in self._parser.constraints.items():
            for ref in cinfo.bound_vars:
                if ref.var_path in self._parser.variables:
                    self._graph.add_edge(
                        cpath, ref.var_path, edge_kind='binds',
                        access_path=ref.access_path,
                        target_class=ref.target_class,
                        bit_range=ref.bit_range,
                        is_conditional=ref.is_conditional,
                        condition=ref.condition,
                        context=ref.context,
                    )
    
    # ================================================================
    # 公共查询 API
    # ================================================================
    
    def _normalize_var_path(self, var_path: str) -> str:
        """将变量路径规范化为定义类的路径 (处理继承)
        
        优先级:
        1. 如果 var_path 直接被约束引用, 返回它
        2. 如果 var_path 存在但未被引用, 查找继承链上被引用的同名变量
        3. 如果 var_path 不存在, 通过类继承链查找
        """
        # 先检查是否直接被约束引用 (即使不在 variables dict 中)
        for cpath, cinfo in self._parser.constraints.items():
            for ref in cinfo.bound_vars:
                if ref.var_path == var_path:
                    return var_path
        
        # 处理不存在的路径 (如 child_cls.value, 实际是 parent_cls.value)
        if var_path not in self._parser.variables:
            parts = var_path.rsplit('.', 1)
            if len(parts) == 2:
                cls_path, var_name = parts
                cls = self._parser.classes.get(cls_path)
                while cls and cls.base_class:
                    parent_var = f"{cls.base_class}.{var_name}"
                    if parent_var in self._parser.variables:
                        return self._normalize_var_path(parent_var)
                    cls = self._parser.classes.get(cls.base_class)
            return var_path
        
        # 未被直接引用, 查找继承链上被引用的同名变量
        var_info = self._parser.variables[var_path]
        var_name = var_info.name
        cls_path = var_info.class_name
        
        # 向上查找父类
        cls = self._parser.classes.get(cls_path)
        while cls and cls.base_class:
            parent_var = f"{cls.base_class}.{var_name}"
            if parent_var in self._parser.variables:
                for cpath, cinfo in self._parser.constraints.items():
                    for ref in cinfo.bound_vars:
                        if ref.var_path == parent_var:
                            return parent_var
            cls = self._parser.classes.get(cls.base_class)
        
        # 向下查找子类
        for vpath, vinfo in self._parser.variables.items():
            if vinfo.name == var_name and vinfo.class_name != cls_path:
                for cpath, cinfo in self._parser.constraints.items():
                    for ref in cinfo.bound_vars:
                        if ref.var_path == vpath:
                            return vpath
        
        return var_path
    
    def _find_all_var_paths(self, var_path: str) -> List[str]:
        """查找变量及其在继承链上的所有对应路径
        
        只查找同一个继承链上的变量，不跨类匹配同名变量。
        """
        normalized = self._normalize_var_path(var_path)
        
        # 从 normalized 获取变量名和类
        parts = normalized.rsplit('.', 1)
        if len(parts) != 2:
            return [normalized]
        cls_path, var_name = parts
        
        result = set()
        
        # 向上查找父类
        for cls in self._walk_inheritance(cls_path):
            candidate = f"{cls}.{var_name}"
            if candidate in self._parser.variables:
                result.add(candidate)
        
        # 向下查找子类
        for cls_path_item, cls_info in self._parser.classes.items():
            if cls_path_item not in result:
                chain = self._walk_inheritance(cls_path_item)
                if cls_path in chain:
                    candidate = f"{cls_path_item}.{var_name}"
                    if candidate in self._parser.variables:
                        result.add(candidate)
        
        # 也查找被约束引用但不在 variables dict 中的路径 (如 MemberAccess 结果)
        for cpath, cinfo in self._parser.constraints.items():
            for ref in cinfo.bound_vars:
                if ref.var_path not in result:
                    ref_parts = ref.var_path.rsplit('.', 1)
                    if len(ref_parts) == 2 and ref_parts[1] == var_name:
                        # 检查是否在同一继承链
                        if ref_parts[0] == cls_path or ref_parts[0] in [c for c in self._walk_inheritance(cls_path)]:
                            result.add(ref.var_path)
        
        return sorted(result) if result else [normalized]
    
    def get_classes(self) -> List[Dict[str, Any]]:
        """获取所有类"""
        return [
            {'name': info.name, 'full_path': path, 'is_abstract': info.is_abstract,
             'base_class': info.base_class}
            for path, info in self._parser.classes.items()
        ]
    
    def get_variables_in_class(self, class_path: str) -> List[Dict[str, Any]]:
        """获取类的所有变量 (含继承)"""
        result = []
        seen: Set[str] = set()
        
        for cls_path in self._walk_inheritance(class_path):
            for path, info in self._parser.variables.items():
                if info.class_name == cls_path and info.name not in seen:
                    seen.add(info.name)
                    result.append({
                        'name': info.name,
                        'full_path': info.full_path,
                        'type_str': info.type_str,
                        'rand_mode': info.rand_mode,
                        'msb': info.msb,
                        'lsb': info.lsb,
                        'bit_width': info.bit_width,
                        'is_dynamic': info.is_dynamic,
                        'type_class': info.type_class,
                        'class_name': info.class_name,
                    })
        
        return result
    
    def get_constraints_in_class(self, class_path: str) -> List[Dict[str, Any]]:
        """获取类的所有约束 (含继承)"""
        result = []
        seen: Set[str] = set()
        
        for cls_path in self._walk_inheritance(class_path):
            for path, info in self._parser.constraints.items():
                if info.class_name == cls_path and info.name not in seen:
                    seen.add(info.name)
                    result.append({
                        'name': info.name,
                        'full_path': info.full_path,
                        'class_name': info.class_name,
                        'expr_count': info.expr_count,
                        'has_soft': info.has_soft,
                        'is_conditional': info.is_conditional,
                        'constraint_body': info.constraint_body,
                        'inside_ranges': info.inside_ranges,
                    })
        
        return result
    
    def get_inheritance_chain(self, class_path: str) -> List[str]:
        """获取继承链 (从当前类到最远祖先)"""
        return self._walk_inheritance(class_path)
    
    # ================================================================
    # Q1: 变量在哪些 constraint 中?
    # ================================================================
    
    def get_constraints_for_variable(
        self,
        var_path: str,
        include_composition: bool = False,
        max_depth: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Q1: 变量出现在哪些 constraint 中?
        
        Args:
            var_path: 变量 full_path (如 'pkg.Class.var')
            include_composition: 是否包含通过组合关系引用的约束
            max_depth: 组合穿透最大深度
        
        Returns:
            约束信息列表, 每个包含 constraint_name, class_name, bit_range,
            is_conditional, condition, context, direct_exprs
        """
        result = []
        seen: Set[str] = set()
        
        # 查找变量在继承链上的所有路径
        all_var_paths = self._find_all_var_paths(var_path)
        
        for vp in all_var_paths:
            # 1. 直接约束 (binds 边)
            self._find_direct_constraints(vp, result, seen)
        
        # 2. 组合引用的约束
        if include_composition:
            self._find_composition_constraints(var_path, result, seen, max_depth)
        
        return result
    
    def _find_direct_constraints(self, var_path: str, result: List, seen: Set[str]):
        """查找直接引用变量的约束"""
        for cpath, cinfo in self._parser.constraints.items():
            for ref in cinfo.bound_vars:
                if ref.var_path == var_path and cpath not in seen:
                    seen.add(cpath)
                    result.append(self._make_constraint_entry(cinfo, ref))
    
    def _find_inherited_constraints(self, var_path: str, result: List, seen: Set[str]):
        """查找继承链上的同名变量约束"""
        var_info = self._parser.variables.get(var_path)
        if not var_info:
            return
        
        var_name = var_info.name
        
        # 沿继承链向上查找
        cls = self._parser.classes.get(var_info.class_name)
        while cls and cls.base_class:
            parent_var_path = f"{cls.base_class}.{var_name}"
            if parent_var_path in self._parser.variables:
                for cpath, cinfo in self._parser.constraints.items():
                    for ref in cinfo.bound_vars:
                        if ref.var_path == parent_var_path and cpath not in seen:
                            seen.add(cpath)
                            result.append(self._make_constraint_entry(cinfo, ref))
            cls = self._parser.classes.get(cls.base_class)
        
        # 子类继承: 查找所有引用了该变量(通过继承)的子类约束
        self._find_child_class_constraints(var_path, var_name, var_info.class_name, result, seen)
    
    def _find_child_class_constraints(self, var_path: str, var_name: str, 
                                       class_path: str, result: List, seen: Set[str]):
        """查找子类中继承引用的约束"""
        for cls_path, cls_info in self._parser.classes.items():
            if cls_info.base_class == class_path:
                child_var_path = f"{cls_path}.{var_name}"
                # 子类中是否有同名变量引用
                for cpath, cinfo in self._parser.constraints.items():
                    for ref in cinfo.bound_vars:
                        if ref.var_path == child_var_path and cpath not in seen:
                            seen.add(cpath)
                            result.append(self._make_constraint_entry(cinfo, ref))
                # 递归查找更深层的子类
                self._find_child_class_constraints(var_path, var_name, cls_path, result, seen)
    
    def _find_composition_constraints(self, var_path: str, result: List, 
                                       seen: Set[str], max_depth: int):
        """查找通过组合关系引用的约束
        
        策略: 查找所有 binds 边中引用了目标变量的约束，
        然后检查 access_path 是否通过组合实例。
        """
        var_info = self._parser.variables.get(var_path)
        if not var_info:
            return
        
        var_name = var_info.name
        
        # 查找所有引用了目标变量的约束
        for cpath, cinfo in self._parser.constraints.items():
            if cpath in seen:
                continue
            for ref in cinfo.bound_vars:
                if ref.var_path == var_path and ref.access_path:
                    # 有 access_path 说明是跨类引用
                    seen.add(cpath)
                    result.append(self._make_constraint_entry(cinfo, ref))
    
    # ================================================================
    # Q2: constraint 影响哪些变量?
    # ================================================================
    
    def get_variables_in_constraint(self, constraint_path: str) -> List[Dict[str, Any]]:
        """
        Q2: constraint 引用了哪些变量?
        
        Returns:
            变量信息列表, 每个包含 name, var_path, class_name,
            access_path, target_class, bit_range, is_conditional
        """
        cinfo = self._parser.constraints.get(constraint_path)
        if not cinfo:
            return []
        
        result = []
        for ref in cinfo.bound_vars:
            entry = {
                'name': ref.var_name,
                'var_path': ref.var_path,
                'class_name': ref.class_name,
                'access_path': ref.access_path,
                'target_class': ref.target_class,
                'bit_range': ref.bit_range,
                'is_conditional': ref.is_conditional,
            }
            result.append(entry)
        
        return result
    
    # ================================================================
    # Q3: 两个变量之间的约束关系
    # ================================================================
    
    def get_constraint_relationship(
        self, var_a_path: str, var_b_path: str
    ) -> Dict[str, Any]:
        """
        Q3: 两个变量之间的约束关系
        
        Returns:
            {
                'shared_constraints': [constraint_name, ...],
                'var_a': var_a_path,
                'var_b': var_b_path,
            }
        """
        cons_a = self.get_constraints_for_variable(var_a_path, include_composition=True)
        cons_b = self.get_constraints_for_variable(var_b_path, include_composition=True)
        
        names_a = {c['constraint_name'] for c in cons_a}
        names_b = {c['constraint_name'] for c in cons_b}
        
        shared = sorted(names_a & names_b)
        
        return {
            'var_a': var_a_path,
            'var_b': var_b_path,
            'shared_constraints': shared,
        }
    
    # ================================================================
    # 辅助方法
    # ================================================================
    
    def _walk_inheritance(self, class_path: str) -> List[str]:
        """沿继承链向上遍历, 返回 [当前类, 父类, 祖父类, ...]"""
        chain = []
        current = class_path
        visited: Set[str] = set()
        
        while current and current in self._parser.classes and current not in visited:
            visited.add(current)
            chain.append(current)
            cls = self._parser.classes[current]
            current = cls.base_class
        
        return chain
    
    def _make_constraint_entry(self, cinfo: ConstraintInfo, ref: VarRef) -> Dict[str, Any]:
        """构造约束条目"""
        return {
            'constraint_name': cinfo.name,
            'constraint_path': cinfo.full_path,
            'class_name': cinfo.class_name,
            'constraint_body': cinfo.constraint_body,
            'inside_ranges': cinfo.inside_ranges,
            'bit_range': ref.bit_range,
            'is_conditional': ref.is_conditional,
            'condition': ref.condition,
            'context': ref.context,
            'direct_exprs': [ref.direct_expr] if ref.direct_expr else [],
            'access_path': ref.access_path,
        }
    
    # ================================================================
    # 底层访问 (调试用)
    # ================================================================
    
    @property
    def graph(self) -> nx.MultiDiGraph:
        """获取底层 NetworkX 图"""
        return self._graph
    
    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()
    
    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()
    
    def summary(self) -> Dict[str, Any]:
        """获取摘要"""
        class_count = sum(1 for _, d in self._graph.nodes(data=True) if d.get('kind') == 'Class')
        var_count = sum(1 for _, d in self._graph.nodes(data=True) if d.get('kind') == 'Variable')
        constraint_count = sum(1 for _, d in self._graph.nodes(data=True) if d.get('kind') == 'Constraint')
        binds_count = sum(1 for _, _, d in self._graph.edges(data=True) if d.get('edge_kind') == 'binds')
        
        return {
            'classes': class_count,
            'variables': var_count,
            'constraints': constraint_count,
            'binds_edges': binds_count,
            'total_nodes': self.node_count,
            'total_edges': self.edge_count,
        }
    
    def __repr__(self) -> str:
        s = self.summary()
        return (f"ConstraintGraph(classes={s['classes']}, vars={s['variables']}, "
                f"constraints={s['constraints']}, edges={s['total_edges']})")
