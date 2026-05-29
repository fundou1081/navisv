"""
ClockStats - 时钟/复位信号 fan-out 统计

输出每个时钟信号驱动的寄存器数量。
"""

from typing import Dict, List
from dataclasses import dataclass


@dataclass
class ClockStat:
    clock: str
    reg_count: int = 0
    registers: List[str] = None

    def __post_init__(self):
        if self.registers is None:
            self.registers = []


@dataclass
class ResetStat:
    reset: str
    reg_count: int = 0
    registers: List[str] = None

    def __post_init__(self):
        if self.registers is None:
            self.registers = []


class ClockStatsAnalyzer:
    """时钟 fan-out 分析器"""

    def __init__(self, design_graph, module_prefix: str = ''):
        self.dg = design_graph
        self.G = design_graph.graph
        self.module_prefix = module_prefix

    def analyze(self):
        all_nodes = list(self.G.nodes)
        if self.module_prefix:
            all_nodes = [n for n in all_nodes if n.startswith(self.module_prefix)]

        registers = [n for n in all_nodes
                    if self.dg.node_attr(n).get('timing') == 'sequential']

        clock_map: Dict[str, List[str]] = {}
        reset_map: Dict[str, List[str]] = {}

        for reg in registers:
            for src, _, data in self.G.in_edges(reg, data=True):
                ek = data.get('edge_kind', '')
                if ek == 'PosEdge':
                    clock_map.setdefault(src, []).append(reg)
                elif ek == 'NegEdge':
                    reset_map.setdefault(src, []).append(reg)

        clock_stats = [ClockStat(clock=k, reg_count=len(v), registers=v)
                      for k, v in sorted(clock_map.items(), key=lambda x: -len(x[1]))]
        reset_stats = [ResetStat(reset=k, reg_count=len(v), registers=v)
                      for k, v in sorted(reset_map.items(), key=lambda x: -len(x[1]))]

        return {
            'module': self.module_prefix or 'all',
            'total_registers': len(registers),
            'total_clocks': len(clock_map),
            'clock_stats': clock_stats,
            'reset_stats': reset_stats,
        }


def run_clock_stats(args):
    """CLI 入口"""
    import tempfile, os, sys, json
    from navisv import DesignDriver

    slang_bin = os.environ.get('NAVISV_SLANG_BIN', '~/my_dv_proj/slang/slang')
    if not os.path.exists(os.path.expanduser(slang_bin)):
        print(f'错误: slang not found at {slang_bin}', file=sys.stderr)
        return {'success': False}

    output_dir = tempfile.mkdtemp(prefix='navisv_clock_')
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

        analyzer = ClockStatsAnalyzer(dg, module_prefix=module_prefix)
        result = analyzer.analyze()

        fmt = getattr(args, 'format', 'text') or 'text'
        if fmt == 'text':
            _print_stats(result)
        elif fmt == 'json':
            print(json.dumps(_to_dict(result), indent=2, ensure_ascii=False))

        return {'success': True}
    except Exception as e:
        print(f'错误: {e}', file=sys.stderr)
        import traceback; traceback.print_exc()
        return {'success': False}


def _print_stats(result: Dict):
    print(f'\n{"="*70}')
    print(f'Clock/Reset Fan-out 报告: {result["module"]}')
    print(f'{"="*70}')
    print(f'  总寄存器: {result["total_registers"]}')
    print(f'  时钟域数量: {result["total_clocks"]}')

    print(f'\n时钟域 (按 fan-out 排序):')
    print(f'  {"时钟":<35} {"寄存器数":<10} 寄存器列表')
    print(f'  {"-"*75}')

    for cs in result['clock_stats']:
        regs_str = ', '.join(r.split('.')[-1] for r in cs.registers[:6])
        more = f' (+{len(cs.registers)-6} more)' if len(cs.registers) > 6 else ''
        print(f'  {cs.clock:<35} {cs.reg_count:<10} {regs_str}{more}')

    if result['reset_stats']:
        print(f'\n复位信号 (按 fan-out 排序):')
        print(f'  {"复位":<35} {"寄存器数":<10} 寄存器列表')
        print(f'  {"-"*75}')
        for rs in result['reset_stats']:
            regs_str = ', '.join(r.split('.')[-1] for r in rs.registers[:6])
            more = f' (+{len(rs.registers)-6} more)' if len(rs.registers) > 6 else ''
            print(f'  {rs.reset:<35} {rs.reg_count:<10} {regs_str}{more}')


def _to_dict(result: Dict) -> Dict:
    return {
        'module': result['module'],
        'total_registers': result['total_registers'],
        'total_clocks': result['total_clocks'],
        'clocks': [
            {'clock': c.clock, 'reg_count': c.reg_count,
             'registers': [r.split('.')[-1] for r in c.registers]}
            for c in result['clock_stats']
        ],
        'resets': [
            {'reset': r.reset, 'reg_count': r.reg_count,
             'registers': [r.split('.')[-1] for r in r.registers]}
            for r in result['reset_stats']
        ],
    }