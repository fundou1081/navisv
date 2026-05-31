"""
RiskAnalyzer - 基于图拓扑的信号风险/复杂度分析

利用有向图的拓扑指标,评估每个信号的风险等级:
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

    # 功能逻辑复杂度
    func_complexity: float = 0.0    # 功能复杂度得分 (0-100)
    func_factors: List[str] = field(default_factory=list)

    # 时序复杂度
    timing_complexity: float = 0.0  # 时序复杂度得分 (0-100)
    timing_factors: List[str] = field(default_factory=list)
    reg_chain_depth: int = 0        # 寄存器链深度
    clock_domain_count: int = 0     # 时钟域数量

    # 综合风险
    risk_level: str = 'low'         # low/medium/high/critical
    total_score: float = 0.0        # 综合得分 (func + timing)


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
    critical_paths: List[Dict] = field(default_factory=list)
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

        # 2. 预计算 betweenness centrality (较慢,只算一次)
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
        report.nodes.sort(key=lambda x: x.total_score, reverse=True)

        # 4. 计算关键路径
        report.critical_paths = self.get_critical_paths(top_n=5)

        return report

    def _compute_node_metrics(self, node: str, bc: dict, cc: dict, pr: dict) -> NodeRiskMetrics:
        """计算单个节点的风险指标"""
        attr = self.dg.node_attr(node)
        kind = attr.get('kind', '')
        timing = attr.get('timing', 'unknown')
        msb, lsb = attr.get('bit_width', (0, 0))
        bit_width = abs(msb - lsb) + 1

        # 时钟域 (只取真正的时钟信号,排除复位)
        clock_domain = ''
        real_clocks = set()
        for src, _, data in self.G.in_edges(node, data=True):
            ek = data.get('edge_kind', '')
            if ek == 'PosEdge':  # 只看 PosEdge (复位通常是 NegEdge)
                clock_domain = src
                real_clocks.add(src)
            elif ek == 'NegEdge':
                src_name = src.split('.')[-1].lower()
                if 'rst' not in src_name and 'reset' not in src_name:
                    real_clocks.add(src)

        # 图拓扑指标 (排除时钟/复位边, 用纯数据图计算 fanin/fanout)
        in_deg = 0
        for src, _, data in self.G.in_edges(node, data=True):
            ek = data.get('edge_kind', '')
            if ek not in ('PosEdge', 'NegEdge'):
                in_deg += 1
        out_deg = self.G.out_degree(node)
        fanin = len(nx.ancestors(self._data_graph, node)) if node in self._data_graph else 0
        fanout = len(nx.descendants(self._data_graph, node)) if node in self._data_graph else 0

        # 计算风险评分
        func_score, timing_score, func_factors, timing_factors = self._calculate_risk_score(
            node, kind, timing, bit_width, clock_domain,
            in_deg, out_deg, fanin, fanout,
            bc.get(node, 0), cc.get(node, 0), pr.get(node, 0)
        )

        # 寄存器链深度
        reg_depth = self._estimate_reg_depth(node)

        # 时钟域数量 (只统计真正的时钟,排除复位)
        clock_domains = set()
        for src, _, data in self.G.in_edges(node, data=True):
            ek = data.get('edge_kind', '')
            if ek == 'PosEdge':
                clock_domains.add(src)
            elif ek == 'NegEdge':
                src_name = src.split('.')[-1].lower()
                if 'rst' not in src_name and 'reset' not in src_name:
                    clock_domains.add(src)

        # 综合得分 = max(功能, 时序) + 0.3 * min(功能, 时序)
        total = max(func_score, timing_score) + 0.3 * min(func_score, timing_score)

        # 确定风险等级
        if total >= 80:
            level = 'critical'
        elif total >= 60:
            level = 'high'
        elif total >= 40:
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
            func_complexity=func_score,
            func_factors=func_factors,
            timing_complexity=timing_score,
            timing_factors=timing_factors,
            reg_chain_depth=reg_depth,
            clock_domain_count=len(clock_domains),
            risk_level=level,
            total_score=round(total, 1),
        )

    def _calculate_risk_score(self, node, kind, timing, bit_width, clock_domain,
                               in_deg, out_deg, fanin, fanout, bc, cc, pr) -> Tuple[float, float, List[str], List[str]]:
        """计算风险评分 (0-100)

        Returns:
            (func_score, timing_score, func_factors, timing_factors)
        """
        # ============================================
        # 功能逻辑复杂度 (0-100)
        # ============================================
        func_score = 0.0
        func_factors = []

        # 1. 度数风险 (0-30分)
        # 高入度 = 多源竞争 = 逻辑复杂
        if in_deg >= 10:
            func_score += 15
            func_factors.append(f'高入度({in_deg})')
        elif in_deg >= 5:
            func_score += 10
            func_factors.append(f'中入度({in_deg})')
        elif in_deg >= 3:
            func_score += 5

        # 高出度 = 影响面大 = 功能重要
        if out_deg >= 10:
            func_score += 10
            func_factors.append(f'高出度({out_deg})')
        elif out_deg >= 5:
            func_score += 5
            func_factors.append(f'中出度({out_deg})')

        # 2. Fan-in/Fan-out 风险 (0-25分)
        if fanin >= 50:
            func_score += 12
            func_factors.append(f'大Fan-in锥({fanin})')
        elif fanin >= 20:
            func_score += 6

        if fanout >= 50:
            func_score += 13
            func_factors.append(f'大Fan-out锥({fanout})')
        elif fanout >= 20:
            func_score += 6

        # 3. 关键路径风险 (0-15分)
        if bc >= 0.1:
            func_score += 15
            func_factors.append(f'关键路径(BC={bc:.3f})')
        elif bc >= 0.05:
            func_score += 10
            func_factors.append(f'重要路径(BC={bc:.3f})')
        elif bc >= 0.02:
            func_score += 5

        # 4. 位宽风险 (0-15分)
        if bit_width >= 32:
            func_score += 15
            func_factors.append(f'宽位宽({bit_width}-bit)')
        elif bit_width >= 16:
            func_score += 10
            func_factors.append(f'中位宽({bit_width}-bit)')
        elif bit_width >= 8:
            func_score += 5

        # 5. 条件复杂度 (0-15分)
        cond_count = sum(1 for _, _, d in self.G.in_edges(node, data=True) if d.get('condition'))
        if cond_count >= 8:
            func_score += 15
            func_factors.append(f'高条件({cond_count}个)')
        elif cond_count >= 5:
            func_score += 10
            func_factors.append(f'多条件({cond_count}个)')
        elif cond_count >= 3:
            func_score += 5
            func_factors.append(f'条件({cond_count}个)')

        func_score = min(100, max(0, func_score))

        # ============================================
        # 时序复杂度 (0-100)
        # ============================================
        timing_score = 0.0
        timing_factors = []

        # 1. 是否寄存器 (0-20分)
        if timing == 'sequential':
            timing_score += 20
            timing_factors.append('寄存器')

        # 2. 时钟域 (0-30分)
        # 统计连接到该信号的时钟域数量 (排除复位)
        clock_domains = set()
        for src, _, data in self.G.in_edges(node, data=True):
            ek = data.get('edge_kind', '')
            if ek == 'PosEdge':
                clock_domains.add(src)
            elif ek == 'NegEdge':
                src_name = src.split('.')[-1].lower()
                if 'rst' not in src_name and 'reset' not in src_name:
                    clock_domains.add(src)

        clock_count = len(clock_domains)
        if clock_count >= 3:
            timing_score += 30
            timing_factors.append(f'跨{clock_count}时钟域')
        elif clock_count >= 2:
            timing_score += 20
            timing_factors.append(f'跨{clock_count}时钟域')
        elif clock_count == 1:
            timing_score += 10

        # 3. 寄存器链深度 (0-25分)
        # 从输入端口到该信号的最长寄存器链
        reg_depth = self._estimate_reg_depth(node)
        if reg_depth >= 5:
            timing_score += 25
            timing_factors.append(f'深寄存器链({reg_depth}级)')
        elif reg_depth >= 3:
            timing_score += 15
            timing_factors.append(f'寄存器链({reg_depth}级)')
        elif reg_depth >= 2:
            timing_score += 8

        # 4. 时序 fan-in 复杂度 (0-15分)
        # 有多少个寄存器驱动这个信号
        seq_fanin = sum(1 for src, dst in self.G.in_edges(node)
                       if self.dg.node_attr(src).get('timing') == 'sequential')
        if seq_fanin >= 5:
            timing_score += 15
            timing_factors.append(f'多寄存器驱动({seq_fanin})')
        elif seq_fanin >= 3:
            timing_score += 10
            timing_factors.append(f'寄存器驱动({seq_fanin})')
        elif seq_fanin >= 1:
            timing_score += 5

        # 5. 时序 fan-out 复杂度 (0-10分)
        # 这个寄存器驱动多少个其他寄存器
        seq_fanout = sum(1 for src, dst in self.G.out_edges(node)
                        if self.dg.node_attr(dst).get('timing') == 'sequential')
        if seq_fanout >= 5:
            timing_score += 10
            timing_factors.append(f'驱动多寄存器({seq_fanout})')
        elif seq_fanout >= 2:
            timing_score += 5

        timing_score = min(100, max(0, timing_score))

        return round(func_score, 1), round(timing_score, 1), func_factors, timing_factors

    def _estimate_reg_depth(self, node: str) -> int:
        """估算信号的寄存器链深度

        使用寄存器级图的最长路径算法
        """
        if not hasattr(self, '_reg_depth_map'):
            self._build_reg_graph()
        return self._reg_depth_map.get(node, 0)

    @property
    def _data_graph(self):
        """纯数据图(排除时钟/复位边), 缓存避免重复构建"""
        if not hasattr(self, '_data_graph_cache'):
            import networkx as nx
            G = nx.DiGraph()
            for src, dst, data in self.G.edges(data=True):
                ek = data.get('edge_kind', '')
                if ek not in ('PosEdge', 'NegEdge'):
                    G.add_edge(src, dst)
            self._data_graph_cache = G
        return self._data_graph_cache

    def _build_reg_graph(self):
        """构建寄存器级图并计算关键路径"""
        from collections import deque

        registers = set(n for n in self.G.nodes if self.dg.node_attr(n).get('timing') == 'sequential')
        inputs = set(n for n in self.G.nodes
                     if self.dg.node_attr(n).get('kind') == 'Port'
                     and self.dg.node_attr(n).get('direction') == 'In')

        # 构建寄存器级图
        reg_graph = nx.DiGraph()

        for src_reg in registers:
            visited = set()
            queue = deque([(src_reg, 0)])

            while queue:
                node, depth = queue.popleft()
                if depth > 3:
                    continue

                for _, dst, data in self.G.out_edges(node, data=True):
                    ek = data.get('edge_kind', '')
                    if ek in ('PosEdge', 'NegEdge'):
                        continue
                    if dst in visited:
                        continue
                    visited.add(dst)

                    if dst in registers and dst != src_reg:
                        if not reg_graph.has_edge(src_reg, dst):
                            reg_graph.add_edge(src_reg, dst)
                    elif dst not in registers and dst not in inputs:
                        queue.append((dst, depth + 1))

        # 添加输入端口到寄存器的边
        for reg in registers:
            for src, _, data in self.G.in_edges(reg, data=True):
                ek = data.get('edge_kind', '')
                if ek in ('PosEdge', 'NegEdge'):
                    continue
                if src in inputs:
                    if not reg_graph.has_edge(src, reg):
                        reg_graph.add_edge(src, reg)

        self._reg_graph = reg_graph
        
        # 计算每个寄存器的时序深度
        self._reg_depth_map = {}
        self._reg_pred_map = {}

        if nx.is_directed_acyclic_graph(reg_graph):
            topo = list(nx.topological_sort(reg_graph))
            dist = {n: 0 for n in topo}
            prev = {n: None for n in topo}

            for u in topo:
                for v in reg_graph.successors(u):
                    if dist[u] + 1 > dist[v]:
                        dist[v] = dist[u] + 1
                        prev[v] = u

            self._reg_depth_map = dist
            self._reg_pred_map = prev
        else:
            # 有环: 缩点后找最长路径
            sccs = list(nx.strongly_connected_components(reg_graph))
            scc_map = {}
            for i, scc in enumerate(sccs):
                for node in scc:
                    scc_map[node] = i

            dag = nx.DiGraph()
            for src, dst in reg_graph.edges():
                if scc_map[src] != scc_map[dst]:
                    if not dag.has_edge(scc_map[src], scc_map[dst]):
                        dag.add_edge(scc_map[src], scc_map[dst])

            topo = list(nx.topological_sort(dag))
            dist = {n: 0 for n in topo}

            for u in topo:
                for v in dag.successors(u):
                    if dist[u] + 1 > dist[v]:
                        dist[v] = dist[u] + 1

            for reg in registers:
                scc_id = scc_map.get(reg)
                if scc_id is not None:
                    self._reg_depth_map[reg] = dist.get(scc_id, 0)

    def get_critical_paths(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """获取关键路径"""
        if not hasattr(self, '_reg_graph'):
            self._build_reg_graph()
        
        paths = []
        sorted_regs = sorted(self._reg_depth_map.items(), key=lambda x: -x[1])
        
        seen = set()
        for target, depth in sorted_regs:
            if depth < 2 or target in seen:
                continue
            
            # 在寄存器级图上回溯
            path = [target]
            current = target
            for _ in range(30):
                best_pred = None
                best_depth = -1
                for pred in self._reg_graph.predecessors(current):
                    pred_depth = self._reg_depth_map.get(pred, 0)
                    if pred_depth > best_depth and pred not in path:
                        best_pred = pred
                        best_depth = pred_depth
                if best_pred:
                    path.append(best_pred)
                    current = best_pred
                else:
                    break
            path.reverse()
            
            seen.add(target)
            paths.append({
                'path': path,
                'depth': depth,
                'source': path[0].split('.')[-1],
                'target': path[-1].split('.')[-1],
            })
            
            if len(paths) >= top_n:
                break
        
        return paths

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
        'critical_paths': report.critical_paths,
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
                'func_complexity': n.func_complexity,
                'func_factors': n.func_factors,
                'timing_complexity': n.timing_complexity,
                'timing_factors': n.timing_factors,
                'reg_chain_depth': n.reg_chain_depth,
                'clock_domain_count': n.clock_domain_count,
                'total_score': n.total_score,
                'risk_level': n.risk_level,
            }
            for n in report.nodes
        ],
    }


def export_risk_dot(report: RiskReport, rankdir: str = 'LR',
                    cdc_edge_pairs=None, cdc_node_set=None) -> str:
    """生成风险 DOT 图

    rankdir: 图方向 (默认 LR, 另支持 TB/TD/BT/RL)
    cdc_edge_pairs: CDC 边对集合，用于高亮 CDC 边
    cdc_node_set: CDC 节点集合，用于高亮 CDC 节点
    """
    lines = []
    lines.append(f'digraph risk_{report.module} {{')
    lines.append(f'  rankdir={rankdir};')
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

        # 标签包含功能+时序分数
        label = f"{short}\nF={n.func_complexity:.0f} T={n.timing_complexity:.0f}"
        if n.func_factors or n.timing_factors:
            factors = (n.func_factors + n.timing_factors)[:2]
            label += f"\n{', '.join(factors)}"

        shape = 'parallelogram' if n.kind == 'Port' else 'box'

        # CDC 节点高亮
        if cdc_node_set and n.signal in cdc_node_set:
            lines.append(f'  "{short}" [fillcolor={color}, shape={shape}, label="{label}", color="#FF1493", penwidth=2];')
        else:
            lines.append(f'  "{short}" [fillcolor={color}, shape={shape}, label="{label}"];')

    # 边（简化版：无显式边，可通过关系推断）
    # 如果需要，可以添加节点间关系边
    lines.append('}')

    return '\n'.join(lines)


def export_risk_mermaid(report: RiskReport, rankdir: str = 'LR',
                    cdc_edge_pairs=None, cdc_node_set=None) -> str:
    """生成风险 Mermaid 图
    
    rankdir: 图方向 (默认 LR, 另支持 TB/BT/RL)"""
    lines = []
    lines.append(f'graph {rankdir}')
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
            cdc_tag = ' ⚡CDC' if cdc_node_set and n.signal in cdc_node_set else ''
            lines.append(f'  {short}[{short}{cdc_tag}]')
        lines.append('')

    if high:
        lines.append('  %% 🟠 高风险')
        for n in high:
            short = n.signal.split('.')[-1]
            cdc_tag = ' ⚡CDC' if cdc_node_set and n.signal in cdc_node_set else ''
            lines.append(f'  {short}[{short}{cdc_tag}]')
        lines.append('')

    if medium:
        lines.append('  %% 🟡 中风险')
        for n in medium[:20]:
            short = n.signal.split('.')[-1]
            cdc_tag = ' ⚡CDC' if cdc_node_set and n.signal in cdc_node_set else ''
            lines.append(f'  {short}[{short}{cdc_tag}]')
        if len(medium) > 20:
            lines.append(f'  %% ... 还有 {len(medium)-20} 个')
        lines.append('')

    if low:
        lines.append('  %% 🟢 低风险')
        for n in low[:20]:
            short = n.signal.split('.')[-1]
            cdc_tag = ' ⚡CDC' if cdc_node_set and n.signal in cdc_node_set else ''
            lines.append(f'  {short}[{short}{cdc_tag}]')
        if len(low) > 20:
            lines.append(f'  %% ... 还有 {len(low)-20} 个')
        lines.append('')

    # 样式
    lines.append('  %% 样式')
    for n in critical:
        short = n.signal.split('.')[-1]
        cdc_style = ',stroke:#FF1493,stroke-width:3px' if cdc_node_set and n.signal in cdc_node_set else ''
        lines.append(f'  style {short} fill:#FF0000,color:#fff{cdc_style}')
    for n in high:
        short = n.signal.split('.')[-1]
        cdc_style = ',stroke:#FF1493,stroke-width:3px' if cdc_node_set and n.signal in cdc_node_set else ''
        lines.append(f'  style {short} fill:#FFA500{cdc_style}')
    for n in medium:
        short = n.signal.split('.')[-1]
        cdc_style = ',stroke:#FF1493,stroke-width:3px' if cdc_node_set and n.signal in cdc_node_set else ''
        lines.append(f'  style {short} fill:#FFD700{cdc_style}')
    for n in low[:20]:
        short = n.signal.split('.')[-1]
        cdc_style = ',stroke:#FF1493,stroke-width:3px' if cdc_node_set and n.signal in cdc_node_set else ''
        lines.append(f'  style {short} fill:#90EE90{cdc_style}')

    return '\n'.join(lines)
