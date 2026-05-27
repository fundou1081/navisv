"""
covergroup_parser.py - 从 slang AST JSON 提取 covergroup 信息

职责:
  1. 解析 CovergroupType 节点 → 提取 covergroup
  2. 解析 Coverpoint 节点 → 提取 coverpoint 和 bins
  3. 解析 CoverCross 节点 → 提取 cross 和 cross bins
  4. 解析 CoverageBin 节点 → 提取 bins/illegal_bins/ignore_bins
  5. 提取 sample 事件和 option
"""

import json
import re
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class BinInfo:
    """CoverageBin 信息"""
    name: str
    kind: str                    # Bins / IllegalBins / IgnoreBins
    values: List[Tuple[int, int]] = field(default_factory=list)  # [(low, high), ...]
    is_wildcard: bool = False
    is_default: bool = False
    cross_select: Optional[Dict] = None  # cross 条件 (如有)


@dataclass
class CoverpointInfo:
    """Coverpoint 信息"""
    name: str
    full_path: str               # covergroup.coverpoint
    covergroup: str              # 所属 covergroup 名
    bins: List[BinInfo] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossInfo:
    """CoverCross 信息"""
    name: str
    full_path: str
    covergroup: str
    targets: List[str] = field(default_factory=list)  # coverpoint 名列表
    bins: List[BinInfo] = field(default_factory=list)


@dataclass
class CovergroupInfo:
    """Covergroup 信息"""
    name: str
    full_path: str               # module_or_class.covergroup
    location: str = ''           # 所在 module 或 class
    coverpoints: List[CoverpointInfo] = field(default_factory=list)
    crosses: List[CrossInfo] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)
    sample_event: Optional[Dict] = None  # {'edge': 'PosEdge', 'signal': 'clk'}


class CovergroupParser:
    """
    从 slang AST JSON 解析 covergroup 信息
    
    Usage:
        parser = CovergroupParser(ast_json_path)
        parser.parse()
        covergroups = parser.covergroups
    """
    
    def __init__(self, ast_json_path: str):
        self.ast_json_path = ast_json_path
        self.covergroups: Dict[str, CovergroupInfo] = {}  # name -> CovergroupInfo
    
    def parse(self) -> 'CovergroupParser':
        """解析 AST JSON"""
        with open(self.ast_json_path) as f:
            data = json.load(f)
        self._walk(data)
        return self
    
    def _walk(self, node: Any, location: str = ''):
        """遍历 AST"""
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind in ('Module', 'ClassType', 'Package'):
                location = node.get('name', location)
            
            if kind == 'CovergroupType':
                self._process_covergroup(node, location)
            
            # 处理 class/module 成员顺序: CovergroupType 后跟 ClassProperty
            if kind in ('ClassType', 'Module'):
                members = node.get('members', [])
                self._process_members_with_covergroups(members, location)
            else:
                for v in node.values():
                    self._walk(v, location)
        
        elif isinstance(node, list):
            for item in node:
                self._walk(item, location)
    
    def _process_members_with_covergroups(self, members: list, location: str):
        """处理成员列表, 将匿名 CovergroupType 与后续 ClassProperty 关联"""
        pending_cg = None  # 待命名的 CovergroupType
        
        for member in members:
            kind = member.get('kind', '')
            name = member.get('name', '')
            
            if kind == 'CovergroupType':
                if name:
                    # 有名称, 直接处理
                    self._process_covergroup(member, location)
                    pending_cg = None
                else:
                    # 无名称, 等待后续 ClassProperty 提供名称
                    pending_cg = member
            
            elif kind == 'ClassProperty' and pending_cg is not None:
                # 检查这个 ClassProperty 的类型是否是 covergroup 类型
                type_str = member.get('type', '')
                # covergroup 类型的 ClassProperty
                if name and not name.startswith('_'):
                    self._process_covergroup_with_name(pending_cg, name, location)
                    pending_cg = None
            
            elif kind in ('ClassType', 'Module', 'Package'):
                # 递归处理嵌套的 class/module
                self._walk(member, location)
                pending_cg = None
            
            else:
                # 其他成员, 递归处理
                if kind not in ('ClassProperty',):
                    self._walk(member, location)
                # 如果遇到非 ClassProperty 成员, pending_cg 不清除
    
    def _process_covergroup_with_name(self, node: dict, cg_name: str, location: str):
        """处理 CovergroupType 节点 (带指定名称)"""
        full_path = f"{location}.{cg_name}" if location else cg_name
        
        info = CovergroupInfo(
            name=cg_name,
            full_path=full_path,
            location=location,
        )
        
        for member in node.get('members', []):
            if member.get('kind') == 'CovergroupBody':
                self._process_body(member, info)
        
        self.covergroups[full_path] = info
    
    def _process_covergroup(self, node: dict, location: str):
        """处理 CovergroupType 节点"""
        name = node.get('name', '')
        if not name:
            return
        
        full_path = f"{location}.{name}" if location else name
        
        info = CovergroupInfo(
            name=name,
            full_path=full_path,
            location=location,
        )
        
        # 处理 CovergroupBody
        for member in node.get('members', []):
            if member.get('kind') == 'CovergroupBody':
                self._process_body(member, info)
        
        self.covergroups[full_path] = info
    
    def _process_body(self, node: dict, cg_info: CovergroupInfo):
        """处理 CovergroupBody 节点"""
        for member in node.get('members', []):
            kind = member.get('kind', '')
            name = member.get('name', '')
            
            if kind == 'ClassProperty' and name == 'option':
                cg_info.options = self._parse_option(member)
            
            elif kind == 'Coverpoint':
                cp = self._process_coverpoint(member, cg_info.name)
                cg_info.coverpoints.append(cp)
            
            elif kind == 'CoverCross':
                cross = self._process_cover_cross(member, cg_info.name)
                cg_info.crosses.append(cross)
        
        # 提取 sample 事件 (如果有 Definition -> Instance -> InstanceBody -> SignalEvent)
        # 需要从更外层查找
    
    def _process_coverpoint(self, node: dict, cg_name: str) -> CoverpointInfo:
        """处理 Coverpoint 节点"""
        name = node.get('name', '')
        full_path = f"{cg_name}.{name}"
        
        cp = CoverpointInfo(
            name=name,
            full_path=full_path,
            covergroup=cg_name,
        )
        
        for member in node.get('members', []):
            kind = member.get('kind', '')
            mname = member.get('name', '')
            
            if kind == 'ClassProperty' and mname == 'option':
                cp.options = self._parse_option(member)
            
            elif kind == 'CoverageBin':
                bin_info = self._process_bin(member)
                cp.bins.append(bin_info)
        
        return cp
    
    def _process_cover_cross(self, node: dict, cg_name: str) -> CrossInfo:
        """处理 CoverCross 节点"""
        name = node.get('name', '')
        full_path = f"{cg_name}.{name}"
        
        # 提取 targets
        targets = []
        for target in node.get('targets', []):
            cp_ref = target.get('coverpoint', '')
            # 格式: "addr name"
            parts = cp_ref.split(' ')
            if len(parts) >= 2:
                targets.append(parts[-1])
        
        cross = CrossInfo(
            name=name,
            full_path=full_path,
            covergroup=cg_name,
            targets=targets,
        )
        
        # 提取 CoverCrossBody 中的 bins
        for member in node.get('members', []):
            if member.get('kind') == 'CoverCrossBody':
                for body_member in member.get('members', []):
                    if body_member.get('kind') == 'CoverageBin':
                        bin_info = self._process_bin(body_member)
                        cross.bins.append(bin_info)
        
        return cross
    
    def _process_bin(self, node: dict) -> BinInfo:
        """处理 CoverageBin 节点"""
        name = node.get('name', '')
        bins_kind = node.get('binsKind', 'Bins')
        is_wildcard = node.get('isWildcard', False)
        is_default = node.get('isDefault', False)
        
        # 提取值
        values = []
        for val_node in node.get('values', []):
            val = self._extract_value(val_node)
            if val is not None:
                values.append(val)
        
        # 提取 crossSelect (如有)
        cross_select = None
        if 'crossSelect' in node:
            cross_select = self._parse_cross_select(node['crossSelect'])
        
        return BinInfo(
            name=name,
            kind=bins_kind,
            values=values,
            is_wildcard=is_wildcard,
            is_default=is_default,
            cross_select=cross_select,
        )
    
    def _extract_value(self, node: dict) -> Optional[Tuple[int, int]]:
        """提取值或值范围为 (low, high) 元组"""
        kind = node.get('kind', '')
        
        if kind == 'ValueRange':
            left = self._extract_int(node.get('left', {}))
            right = self._extract_int(node.get('right', {}))
            if left is not None and right is not None:
                return (min(left, right), max(left, right))
        
        elif kind == 'IntegerLiteral':
            val = self._extract_int(node)
            if val is not None:
                return (val, val)
        
        elif kind == 'Conversion':
            # 递归到 operand
            operand = node.get('operand', {})
            return self._extract_value(operand)
        
        # 常量字段
        const = node.get('constant', '')
        if const:
            val = self._parse_constant(const)
            if val is not None:
                return (val, val)
        
        return None
    
    def _extract_int(self, node: dict) -> Optional[int]:
        """从节点提取整数值"""
        kind = node.get('kind', '')
        
        if kind == 'IntegerLiteral':
            return self._parse_constant(node.get('value', ''))
        
        elif kind == 'Conversion':
            return self._extract_int(node.get('operand', {}))
        
        # 直接从 constant 字段
        const = node.get('constant', '')
        if const:
            return self._parse_constant(const)
        
        return None
    
    def _parse_constant(self, const: str) -> Optional[int]:
        """解析常量字符串 (如 8'd255, 4'hF, 2'b10)"""
        if not const:
            return None
        
        try:
            if "'" in const:
                parts = const.split("'")
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
            return int(const)
        except (ValueError, IndexError):
            return None
    
    def _parse_option(self, node: dict) -> Dict[str, Any]:
        """解析 option ClassProperty"""
        # option 的值在 type 字段中以 struct 定义
        # 实际赋值需要从更上层获取
        # 这里先返回空, 后续从 Assignment 节点获取
        return {}
    
    def _parse_cross_select(self, node: dict) -> Dict:
        """解析 crossSelect 条件"""
        kind = node.get('kind', '')
        if kind == 'Condition':
            target = node.get('target', '')
            parts = target.split(' ')
            return {'type': 'binsof', 'bin': parts[-1] if len(parts) >= 2 else target}
        elif kind == 'Binary':
            left = self._parse_cross_select(node.get('left', {}))
            right = self._parse_cross_select(node.get('right', {}))
            op = node.get('op', 'and')
            return {'type': 'binary', 'op': op, 'left': left, 'right': right}
        return {}
