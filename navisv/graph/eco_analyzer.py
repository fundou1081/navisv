"""
ECO Impact Analyzer — 影响分析和 CDC 对比

两种输入模式:
  1. --diff <git_diff_file>       (git diff 格式)
  2. --before <old.sv> --after <new.sv>  (两版文件)

两种分析模式:
  1. --mode impact  (默认)  — 改动信号的影响范围
  2. --mode cdc      — CDC 路径变化对比
"""

import re
import os
import tempfile
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import deque


# ── 数据结构 ───────────────────────────────────────────────────────────

@dataclass
class Change:
    signal: str           # 信号完整路径
    short_name: str        # 信号简称
    change_type: str      # 'assigned' | 'removed' | 'modified' | 'new'
    old_driver: str        # 原驱动表达式
    new_driver: str        # 新驱动表达式
    location: str          # "module:line"
    module: str            # 所属模块


@dataclass
class ImpactNode:
    node: str
    level: int             # 1=L1直接, 2=L2, 3=L3+
    via: str               # 经由哪个节点到达
    kind: str              # 'sequential' | 'combinational' | 'Port'
    cross_module: bool     # 是否跨模块
    is_clock_domain_cross: bool  # 是否跨时钟域
    affected_clocks: List[str] = field(default_factory=list)


@dataclass
class ImpactReport:
    changes: List[Change] = field(default_factory=list)
    l1_nodes: List[ImpactNode] = field(default_factory=list)
    l2_nodes: List[ImpactNode] = field(default_factory=list)
    l3plus_nodes: List[ImpactNode] = field(default_factory=list)
    cross_module_nodes: List[ImpactNode] = field(default_factory=list)
    cdc_related: List[ImpactNode] = field(default_factory=list)
    total_affected: int = 0
    safe_paths: int = 0


@dataclass
class CDCPath:
    src_reg: str
    dst_reg: str
    src_clock: str
    dst_clock: str
    intermediate: List[str] = field(default_factory=list)
    path_depth: int = 0
    edge_count: int = 0

    def key(self):
        return (self.src_reg, self.dst_reg, self.src_clock, self.dst_clock)


@dataclass
class CDCImpactReport:
    before_paths: List[CDCPath] = field(default_factory=list)
    after_paths: List[CDCPath] = field(default_factory=list)
    added_paths: List[CDCPath] = field(default_factory=list)
    removed_paths: List[CDCPath] = field(default_factory=list)
    unchanged_count: int = 0


# ── DiffParser ──────────────────────────────────────────────────────────

class DiffParser:
    """解析代码改动，提取信号变化"""

    ASSIGN_PAT = re.compile(
        r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)\s*(?:<=?|=|:)\s*[^;]+'
    )

    def parse_diff_file(self, diff_path: str) -> List[Change]:
        with open(os.path.expanduser(diff_path)) as f:
            return self.parse_diff_text(f.read())

    def parse_diff_text(self, diff_text: str) -> List[Change]:
        changes = []
        current_file = ''
        current_module = ''
        prev_lines = {}  # line_num -> content for removed lines

        i = 0
        lines = diff_text.split('\n')
        while i < len(lines):
            line = lines[i]

            if line.startswith('+++ '):
                parts = line[4:].strip()
                if parts.startswith('a/'):
                    parts = parts[2:]
                if parts and parts != '/dev/null':
                    current_file = parts
                    current_module = self._guess_module(parts)

            elif line.startswith('@@ '):
                # Parse hunk header like @@ -10,7 +10,7 @@
                m = re.search(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
                if m:
                    pass  # line nums available if needed

            elif line.startswith('-') and not line.startswith('---'):
                content = line[1:].strip()
                if content:
                    for ch in self._extract_changes(content, 'removed', current_module, i+1):
                        changes.append(ch)

            elif line.startswith('+') and not line.startswith('+++'):
                content = line[1:].strip()
                if content:
                    for ch in self._extract_changes(content, 'new', current_module, i+1):
                        changes.append(ch)

            i += 1

        return changes[:20]  # 限制数量

    def parse_two_files(self, old_path: str, new_path: str) -> List[Change]:
        with open(os.path.expanduser(old_path)) as f:
            old_lines = f.readlines()
        with open(os.path.expanduser(new_path)) as f:
            new_lines = f.readlines()

        changes = []
        for i in range(min(len(old_lines), len(new_lines))):
            old_line = old_lines[i].strip()
            new_line = new_lines[i].strip()
            if old_line != new_line and old_line and new_line:
                sigs_old = self.ASSIGN_PAT.findall(old_line)
                sigs_new = self.ASSIGN_PAT.findall(new_line)
                for sig in sigs_new[:5]:
                    module = self._guess_module(old_path)
                    changes.append(Change(
                        signal=sig if '.' in sig else f"{module}.{sig}" if module else sig,
                        short_name=sig.split('.')[-1],
                        change_type='modified',
                        old_driver=old_line[:60],
                        new_driver=new_line[:60],
                        location=f"{module}:{i+1}",
                        module=module,
                    ))
        return changes[:20]

    def _extract_changes(self, line: str, change_type: str,
                        module: str, line_num: int) -> List[Change]:
        changes = []
        for match in self.ASSIGN_PAT.finditer(line):
            sig = match.group(1)
            expr = match.group(0)[:60]
            changes.append(Change(
                signal=sig if '.' in sig else f"{module}.{sig}" if module else sig,
                short_name=sig.split('.')[-1],
                change_type=change_type,
                old_driver=expr if change_type == 'removed' else '',
                new_driver=expr if change_type == 'new' else '',
                location=f"{module}:{line_num}",
                module=module,
            ))
        return changes

    def _guess_module(self, filepath: str) -> str:
        basename = os.path.basename(filepath)
        if '.' in basename:
            name = basename.rsplit('.', 1)[0]
            for suffix in ('_tb', '_test', '_harness', '_driver'):
                if name.endswith(suffix):
                    name = name[:-len(suffix)]
            return name
        return basename


# ── ImpactAnalyzer ────────────────────────────────────────────────────

class ECOImpactAnalyzer:
    """BFS fan-out 影响分析"""

    def __init__(self, design_graph, cdc_analyzer=None):
        self.dg = design_graph
        self.G = design_graph.graph
        self.cdc = cdc_analyzer

    def analyze(self, changes: List[Change], max_depth: int = 3) -> ImpactReport:
        report = ImpactReport(changes=changes)

        changed_nodes = []
        for ch in changes:
            matched = self._find_matching_nodes(ch.signal)
            changed_nodes.extend(matched)

        if not changed_nodes:
            return report

        visited = {}
        queue = deque()

        for node in changed_nodes:
            visited[node] = (1, node)
            queue.append((node, 1, node))

        cdc_paths = set()
        if self.cdc:
            for p in self.cdc.analyze().cross_clock_paths:
                cdc_paths.add(p.src_reg)
                cdc_paths.add(p.dst_reg)

        while queue:
            current, level, via = queue.popleft()
            if level >= max_depth:
                continue

            for _, dst, data in self.G.out_edges(current, data=True):
                if dst in visited:
                    continue

                next_level = level + 1
                visited[dst] = (next_level, current)
                queue.append((dst, next_level, current))

        for node, (level, via) in visited.items():
            if node in changed_nodes:
                continue

            attr = self.dg.node_attr(node)
            kind = attr.get('kind', 'Net')

            cross_mod = self._is_cross_module(
                changed_nodes[0] if changed_nodes else node, node)

            cdc_related = node in cdc_paths

            affected_clocks = []
            for src, _, data in self.G.in_edges(node, data=True):
                if data.get('edge_kind') in ('PosEdge', 'NegEdge'):
                    affected_clocks.append(src)

            imp = ImpactNode(
                node=node, level=level, via=via, kind=kind,
                cross_module=cross_mod, is_clock_domain_cross=cdc_related,
                affected_clocks=affected_clocks,
            )

            if level == 1:
                report.l1_nodes.append(imp)
            elif level == 2:
                report.l2_nodes.append(imp)
            else:
                report.l3plus_nodes.append(imp)

            if cross_mod:
                report.cross_module_nodes.append(imp)
            if cdc_related:
                report.cdc_related.append(imp)

        report.total_affected = len(visited) - len(changed_nodes)
        return report

    def _find_matching_nodes(self, signal: str) -> List[str]:
        result = []
        if signal in self.G:
            result.append(signal)

        short = signal.split('.')[-1]
        for node in self.G.nodes:
            if node.endswith(short) and node not in result:
                if len(result) < 10:
                    result.append(node)

        if not result:
            for node in self.G.nodes:
                if signal in node and node not in result:
                    if len(result) < 5:
                        result.append(node)
        return result

    def _is_cross_module(self, src: str, dst: str) -> bool:
        sp = src.split('.')
        dp = dst.split('.')
        return sp[0] != dp[0] if sp and dp else False


# ── CDCDeltaAnalyzer ──────────────────────────────────────────────────

class CDCDeltaAnalyzer:
    """CDC 变化对比"""

    def __init__(self, design_graph):
        self.dg = design_graph
        self.G = design_graph.graph

    def analyze_before(self) -> List[CDCPath]:
        return self._get_cdc_paths()

    def compare(self, before_paths: List[CDCPath],
                after_paths: List[CDCPath]) -> CDCImpactReport:
        report = CDCImpactReport(
            before_paths=before_paths,
            after_paths=after_paths,
        )

        before_keys = set(p.key() for p in before_paths)
        after_keys = set(p.key() for p in after_paths)

        report.added_paths = [p for p in after_paths if p.key() in (after_keys - before_keys)]
        report.removed_paths = [p for p in before_paths if p.key() in (before_keys - after_keys)]
        report.unchanged_count = len(before_keys & after_keys)
        return report

    def _get_cdc_paths(self) -> List[CDCPath]:
        from navisv.graph.cdc_analyzer import CDCAnalyzer
        # 自动检测 top-level module prefix
        module_prefix = ''
        for n in self.G.nodes:
            parts = n.split('.')
            if len(parts) >= 2:
                module_prefix = parts[0]
                break
        analyzer = CDCAnalyzer(self.dg, module_prefix=module_prefix)
        report = analyzer.analyze()
        return report.cross_clock_paths


# ── CLI ────────────────────────────────────────────────────────────────

def run_eco(args):
    """ECO 分析 CLI 入口"""
    import sys, tempfile
    from navisv import DesignDriver

    slang_bin = os.environ.get('NAVISV_SLANG_BIN', '~/my_dv_proj/slang/slang')
    if not os.path.exists(os.path.expanduser(slang_bin)):
        print(f'错误: slang not found', file=sys.stderr)
        return {'success': False}

    mode = getattr(args, 'mode', 'impact') or 'impact'

    try:
        if mode == 'impact':
            return _run_impact_mode(args)
        elif mode == 'cdc':
            return _run_cdc_mode(args)
        else:
            print(f'未知模式: {mode}', file=sys.stderr)
            return {'success': False}
    except Exception as e:
        print(f'错误: {e}', file=sys.stderr)
        import traceback; traceback.print_exc()
        return {'success': False}


def _run_impact_mode(args):
    """影响分析模式"""
    import sys, tempfile
    from navisv import DesignDriver

    parser = DiffParser()
    if getattr(args, 'diff', None):
        changes = parser.parse_diff_file(args.diff)
    elif getattr(args, 'before', None) and getattr(args, 'after', None):
        changes = parser.parse_two_files(args.before, args.after)
    else:
        print('错误: 需要 --diff 或 --before+--after', file=sys.stderr)
        return {'success': False}

    if not changes:
        print('未检测到信号改动')
        return {'success': False}

    print(f'\n检测到 {len(changes)} 个信号改动:')
    for ch in changes[:10]:
        print(f'  [{ch.change_type}] {ch.short_name}')
    if len(changes) > 10:
        print(f'  ... 还有 {len(changes)-10} 个')

    output_dir = tempfile.mkdtemp(prefix='navisv_eco_')
    dd = DesignDriver([args.file], output_dir=output_dir,
                     include_dirs=args.include or [], cache=True)
    dd.build()

    max_depth = getattr(args, 'depth', 3) or 3
    analyzer = ECOImpactAnalyzer(dd.design_graph)
    report = analyzer.analyze(changes, max_depth=max_depth)

    _print_impact_report(report)
    return {'success': True}


def _run_cdc_mode(args):
    """CDC 对比模式"""
    import sys, tempfile
    from navisv import DesignDriver

    if not (getattr(args, 'before', None) and getattr(args, 'after', None)):
        print('错误: CDC 模式需要 --before 和 --after 两个文件', file=sys.stderr)
        return {'success': False}

    print(f'\nCDC 影响分析:')
    print(f'  Before: {args.before}')
    print(f'  After:  {args.after}')

    od1 = tempfile.mkdtemp(prefix='navisv_eco_before_')
    dd1 = DesignDriver([args.before], output_dir=od1,
                       include_dirs=args.include or [], cache=False)
    dd1.build()

    od2 = tempfile.mkdtemp(prefix='navisv_eco_after_')
    dd2 = DesignDriver([args.after], output_dir=od2,
                       include_dirs=args.include or [], cache=False)
    dd2.build()

    analyzer1 = CDCDeltaAnalyzer(dd1.design_graph)
    analyzer2 = CDCDeltaAnalyzer(dd2.design_graph)

    before_paths = analyzer1.analyze_before()
    after_paths = analyzer2.analyze_before()

    delta = analyzer1.compare(before_paths, after_paths)
    _print_cdc_impact(delta)
    return {'success': True}


def _print_impact_report(report: ImpactReport):
    print(f'\n{"="*70}')
    print(f'ECO 影响分析报告')
    print(f'{"="*70}')

    s = len(report.l1_nodes), len(report.l2_nodes), len(report.l3plus_nodes)
    print(f'  改动信号数: {len(report.changes)}')
    print(f'  L1 直接影响: {len(report.l1_nodes)} 个节点')
    print(f'  L2 间接影响: {len(report.l2_nodes)} 个节点')
    print(f'  L3+ 深层影响: {len(report.l3plus_nodes)} 个节点')
    print(f'  跨模块影响: {len(report.cross_module_nodes)} 个节点')
    print(f'  CDC 相关: {len(report.cdc_related)} 个节点')
    print(f'  总受影响: {report.total_affected} 个节点')

    if report.l1_nodes:
        print(f'\nL1 直接下游:')
        for n in report.l1_nodes[:10]:
            short = n.node.split('.')[-1][:25]
            via = n.via.split('.')[-1][:20] if n.via else '-'
            cross = ' [X]' if n.cross_module else ''
            print(f'    {short:<25} via {via:<20}{cross}')

    if report.l2_nodes:
        print(f'\nL2 间接下游:')
        for n in report.l2_nodes[:10]:
            short = n.node.split('.')[-1][:25]
            via = n.via.split('.')[-1][:20] if n.via else '-'
            print(f'    {short:<25} via {via}')

    if report.cross_module_nodes:
        print(f'\n跨模块影响:')
        for n in report.cross_module_nodes[:10]:
            print(f'    {n.node.split(".")[-1]}')

    if report.cdc_related:
        print(f'\nCDC 相关影响:')
        for n in report.cdc_related[:10]:
            clocks = ', '.join(c.split('.')[-1] for c in n.affected_clocks[:2])
            print(f'    {n.node.split(".")[-1]} (clocks: {clocks})')


def _print_cdc_impact(delta: CDCImpactReport):
    print(f'\n{"="*70}')
    print(f'CDC 影响报告')
    print(f'{"="*70}')
    print(f'  改动前 CDC 路径: {len(delta.before_paths)}')
    print(f'  改动后 CDC 路径: {len(delta.after_paths)}')
    print(f'  新增 CDC: {len(delta.added_paths)}')
    print(f'  移除 CDC: {len(delta.removed_paths)}')
    print(f'  不变: {delta.unchanged_count}')

    if delta.added_paths:
        print(f'\n新增 CDC 路径 ({len(delta.added_paths)} 条):')
        for p in delta.added_paths[:10]:
            src = p.src_reg.split('.')[-1][:20]
            dst = p.dst_reg.split('.')[-1][:20]
            src_c = p.src_clock.split('.')[-1][:12]
            dst_c = p.dst_clock.split('.')[-1][:12]
            print(f'    {src}({src_c}) -> {dst}({dst_c})')

    if delta.removed_paths:
        print(f'\n移除 CDC 路径 ({len(delta.removed_paths)} 条):')
        for p in delta.removed_paths[:5]:
            print(f'    {p.src_reg.split(".")[-1]} -> {p.dst_reg.split(".")[-1]}')

    if not delta.added_paths and not delta.removed_paths:
        print('\n  CDC 路径无变化')