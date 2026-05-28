"""
uvm_tb_parser.py - 从 slang AST 提取 UVM testbench 静态结构

提取:
  - UVM 组件 (env/driver/monitor/scoreboard/agent/test)
  - Sequence / SequenceItem
  - 组件层级 (build_phase 中的 new/create)
  - 继承关系
  - Phase 方法
  - Sequence 使用关系
"""

import json
import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class UVMComponent:
    """UVM 组件"""
    name: str
    full_path: str
    uvm_type: str = ''            # uvm_env / uvm_driver / uvm_monitor / ...
    base_class: str = ''
    base_class_addr: str = ''
    class_name: str = ''          # 所在 class/package


@dataclass
class UVMSequence:
    """UVM Sequence"""
    name: str
    full_path: str
    base_class: str = ''
    seq_item_type: str = ''       # 关联的 sequence_item 类型
    class_name: str = ''


@dataclass
class UVMSequenceItem:
    """UVM Sequence Item"""
    name: str
    full_path: str
    base_class: str = ''
    class_name: str = ''


@dataclass
class UVMChild:
    """组件层级关系"""
    parent: str
    child: str
    child_type: str = ''
    field_name: str = ''          # 字段名 (如 drv, mon)


@dataclass
class UVMPhase:
    """Phase 方法"""
    name: str                     # build_phase / connect_phase / run_phase
    class_name: str


@dataclass
class UVMSequenceUsage:
    """Sequence 使用关系"""
    user: str                     # 使用 sequence 的类
    sequence: str                 # 被使用的 sequence
    method: str = ''              # new / start / body


@dataclass
class UVMPortConnection:
    """端口连接"""
    source: str           # 如 axi_agt.mon.ap
    target: str           # 如 sb.axi_imp
    source_class: str = ''
    target_class: str = ''


class UVMTestbenchParser:
    """
    从 slang AST JSON 提取 UVM testbench 静态结构
    
    Usage:
        parser = UVMTestbenchParser(ast_json_path)
        parser.parse()
        components = parser.components
    """
    
    # UVM 基类名
    UVM_COMPONENT_BASES = {
        'uvm_object', 'uvm_component', 'uvm_env', 'uvm_test',
        'uvm_driver', 'uvm_monitor', 'uvm_scoreboard', 'uvm_agent',
    }
    UVM_SEQUENCE_BASES = {'uvm_sequence', 'uvm_sequence_item'}
    
    def __init__(self, ast_json_path: str):
        self.ast_json_path = ast_json_path
        
        self.components: Dict[str, UVMComponent] = {}
        self.sequences: Dict[str, UVMSequence] = {}
        self.sequence_items: Dict[str, UVMSequenceItem] = {}
        self.children: Dict[str, List[UVMChild]] = {}  # parent_path -> [UVMChild]
        self.phases: Dict[str, List[UVMPhase]] = {}    # class_path -> [UVMPhase]
        self.sequence_usages: List[UVMSequenceUsage] = []
        self.port_connections: List[UVMPortConnection] = []
        
        # 地址映射
        self._addr_to_class: Dict[str, str] = {}
        self._addr_to_name: Dict[str, str] = {}
        
        self._current_pkg: str = ''
    
    def parse(self) -> 'UVMTestbenchParser':
        with open(self.ast_json_path) as f:
            data = json.load(f)
        self._walk(data)
        return self
    
    def _walk(self, node: Any, location: str = ''):
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'Package':
                self._current_pkg = node.get('name', '')
                for member in node.get('members', []):
                    self._walk(member, node.get('name', ''))
                self._current_pkg = ''
            elif kind == 'ClassType':
                self._process_class(node, location)
            else:
                for v in node.values():
                    self._walk(v, location)
        elif isinstance(node, list):
            for item in node:
                self._walk(item, location)
    
    def _process_class(self, node: dict, location: str):
        cls_name = node.get('name', '')
        if not cls_name:
            return
        
        full_path = f"{self._current_pkg}.{cls_name}" if self._current_pkg else cls_name
        addr = str(node.get('addr', ''))
        self._addr_to_class[addr] = full_path
        self._addr_to_name[addr] = cls_name
        
        # 解析 baseClass
        base_class = ''
        base_addr = ''
        base_str = node.get('baseClass', '')
        if base_str:
            match = re.match(r'(\d+)\s+(.+)', str(base_str))
            if match:
                base_addr = match.group(1)
                base_name = match.group(2).strip()
                # 处理泛型: uvm_sequence#(my_transaction) -> uvm_sequence
                base_name_clean = re.sub(r'#\(.*\)', '', base_name)
                base_class = self._addr_to_class.get(base_addr, base_name_clean)
        
        # 判断组件类型
        uvm_type = self._classify_uvm_type(base_class, cls_name)
        
        # 提取 sequence_item 类型 (如果是 uvm_sequence#(T))
        seq_item_type = ''
        if 'uvm_sequence' in base_class and '#' in str(base_str):
            match = re.search(r'#\(\d+\s+(\w+)', str(base_str))
            if match:
                seq_item_type = match.group(1)
        
        # 创建组件/序列
        if uvm_type in ('uvm_env', 'uvm_test', 'uvm_driver', 'uvm_monitor',
                        'uvm_scoreboard', 'uvm_agent', 'uvm_component'):
            comp = UVMComponent(
                name=cls_name,
                full_path=full_path,
                uvm_type=uvm_type,
                base_class=base_class,
                base_class_addr=base_addr,
                class_name=full_path,
            )
            self.components[full_path] = comp
        elif uvm_type == 'uvm_sequence':
            seq = UVMSequence(
                name=cls_name,
                full_path=full_path,
                base_class=base_class,
                seq_item_type=seq_item_type,
                class_name=full_path,
            )
            self.sequences[full_path] = seq
        elif uvm_type == 'uvm_sequence_item':
            item = UVMSequenceItem(
                name=cls_name,
                full_path=full_path,
                base_class=base_class,
                class_name=full_path,
            )
            self.sequence_items[full_path] = item
        
        # 处理成员
        for member in node.get('members', []):
            kind = member.get('kind', '')
            if kind == 'Subroutine':
                self._process_subroutine(member, full_path, cls_name)
            elif kind == 'ClassProperty':
                self._process_class_property(member, full_path, cls_name)
    
    def _classify_uvm_type(self, base_class: str, cls_name: str) -> str:
        """根据继承链判断 UVM 类型"""
        # 优先检查 sequence_item (先于 sequence)
        if 'uvm_sequence_item' in base_class:
            return 'uvm_sequence_item'
        # 再检查 sequence
        if 'uvm_sequence' in base_class:
            return 'uvm_sequence'
        # 检查组件基类
        for base in self.UVM_COMPONENT_BASES:
            if base in base_class:
                return base
        
        # 递归检查已解析的类
        if base_class in self.components:
            return self.components[base_class].uvm_type
        if base_class in self.sequences:
            return 'uvm_sequence'
        if base_class in self.sequence_items:
            return 'uvm_sequence_item'
        
        return ''
    
    def _process_subroutine(self, node: dict, class_path: str, cls_name: str):
        """处理 Subroutine 节点"""
        name = node.get('name', '')
        
        # 识别 phase 方法
        if name.endswith('_phase'):
            phase = UVMPhase(name=name, class_name=class_path)
            if class_path not in self.phases:
                self.phases[class_path] = []
            self.phases[class_path].append(phase)
        
        # 分析 build_phase 中的 new() 调用 → 组件创建
        if name == 'build_phase':
            body = node.get('body', {})
            self._find_component_creates(body, class_path)
        
        # 分析 run_phase 中的 sequence 使用
        if name == 'run_phase':
            body = node.get('body', {})
            self._find_sequence_usages(body, class_path, cls_name)
        
        # 分析 connect_phase 中的端口连接
        if name == 'connect_phase':
            body = node.get('body', {})
            self._find_port_connections(body, class_path, cls_name)
    
    def _process_class_property(self, node: dict, class_path: str, cls_name: str):
        """处理 ClassProperty 节点"""
        prop_name = node.get('name', '')
        prop_type = node.get('type', '')
        
        if not prop_name or prop_name.startswith('_'):
            return
        
        # 检查类型是否是 UVM 组件
        type_class = self._resolve_type_class(prop_type)
        if type_class:
            child = UVMChild(
                parent=cls_name,
                child=type_class.split('.')[-1] if '.' in type_class else type_class,
                child_type='',
                field_name=prop_name,
            )
            if class_path not in self.children:
                self.children[class_path] = []
            self.children[class_path].append(child)
    
    def _find_component_creates(self, body: dict, class_path: str):
        """在 build_phase 中查找组件创建 (new() 调用)"""
        self._walk_for_new(body, class_path)
    
    def _walk_for_new(self, node: Any, class_path: str):
        """遍历查找 new() 调用"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'NewClass':
                # new("name", this) 调用
                type_str = node.get('type', '')
                target_class = self._resolve_type_class(type_str)
                if target_class:
                    # 查找父组件名
                    parent_name = class_path.split('.')[-1] if '.' in class_path else class_path
                    child_name = target_class.split('.')[-1] if '.' in target_class else target_class
                    
                    child = UVMChild(
                        parent=parent_name,
                        child=child_name,
                        child_type='',
                        field_name='',
                    )
                    if class_path not in self.children:
                        self.children[class_path] = []
                    # 避免重复
                    existing = {(c.child, c.field_name) for c in self.children[class_path]}
                    if (child_name, '') not in existing:
                        self.children[class_path].append(child)
            
            for v in node.values():
                self._walk_for_new(v, class_path)
        elif isinstance(node, list):
            for item in node:
                self._walk_for_new(item, class_path)
    
    def _find_sequence_usages(self, body: dict, class_path: str, cls_name: str):
        """在 run_phase 中查找 sequence 使用"""
        self._walk_for_seq(body, class_path, cls_name)
    
    def _walk_for_seq(self, node: Any, class_path: str, cls_name: str):
        """遍历查找 sequence 创建"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            if kind == 'NewClass':
                type_str = node.get('type', '')
                seq_class = self._resolve_type_class(type_str)
                if seq_class:
                    seq_name = seq_class.split('.')[-1] if '.' in seq_class else seq_class
                    # 检查是否是 sequence 类型
                    if seq_class in self.sequences or any(s.base_class for s in self.sequences.values()):
                        usage = UVMSequenceUsage(
                            user=cls_name,
                            sequence=seq_name,
                            method='new',
                        )
                        self.sequence_usages.append(usage)
            
            for v in node.values():
                self._walk_for_seq(v, class_path, cls_name)
        elif isinstance(node, list):
            for item in node:
                self._walk_for_seq(item, class_path, cls_name)
    
    def _resolve_type_class(self, type_str: str) -> str:
        """解析类型地址为类 full_path"""
        if not type_str:
            return ''
        match = re.match(r'(\d+)\s+(.+)', str(type_str))
        if match:
            addr = match.group(1)
            name = match.group(2).strip()
            name = re.sub(r'#\(.*\)', '', name)
            return self._addr_to_class.get(addr, name)
        return type_str
    
    def _find_port_connections(self, body: dict, class_path: str, cls_name: str):
        """在 connect_phase 中查找 port.connect() 调用"""
        self._walk_for_connect(body, class_path, cls_name)
    
    def _walk_for_connect(self, node: Any, class_path: str, cls_name: str):
        """遍历查找 .connect() 调用
        
        AST 结构: MemberAccess(source) + Call(connect, target) 是兄弟节点
        需要先收集所有 MemberAccess，再匹配 connect 调用
        """
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind == 'List':
                # 在 List 中查找 connect 调用和对应的 MemberAccess
                items = node.get('list', [])
                self._find_connect_in_list(items, class_path, cls_name)
            
            for v in node.values():
                self._walk_for_connect(v, class_path, cls_name)
        elif isinstance(node, list):
            for item in node:
                self._walk_for_connect(item, class_path, cls_name)
    
    def _find_connect_in_list(self, items: list, class_path: str, cls_name: str):
        """在 List 中匹配 connect 调用"""
        for item in items:
            call_node = None
            if item.get('kind') == 'Call' and 'connect' in str(item.get('subroutine', '')):
                call_node = item
            elif item.get('kind') == 'ExpressionStatement':
                expr = item.get('expr', {})
                if expr.get('kind') == 'Call' and 'connect' in str(expr.get('subroutine', '')):
                    call_node = expr
            
            if call_node:
                source, target = self._extract_connect_parts(call_node)
                if source or target:
                    conn = UVMPortConnection(
                        source=source,
                        target=target,
                        source_class=cls_name,
                    )
                    self.port_connections.append(conn)
    
    def _extract_connect_parts(self, call_node: dict) -> Tuple[str, str]:
        """从 connect() Call 节点提取 source 和 target 路径
        
        结构: Call(thisClass=MemberAccess(source), arguments=[Conversion(target)])
        """
        source = ''
        target = ''
        
        # source: thisClass
        this_class = call_node.get('thisClass', {})
        if this_class.get('kind') == 'MemberAccess':
            source = self._member_access_to_path(this_class)
        
        # target: arguments[0]
        arguments = call_node.get('arguments', [])
        if arguments:
            arg = arguments[0]
            kind = arg.get('kind', '')
            if kind == 'Conversion':
                inner = arg.get('operand', {})
                if inner.get('kind') == 'MemberAccess':
                    target = self._member_access_to_path(inner)
                elif inner.get('kind') == 'NamedValue':
                    sym = inner.get('symbol', '')
                    target = sym.split(' ')[-1] if ' ' in sym else sym
            elif kind == 'MemberAccess':
                target = self._member_access_to_path(arg)
            elif kind == 'NamedValue':
                sym = arg.get('symbol', '')
                target = sym.split(' ')[-1] if ' ' in sym else sym
        
        return source, target
    
    def _call_arg_to_path(self, node: dict) -> str:
        """将 Call 参数转为路径字符串 (如 sb.axi_imp)"""
        kind = node.get('kind', '')
        if kind == 'MemberAccess':
            return self._member_access_to_path(node)
        if kind == 'NamedValue':
            sym = node.get('symbol', '')
            if ' ' in sym:
                return sym.split(' ')[1]
            return sym
        return ''
    
    def _member_access_to_path(self, node: dict) -> str:
        """将 MemberAccess 转为路径字符串 (如 axi_agt.mon.ap)"""
        kind = node.get('kind', '')
        if kind == 'MemberAccess':
            value_path = self._member_access_to_path(node.get('value', {}))
            member = node.get('member', '')
            if ' ' in member:
                member_name = member.split(' ')[1]
            else:
                member_name = member
            if value_path:
                return f'{value_path}.{member_name}'
            return member_name
        if kind == 'NamedValue':
            sym = node.get('symbol', '')
            if ' ' in sym:
                return sym.split(' ')[1]
            return sym
        return ''
        if not type_str:
            return ''
        match = re.match(r'(\d+)\s+(.+)', str(type_str))
        if match:
            addr = match.group(1)
            name = match.group(2).strip()
            # 去掉泛型参数
            name = re.sub(r'#\(.*\)', '', name)
            return self._addr_to_class.get(addr, name)
        return type_str
