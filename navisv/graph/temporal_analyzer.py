"""
TemporalAnalyzer - 信号时序关系分析

分析信号图上两个或多个信号的时序行为关系：
- 寄存器链: A → reg → B (N 周期延迟)
- 组合路径: A → comb → B (0 周期)
- 条件使能: A enables B (条件赋值)
- 时钟域: 信号所属时钟域

用于与 SVA 对齐检查。
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class TemporalRelation:
    """两个信号之间的时序关系"""
    source: str
    target: str
    relation: str          # 'combinational' | 'sequential' | 'conditional' | 'clock_enable'
    latency: int = 0       # 寄存器级数 (0=组合)
    clock_domain: str = '' # 时钟信号
    condition: str = ''    # 条件表达式
    path: List[str] = field(default_factory=list)  # 中间信号
    edge_details: List[Dict] = field(default_factory=list)  # 边详情


@dataclass
class SignalTimingProfile:
    """信号时序画像"""
    signal: str
    kind: str              # 'Port' | 'State' | 'Net'
    timing: str            # 'sequential' | 'combinational' | 'unknown'
    clock_domain: str = ''
    is_register: bool = False
    is_input: bool = False
    is_output: bool = False
    drivers: List[str] = field(default_factory=list)
    loads: List[str] = field(default_factory=list)


class TemporalAnalyzer:
    """信号时序关系分析器"""

    def __init__(self, dg):
        """
        Args:
            dg: DesignGraph 实例
        """
        self.dg = dg
        self.graph = dg.graph

    def get_signal_profile(self, signal: str) -> SignalTimingProfile:
        """获取信号时序画像"""
        attr = self.dg.node_attr(signal)
        kind = attr.get('kind', '')
        timing = attr.get('timing', 'unknown')

        # 从边推断时钟域
        clock_domain = self._infer_clock_domain(signal)

        return SignalTimingProfile(
            signal=signal,
            kind=kind,
            timing=timing,
            clock_domain=clock_domain,
            is_register=(kind == 'State' and timing == 'sequential'),
            is_input=(kind == 'Port' and attr.get('direction') == 'In'),
            is_output=(kind == 'Port' and attr.get('direction') == 'Out'),
            drivers=list(set(self.dg.get_drivers(signal))),
            loads=list(set(self.dg.get_loads(signal))),
        )

    def get_temporal_relation(self, sig_a: str, sig_b: str) -> TemporalRelation:
        """分析两个信号之间的时序关系

        Args:
            sig_a: 源信号
            sig_b: 目标信号

        Returns:
            TemporalRelation 描述两者关系
        """
        # 1. 直接边检查
        direct = self._check_direct_edge(sig_a, sig_b)
        if direct:
            return direct

        # 2. 路径追踪
        path_result = self.dg.trace_path(sig_a, sig_b)
        if path_result.get('success') and path_result.get('path'):
            return self._analyze_path_relation(sig_a, sig_b, path_result['path'])

        # 3. 反向检查 (sig_b → sig_a)
        path_rev = self.dg.trace_path(sig_b, sig_a)
        if path_rev.get('success') and path_rev.get('path'):
            rel = self._analyze_path_relation(sig_b, sig_a, path_rev['path'])
            # 反转关系
            rel.source, rel.target = sig_a, sig_b
            rel.relation = f'inverse_{rel.relation}'
            return rel

        # 4. Fan-in/Fan-out 关系
        fanin = self.dg.get_fanin_cone(sig_b, depth=5)
        if sig_a in fanin:
            return TemporalRelation(
                source=sig_a, target=sig_b,
                relation='indirect',
                path=list(fanin),
            )

        return TemporalRelation(
            source=sig_a, target=sig_b,
            relation='unrelated',
        )

    def get_multi_signal_relations(self, signals: List[str]) -> Dict[Tuple[str, str], TemporalRelation]:
        """分析多个信号之间的时序关系

        Args:
            signals: 信号列表

        Returns:
            {(sig_a, sig_b): TemporalRelation} 映射
        """
        relations = {}
        for i, a in enumerate(signals):
            for j, b in enumerate(signals):
                if i != j:
                    rel = self.get_temporal_relation(a, b)
                    if rel.relation != 'unrelated':
                        relations[(a, b)] = rel
        return relations

    def find_register_chains(self, start: str, max_depth: int = 5) -> List[List[str]]:
        """找到从 start 出发的所有寄存器链

        寄存器链: reg → reg → reg (每级一个时钟周期)

        Returns:
            [[reg1, reg2, reg3], ...] 寄存器链列表
        """
        chains = []
        self._dfs_register_chain(start, [start], chains, max_depth)
        return chains

    def find_clock_domain_signals(self, clock: str) -> Dict[str, List[str]]:
        """找到属于指定时钟域的所有信号

        Args:
            clock: 时钟信号名

        Returns:
            {'sequential': [...], 'combinational': [...]}
        """
        result = {'sequential': [], 'combinational': []}

        for n in self.graph.nodes:
            domain = self._infer_clock_domain(n)
            if domain == clock:
                attr = self.dg.node_attr(n)
                if attr.get('timing') == 'sequential':
                    result['sequential'].append(n)
                else:
                    result['combinational'].append(n)

        return result

    def get_timing_fanin(self, signal: str, clock: str = None) -> Dict[str, Any]:
        """获取信号的时序 fan-in 分析

        Returns:
            {
                'sequential_inputs': [...],   # 寄存器输入
                'combinational_inputs': [...], # 组合输入
                'clock': '...',
                'reset': '...',
                'enable': '...',
            }
        """
        drivers = list(set(self.dg.get_drivers(signal)))
        sequential = []
        combinational = []

        for d in drivers:
            attr = self.dg.node_attr(d)
            timing = attr.get('timing', 'unknown')
            if timing == 'sequential':
                sequential.append(d)
            else:
                combinational.append(d)

        # 找时钟和复位
        clock_sig = self._find_clock_signal(signal)
        reset_sig = self._find_reset_signal(signal)
        enable_sig = self._find_enable_signal(signal)

        return {
            'sequential_inputs': sequential,
            'combinational_inputs': combinational,
            'clock': clock_sig,
            'reset': reset_sig,
            'enable': enable_sig,
        }

    # ================================================================
    # 内部方法
    # ================================================================

    def _check_direct_edge(self, sig_a: str, sig_b: str) -> Optional[TemporalRelation]:
        """检查直接边"""
        if not self.graph.has_edge(sig_a, sig_b):
            return None

        edge_data = self.graph.get_edge_data(sig_a, sig_b)
        if not edge_data:
            return None

        # 取第一条边的数据
        data = list(edge_data.values())[0] if isinstance(edge_data, dict) else edge_data

        timing = data.get('timing', 'unknown')
        edge_kind = data.get('edge_kind', '')
        condition = data.get('condition', '')

        if timing == 'combinational':
            relation = 'combinational'
            latency = 0
        elif timing in ('sequential', 'sequential_output', 'sequential_input'):
            relation = 'sequential'
            latency = 1
        else:
            relation = 'unknown'
            latency = 0

        if condition:
            relation = 'conditional'

        return TemporalRelation(
            source=sig_a,
            target=sig_b,
            relation=relation,
            latency=latency,
            clock_domain=self._infer_clock_domain(sig_b),
            condition=condition,
            path=[sig_a, sig_b],
            edge_details=[data],
        )

    def _analyze_path_relation(self, src: str, dst: str, path: List) -> TemporalRelation:
        """分析路径上的时序关系"""
        # 统计路径上的寄存器级数
        reg_count = 0
        edge_details = []

        for i in range(len(path) - 1):
            a = path[i] if isinstance(path[i], str) else path[i].get('path', path[i].get('signal', ''))
            b = path[i+1] if isinstance(path[i+1], str) else path[i+1].get('path', path[i+1].get('signal', ''))

            if self.graph.has_edge(a, b):
                edge_data = self.graph.get_edge_data(a, b)
                if edge_data:
                    data = list(edge_data.values())[0] if isinstance(edge_data, dict) else edge_data
                    timing = data.get('timing', '')
                    if 'sequential' in timing:
                        reg_count += 1
                    edge_details.append(data)

        # 确定关系类型
        if reg_count == 0:
            relation = 'combinational'
        elif reg_count == 1:
            relation = 'sequential'
        else:
            relation = f'sequential_chain_{reg_count}'

        return TemporalRelation(
            source=src,
            target=dst,
            relation=relation,
            latency=reg_count,
            clock_domain=self._infer_clock_domain(dst),
            path=[p if isinstance(p, str) else p.get('path', '') for p in path],
            edge_details=edge_details,
        )

    def _infer_clock_domain(self, signal: str) -> str:
        """从边推断信号的时钟域"""
        # 找 PosEdge/NegEdge 边
        for src, dst, data in self.graph.in_edges(signal, data=True):
            edge_kind = data.get('edge_kind', '')
            if edge_kind in ('PosEdge', 'NegEdge'):
                return src

        # 找驱动信号的时钟
        for src, dst, data in self.graph.in_edges(signal, data=True):
            timing = data.get('timing', '')
            if 'sequential' in timing:
                # 递归找时钟
                return self._infer_clock_domain(src)

        return ''

    def _find_clock_signal(self, signal: str) -> str:
        """找时钟信号"""
        return self._infer_clock_domain(signal)

    def _find_reset_signal(self, signal: str) -> str:
        """找复位信号"""
        for src, dst, data in self.graph.in_edges(signal, data=True):
            condition = data.get('condition', '')
            if 'rst' in condition.lower() or 'reset' in condition.lower():
                return condition
            edge_kind = data.get('edge_kind', '')
            if edge_kind == 'NegEdge' and 'rst' in src.lower():
                return src
        return ''

    def _find_enable_signal(self, signal: str) -> str:
        """找使能信号"""
        for src, dst, data in self.graph.in_edges(signal, data=True):
            condition = data.get('condition', '')
            if 'en' in condition.lower() or 'enable' in condition.lower():
                return condition
        return ''

    def _dfs_register_chain(self, current: str, path: List[str], chains: List[List[str]], max_depth: int):
        """DFS 找寄存器链"""
        if len(path) > max_depth:
            return

        # 找当前信号的寄存器负载
        for _, dst, data in self.graph.out_edges(current, data=True):
            timing = data.get('timing', '')
            if 'sequential' in timing and dst not in path:
                new_path = path + [dst]
                chains.append(new_path.copy())
                self._dfs_register_chain(dst, new_path, chains, max_depth)
