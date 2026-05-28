"""
call_graph_parser.py - 从 slang AST 提取函数调用图

提取:
  - function/task 定义和调用关系
  - fork/join (join / join_any / join_none)
  - randomize() 调用标记
  - new() 构造调用
  - super 调用
"""

import json
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field


@dataclass
class MethodInfo:
    """函数/任务信息"""
    name: str
    full_path: str              # class.method
    class_name: str             # 所属类
    kind: str = 'task'          # task / function
    is_virtual: bool = False
    is_super_call: bool = False  # 是否是 super.xxx() 调用


@dataclass
class CallInfo:
    """一条调用"""
    callee: str                 # 被调用方法名
    callee_path: str = ''       # 被调用方法 full_path
    target_class: str = ''      # 目标类 (new() 时)
    is_super: bool = False      # 是否 super 调用
    is_constructor: bool = False  # 是否 new() 构造
    is_randomize: bool = False  # 是否 randomize() 调用
    is_builtin: bool = False    # 是否内置函数
    arguments: List[str] = field(default_factory=list)


@dataclass
class ForkInfo:
    """fork 块信息"""
    name: str                   # fork 块名 (自动生成)
    parent_method: str          # 所属方法
    join_type: str = 'join'     # join / join_any / join_none
    branches: List[CallInfo] = field(default_factory=list)  # fork 内的调用


class CallGraphParser:
    """
    从 slang AST JSON 提取函数调用图
    
    Usage:
        parser = CallGraphParser(ast_json_path)
        parser.parse()
        methods = parser.methods
        calls = parser.calls
        forks = parser.forks
    """
    
    def __init__(self, ast_json_path: str):
        self.ast_json_path = ast_json_path
        
        # 解析结果
        self.methods: Dict[str, MethodInfo] = {}      # full_path -> MethodInfo
        self.calls: Dict[str, List[CallInfo]] = {}     # caller_full_path -> [CallInfo]
        self.forks: Dict[str, List[ForkInfo]] = {}     # class_name -> [ForkInfo]
        self._class_info: Dict[str, Dict] = {}           # class_name -> {base_class: ...}
        
        # 别名
        self._methods = self.methods
        
        # 地址映射
        self._addr_to_method: Dict[str, str] = {}  # addr -> method full_path
        self._addr_to_class: Dict[str, str] = {}   # addr -> class full_path
        
        self._current_pkg: str = ''
        self._fork_counter: int = 0
    
    def parse(self) -> 'CallGraphParser':
        with open(self.ast_json_path) as f:
            data = json.load(f)
        self._walk(data)
        return self
    
    def _walk(self, node: Any, location: str = ''):
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind == 'Package':
                old_pkg = self._current_pkg
                self._current_pkg = node.get('name', '')
                for member in node.get('members', []):
                    self._walk(member, node.get('name', ''))
                self._current_pkg = old_pkg
            elif kind == 'ClassType':
                self._process_class(node, location)
            else:
                for v in node.values():
                    self._walk(v, location)
        elif isinstance(node, list):
            for item in node:
                self._walk(item, location)
    
    def _process_class(self, node: dict, location: str):
        """处理 ClassType 节点"""
        cls_name = node.get('name', '')
        if not cls_name:
            return
        
        full_path = f"{self._current_pkg}.{cls_name}" if self._current_pkg else cls_name
        addr = str(node.get('addr', ''))
        self._addr_to_class[addr] = full_path
        
        # 解析继承
        base_class = None
        base_str = node.get('baseClass', '')
        if base_str:
            parts = str(base_str).strip().split(' ', 1)
            if len(parts) == 2:
                base_addr = parts[0]
                base_class = self._addr_to_class.get(base_addr)
                if not base_class:
                    base_name = parts[1].strip()
                    base_class = f"{self._current_pkg}.{base_name}" if self._current_pkg else base_name
        
        self._class_info[full_path] = {'base_class': base_class}
        
        # 处理成员
        for member in node.get('members', []):
            kind = member.get('kind', '')
            if kind == 'Subroutine':
                self._process_subroutine(member, full_path)
            elif kind == 'ClassType':
                self._walk(member, full_path)
    
    def _process_subroutine(self, node: dict, class_path: str):
        """处理 Subroutine (function/task)"""
        name = node.get('name', '')
        if not name:
            return
        
        full_path = f"{class_path}.{name}"
        addr = str(node.get('addr', ''))
        self._addr_to_method[addr] = full_path
        
        method = MethodInfo(
            name=name,
            full_path=full_path,
            class_name=class_path,
            kind=node.get('subroutineKind', 'task').lower(),
            is_virtual='virtual' in node.get('flags', ''),
        )
        self.methods[full_path] = method
        
        # 解析函数体中的调用
        body = node.get('body', {})
        calls = []
        forks = []
        self._walk_body(body, full_path, calls, forks, class_path)
        
        if calls:
            self.calls[full_path] = calls
        if forks:
            if class_path not in self.forks:
                self.forks[class_path] = []
            self.forks[class_path].extend(forks)
    
    def _walk_body(self, node: Any, caller_path: str, calls: list, forks: list, class_path: str):
        """遍历函数体，提取调用和 fork"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind == 'Call':
                call = self._process_call(node, class_path)
                if call:
                    calls.append(call)
            
            elif kind == 'NewClass':
                target = node.get('type', '')
                call = CallInfo(
                    callee='new',
                    target_class=self._resolve_type(target),
                    is_constructor=True,
                )
                calls.append(call)
            
            elif kind == 'Block':
                block_kind = node.get('blockKind', '')
                if block_kind in ('Join', 'JoinAny', 'JoinNone'):
                    # fork 块
                    fork = self._process_fork(node, caller_path, class_path, block_kind)
                    forks.append(fork)
                else:
                    # 普通 block，继续遍历
                    for v in node.values():
                        self._walk_body(v, caller_path, calls, forks, class_path)
            
            else:
                for v in node.values():
                    self._walk_body(v, caller_path, calls, forks, class_path)
        
        elif isinstance(node, list):
            for item in node:
                self._walk_body(item, caller_path, calls, forks, class_path)
    
    def _process_call(self, node: dict, caller_class: str = '') -> Optional[CallInfo]:
        """处理 Call 节点"""
        sub = node.get('subroutine', '')
        
        # 解析 subroutine 地址和名称
        if ' ' in sub:
            # 有地址: "6338699675320 do_init"
            addr, name = sub.split(' ', 1)
            callee_path = self._addr_to_method.get(addr, '')
            is_randomize = name == 'randomize'
            is_builtin = False
            
            # 检查是否是 super 调用
            is_super = False
            if callee_path and caller_class:
                callee_class = callee_path.rsplit('.', 1)[0] if '.' in callee_path else ''
                if callee_class and callee_class != caller_class:
                    # 检查 callee_class 是否是 caller_class 的父类
                    cls_info = self._class_info.get(caller_class, {})
                    base = cls_info.get('base_class')
                    while base:
                        if base == callee_class:
                            is_super = True
                            break
                        base_info = self._class_info.get(base, {})
                        base = base_info.get('base_class')
        else:
            # 无地址 (内置): "randomize"
            name = sub
            callee_path = ''
            is_randomize = name == 'randomize'
            is_builtin = True
            is_super = False
        
        # 提取参数
        args = []
        for arg in node.get('arguments', []):
            arg_str = self._arg_to_string(arg)
            if arg_str:
                args.append(arg_str)
        
        return CallInfo(
            callee=name,
            callee_path=callee_path,
            is_super=is_super,
            is_randomize=is_randomize,
            is_builtin=is_builtin,
            arguments=args,
        )
    
    def _process_fork(self, node: dict, caller_path: str, class_path: str, block_kind: str) -> ForkInfo:
        """处理 fork 块"""
        self._fork_counter += 1
        join_type_map = {
            'Join': 'join',
            'JoinAny': 'join_any',
            'JoinNone': 'join_none',
        }
        
        fork = ForkInfo(
            name=f'fork_{self._fork_counter}',
            parent_method=caller_path,
            join_type=join_type_map.get(block_kind, 'join'),
        )
        
        # 收集 fork 内的调用
        body = node.get('body', {})
        self._collect_fork_calls(body, fork.branches, class_path)
        
        return fork
    
    def _collect_fork_calls(self, node: Any, branches: list, class_path: str = ''):
        """收集 fork 块内的调用"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'Call':
                call = self._process_call(node, class_path)
                if call:
                    branches.append(call)
            elif kind == 'NewClass':
                target = node.get('type', '')
                call = CallInfo(
                    callee='new',
                    target_class=self._resolve_type(target),
                    is_constructor=True,
                )
                branches.append(call)
            else:
                for v in node.values():
                    self._collect_fork_calls(v, branches)
        elif isinstance(node, list):
            for item in node:
                self._collect_fork_calls(item, branches)
    
    def _resolve_type(self, type_str: str) -> str:
        """解析类型地址为类 full_path"""
        if ' ' in type_str:
            addr = type_str.split(' ')[0]
            return self._addr_to_class.get(addr, type_str)
        return type_str
    
    def _arg_to_string(self, node: dict) -> str:
        """将参数节点转为字符串"""
        kind = node.get('kind', '')
        if kind == 'NamedValue':
            sym = node.get('symbol', '')
            if ' ' in sym:
                return sym.split(' ')[1]
            return sym
        if kind == 'IntegerLiteral':
            return node.get('constant', node.get('value', ''))
        if kind == 'Conversion':
            return self._arg_to_string(node.get('operand', {}))
        return f'<{kind}>'
