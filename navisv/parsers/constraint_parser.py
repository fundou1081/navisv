"""
constraint_parser.py - 从 slang AST JSON 提取 class/constraint 信息

职责:
  1. 解析 ClassType 节点 → 提取类、变量、约束
  2. 解析 ConstraintBlock 节点 → 提取约束表达式中的变量引用
  3. 处理继承关系 (baseClass)
  4. 处理组合关系 (ClassProperty 类型为 class instance)
  5. 处理位精确度 (RangeSelect / ElementSelect)
  6. 处理条件约束 (Conditional)
"""

import json
import re
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class ClassInfo:
    """类信息"""
    name: str                    # 类名 (不含包名)
    full_path: str               # 完整路径 (pkg.class)
    is_abstract: bool = False
    base_class: Optional[str] = None   # 父类 full_path
    base_class_addr: Optional[str] = None


@dataclass
class VariableInfo:
    """变量信息"""
    name: str
    full_path: str               # 类.变量
    class_name: str              # 所属类 full_path
    type_str: str                # 原始类型字符串
    rand_mode: str = 'none'      # Rand / RandC / none
    msb: Optional[int] = None
    lsb: Optional[int] = None
    bit_width: Optional[int] = None
    is_dynamic: bool = False
    type_class: Optional[str] = None  # 如果类型是 class instance, 记录类 full_path


@dataclass
class VarRef:
    """约束中的变量引用"""
    var_name: str                # 变量名
    var_path: str                # 变量 full_path (类.变量)
    class_name: str              # 变量所属类 full_path
    access_path: str = ''        # 跨类访问路径, 如 'pkt.length'
    target_class: str = ''       # 目标变量所属类 (跨类时)
    bit_range: Optional[List[int]] = None  # [msb, lsb] 或 None (全宽)
    is_conditional: bool = False
    condition: str = ''
    context: str = ''            # 完整约束上下文
    direct_expr: str = ''        # 直接命中的表达式


@dataclass
class ConstraintInfo:
    """约束信息"""
    name: str
    full_path: str               # 类.约束名
    class_name: str              # 所属类 full_path
    expr_count: int = 0          # 表达式数量
    source_text: str = ''        # 原始源码
    constraint_body: str = ''    # 约束体内容 (可读)
    has_soft: bool = False
    is_conditional: bool = False
    bound_vars: List[VarRef] = field(default_factory=list)


class ConstraintParser:
    """
    从 slang AST JSON 解析 class/constraint 信息
    
    Usage:
        parser = ConstraintParser(ast_json_path)
        parser.parse()
        classes = parser.classes
        variables = parser.variables
        constraints = parser.constraints
    """
    
    def __init__(self, ast_json_path: str, source_files: Optional[List[str]] = None):
        self.ast_json_path = ast_json_path
        self.source_files = source_files or []
        
        # 解析结果
        self.classes: Dict[str, ClassInfo] = {}          # full_path -> ClassInfo
        self.variables: Dict[str, VariableInfo] = {}     # full_path -> VariableInfo
        self.constraints: Dict[str, ConstraintInfo] = {} # full_path -> ConstraintInfo
        
        # 地址 -> full_path 映射 (用于解析 symbol 引用)
        self._addr_to_class: Dict[str, str] = {}    # addr -> class full_path
        self._addr_to_var: Dict[str, str] = {}      # addr -> var full_path (保留首次, 即父类)
        self._addr_to_name: Dict[str, str] = {}     # addr -> name
        self._addr_to_owning_classes: Dict[str, List[str]] = {}  # addr -> [所有拥有此变量的类]
        
        # 包名
        self._current_pkg: str = ''
        
        # 源码缓存
        self._source_cache: Dict[str, str] = {}
    
    def parse(self) -> 'ConstraintParser':
        """解析 AST JSON"""
        with open(self.ast_json_path) as f:
            data = json.load(f)
        
        # 先遍历收集所有类和变量
        self._collect_classes(data)
        
        # 再遍历解析约束中的变量引用
        self._collect_constraints(data)
        
        return self
    
    # ================================================================
    # 第一遍：收集类、变量、继承关系
    # ================================================================
    
    def _collect_classes(self, node: Any):
        """遍历 AST 收集 ClassType 节点"""
        if isinstance(node, dict):
            if node.get('kind') == 'Package':
                old_pkg = self._current_pkg
                self._current_pkg = node.get('name', '')
                for member in node.get('members', []):
                    self._collect_classes(member)
                self._current_pkg = old_pkg
            elif node.get('kind') == 'ClassType':
                self._process_class(node)
            else:
                for k, v in node.items():
                    if k not in ('kind', 'name', 'addr'):
                        self._collect_classes(v)
        elif isinstance(node, list):
            for item in node:
                self._collect_classes(item)
    
    def _process_class(self, node: dict):
        """处理 ClassType 节点"""
        cls_name = node.get('name', '')
        if not cls_name:
            return
        
        full_path = f"{self._current_pkg}.{cls_name}" if self._current_pkg else cls_name
        addr = str(node.get('addr', ''))
        
        self._addr_to_class[addr] = full_path
        self._addr_to_name[addr] = cls_name
        
        # baseClass
        base_class = None
        base_class_addr = None
        base_str = node.get('baseClass', '')
        if base_str:
            # baseClass 格式: "6338699674504 base_packet"
            match = re.match(r'(\d+)\s+(\w+)', str(base_str))
            if match:
                base_class_addr = match.group(1)
                base_cls_name = match.group(2)
                # 查找父类 full_path
                if base_class_addr in self._addr_to_class:
                    base_class = self._addr_to_class[base_class_addr]
                else:
                    # 父类可能还没处理, 先用包名推断
                    base_class = f"{self._current_pkg}.{base_cls_name}" if self._current_pkg else base_cls_name
        
        info = ClassInfo(
            name=cls_name,
            full_path=full_path,
            is_abstract=node.get('isAbstract', False),
            base_class=base_class,
            base_class_addr=base_class_addr,
        )
        self.classes[full_path] = info
        
        # 处理成员
        for member in node.get('members', []):
            kind = member.get('kind', '')
            if kind == 'ClassProperty':
                self._process_class_property(member, full_path)
            # ConstraintBlock 在第二遍处理
    
    def _process_class_property(self, node: dict, class_path: str):
        """处理 ClassProperty 节点"""
        var_name = node.get('name', '')
        if not var_name:
            return
        
        full_path = f"{class_path}.{var_name}"
        addr = str(node.get('addr', ''))
        
        # 保留首次映射 (父类变量), 不覆盖
        if addr not in self._addr_to_var:
            self._addr_to_var[addr] = full_path
        if addr not in self._addr_to_name:
            self._addr_to_name[addr] = var_name
        
        # 跟踪所有拥有此变量的类
        if addr not in self._addr_to_owning_classes:
            self._addr_to_owning_classes[addr] = []
        if class_path not in self._addr_to_owning_classes[addr]:
            self._addr_to_owning_classes[addr].append(class_path)
        
        type_str = node.get('type', '')
        rand_mode = node.get('randMode', 'none')
        
        # 解析位宽
        msb, lsb, bit_width, is_dynamic = self._parse_type(type_str)
        
        # 检查类型是否是 class instance
        type_class = self._resolve_type_class(type_str)
        
        info = VariableInfo(
            name=var_name,
            full_path=full_path,
            class_name=class_path,
            type_str=type_str,
            rand_mode=rand_mode,
            msb=msb,
            lsb=lsb,
            bit_width=bit_width,
            is_dynamic=is_dynamic,
            type_class=type_class,
        )
        self.variables[full_path] = info
    
    def _parse_type(self, type_str: str) -> Tuple[Optional[int], Optional[int], Optional[int], bool]:
        """解析类型字符串, 提取位宽信息"""
        is_dynamic = '$[]' in type_str or '[]' in type_str
        
        # bit[N:0] 或 logic[N:0]
        m = re.search(r'(?:bit|logic|reg|wire)\[(\d+):(\d+)\]', type_str)
        if m:
            msb = int(m.group(1))
            lsb = int(m.group(2))
            width = abs(msb - lsb) + 1
            return msb, lsb, width, is_dynamic
        
        # bit[N] (单维度)
        m = re.search(r'(?:bit|logic|reg|wire)\[(\d+)\]', type_str)
        if m:
            w = int(m.group(1))
            return w, 0, w + 1, is_dynamic
        
        # int, byte, shortint, longint
        width_map = {'byte': 8, 'shortint': 16, 'int': 32, 'longint': 64, 'integer': 32}
        for kw, w in width_map.items():
            if kw in type_str:
                return w - 1, 0, w, is_dynamic
        
        return None, None, None, is_dynamic
    
    def _resolve_type_class(self, type_str: str) -> Optional[str]:
        """如果类型是 class instance, 返回类 full_path"""
        # type_str 格式: "6338699682424 eth_packet"
        m = re.match(r'(\d+)\s+(\w+)', type_str)
        if m:
            addr = m.group(1)
            cls_name = m.group(2)
            if addr in self._addr_to_class:
                return self._addr_to_class[addr]
            # 可能是同一个包内的类
            if self._current_pkg:
                candidate = f"{self._current_pkg}.{cls_name}"
                if candidate in self.classes:
                    return candidate
        return None
    
    # ================================================================
    # 第二遍：收集约束和变量引用
    # ================================================================
    
    def _collect_constraints(self, node: Any, class_path: str = ''):
        """遍历 AST 收集 ConstraintBlock 节点"""
        if isinstance(node, dict):
            if node.get('kind') == 'Package':
                old_pkg = self._current_pkg
                self._current_pkg = node.get('name', '')
                for member in node.get('members', []):
                    self._collect_constraints(member)
                self._current_pkg = old_pkg
            elif node.get('kind') == 'ClassType':
                cls_name = node.get('name', '')
                full_path = f"{self._current_pkg}.{cls_name}" if self._current_pkg else cls_name
                for member in node.get('members', []):
                    if member.get('kind') == 'ConstraintBlock':
                        self._process_constraint_block(member, full_path)
            else:
                for k, v in node.items():
                    if k not in ('kind',):
                        self._collect_constraints(v, class_path)
        elif isinstance(node, list):
            for item in node:
                self._collect_constraints(item, class_path)
    
    def _process_constraint_block(self, node: dict, class_path: str):
        """处理 ConstraintBlock 节点"""
        cname = node.get('name', '')
        if not cname:
            return
        
        full_path = f"{class_path}.{cname}"
        
        # 检查 soft
        has_soft = self._check_soft(node)
        
        # 检查是否是条件约束
        is_conditional = self._check_conditional(node)
        
        # 提取所有变量引用
        var_refs = self._extract_var_refs(node, class_path)
        
        # 计算表达式数量
        expr_count = self._count_expressions(node)
        
        # 约束体内容
        constraints_node = node.get('constraints', {})
        constraint_body = self._constraint_to_string(constraints_node)
        
        info = ConstraintInfo(
            name=cname,
            full_path=full_path,
            class_name=class_path,
            expr_count=expr_count,
            has_soft=has_soft,
            is_conditional=is_conditional,
            bound_vars=var_refs,
            constraint_body=constraint_body,
        )
        self.constraints[full_path] = info
    
    def _check_soft(self, node: Any) -> bool:
        """检查约束中是否有 soft 表达式"""
        if isinstance(node, dict):
            if node.get('isSoft') is True:
                return True
            for k, v in node.items():
                if self._check_soft(v):
                    return True
        elif isinstance(node, list):
            for item in node:
                if self._check_soft(item):
                    return True
        return False
    
    def _check_conditional(self, node: Any) -> bool:
        """检查约束中是否包含 Conditional 节点"""
        if isinstance(node, dict):
            if node.get('kind') == 'Conditional':
                return True
            for k, v in node.items():
                if k != 'kind' and self._check_conditional(v):
                    return True
        elif isinstance(node, list):
            for item in node:
                if self._check_conditional(item):
                    return True
        return False
    
    def _count_expressions(self, node: Any) -> int:
        """计算约束中的表达式数量"""
        count = 0
        if isinstance(node, dict):
            if node.get('kind') == 'Expression':
                count += 1
            for k, v in node.items():
                if k != 'kind':
                    count += self._count_expressions(v)
        elif isinstance(node, list):
            for item in node:
                count += self._count_expressions(item)
        return count
    
    def _extract_var_refs(self, node: dict, class_path: str) -> List[VarRef]:
        """从 ConstraintBlock 提取所有变量引用"""
        refs: List[VarRef] = []
        seen: Set[str] = set()  # 去重 (var_path, bit_range, access_path)
        
        constraints_node = node.get('constraints', {})
        self._walk_constraint_expr(constraints_node, class_path, refs, seen, 
                                    is_conditional=False, condition='', parent_context='')
        
        return refs
    
    def _constraint_to_string(self, node: Any) -> str:
        """将约束表达式子树转换为可读字符串"""
        if not node:
            return ''
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'List':
                items = [self._constraint_to_string(item) for item in node.get('list', [])]
                return '; '.join(items)
            elif kind == 'Foreach':
                loop_dims = node.get('loopDims', [])
                loop_vars = []
                for dim in loop_dims:
                    var_info = dim.get('var', {})
                    loop_vars.append(var_info.get('name', '?'))
                body = self._constraint_to_string(node.get('body', {}))
                return f"foreach (...[{', '.join(loop_vars)}]) {{ {body} }}"
            
            elif kind == 'SolveBefore':
                solve_list = node.get('solve', [])
                after_list = node.get('after', [])
                solves = [self._expr_to_string(n) for n in solve_list]
                afters = [self._expr_to_string(n) for n in after_list]
                return f"solve {', '.join(solves)} before {', '.join(afters)}"
            
            elif kind == 'Expression':
                expr = node.get('expr', {})
                return self._expr_to_string(expr)
            elif kind == 'Conditional':
                pred = self._expr_to_string(node.get('predicate', {}))
                if_body = self._constraint_to_string(node.get('ifBody', {}))
                else_body = self._constraint_to_string(node.get('elseBody', {}))
                result = f"if ({pred}) {{ {if_body} }}"
                if else_body:
                    result += f" else {{ {else_body} }}"
                return result
            else:
                return self._expr_to_string(node)
        elif isinstance(node, list):
            return '; '.join(self._constraint_to_string(item) for item in node)
        return ''
    
    def _walk_constraint_expr(
        self,
        node: Any,
        class_path: str,
        refs: List[VarRef],
        seen: Set[str],
        is_conditional: bool,
        condition: str,
        parent_context: str,
        current_expr_str: str = '',
    ):
        """递归遍历约束表达式树"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind == 'Expression':
                # 捕获当前表达式文本, 传递给子节点作为 direct_expr
                expr_str = self._expr_to_string(node.get('expr', {}))
                for k, v in node.items():
                    if k not in ('kind', 'isSoft'):
                        self._walk_constraint_expr(v, class_path, refs, seen,
                                                    is_conditional, condition, parent_context,
                                                    current_expr_str=expr_str)
            
            elif kind == 'Conditional':
                # 提取条件
                predicate = node.get('predicate', {})
                cond_str = self._expr_to_string(predicate)
                
                # 遍历 predicate 中的变量引用
                self._walk_constraint_expr(predicate, class_path, refs, seen,
                                            is_conditional=True, condition='',
                                            parent_context=parent_context,
                                            current_expr_str=current_expr_str)
                
                # if 分支
                if_body = node.get('ifBody', {})
                if_body_str = self._constraint_to_string(if_body)
                if_ctx = f"if ({cond_str}) {{ {if_body_str} }}"
                full_ctx = f"{parent_context}{if_ctx}" if parent_context else if_ctx
                self._walk_constraint_expr(if_body, class_path, refs, seen,
                                            is_conditional=True, condition=cond_str,
                                            parent_context=full_ctx + " ",
                                            current_expr_str=current_expr_str)
                
                # else 分支
                else_body = node.get('elseBody', {})
                if else_body:
                    else_body_str = self._constraint_to_string(else_body)
                    else_ctx = f"else {{ {else_body_str} }}"
                    full_else_ctx = f"{parent_context}{if_ctx} {else_ctx}" if parent_context else f"{if_ctx} {else_ctx}"
                    self._walk_constraint_expr(else_body, class_path, refs, seen,
                                                is_conditional=True, condition=f"!({cond_str})",
                                                parent_context=full_else_ctx + " ",
                                                current_expr_str=current_expr_str)
            
            elif kind == 'Foreach':
                # 构建 foreach 上下文
                body = node.get('body', {})
                body_str = self._constraint_to_string(body)
                loop_dims = node.get('loopDims', [])
                loop_vars = [d.get('var', {}).get('name', '?') for d in loop_dims]
                foreach_ctx = f"foreach (...[{', '.join(loop_vars)}]) {{ {body_str} }}"
                full_ctx = f"{parent_context}{foreach_ctx}" if parent_context else foreach_ctx
                
                # 遍历 foreach 的子节点
                for k, v in node.items():
                    if k not in ('kind',):
                        self._walk_constraint_expr(v, class_path, refs, seen,
                                                    is_conditional, condition, full_ctx,
                                                    current_expr_str=body_str)
            
            elif kind == 'SolveBefore':
                # 构建 solve...before 上下文
                solve_list = node.get('solve', [])
                after_list = node.get('after', [])
                solves = [self._expr_to_string(n) for n in solve_list]
                afters = [self._expr_to_string(n) for n in after_list]
                solve_str = f"solve {', '.join(solves)} before {', '.join(afters)}"
                full_ctx = f"{parent_context}{solve_str}" if parent_context else solve_str
                
                for k, v in node.items():
                    if k not in ('kind',):
                        self._walk_constraint_expr(v, class_path, refs, seen,
                                                    is_conditional, condition, full_ctx,
                                                    current_expr_str=solve_str)
            
            elif kind == 'NamedValue':
                self._process_named_value(node, class_path, refs, seen,
                                            is_conditional, condition, parent_context,
                                            current_expr_str=current_expr_str)
            
            elif kind == 'MemberAccess':
                self._process_member_access(node, class_path, refs, seen,
                                              is_conditional, condition, parent_context,
                                              current_expr_str=current_expr_str)
            
            elif kind == 'RangeSelect':
                self._process_range_select(node, class_path, refs, seen,
                                             is_conditional, condition, parent_context,
                                             current_expr_str=current_expr_str)
            
            elif kind == 'ElementSelect':
                self._process_element_select(node, class_path, refs, seen,
                                               is_conditional, condition, parent_context,
                                               current_expr_str=current_expr_str)
            
            else:
                # 继续遍历子节点
                for k, v in node.items():
                    if k not in ('kind', 'isSoft'):
                        self._walk_constraint_expr(v, class_path, refs, seen,
                                                    is_conditional, condition, parent_context,
                                                    current_expr_str=current_expr_str)
        
        elif isinstance(node, list):
            for item in node:
                self._walk_constraint_expr(item, class_path, refs, seen,
                                            is_conditional, condition, parent_context)
    
    def _process_named_value(
        self, node: dict, class_path: str,
        refs: List[VarRef], seen: Set[str],
        is_conditional: bool, condition: str, parent_context: str,
        current_expr_str: str = ''
    ):
        """处理 NamedValue 节点 (直接变量引用)"""
        symbol = node.get('symbol', '')
        if not symbol:
            return
        
        # 解析 symbol: "6338699674760 length"
        addr, var_name = self._parse_symbol(symbol)
        if not var_name:
            return
        
        # 查找变量 full_path
        var_path = self._find_var_path(addr, var_name, class_path)
        if not var_path:
            return
        
        # 去重 key
        key = (var_path, None, '')
        if key in seen:
            return
        seen.add(key)
        
        var_info = self.variables.get(var_path)
        direct_expr = current_expr_str
        ref = VarRef(
            var_name=var_name,
            var_path=var_path,
            class_name=var_info.class_name if var_info else class_path,
            access_path='',
            target_class=var_info.class_name if var_info else '',
            bit_range=None,
            is_conditional=is_conditional,
            condition=condition,
            context=parent_context,
            direct_expr=direct_expr,
        )
        refs.append(ref)
    
    def _process_member_access(
        self, node: dict, class_path: str,
        refs: List[VarRef], seen: Set[str],
        is_conditional: bool, condition: str, parent_context: str,
        current_expr_str: str = ''
    ):
        """处理 MemberAccess 节点 (跨类访问, 如 pkt.length)"""
        value = node.get('value', {})
        member = node.get('member', '')
        
        # value 是宿主对象 (如 pkt)
        value_symbol = value.get('symbol', '')
        value_addr, value_name = self._parse_symbol(value_symbol)
        
        # member 是目标成员 (如 length)
        member_addr, member_name = self._parse_symbol(member)
        
        if not value_name or not member_name:
            return
        
        # 宿主变量
        host_var_path = self._find_var_path(value_addr, value_name, class_path)
        if not host_var_path:
            return
        
        host_var = self.variables.get(host_var_path)
        if not host_var or not host_var.type_class:
            return
        
        # 目标变量 (在宿主类中)
        target_var_path = f"{host_var.type_class}.{member_name}"
        target_var = self.variables.get(target_var_path)
        
        access_path = f"{value_name}.{member_name}"
        
        # 去重
        key = (target_var_path, None, access_path)
        if key in seen:
            return
        seen.add(key)
        
        ref = VarRef(
            var_name=member_name,
            var_path=target_var_path,
            class_name=target_var.class_name if target_var else host_var.type_class,
            access_path=access_path,
            target_class=host_var.type_class,
            bit_range=None,
            is_conditional=is_conditional,
            condition=condition,
            context=parent_context,
            direct_expr=current_expr_str,
        )
        refs.append(ref)
    
    def _process_range_select(
        self, node: dict, class_path: str,
        refs: List[VarRef], seen: Set[str],
        is_conditional: bool, condition: str, parent_context: str,
        current_expr_str: str = ''
    ):
        """处理 RangeSelect 节点 (如 ctrl_word[15:12])"""
        value = node.get('value', {})
        left_node = node.get('left', {})
        right_node = node.get('right', {})
        
        # 提取位范围
        msb = self._extract_int_literal(left_node)
        lsb = self._extract_int_literal(right_node)
        bit_range = [msb, lsb] if msb is not None and lsb is not None else None
        
        # 递归处理 value (应该是 NamedValue 或 MemberAccess)
        value_kind = value.get('kind', '')
        if value_kind == 'NamedValue':
            symbol = value.get('symbol', '')
            addr, var_name = self._parse_symbol(symbol)
            var_path = self._find_var_path(addr, var_name, class_path)
            if var_path:
                key = (var_path, str(bit_range), '')
                if key not in seen:
                    seen.add(key)
                    var_info = self.variables.get(var_path)
                    ref = VarRef(
                        var_name=var_name,
                        var_path=var_path,
                        class_name=var_info.class_name if var_info else class_path,
                        access_path='',
                        target_class=var_info.class_name if var_info else '',
                        bit_range=bit_range,
                        is_conditional=is_conditional,
                        condition=condition,
                        context=parent_context,
                        direct_expr=current_expr_str,
                    )
                    refs.append(ref)
        elif value_kind == 'MemberAccess':
            # 跨类 + 位选择: pkt.length[3:0]
            self._process_member_access_with_bit_range(
                value, class_path, refs, seen, bit_range,
                is_conditional, condition, context_stack
            )
    
    def _process_element_select(
        self, node: dict, class_path: str,
        refs: List[VarRef], seen: Set[str],
        is_conditional: bool, condition: str, parent_context: str,
        current_expr_str: str = ''
    ):
        """处理 ElementSelect 节点 (如 ctrl_word[8])"""
        value = node.get('value', {})
        selector = node.get('selector', {})
        
        bit_idx = self._extract_int_literal(selector)
        if bit_idx is not None:
            bit_range = [bit_idx, bit_idx]
        else:
            # 循环变量等非整数索引, 用字符串表示
            selector_str = self._expr_to_string(selector)
            bit_range = [selector_str, selector_str] if selector_str else None
        
        value_kind = value.get('kind', '')
        if value_kind == 'NamedValue':
            symbol = value.get('symbol', '')
            addr, var_name = self._parse_symbol(symbol)
            var_path = self._find_var_path(addr, var_name, class_path)
            if var_path:
                key = (var_path, str(bit_range), '')
                if key not in seen:
                    seen.add(key)
                    var_info = self.variables.get(var_path)
                    ref = VarRef(
                        var_name=var_name,
                        var_path=var_path,
                        class_name=var_info.class_name if var_info else class_path,
                        access_path='',
                        target_class=var_info.class_name if var_info else '',
                        bit_range=bit_range,
                        is_conditional=is_conditional,
                        condition=condition,
                        context=parent_context,
                        direct_expr=current_expr_str,
                    )
                    refs.append(ref)
    
    def _process_member_access_with_bit_range(
        self, node: dict, class_path: str,
        refs: List[VarRef], seen: Set[str],
        bit_range: Optional[List[int]],
        is_conditional: bool, condition: str, parent_context: str
    ):
        """处理 MemberAccess + 位选择"""
        value = node.get('value', {})
        member = node.get('member', '')
        
        value_symbol = value.get('symbol', '')
        value_addr, value_name = self._parse_symbol(value_symbol)
        
        member_addr, member_name = self._parse_symbol(member)
        
        if not value_name or not member_name:
            return
        
        host_var_path = self._find_var_path(value_addr, value_name, class_path)
        if not host_var_path:
            return
        
        host_var = self.variables.get(host_var_path)
        if not host_var or not host_var.type_class:
            return
        
        target_var_path = f"{host_var.type_class}.{member_name}"
        target_var = self.variables.get(target_var_path)
        
        access_path = f"{value_name}.{member_name}"
        
        key = (target_var_path, str(bit_range), access_path)
        if key in seen:
            return
        seen.add(key)
        
        ref = VarRef(
            var_name=member_name,
            var_path=target_var_path,
            class_name=target_var.class_name if target_var else host_var.type_class,
            access_path=access_path,
            target_class=host_var.type_class,
            bit_range=bit_range,
            is_conditional=is_conditional,
            condition=condition,
            context=parent_context,
            direct_expr=current_expr_str,
        )
        refs.append(ref)
    
    # ================================================================
    # 工具方法
    # ================================================================
    
    def _parse_symbol(self, symbol: str) -> Tuple[str, str]:
        """解析 symbol 字符串: '6338699674760 length' -> ('6338699674760', 'length')"""
        if not symbol:
            return '', ''
        parts = symbol.strip().split(' ', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return '', symbol
    
    def _find_var_path(self, addr: str, var_name: str, class_path: str) -> Optional[str]:
        """查找变量的 full_path"""
        # 先用地址查
        if addr and addr in self._addr_to_var:
            return self._addr_to_var[addr]
        
        # 回退: 在当前类中查找
        candidate = f"{class_path}.{var_name}"
        if candidate in self.variables:
            return candidate
        
        # 在父类中查找
        cls = self.classes.get(class_path)
        while cls and cls.base_class:
            candidate = f"{cls.base_class}.{var_name}"
            if candidate in self.variables:
                return candidate
            cls = self.classes.get(cls.base_class)
        
        return None
    
    def _extract_int_literal(self, node: dict) -> Optional[int]:
        """提取整数字面量"""
        if not node:
            return None
        kind = node.get('kind', '')
        if kind == 'IntegerLiteral':
            val_str = node.get('value', '')
            try:
                # 处理各种格式: "15", "4'hF", "8'd255", "3'b101"
                if "'" in val_str:
                    # 去掉前缀如 4'h
                    parts = val_str.split("'")
                    if len(parts) == 2:
                        radix_val = parts[1]
                        if radix_val.startswith('h'):
                            return int(radix_val[1:], 16)
                        elif radix_val.startswith('d'):
                            return int(radix_val[1:])
                        elif radix_val.startswith('b'):
                            return int(radix_val[1:], 2)
                        elif radix_val.startswith('o'):
                            return int(radix_val[1:], 8)
                return int(val_str)
            except (ValueError, IndexError):
                return None
        elif kind == 'Conversion':
            operand = node.get('operand', {})
            return self._extract_int_literal(operand)
        return None
    
    def _expr_to_string(self, node: Any) -> str:
        """将表达式节点转换为可读字符串 (简化版)"""
        if not isinstance(node, dict):
            return str(node)
        
        kind = node.get('kind', '')
        
        if kind == 'NamedValue':
            symbol = node.get('symbol', '')
            _, name = self._parse_symbol(symbol)
            if not name:
                # 可能是 Iterator 节点
                name = node.get('name', '<var>')
            return name
        
        elif kind == 'IntegerLiteral':
            return node.get('value', '')
        
        elif kind == 'BinaryOp':
            left = self._expr_to_string(node.get('left', {}))
            right = self._expr_to_string(node.get('right', {}))
            op = node.get('op', '?')
            op_map = {
                'Equality': '==', 'Inequality': '!=',
                'LessThan': '<', 'LessThanEqual': '<=',
                'GreaterThan': '>', 'GreaterThanEqual': '>=',
                'LogicalAnd': '&&', 'LogicalOr': '||',
                'BinaryAnd': '&', 'BinaryOr': '|',
                'Add': '+', 'Subtract': '-', 'Multiply': '*', 'Divide': '/',
                'Power': '**', 'Mod': '%',
                'BinaryXor': '^', 'BinaryXnor': '~^',
                'LogicalImplication': '->',
            }
            return f"{left} {op_map.get(op, op)} {right}"
        
        elif kind == 'MemberAccess':
            value = self._expr_to_string(node.get('value', {}))
            member = node.get('member', '')
            _, member_name = self._parse_symbol(member)
            return f"{value}.{member_name}"
        
        elif kind == 'Inside':
            left = self._expr_to_string(node.get('left', {}))
            range_list = node.get('rangeList', [])
            ranges = []
            for r in range_list:
                r_kind = r.get('kind', '')
                if r_kind == 'ValueRange':
                    l = self._expr_to_string(r.get('left', {}))
                    rv = self._expr_to_string(r.get('right', {}))
                    ranges.append(f"{l}:{rv}")
                else:
                    ranges.append(self._expr_to_string(r))
            return f"{left} inside {{ {', '.join(ranges)} }}"
        
        elif kind == 'RangeSelect':
            value = self._expr_to_string(node.get('value', {}))
            left = self._extract_int_literal(node.get('left', {}))
            right = self._extract_int_literal(node.get('right', {}))
            return f"{value}[{left}:{right}]"
        
        elif kind == 'ElementSelect':
            value = self._expr_to_string(node.get('value', {}))
            idx = self._extract_int_literal(node.get('selector', {}))
            if idx is None:
                idx = self._expr_to_string(node.get('selector', {}))
            return f"{value}[{idx}]"
        
        elif kind == 'Conversion':
            operand = node.get('operand', {})
            return self._expr_to_string(operand)
        
        elif kind == 'Call':
            sub = node.get('subroutine', '')
            args = [self._expr_to_string(a) for a in node.get('arguments', [])]
            return f"{sub}({', '.join(args)})"
        
        elif kind == 'UnaryOp':
            operand = self._expr_to_string(node.get('operand', {}))
            op = node.get('op', '')
            return f"{op}{operand}"
        
        return f"<{kind}>"
