"""
VerifyMapper - 模块验证覆盖率地图

给定一个模块，分析：
1. 哪些信号/路径有 SVA 覆盖
2. 哪些信号/路径有 CoverGroup 覆盖
3. 验证覆盖的完整度

输出 JSON + 图，便于 agent 精确读取和人快速理解。
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class SignalVerifyStatus:
    """信号验证状态"""
    signal: str
    kind: str               # Port/State/Net
    timing: str              # sequential/combinational
    clock_domain: str = ''
    has_sva: bool = False
    sva_properties: List[str] = field(default_factory=list)
    has_coverage: bool = False
    covergroups: List[str] = field(default_factory=list)
    coverpoints: List[str] = field(default_factory=list)
    has_temporal_relation: bool = False
    temporal_relations: int = 0
    verify_level: str = 'none'  # none/partial/full


@dataclass
class VerifyReport:
    """模块验证报告"""
    module: str
    total_signals: int = 0
    sva_covered: int = 0
    coverage_covered: int = 0
    both_covered: int = 0
    neither_covered: int = 0
    signals: List[SignalVerifyStatus] = field(default_factory=list)
    sva_properties: List[Dict] = field(default_factory=list)
    covergroups: List[Dict] = field(default_factory=list)
    uncovered_inputs: List[str] = field(default_factory=list)
    uncovered_outputs: List[str] = field(default_factory=list)
    uncovered_registers: List[str] = field(default_factory=list)


class VerifyMapper:
    """模块验证覆盖率分析器"""

    def __init__(self, dg, sva_parser=None, covergroup_analyzer=None, temporal_analyzer=None):
        """
        Args:
            dg: DesignGraph 实例
            sva_parser: SVAParser 实例 (可选)
            covergroup_analyzer: CovergroupAnalyzer 实例 (可选)
            temporal_analyzer: TemporalAnalyzer 实例 (可选)
        """
        self.dg = dg
        self.sva_parser = sva_parser
        self.cg_analyzer = covergroup_analyzer
        self.ta = temporal_analyzer

    def analyze(self, module_prefix: str = '') -> VerifyReport:
        """分析模块的验证覆盖情况

        Args:
            module_prefix: 模块前缀 (如 'uart_controller')

        Returns:
            VerifyReport
        """
        report = VerifyReport(module=module_prefix or 'all')

        # 1. 收集所有信号
        all_signals = list(self.dg.graph.nodes)
        if module_prefix:
            all_signals = [s for s in all_signals if s.startswith(module_prefix)]

        report.total_signals = len(all_signals)

        # 2. 收集 SVA 属性
        sva_props = self._get_sva_properties()
        report.sva_properties = sva_props
        sva_signals = self._extract_sva_signal_map(sva_props)

        # 3. 收集 CoverGroup
        cg_data = self._get_covergroup_data()
        report.covergroups = cg_data['covergroups']
        cg_signals = cg_data['signal_map']

        # 4. 分析每个信号
        for signal in all_signals:
            status = self._analyze_signal(signal, sva_signals, cg_signals)
            report.signals.append(status)

            if status.has_sva:
                report.sva_covered += 1
            if status.has_coverage:
                report.coverage_covered += 1
            if status.has_sva and status.has_coverage:
                report.both_covered += 1
            if not status.has_sva and not status.has_coverage:
                report.neither_covered += 1
                # 分类未覆盖信号
                attr = self.dg.node_attr(signal)
                kind = attr.get('kind', '')
                if kind == 'Port' and attr.get('direction') == 'In':
                    report.uncovered_inputs.append(signal)
                elif kind == 'Port' and attr.get('direction') == 'Out':
                    report.uncovered_outputs.append(signal)
                elif kind == 'State':
                    report.uncovered_registers.append(signal)

        return report

    def _analyze_signal(self, signal: str, sva_signals: Dict, cg_signals: Dict) -> SignalVerifyStatus:
        """分析单个信号的验证状态"""
        attr = self.dg.node_attr(signal)
        kind = attr.get('kind', '')
        timing = attr.get('timing', 'unknown')
        short_name = signal.split('.')[-1]

        # SVA 覆盖
        has_sva = False
        sva_props = []
        if short_name in sva_signals:
            has_sva = True
            sva_props = sva_signals[short_name]
        elif signal in sva_signals:
            has_sva = True
            sva_props = sva_signals[signal]

        # CoverGroup 覆盖
        has_coverage = False
        covergroups = []
        coverpoints = []
        if short_name in cg_signals:
            has_coverage = True
            covergroups = cg_signals[short_name].get('covergroups', [])
            coverpoints = cg_signals[short_name].get('coverpoints', [])

        # 时序关系
        has_temporal = False
        temporal_count = 0
        if self.ta:
            profile = self.ta.get_signal_profile(signal)
            temporal_count = len(profile.drivers) + len(profile.loads)
            has_temporal = temporal_count > 0

        # 验证等级
        if has_sva and has_coverage:
            level = 'full'
        elif has_sva or has_coverage:
            level = 'partial'
        else:
            level = 'none'

        return SignalVerifyStatus(
            signal=signal,
            kind=kind,
            timing=timing,
            has_sva=has_sva,
            sva_properties=sva_props,
            has_coverage=has_coverage,
            covergroups=covergroups,
            coverpoints=coverpoints,
            has_temporal_relation=has_temporal,
            temporal_relations=temporal_count,
            verify_level=level,
        )

    def _get_sva_properties(self) -> List[Dict]:
        """获取 SVA 属性列表"""
        if not self.sva_parser:
            return []
        props = []
        for prop in self.sva_parser.properties:
            props.append({
                'name': prop.name,
                'expression': prop.expression,
                'signals': prop.signals,
                'clock': prop.clock,
            })
        return props

    def _extract_sva_signal_map(self, sva_props: List[Dict]) -> Dict[str, List[str]]:
        """从 SVA 属性提取信号→属性名映射"""
        signal_map = {}
        for prop in sva_props:
            prop_name = prop['name']
            for sig in prop.get('signals', []):
                short = sig.split('.')[-1]
                signal_map.setdefault(short, []).append(prop_name)
                signal_map.setdefault(sig, []).append(prop_name)
        return signal_map

    def _get_covergroup_data(self) -> Dict:
        """获取 CoverGroup 数据"""
        result = {'covergroups': [], 'signal_map': {}}

        if not self.cg_analyzer:
            return result

        for cg in self.cg_analyzer.get_covergroups():
            cg_name = cg['name']
            result['covergroups'].append(cg)

            cps = self.cg_analyzer.get_coverpoints_by_cg(cg_name)
            for cp in cps:
                cp_name = cp['name']
                # 从 coverpoint 名推断信号
                signal_name = cp_name.replace('cp_', '')
                result['signal_map'].setdefault(signal_name, {
                    'covergroups': [], 'coverpoints': []
                })
                result['signal_map'][signal_name]['covergroups'].append(cg_name)
                result['signal_map'][signal_name]['coverpoints'].append(cp_name)

        return result


def export_verify_dot(report: VerifyReport) -> str:
    """生成验证覆盖 DOT 图"""
    lines = []
    lines.append(f'digraph verify_{report.module} {{')
    lines.append('  rankdir=LR;')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica", fontsize=10];')
    lines.append('')

    # 图例
    lines.append('  subgraph cluster_legend {')
    lines.append('    label="图例"; style=dashed; color=gray;')
    lines.append('    l1 [label="✅ SVA+Coverage", fillcolor=lightgreen];')
    lines.append('    l2 [label="⚠️ 仅SVA", fillcolor=lightyellow];')
    lines.append('    l3 [label="⚠️ 仅Coverage", fillcolor=lightblue];')
    lines.append('    l4 [label="❌ 无验证", fillcolor=lightcoral];')
    lines.append('  }')
    lines.append('')

    # 按类型分组
    ports_in = []
    ports_out = []
    registers = []
    others = []

    for s in report.signals:
        short = s.signal.split('.')[-1]
        if s.kind == 'Port':
            # 从 signal 属性获取 direction
            if any(s.signal.endswith(f'.{p}') for p in ['i', 'clk', 'rst', 'en']):
                ports_in.append((short, s))
            else:
                ports_out.append((short, s))
        elif s.kind == 'State':
            registers.append((short, s))
        else:
            others.append((short, s))

    # 节点
    def add_node(name, status):
        if status.verify_level == 'full':
            color = 'lightgreen'
        elif status.has_sva:
            color = 'lightyellow'
        elif status.has_coverage:
            color = 'lightblue'
        else:
            color = 'lightcoral'
        lines.append(f'  "{name}" [fillcolor={color}];')

    if ports_in:
        lines.append('  subgraph cluster_input { label="输入端口"; style=dashed; color=blue;')
        for name, s in ports_in:
            add_node(name, s)
        lines.append('  }')

    if ports_out:
        lines.append('  subgraph cluster_output { label="输出端口"; style=dashed; color=blue;')
        for name, s in ports_out:
            add_node(name, s)
        lines.append('  }')

    if registers:
        lines.append('  subgraph cluster_reg { label="寄存器"; style=dashed; color=red;')
        for name, s in registers:
            add_node(name, s)
        lines.append('  }')

    if others:
        lines.append('  subgraph cluster_net { label="内部信号"; style=dashed; color=gray;')
        for name, s in others:
            add_node(name, s)
        lines.append('  }')

    lines.append('}')

    return '\n'.join(lines)


def export_verify_mermaid(report: VerifyReport) -> str:
    """生成验证覆盖 Mermaid 图"""
    lines = []
    lines.append('graph LR')
    lines.append('')

    # 图例
    lines.append('  %% 图例')
    lines.append('  ✅sva_cov[✅ SVA+Coverage]')
    lines.append('  ⚠️sva[⚠️ 仅SVA]')
    lines.append('  ⚠️cov[⚠️ 仅Coverage]')
    lines.append('  ❌none[❌ 无验证]')
    lines.append('')

    # 按验证等级分组
    full = []
    sva_only = []
    cov_only = []
    none_list = []

    for s in report.signals:
        short = s.signal.split('.')[-1]
        if s.verify_level == 'full':
            full.append(short)
        elif s.has_sva:
            sva_only.append(short)
        elif s.has_coverage:
            cov_only.append(short)
        else:
            none_list.append(short)

    if full:
        lines.append('  %% ✅ 完全覆盖')
        for n in full:
            lines.append(f'  {n}[{n}]')
        lines.append('')

    if sva_only:
        lines.append('  %% ⚠️ 仅SVA覆盖')
        for n in sva_only:
            lines.append(f'  {n}[{n}]')
        lines.append('')

    if cov_only:
        lines.append('  %% ⚠️ 仅Coverage覆盖')
        for n in cov_only:
            lines.append(f'  {n}[{n}]')
        lines.append('')

    if none_list:
        lines.append('  %% ❌ 未覆盖')
        for n in none_list[:30]:  # 限制数量
            lines.append(f'  {n}[{n}]')
        if len(none_list) > 30:
            lines.append(f'  %% ... 还有 {len(none_list)-30} 个')
        lines.append('')

    # 样式
    lines.append('  %% 样式')
    for n in full:
        lines.append(f'  style {n} fill:#90EE90')
    for n in sva_only:
        lines.append(f'  style {n} fill:#FFFFE0')
    for n in cov_only:
        lines.append(f'  style {n} fill:#ADD8E6')
    for n in none_list[:30]:
        lines.append(f'  style {n} fill:#F08080')

    return '\n'.join(lines)


def export_verify_json(report: VerifyReport) -> Dict:
    """导出 JSON 格式"""
    return {
        'module': report.module,
        'summary': {
            'total_signals': report.total_signals,
            'sva_covered': report.sva_covered,
            'coverage_covered': report.coverage_covered,
            'both_covered': report.both_covered,
            'neither_covered': report.neither_covered,
            'verify_rate': round((report.sva_covered + report.coverage_covered - report.both_covered) / max(report.total_signals, 1) * 100, 1),
        },
        'signals': [
            {
                'signal': s.signal.split('.')[-1],
                'full_path': s.signal,
                'kind': s.kind,
                'timing': s.timing,
                'has_sva': s.has_sva,
                'sva_properties': s.sva_properties,
                'has_coverage': s.has_coverage,
                'covergroups': s.covergroups,
                'coverpoints': s.coverpoints,
                'verify_level': s.verify_level,
            }
            for s in report.signals
        ],
        'uncovered': {
            'inputs': [s.split('.')[-1] for s in report.uncovered_inputs],
            'outputs': [s.split('.')[-1] for s in report.uncovered_outputs],
            'registers': [s.split('.')[-1] for s in report.uncovered_registers],
        },
        'sva_properties': report.sva_properties,
        'covergroups': report.covergroups,
    }
