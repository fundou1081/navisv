"""
covergroup_analyzer.py - Covergroup 查询 API

基于 CovergroupParser 的解析结果, 提供查询接口:
  - get_covergroups(): 列出所有 covergroup
  - get_coverpoints(cg_name): 获取 covergroup 的 coverpoint 列表
  - get_bins(cg_name, cp_name): 获取 coverpoint 的 bins
  - get_crosses(cg_name): 获取 covergroup 的 cross
  - get_options(cg_name): 获取 covergroup 的 option
  - get_sample_event(cg_name): 获取 sample 事件
"""

from typing import Dict, List, Optional, Any, Tuple

from navisv.parsers.covergroup_parser import (
    CovergroupParser, CovergroupInfo, CoverpointInfo, CrossInfo, BinInfo
)


class CovergroupAnalyzer:
    """
    Covergroup 查询接口
    """
    
    def __init__(self, parser: CovergroupParser, constraint_graph=None):
        self._parser = parser
        self._constraint_graph = constraint_graph
    
    def get_covergroups(self) -> List[Dict[str, Any]]:
        """获取所有 covergroup"""
        result = []
        for name, info in self._parser.covergroups.items():
            result.append({
                'name': info.name,
                'full_path': info.full_path,
                'location': info.location,
                'coverpoint_count': len(info.coverpoints),
                'cross_count': len(info.crosses),
            })
        return result
    
    def get_coverpoints(self, cg_name: str) -> List[Dict[str, Any]]:
        """获取 covergroup 的所有 coverpoint (按名称查找)"""
        info = self._find_covergroup(cg_name)
        if not info:
            return []
        return [self._coverpoint_to_dict(cp) for cp in info.coverpoints]
    
    def get_coverpoints_by_cg(self, cg_name: str) -> List[Dict[str, Any]]:
        """按 covergroup 精确名查找 coverpoint"""
        # 先精确匹配
        info = self._parser.covergroups.get(cg_name)
        if not info:
            # 按 name 字段匹配
            for key, cg in self._parser.covergroups.items():
                if cg.name == cg_name:
                    info = cg
                    break
        if not info:
            return []
        return [self._coverpoint_to_dict(cp) for cp in info.coverpoints]
    
    def get_bins(self, cg_name: str, cp_name: str) -> List[Dict[str, Any]]:
        """获取 coverpoint 的所有 bins"""
        info = self._find_covergroup(cg_name)
        if not info:
            return []
        cp = next((c for c in info.coverpoints if c.name == cp_name), None)
        if not cp:
            return []
        return [self._bin_to_dict(b) for b in cp.bins]
    
    def get_crosses(self, cg_name: str) -> List[Dict[str, Any]]:
        """获取 covergroup 的所有 cross"""
        info = self._find_covergroup(cg_name)
        if not info:
            return []
        return [self._cross_to_dict(c) for c in info.crosses]
    
    def get_options(self, cg_name: str) -> Dict[str, Any]:
        """获取 covergroup 的 option"""
        info = self._find_covergroup(cg_name)
        if not info:
            return {}
        return dict(info.options)
    
    def get_cp_options(self, cg_name: str, cp_name: str) -> Dict[str, Any]:
        """获取 coverpoint 的 option"""
        info = self._find_covergroup(cg_name)
        if not info:
            return {}
        cp = next((c for c in info.coverpoints if c.name == cp_name), None)
        if not cp:
            return {}
        return dict(cp.options)
    
    def get_sample_event(self, cg_name: str) -> Optional[Dict[str, Any]]:
        """获取 covergroup 的 sample 事件"""
        info = self._find_covergroup(cg_name)
        if not info:
            return None
        return info.sample_event
    
    # ================================================================
    # bin-constraint 一致性检查
    # ================================================================
    
    def check_bin_constraint_consistency(
        self,
        var_path: str,
        cg_name: str,
        cp_name: str,
    ) -> List[Dict[str, Any]]:
        """
        检查 coverpoint 的 bins 与变量 constraint 是否一致。
        
        Args:
            var_path: 变量 full_path (如 pkg.Class.var)
            cg_name: covergroup 名
            cp_name: coverpoint 名
        
        Returns:
            问题列表, 每个包含:
            - type: 'dead_bin' / 'missing_bin' / 'missing_illegal_bin'
            - bin_name: 相关 bin 名 (dead_bin/missing_illegal_bin)
            - reason: 描述
            - range / uncovered_range / forbidden_range: 相关范围
        """
        issues: List[Dict[str, Any]] = []
        
        # 1. 获取 coverpoint 的 bins
        bins = self.get_bins(cg_name, cp_name)
        if not bins:
            return issues
        
        # 2. 获取变量的约束范围 (从 ConstraintGraph)
        constraint_ranges = self._get_constraint_ranges(var_path)
        if not constraint_ranges:
            # 没有约束, 无法检查
            return issues
        
        # 合并约束范围为一组允许的区间
        allowed = self._merge_ranges(constraint_ranges)
        forbidden = self._invert_ranges(allowed, bit_width=8)
        
        # 3. 检查每个 bin
        covered_ranges = []
        has_illegal = False
        
        for b in bins:
            bin_ranges = b.get('values', [])
            bin_kind = b.get('kind', 'Bins')
            
            if bin_kind == 'IllegalBins':
                has_illegal = True
            
            if not bin_ranges or b.get('is_default'):
                continue
            
            # 展开 bin 范围
            bin_intervals = [(lo, hi) for lo, hi in bin_ranges]
            
            if bin_kind == 'Bins':
                covered_ranges.extend(bin_intervals)
                
                # 检查是否是死 bin: bin 范围完全在约束禁止区域
                for blo, bhi in bin_intervals:
                    overlap = self._range_overlap((blo, bhi), allowed)
                    if overlap is None:
                        issues.append({
                            'type': 'dead_bin',
                            'bin_name': b['name'],
                            'reason': f'bin [{blo}:{bhi}] 被 constraint 排除, 永远无法 hit',
                            'range': (blo, bhi),
                        })
                    elif overlap != (blo, bhi):
                        # 部分重叠
                        issues.append({
                            'type': 'dead_bin',
                            'bin_name': b['name'],
                            'reason': f'bin [{blo}:{bhi}] 部分被 constraint 排除',
                            'range': (blo, bhi),
                            'effective_range': overlap,
                        })
        
        # 4. 检查遗漏 bin: 约束允许但没有 bin 覆盖的区域
        uncovered = self._subtract_ranges(allowed, covered_ranges)
        if uncovered:
            issues.append({
                'type': 'missing_bin',
                'reason': f'constraint 允许的取值没有 bin 覆盖',
                'uncovered_range': uncovered,
            })
        
        # 5. 检查 missing illegal bin: 约束禁止但没有标 illegal_bins
        if forbidden and not has_illegal:
            issues.append({
                'type': 'missing_illegal_bin',
                'reason': f'constraint 禁止的取值没有标 illegal_bins',
                'forbidden_range': forbidden,
            })
        
        return issues
    
    def _get_constraint_ranges(self, var_path: str) -> List[Tuple[int, int]]:
        """从 ConstraintGraph 获取变量的约束范围"""
        if self._constraint_graph is None:
            return []
        
        cons = self._constraint_graph.get_constraints_for_variable(var_path)
        if not cons:
            return []
        
        ranges = []
        for c in cons:
            # 优先使用结构化字段
            if hasattr(c, 'inside_ranges') and c.inside_ranges:
                ranges.extend(c.inside_ranges)
            else:
                body = c.get('constraint_body', '') if isinstance(c, dict) else getattr(c, 'constraint_body', '')
                parsed = self._parse_inside_range(body)
                if parsed:
                    ranges.extend(parsed)
        
        return ranges
    
    def _parse_inside_range(self, body: str) -> List[Tuple[int, int]]:
        """解析约束体中的 inside { ... } 范围 (支持多分支)"""
        import re
        ranges = []
        
        # 找到所有 inside { ... } 内容 (支持条件约束的多分支)
        for inside_match in re.finditer(r'inside\s*\{\s*([^}]+)\}', body):
            content = inside_match.group(1)
            # 解析带括号的范围: [lo:hi]
            for range_m in re.finditer(r'\[(\d+):(\d+)\]', content):
                lo = int(range_m.group(1))
                hi = int(range_m.group(2))
                r = (min(lo, hi), max(lo, hi))
                if r not in ranges:
                    ranges.append(r)
            # 解析不带括号的范围: lo:hi
            for range_m in re.finditer(r'(?<!\[)(\d+):(\d+)(?!\])', content):
                lo = int(range_m.group(1))
                hi = int(range_m.group(2))
                r = (min(lo, hi), max(lo, hi))
                if r not in ranges:
                    ranges.append(r)
            # 解析单个值 (不在范围中的)
            for val_m in re.finditer(r'(?<![:\[])(\d+)(?![:\]])', content):
                val = int(val_m.group(1))
                if not any(lo <= val <= hi for lo, hi in ranges):
                    ranges.append((val, val))
        
        return ranges
    
    def _merge_ranges(self, ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """合并重叠的范围"""
        if not ranges:
            return []
        sorted_ranges = sorted(ranges)
        merged = [sorted_ranges[0]]
        for lo, hi in sorted_ranges[1:]:
            if lo <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        return merged
    
    def _invert_ranges(
        self, ranges: List[Tuple[int, int]], bit_width: int = 8
    ) -> List[Tuple[int, int]]:
        """取反: 返回 ranges 之外的区域"""
        max_val = (1 << bit_width) - 1
        if not ranges:
            return [(0, max_val)]
        
        sorted_ranges = self._merge_ranges(ranges)
        inverted = []
        cursor = 0
        for lo, hi in sorted_ranges:
            if cursor < lo:
                inverted.append((cursor, lo - 1))
            cursor = hi + 1
        if cursor <= max_val:
            inverted.append((cursor, max_val))
        return inverted
    
    def _range_overlap(
        self, a: Tuple[int, int], ranges: List[Tuple[int, int]]
    ) -> Optional[Tuple[int, int]]:
        """计算 a 与 ranges 集合的交集。返回 None 如果无交集。"""
        a_lo, a_hi = a
        overlaps = []
        for r_lo, r_hi in ranges:
            lo = max(a_lo, r_lo)
            hi = min(a_hi, r_hi)
            if lo <= hi:
                overlaps.append((lo, hi))
        if not overlaps:
            return None
        # 合并
        return self._merge_ranges(overlaps)[0] if len(overlaps) == 1 else self._merge_ranges(overlaps)[0]
    
    def _subtract_ranges(
        self, a_ranges: List[Tuple[int, int]], b_ranges: List[Tuple[int, int]]
    ) -> List[Tuple[int, int]]:
        """a_ranges - b_ranges: 从 a 中减去 b 覆盖的区域"""
        if not b_ranges:
            return list(a_ranges)
        
        result = list(a_ranges)
        for blo, bhi in b_ranges:
            new_result = []
            for alo, ahi in result:
                if bhi < alo or blo > ahi:
                    # 无重叠
                    new_result.append((alo, ahi))
                else:
                    # 有重叠, 切割
                    if blo > alo:
                        new_result.append((alo, blo - 1))
                    if bhi < ahi:
                        new_result.append((bhi + 1, ahi))
            result = new_result
        return [r for r in result if r[0] <= r[1]]
    
    # ================================================================
    # coverage 质量评估
    # ================================================================
    
    def check_coverage_quality(
        self,
        var_path: str,
        cg_name: str,
        cp_name: str,
        signal_type: str = 'data',
    ) -> List[Dict[str, Any]]:
        """
        评估 coverpoint 的 bin 策略质量。
        
        Args:
            var_path: 变量路径
            cg_name: covergroup 名
            cp_name: coverpoint 名
            signal_type: 'data' (关心范围/极值) 或 'control' (关心特殊值)
        
        Returns:
            报告列表, 每个包含:
            - type: 'info' / 'warning' / 'score'
            - reason: 描述
            - value: 分数 (score 类型)
        """
        report: List[Dict[str, Any]] = []
        
        bins = self.get_bins(cg_name, cp_name)
        if not bins:
            report.append({'type': 'warning', 'reason': '无 bins 定义'})
            report.append({'type': 'score', 'value': 0.0})
            return report
        
        score = 1.0
        
        if signal_type == 'data':
            score, warnings = self._evaluate_data_bins(bins)
            report.extend(warnings)
        elif signal_type == 'control':
            score, warnings = self._evaluate_control_bins(bins)
            report.extend(warnings)
        
        report.append({'type': 'score', 'value': round(score, 2)})
        return report
    
    def check_cg_quality(self, cg_name: str) -> List[Dict[str, Any]]:
        """
        covergroup 级别综合质量检查。
        """
        report: List[Dict[str, Any]] = []
        
        info = self._find_covergroup(cg_name)
        if not info:
            report.append({'type': 'warning', 'reason': f'covergroup {cg_name} 未找到'})
            return report
        
        # 1. 检查是否有 cross
        if info.crosses:
            report.append({'type': 'info', 'reason': f'有 {len(info.crosses)} 个 cross 覆盖'})
        else:
            # 检查是否有多个 coverpoint (需要 cross)
            cp_count = len(info.coverpoints)
            if cp_count >= 2:
                report.append({
                    'type': 'warning',
                    'reason': f'有 {cp_count} 个 coverpoint 但无 cross 覆盖, 建议添加 cross',
                })
        
        # 2. 检查每个 coverpoint 的 bin 数量
        for cp in info.coverpoints:
            bin_count = len(cp.bins)
            if bin_count == 0:
                report.append({
                    'type': 'warning',
                    'reason': f'coverpoint {cp.name} 无 bins 定义',
                })
            elif bin_count == 1:
                report.append({
                    'type': 'warning',
                    'reason': f'coverpoint {cp.name} 只有 1 个 bin, 覆盖粒度不足',
                })
        
        # 3. 综合分数
        total_score = 1.0
        if not info.crosses and len(info.coverpoints) >= 2:
            total_score -= 0.3
        for cp in info.coverpoints:
            if len(cp.bins) == 0:
                total_score -= 0.3
            elif len(cp.bins) == 1:
                total_score -= 0.1
        
        report.append({'type': 'score', 'value': round(max(0, total_score), 2)})
        return report
    
    def _evaluate_data_bins(
        self, bins: List[Dict]
    ) -> Tuple[float, List[Dict]]:
        """评估 data 类信号的 bin 策略"""
        warnings = []
        score = 1.0
        
        # 检查是否有独立的极值 bin
        has_dedicated_zero = False
        has_dedicated_max = False
        
        for b in bins:
            if b.get('kind') != 'Bins' or b.get('is_default'):
                continue
            values = b.get('values', [])
            for lo, hi in values:
                if lo == 0 and hi == 0:
                    has_dedicated_zero = True
                if lo == 255 and hi == 255:
                    has_dedicated_max = True
        
        # 检查极值
        if not has_dedicated_zero:
            warnings.append({
                'type': 'warning',
                'reason': '缺少极值 bin: 建议添加 bins zero = {0}',
            })
            score -= 0.2
        
        if not has_dedicated_max:
            warnings.append({
                'type': 'warning',
                'reason': '缺少极值 bin: 建议添加 bins max = {255}',
            })
            score -= 0.2
        
        # 检查 bin 数量
        real_bins = [b for b in bins if b.get('kind') == 'Bins' and not b.get('is_default')]
        if len(real_bins) < 3:
            warnings.append({
                'type': 'warning',
                'reason': f'bin 数量较少 ({len(real_bins)}), 建议细化范围划分',
            })
            score -= 0.1
        
        return max(0, score), warnings
    
    def _evaluate_control_bins(
        self, bins: List[Dict]
    ) -> Tuple[float, List[Dict]]:
        """评估 control 类信号的 bin 策略"""
        warnings = []
        score = 1.0
        
        real_bins = [b for b in bins if b.get('kind') == 'Bins' and not b.get('is_default')]
        
        # 检查是否有独立的特殊值 bin
        has_named_bins = len(real_bins) > 1
        
        if not has_named_bins:
            warnings.append({
                'type': 'warning',
                'reason': 'control 信号缺少特殊值 bin: 建议为每个状态值创建独立 bin (如 bins idle = {0}, bins error = {1})',
            })
            score -= 0.3
        
        # 检查 bin 数量 (control 信号通常值域较小)
        if len(real_bins) < 2:
            warnings.append({
                'type': 'warning',
                'reason': f'control 信号 bin 数量不足 ({len(real_bins)}), 建议覆盖所有状态',
            })
            score -= 0.2
        
        return max(0, score), warnings
    
    # ================================================================
    # 辅助方法
    # ================================================================
    
    def _find_covergroup(self, cg_name: str) -> Optional[CovergroupInfo]:
        """按名称查找 covergroup (支持短名匹配)"""
        # 精确匹配
        if cg_name in self._parser.covergroups:
            return self._parser.covergroups[cg_name]
        
        # 短名匹配 (location.name)
        for name, info in self._parser.covergroups.items():
            if info.name == cg_name or info.full_path.endswith(f".{cg_name}"):
                return info
        
        return None
    
    def _coverpoint_to_dict(self, cp: CoverpointInfo) -> Dict[str, Any]:
        return {
            'name': cp.name,
            'full_path': cp.full_path,
            'covergroup': cp.covergroup,
            'bin_count': len(cp.bins),
            'options': dict(cp.options),
        }
    
    def _bin_to_dict(self, b: BinInfo) -> Dict[str, Any]:
        return {
            'name': b.name,
            'kind': b.kind,
            'values': b.values,
            'is_wildcard': b.is_wildcard,
            'is_default': b.is_default,
            'cross_select': b.cross_select,
        }
    
    def _cross_to_dict(self, c: CrossInfo) -> Dict[str, Any]:
        return {
            'name': c.name,
            'full_path': c.full_path,
            'covergroup': c.covergroup,
            'targets': c.targets,
            'bins': [self._bin_to_dict(b) for b in c.bins],
        }
