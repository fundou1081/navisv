"""
RiskAnalyzer - 基于图拓扑的信号风险/复杂度分析

利用有向图的拓扑指标，评估每个信号的风险等级：
- 入度/出度 (收敛/发散)
- Fan-in/Fan-out 锥大小
- Betweenness centrality (关键路径)
- 位宽、时序类型、条件复杂度
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
import networkx as nx


@dataclass
class NodeRiskMetrics:
    """节点风险指标"""
    signal: str
    kind: str               # Port/State/Net
    timing: str              # sequential/combinational
    bit_width: int = 1
    clock_domain: str = ''

    # 图拓扑指标
    in_degree: int = 0
    out_degree: int = 0
    fanin_size: int = 0      # 上游信号总数
    fanout_size: int = 0     # 下游信号总数
    betweenness: float = 0.0 # 介数中心性
    closeness: float = 0.0   # 接近中心性
    pagerank: float = 0.0    # PageRank

    # 风险评分
    complexity_score: float = 0.0   # 复杂度得分
    risk_level: str = 'low'         # low/medium/high/critical
    risk_factors: List[str] = field(default_factory=list)


@dataclass
class RiskReport:
    """风险分析报告"""
    module: str
    total_nodes: int = 0
    total_edges: int = 0
    critical_nodes: int = 0
    high_risk_nodes: int = 0
    medium_risk_nodes: int = 0
    low_risk_nodes: int = 0
    nodes: List[NodeRiskMetrics] = field(default_factory=list)
    graph_metrics: Dict[str, Any] = field(default_factory=dict)


class RiskAnalyzer:
    """基于图拓扑的风险分析器"""

    def __init__(self, dg, module_prefix: str = ''):
        """
        Args:
            dg: DesignGraph 实例
            module_prefix: 模块前缀
        """
        self.dg = dg
        self.G = dg.graph
        self.module_prefix = module_prefix

    def analyze(self) -> RiskReport:
        """执行风险分析"""
        report = RiskReport(module=self.module_prefix or 'all')

        # 筛选模块内的节点
        nodes = list(self.G.nodes)
        if self.module_prefix:
            nodes = [n for n in nodes if n.startswith(self.module_prefix)]

        report.total_nodes = len(nodes)
        report.total_edges = sum(1 for u, v in self.G.edges() if u in nodes and v in nodes)

        # 1. 计算全局图指标
        report.graph_metrics = self._compute_graph_metrics(nodes)

        # 2. 预计算 betweenness centrality (较慢，只算一次)
        subgraph = self.G.subgraph(nodes) if self.module_prefix else self.G
        try:
            bc = nx.betweenness_centrality(subgraph)
        except Exception:
            bc = {}

        try:
            cc = nx.closeness_centrality(subgraph)
        except Exception:
            cc = {}

        try:
            pr = nx.pagerank(subgraph, max_iter=100)
        except Exception:
            pr = {}

        # 3. 计算每个节点的风险指标
        for node in nodes:
            metrics = self._compute_node_metrics(node, bc, cc, pr)
            report.nodes.append(metrics)

            if metrics.risk_level == 'critical':
                report.critical_nodes += 1
            elif metrics.risk_level == 'high':
                report.high_risk_nodes += 1
            elif metrics.risk_level == 'medium':
                report.medium_risk_nodes += 1
            else:
                report.low_risk_nodes += 1

        # 按复杂度排序
        report.nodes.sort(key=lambda x: x.complexity_score, reverse=True)

        return report

    def _compute_node_metrics(self, node: str, bc: dict, cc: dict, pr: dict) -> NodeRiskMetrics:
        """计算单个节点的风险指标"""
        attr = self.dg.node_attr(node)
        kind = attr.get('kind', '')
        timing = attr.get('timing', 'unknown')
        msb, lsb = attr.get('bit_width', (0, 0))
        bit_width = abs(msb - lsb) + 1

        # 时钟域
        clock_domain = ''
        for src, _, data in self.G.in_edges(node, data=True):
            ek = data.get('edge_kind', '')
            if ek in ('PosEdge', 'NegEdge'):
                clock_domain = src
                break

        # 图拓扑指标
        in_deg = self.G.in_degree(node)
        out_deg = self.G.out_degree(node)
        fanin = len(nx.ancestors(self.G, node))
        fanout = len(nx.descendants(self.G, node))

        # 计算风险评分
        score, factors = self._calculate_risk_score(
            node, kind, timing, bit_width, clock_domain,
            in_deg, out_deg, fanin, fanout,
            bc.get(node, 0), cc.get(node, 0), pr.get(node, 0)
        )

        # 确定风险等级
        if score >= 80:
            level = 'critical'
        elif score >= 60:
            level = 'high'
        elif score >= 40:
            level = 'medium'
        else:
            level = 'low'

        return NodeRiskMetrics(
            signal=node,
            kind=kind,
            timing=timing,
            bit_width=bit_width,
            clock_domain=clock_domain,
            in_degree=in_deg,
            out_degree=out_deg,
            fanin_size=fanin,
            fanout_size=fanout,
            betweenness=bc.get(node, 0),
            closeness=cc.get(node, 0),
            pagerank=pr.get(node, 0),
            complexity_score=score,
            risk_level=level,
            risk_factors=factors,
        )

    def _calculate_risk_score(self, node, kind, timing, bit_width, clock_domain,
                               in_deg, out_deg, fanin, fanout, bc, cc, pr) -> Tuple[float, List[str]]:
        """计算风险评分 (0-100)"""
        score = 0.0
        factors = []

        # 1. 度数风险 (0-25分)
        # 高入度 = 多源竞争
        if in_deg >= 10:
            score += 15
            factors.append(f'高入度({in_deg})')
        elif in_deg >= 5:
            score += 10
            factors.append(f'中入度({in_deg})')
        elif in_deg >= 3:
            score += 5

        # 高出度 = 影响面大
        if out_deg >= 10:
            score += 10
            factors.append(f'高出度({out_deg})')
        elif out_deg >= 5:
            score += 5
            factors.append(f'中出度({out_deg})')

        # 2. Fan-in/Fan-out 风险 (0-20分)
        if fanin >= 50:
            score += 10
            factors.append(f'大Fan-in锥({fanin})')
        elif fanin >= 20:
            score += 5

        if fanout >= 50:
            score += 10
            factors.append(f'大Fan-out锥({fanout})')
        elif fanout >= 20:
            score += 5

        # 3. 关键路径风险 (0-15分)
        if bc >= 0.1:
            score += 15
            factors.append(f'关键路径(BC={bc:.3f})')
        elif bc >= 0.05:
            score += 10
            factors.append(f'重要路径(BC={bc:.3f})')
        elif bc >= 0.02:
            score += 5

        # 4. 时序风险 (0-15分)
        if timing == 'sequential':
            score += 5
            if clock_domain:
                # 检查是否跨时钟域
                other_clocks = set()
                for src, _, data in self.G.in_edges(node, data=True):
                    ek = data.get('edge_kind', '')
                    if ek in ('PosEdge', 'NegEdge') and src != clock_domain:
                        other_clocks.add(src)
                if other_clocks:
                    score += 10
                    factors.append(f'跨时钟域({len(other_clocks)+1}个)')

        # 5. 位宽风险 (0-10分)
        if bit_width >= 32:
            score += 10
            factors.append(f'宽位宽({bit_width}-bit)')
        elif bit_width >= 16:
            score += 7
            factors.append(f'中位宽({bit_width}-bit)')
        elif bit_width >= 8:
            score += 3

        # 6. 条件复杂度 (0-10分)
        cond_count = sum(1 for _, _, d in self.G.in_edges(node, data=True) if d.get('condition'))
        if cond_count >= 5:
            score += 10
            factors.append(f'多条件({cond_count}个)')
        elif cond_count >= 3:
            score += 5
            factors.append(f'条件({cond_count}个)')

        # 7. 类型风险 (0-5分)
        if kind == 'State':
            score += 3  # 寄存器比线网风险高
        elif kind == 'Port':
            score += 2  # 端口是外部接口

        # 限制在 0-100
        score = min(100, max(0, score))

        return round(score, 1), factors

    def _compute_graph_metrics(self, nodes: List[str]) -> Dict[str, Any]:
        """计算全局图指标"""
        subgraph = self.G.subgraph(nodes) if self.module_prefix else self.G

        # 强连通分量
        sccs = list(nx.strongly_connected_components(subgraph))
        scc_sizes = [len(c) for c in sccs]

        # DAG 检查
        is_dag = nx.is_directed_acyclic_graph(subgraph)

        # 度数分布
        in_degrees = [d for _, d in subgraph.in_degree()]
        out_degrees = [d for _, d in subgraph.out_degree()]

        return {
            'nodes': subgraph.number_of_nodes(),
            'edges': subgraph.number_of_edges(),
            'is_dag': is_dag,
            'scc_count': len(sccs),
            'scc_max_size': max(scc_sizes) if scc_sizes else 0,
            'avg_in_degree': round(sum(in_degrees) / max(len(in_degrees), 1), 2),
            'avg_out_degree': round(sum(out_degrees) / max(len(out_degrees), 1), 2),
            'max_in_degree': max(in_degrees) if in_degrees else 0,
            'max_out_degree': max(out_degrees) if out_degrees else 0,
        }


def export_risk_json(report: RiskReport) -> Dict:
    """导出 JSON 格式"""
    return {
        'module': report.module,
        'graph_metrics': report.graph_metrics,
        'summary': {
            'total_nodes': report.total_nodes,
            'critical_nodes': report.critical_nodes,
            'high_risk_nodes': report.high_risk_nodes,
            'medium_risk_nodes': report.medium_risk_nodes,
            'low_risk_nodes': report.low_risk_nodes,
        },
        'nodes': [
            {
                'signal': n.signal.split('.')[-1],
                'full_path': n.signal,
                'kind': n.kind,
                'timing': n.timing,
                'bit_width': n.bit_width,
                'clock_domain': n.clock_domain.split('.')[-1] if n.clock_domain else '',
                'in_degree': n.in_degree,
                'out_degree': n.out_degree,
                'fanin_size': n.fanin_size,
                'fanout_size': n.fanout_size,
                'betweenness': round(n.betweenness, 4),
                'closeness': round(n.closeness, 4),
                'pagerank': round(n.pagerank, 4),
                'complexity_score': n.complexity_score,
                'risk_level': n.risk_level,
                'risk_factors': n.risk_factors,
            }
            for n in report.nodes
        ],
    }


def export_risk_dot(report: RiskReport) -> str:
    """生成风险 DOT 图"""
    lines = []
    lines.append(f'digraph risk_{report.module} {{')
    lines.append('  rankdir=LR;')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica", fontsize=9];')
    lines.append('')

    # 节点按风险等级着色
    for n in report.nodes:
        short = n.signal.split('.')[-1]
        if n.risk_level == 'critical':
            color = 'red'
        elif n.risk_level == 'high':
            color = 'orange'
        elif n.risk_level == 'medium':
            color = 'yellow'
        else:
            color = 'lightgreen'

        # 标签包含关键指标
        label = f"{short}\\n[{n.risk_level}] score={n.complexity_score}"
        if n.risk_factors:
            label += f"\\n{', '.join(n.risk_factors[:2])}"

        shape = 'parallelogram' if n.kind == 'Port' else 'box'
        lines.append(f'  "{short}" [fillcolor={color}, shape={shape}, label="{label}"];')

    lines.append('}')

    return '\n'.join(lines)


def export_risk_mermaid(report: RiskReport) -> str:
    """生成风险 Mermaid 图"""
    lines = []
    lines.append('graph LR')
    lines.append('')

    # 按风险等级分组
    critical = [n for n in report.nodes if n.risk_level == 'critical']
    high = [n for n in report.nodes if n.risk_level == 'high']
    medium = [n for n in report.nodes if n.risk_level == 'medium']
    low = [n for n in report.nodes if n.risk_level == 'low']

    if critical:
        lines.append('  %% 🔴 关键风险')
        for n in critical:
            short = n.signal.split('.')[-1]
            lines.append(f'  {short}[{short}]')
        lines.append('')

    if high:
        lines.append('  %% 🟠 高风险')
        for n in high:
            short = n.signal.split('.')[-1]
            lines.append(f'  {short}[{short}]')
        lines.append('')

    if medium:
        lines.append('  %% 🟡 中风险')
        for n in medium[:20]:
            short = n.signal.split('.')[-1]
            lines.append(f'  {short}[{short}]')
        lines.append('')

    if low:
        lines.append('  %% 🟢 低风险')
        for n in low[:20]:
            short = n.signal.split('.')[-1]
            lines.append(f'  {short}[{short}]')
        if len(low) > 20:
            lines.append(f'  %% ... 还有 {len(low)-20} 个')
        lines.append('')

    # 样式
    lines.append('  %% 样式')
    for n in critical:
        lines.append(f'  style {n.signal.split(".")[-1]} fill:#FF0000,color:#fff')
    for n in high:
        lines.append(f'  style {n.signal.split(".")[-1]} fill:#FFA500')
    for n in medium:
        lines.append(f'  style {n.signal.split(".")[-1]} fill:#FFD700')
    for n in low[:20]:
        lines.append(f'  style {n.signal.split(".")[-1]} fill:#90EE90')

    return '\n'.join(lines)
