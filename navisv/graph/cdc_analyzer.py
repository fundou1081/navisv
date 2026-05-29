"""
CDCAnalyzer - 跨时钟域检测

识别所有跨时钟域的信号路径，给出每条 CDC 路径的详细信息。
"""

from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import deque
import networkx as nx


@dataclass
class CDCPath:
    """单条 CDC 路径"""
    src_reg: str           # 源寄存器 (clock domain A)
    dst_reg: str           # 目标寄存器 (clock domain B)
    src_clock: str         # 源时钟域名
    dst_clock: str         # 目标时钟域名
    intermediate: List[str]  # 中间节点 (组合逻辑/无寄存器, 可能为空)
    path_depth: int         # 路径深度 (寄存器跳数)
    edge_count: int         # 总边数
    cross_points: List[str] = field(default_factory=list)

    def __str__(self):
        depth_str = f"({self.path_depth} hops)" if self.path_depth > 1 else "(direct)"
        src = self.src_reg.split('.')[-1][:20]
        dst = self.dst_reg.split('.')[-1][:20]
        src_c = self.src_clock.split('.')[-1][:12]
        dst_c = self.dst_clock.split('.')[-1][:12]
        return f"{src}({src_c}) → {dst}({dst_c}) {depth_str} [{self.edge_count} edges]"


@dataclass
class CDCReport:
    """CDC 分析报告"""
    module: str = ''
    total_paths: int = 0
    cross_clock_paths: List[CDCPath] = field(default_factory=list)
    clock_domains: Dict[str, int] = field(default_factory=dict)
    registers_by_clock: Dict[str, List[str]] = field(default_factory=dict)
    graph_metrics: Dict[str, Any] = field(default_factory=dict)


class CDCAnalyzer:
    """
    CDC 检测器

    算法:
    1. 识别所有时钟域 (通过 PosEdge 边找到时钟信号)
    2. 建立寄存器→时钟域映射
    3. 在寄存器级图上找所有路径
    4. 输出两端时钟域不同的路径
    """

    def __init__(self, design_graph, module_prefix: str = ''):
        self.dg = design_graph
        self.G = design_graph.graph
        self.module_prefix = module_prefix

    def analyze(self) -> CDCReport:
        report = CDCReport(module=self.module_prefix or 'all')

        clock_domains, reg_to_clock = self._identify_clock_domains()
        report.clock_domains = clock_domains
        report.registers_by_clock = {c: [] for c in clock_domains}
        for reg, clk in reg_to_clock.items():
            if clk in report.registers_by_clock:
                report.registers_by_clock[clk].append(reg)

        reg_graph = self._build_reg_graph(reg_to_clock)
        cdc_paths = self._find_cdc_paths(reg_graph, reg_to_clock)
        report.cross_clock_paths = cdc_paths
        report.total_paths = len(cdc_paths)

        report.graph_metrics = {
            'total_registers': len(reg_to_clock),
            'clock_domains': len(clock_domains),
            'cdc_paths': len(cdc_paths),
        }
        return report

    def _identify_clock_domains(self) -> Tuple[Dict[str, int], Dict[str, str]]:
        """识别所有时钟域"""
        clock_domains: Dict[str, int] = {}
        reg_to_clock: Dict[str, str] = {}

        all_nodes = list(self.G.nodes)
        if self.module_prefix:
            all_nodes = [n for n in all_nodes if n.startswith(self.module_prefix)]

        registers = [n for n in all_nodes
                    if self.dg.node_attr(n).get('timing') == 'sequential']

        for reg in registers:
            clock_signal = None
            for src, _, data in self.G.in_edges(reg, data=True):
                if data.get('edge_kind') == 'PosEdge':
                    clock_signal = src
                    break
            if clock_signal:
                reg_to_clock[reg] = clock_signal
                clock_domains[clock_signal] = clock_domains.get(clock_signal, 0) + 1

        return clock_domains, reg_to_clock

    def _build_reg_graph(self, reg_to_clock: Dict[str, str]) -> nx.DiGraph:
        """构建寄存器级图"""
        reg_graph = nx.DiGraph()
        registers = set(reg_to_clock.keys())

        all_nodes = list(self.G.nodes)
        if self.module_prefix:
            all_nodes = [n for n in all_nodes if n.startswith(self.module_prefix)]

        inputs = set(n for n in all_nodes
                     if self.dg.node_attr(n).get('kind') == 'Port'
                     and self.dg.node_attr(n).get('direction') in ('In', 'in'))

        for reg in registers:
            if not reg_graph.has_node(reg):
                reg_graph.add_node(reg, clock=reg_to_clock[reg])

        for src_reg in registers:
            visited = set([src_reg])
            queue = deque([(src_reg, 0, [])])

            while queue:
                node, depth, path = queue.popleft()
                if depth > 10:
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
                        queue.append((dst, depth + 1, path + [dst]))

        for reg in registers:
            for src, _, data in self.G.in_edges(reg, data=True):
                ek = data.get('edge_kind', '')
                if ek in ('PosEdge', 'NegEdge'):
                    continue
                if src in inputs:
                    if not reg_graph.has_edge(src, reg):
                        reg_graph.add_edge(src, reg)

        return reg_graph

    def _find_cdc_paths(self, reg_graph: nx.DiGraph,
                        reg_to_clock: Dict[str, str]) -> List[CDCPath]:
        """找所有 CDC 路径"""
        cdc_paths: List[CDCPath] = []
        registers = set(reg_to_clock.keys())

        for src_reg in registers:
            src_clock = reg_to_clock[src_reg]
            visited_path = {src_reg: [src_reg]}
            queue = deque([(src_reg, 0, [src_reg])])

            while queue:
                node, depth, path = queue.popleft()
                if depth > 10:
                    continue

                for _, dst in reg_graph.out_edges(node):
                    if dst in visited_path:
                        continue
                    new_path = path + [dst]
                    visited_path[dst] = new_path

                    if dst in registers:
                        dst_clock = reg_to_clock[dst]
                        if dst_clock != src_clock:
                            intermediate = path[1:-1] if len(path) > 2 else []
                            cdc = CDCPath(
                                src_reg=src_reg,
                                dst_reg=dst,
                                src_clock=src_clock,
                                dst_clock=dst_clock,
                                intermediate=intermediate,
                                path_depth=len(new_path) - 1,
                                edge_count=len(new_path) - 1 + len(intermediate),
                            )
                            cdc_paths.append(cdc)

                    queue.append((dst, depth + 1, new_path))

        cdc_paths.sort(key=lambda p: (p.dst_clock, p.path_depth))
        return cdc_paths


# ── CLI ───────────────────────────────────────────────────────────────

def run_cdc(args):
    """CDC 分析 CLI"""
    import tempfile, os, json, sys
    from navisv import DesignDriver

    errors = []
    slang_bin = os.environ.get('NAVISV_SLANG_BIN', '~/my_dv_proj/slang/slang')
    if not os.path.exists(os.path.expanduser(slang_bin)):
        errors.append(f'slang not found at {slang_bin}')
    if errors:
        for e in errors:
            print(f'错误: {e}', file=sys.stderr)
        return {'success': False}

    output_dir = tempfile.mkdtemp(prefix='navisv_cdc_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir,
                         include_dirs=args.include or [], cache=True)
        dd.build()
        dg = dd.design_graph

        module_prefix = args.module
        if not module_prefix:
            for n in dg.graph.nodes:
                parts = n.split('.')
                if len(parts) >= 2:
                    module_prefix = parts[0]
                    break

        analyzer = CDCAnalyzer(dg, module_prefix=module_prefix)
        report = analyzer.analyze()

        fmt = getattr(args, 'format', 'text') or 'text'
        limit = getattr(args, 'limit', 50) or 50

        if fmt == 'text':
            _print_cdc_text(report, limit)
        elif fmt == 'json':
            print(json.dumps(_cdc_to_dict(report), indent=2, ensure_ascii=False))
        else:
            print(f'不支持的格式: {fmt}', file=sys.stderr)

        return {'success': True}
    except Exception as e:
        print(f'错误: {e}', file=sys.stderr)
        import traceback; traceback.print_exc()
        return {'success': False}


def _print_cdc_text(report: CDCReport, limit: int = 50):
    """打印 CDC 报告"""
    print(f'\n{"="*70}')
    print(f'CDC 分析报告: {report.module}')
    print(f'{"="*70}')
    print(f'  总 CDC 路径: {report.total_paths}')
    print(f'  时钟域数量: {len(report.clock_domains)}')

    print(f'\n时钟域:')
    for clk, cnt in sorted(report.clock_domains.items(), key=lambda x: -x[1]):
        print(f'  {clk.split(".")[-1]}: {cnt} 个寄存器')

    if not report.cross_clock_paths:
        print('\n  ✅ 未发现 CDC 路径')
        return

    print(f'\n跨时钟域路径 (共 {report.total_paths} 条, 显示前 {limit} 条):')
    print(f'  {"源寄存器":<22} {"时钟":<15}  {"目标寄存器":<22} {"时钟":<15} {"跳数"}')
    print(f'  {"-"*82}')

    for p in report.cross_clock_paths[:limit]:
        src = p.src_reg.split('.')[-1][:21]
        dst = p.dst_reg.split('.')[-1][:21]
        src_c = p.src_clock.split('.')[-1][:14]
        dst_c = p.dst_clock.split('.')[-1][:14]
        print(f'  {src:<22} [{src_c}] -> {dst:<22} [{dst_c}]  {p.edge_count}')


def _cdc_to_dict(report: CDCReport) -> Dict:
    """CDC 报告转字典"""
    return {
        'module': report.module,
        'summary': {
            'total_paths': report.total_paths,
            'clock_domains': len(report.clock_domains),
            'registers': sum(report.clock_domains.values()),
        },
        'clock_domains': {k.split('.')[-1]: v for k, v in report.clock_domains.items()},
        'registers_by_clock': {k.split('.')[-1]: [n.split('.')[-1] for n in v]
                               for k, v in report.registers_by_clock.items()},
        'cdc_paths': [
            {
                'src_reg': p.src_reg.split('.')[-1],
                'dst_reg': p.dst_reg.split('.')[-1],
                'src_clock': p.src_clock.split('.')[-1],
                'dst_clock': p.dst_clock.split('.')[-1],
                'path_depth': p.path_depth,
                'edge_count': p.edge_count,
                'intermediate': [n.split('.')[-1] for n in p.intermediate],
            }
            for p in report.cross_clock_paths
        ],
    }