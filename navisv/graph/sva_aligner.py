"""
SVAAligner - SVA 与时序关系对齐检查

功能:
1. 从 DesignGraph 提取信号时序关系
2. 从 SVA Parser 提取已有的 SVA 属性
3. 检查时序关系是否被 SVA 覆盖
4. 为未覆盖的时序关系生成 SVA 建议
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class SVACoverage:
    """SVA 覆盖情况"""
    temporal_source: str
    temporal_target: str
    temporal_relation: str  # 时序关系
    sva_property: str = ''  # 匹配的 SVA 属性名
    sva_expression: str = ''  # 匹配的 SVA 表达式
    is_covered: bool = False
    gap_description: str = ''  # 缺口描述


@dataclass
class SVAAlignmentReport:
    """SVA 对齐报告"""
    total_relations: int = 0
    covered_relations: int = 0
    uncovered_relations: int = 0
    coverage_gaps: List[SVACoverage] = field(default_factory=list)
    sva_properties: List[Dict] = field(default_factory=list)
    suggestions: List[Dict] = field(default_factory=list)


class SVAAligner:
    """SVA 与时序关系对齐检查器"""

    def __init__(self, dg, sva_parser=None):
        """
        Args:
            dg: DesignGraph 实例
            sva_parser: SVAParser 实例 (可选)
        """
        self.dg = dg
        self.sva_parser = sva_parser

    def check_alignment(self, signals: List[str] = None) -> SVAAlignmentReport:
        """检查 SVA 与时序关系的对齐情况

        Args:
            signals: 要检查的信号列表 (None=检查所有信号)

        Returns:
            SVAAlignmentReport
        """
        report = SVAAlignmentReport()

        # 1. 获取所有 SVA 属性
        sva_props = self._get_sva_properties()
        report.sva_properties = sva_props

        # 2. 提取时序关系
        if signals is None:
            signals = self._select_important_signals()

        relations = self._extract_temporal_relations(signals)
        report.total_relations = len(relations)

        # 3. 检查每个时序关系是否有 SVA 覆盖
        for rel in relations:
            coverage = self._check_relation_coverage(rel, sva_props)
            if coverage.is_covered:
                report.covered_relations += 1
            else:
                report.uncovered_relations += 1
                report.coverage_gaps.append(coverage)

        # 4. 生成建议
        report.suggestions = self._generate_suggestions(report.coverage_gaps)

        return report

    def check_signal_pair(self, sig_a: str, sig_b: str) -> Dict[str, Any]:
        """检查两个信号之间的时序关系和 SVA 覆盖

        Returns:
            {
                'relation': TemporalRelation,
                'sva_coverage': SVACoverage,
                'suggestions': [...]
            }
        """
        from navisv.graph.temporal_analyzer import TemporalAnalyzer

        ta = TemporalAnalyzer(self.dg)
        rel = ta.get_temporal_relation(sig_a, sig_b)

        sva_props = self._get_sva_properties()
        # 转为 dict 格式
        rel_dict = {
            'source': rel.source,
            'target': rel.target,
            'relation': rel.relation,
            'latency': rel.latency,
            'clock_domain': rel.clock_domain,
            'condition': rel.condition,
        }
        coverage = self._check_relation_coverage(rel_dict, sva_props)

        suggestions = []
        if not coverage.is_covered:
            suggestions = self._generate_suggestions([coverage])

        return {
            'relation': rel,
            'sva_coverage': coverage,
            'suggestions': suggestions,
        }

    def find_uncovered_temporal_paths(self, min_latency: int = 1) -> List[Dict]:
        """找到所有未被 SVA 覆盖的时序路径

        Args:
            min_latency: 最小延迟级数 (默认1=只看寄存器路径)

        Returns:
            [{'source': ..., 'target': ..., 'latency': ..., 'path': ...}]
        """
        from navisv.graph.temporal_analyzer import TemporalAnalyzer

        ta = TemporalAnalyzer(self.dg)
        sva_props = self._get_sva_properties()
        sva_signals = self._extract_sva_signals(sva_props)

        uncovered = []

        # 找所有寄存器
        registers = self.dg.get_registers()

        for reg in registers:
            # 找寄存器的 fan-out
            fanout = self.dg.get_fanout_cone(reg, depth=3)

            for target in fanout:
                rel = ta.get_temporal_relation(reg, target)

                if rel.latency >= min_latency and rel.relation != 'unrelated':
                    # 检查是否被 SVA 覆盖
                    covered = self._is_pair_in_sva(reg, target, sva_signals, sva_props)
                    if not covered:
                        uncovered.append({
                            'source': reg,
                            'target': target,
                            'latency': rel.latency,
                            'relation': rel.relation,
                            'path': rel.path,
                            'clock_domain': rel.clock_domain,
                        })

        return uncovered

    # ================================================================
    # 内部方法
    # ================================================================

    def _get_sva_properties(self) -> List[Dict]:
        """获取所有 SVA 属性"""
        if not self.sva_parser:
            return []

        props = []
        for prop in self.sva_parser.properties:
            props.append({
                'name': prop.name,
                'expression': prop.expression,
                'signals': prop.signals,
                'clock': prop.clock,
                'disable_iff': prop.disable_iff,
                'assertion_type': prop.assertion_type,
            })
        return props

    def _select_important_signals(self) -> List[str]:
        """选择重要信号进行分析"""
        signals = []

        # 输入端口
        signals.extend(self.dg.get_input_ports()[:10])

        # 输出端口
        for n in self.dg.graph.nodes:
            attr = self.dg.node_attr(n)
            if attr.get('kind') == 'Port' and attr.get('direction') == 'Out':
                signals.append(n)

        # 寄存器
        signals.extend(self.dg.get_registers()[:10])

        return list(set(signals))

    def _extract_temporal_relations(self, signals: List[str]) -> List[Dict]:
        """提取信号之间的时序关系"""
        from navisv.graph.temporal_analyzer import TemporalAnalyzer

        ta = TemporalAnalyzer(self.dg)
        relations = []

        for i, a in enumerate(signals):
            for b in signals[i+1:]:
                rel = ta.get_temporal_relation(a, b)
                if rel.relation not in ('unrelated', 'unknown'):
                    relations.append({
                        'source': rel.source,
                        'target': rel.target,
                        'relation': rel.relation,
                        'latency': rel.latency,
                        'clock_domain': rel.clock_domain,
                        'condition': rel.condition,
                        'path': rel.path,
                    })

        return relations

    def _check_relation_coverage(self, rel: Dict, sva_props: List[Dict]) -> SVACoverage:
        """检查时序关系是否被 SVA 覆盖"""
        src = rel.get('source', '')
        dst = rel.get('target', '')
        relation = rel.get('relation', '')

        src_short = src.split('.')[-1] if src else ''
        dst_short = dst.split('.')[-1] if dst else ''

        # 在 SVA 属性中查找匹配
        for prop in sva_props:
            prop_signals = prop.get('signals', [])
            prop_expr = prop.get('expression', '')

            # 检查信号是否出现在 SVA 中
            src_in_sva = any(src_short in s or src in s for s in prop_signals)
            dst_in_sva = any(dst_short in s or dst in s for s in prop_signals)

            if src_in_sva and dst_in_sva:
                return SVACoverage(
                    temporal_source=src,
                    temporal_target=dst,
                    temporal_relation=relation,
                    sva_property=prop['name'],
                    sva_expression=prop_expr,
                    is_covered=True,
                )

            # 检查表达式中是否包含信号
            if src_short in prop_expr and dst_short in prop_expr:
                return SVACoverage(
                    temporal_source=src,
                    temporal_target=dst,
                    temporal_relation=relation,
                    sva_property=prop['name'],
                    sva_expression=prop_expr,
                    is_covered=True,
                )

        # 未覆盖
        return SVACoverage(
            temporal_source=src,
            temporal_target=dst,
            temporal_relation=relation,
            is_covered=False,
            gap_description=f'{src_short} → {dst_short} ({relation}) 无 SVA 覆盖',
        )

    def _extract_sva_signals(self, sva_props: List[Dict]) -> Set[str]:
        """从 SVA 属性中提取所有信号"""
        signals = set()
        for prop in sva_props:
            for s in prop.get('signals', []):
                signals.add(s)
                signals.add(s.split('.')[-1])
        return signals

    def _is_pair_in_sva(self, sig_a: str, sig_b: str, sva_signals: Set[str], sva_props: List[Dict]) -> bool:
        """检查信号对是否在 SVA 中出现"""
        a_short = sig_a.split('.')[-1]
        b_short = sig_b.split('.')[-1]

        for prop in sva_props:
            prop_signals = prop.get('signals', [])
            prop_expr = prop.get('expression', '')

            a_in = a_short in sva_signals or any(a_short in s for s in prop_signals)
            b_in = b_short in sva_signals or any(b_short in s for s in prop_signals)

            if a_in and b_in:
                return True
            if a_short in prop_expr and b_short in prop_expr:
                return True

        return False

    def _generate_suggestions(self, gaps: List[SVACoverage]) -> List[Dict]:
        """为未覆盖的时序关系生成 SVA 建议"""
        suggestions = []

        for gap in gaps:
            src = gap.temporal_source.split('.')[-1]
            dst = gap.temporal_target.split('.')[-1]
            rel = gap.temporal_relation

            if 'sequential' in rel:
                # 寄存器关系: 信号在 N 周期后出现
                latency = gap.temporal_relation.count('_') if '_' in gap.temporal_relation else 1
                sva_expr = f'##{latency} {dst}'
                suggestion = {
                    'type': 'sequential',
                    'source': src,
                    'target': dst,
                    'expression': sva_expr,
                    'property_template': f'property p_{src}_to_{dst}; @(posedge clk) {src} |-> ##{latency} {dst}; endproperty',
                    'description': f'{src} 在 {latency} 个时钟周期后应出现在 {dst}',
                }
            elif rel == 'combinational':
                # 组合关系: 信号同时出现
                suggestion = {
                    'type': 'combinational',
                    'source': src,
                    'target': dst,
                    'expression': f'{src} |-> {dst}',
                    'property_template': f'property p_{src}_implies_{dst}; @(posedge clk) {src} |-> {dst}; endproperty',
                    'description': f'{src} 为真时 {dst} 应同时为真 (组合逻辑)',
                }
            elif 'conditional' in rel:
                # 条件关系
                condition = gap.temporal_relation.replace('conditional_', '')
                suggestion = {
                    'type': 'conditional',
                    'source': src,
                    'target': dst,
                    'expression': f'{condition} && {src} |-> {dst}',
                    'property_template': f'property p_{src}_cond_{dst}; @(posedge clk) {condition} && {src} |-> {dst}; endproperty',
                    'description': f'当 {condition} 且 {src} 为真时，{dst} 应出现',
                }
            else:
                suggestion = {
                    'type': 'general',
                    'source': src,
                    'target': dst,
                    'expression': f'{src} |-> ##1 {dst}',
                    'property_template': f'property p_{src}_to_{dst}; @(posedge clk) {src} |-> ##1 {dst}; endproperty',
                    'description': f'{src} 和 {dst} 之间存在时序关系',
                }

            suggestions.append(suggestion)

        return suggestions
