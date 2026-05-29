"""
navisv 图形可视化导出器

支持 DOT (Graphviz) 和 Mermaid 格式，核心特性：
- 节点样式：风险等级着色 / 验证覆盖状态着色
- 边样式：边类型着色（数据/寄存器/条件）+ 时序标注
- 可裁剪：大图只显示高风险/高度数区域
- label_fn：自定义标签，可显示多维分数

使用方式:
    from navisv.graph.graphviz_exporter import (
        export_risk_dot, export_risk_mermaid,
        export_verify_dot, export_verify_mermaid,
    )

    dot = export_risk_dot(dg, module_prefix='top', max_nodes=100, max_edges=200)
    mmd = export_risk_mermaid(dg, module_prefix='top', max_nodes=80)
"""

import networkx as nx
from typing import Dict, Any, List, Optional, Callable, Tuple


RISK_COLORS = {
    'critical': ('#FF4444', 'white'),
    'high':     ('#FF8833', 'black'),
    'medium':   ('#FFCC00', 'black'),
    'low':      ('#44CC44', 'white'),
}

VERIFY_COLORS = {
    'dual_covered': ('#44CC44', 'white'),
    'sva_only':     ('#FFCC00', 'black'),
    'cg_only':      ('#4488FF', 'white'),
    'uncovered':     ('#FF4444', 'white'),
}

EDGE_STYLE = {
    'combinational': ('blue',   'dashed'),
    'state':         ('red',    'bold'),
    'condition':     ('orange', 'solid'),
    'clock':         ('#888888', 'dashed'),
}

NODE_SHAPE = {
    'Port':  'parallelogram',
    'State': 'box',
    'Net':   'ellipse',
}


def _edge_color(timing: str, edge_kind: str, condition: str) -> Tuple[str, str]:
    if edge_kind in ('PosEdge', 'NegEdge'):
        return EDGE_STYLE['clock']
    if timing == 'state':
        return EDGE_STYLE['state']
    if edge_kind == 'condition' or condition:
        return EDGE_STYLE['condition']
    return EDGE_STYLE['combinational']


def _mermaid_shape(kind: str) -> str:
    return {'Port': '([', 'State': '[', 'Net': '>'}.get(kind, '(')


def _is_cross_module(src: str, dst: str) -> bool:
    """检查边是否跨模块边界 (top-level module 不同)"""
    sp = src.split('.')
    dp = dst.split('.')
    return sp[0] != dp[0]


def _node_depth(node: str) -> int:
    """返回节点层级 (module hierarchy 深度)"""
    return len(node.split('.'))



# ── 核心导出 ───────────────────────────────────────────────────────────────

def export_dg_dot(
    dg,
    module_prefix: str = '',
    node_color: Optional[Callable] = None,
    max_nodes: int = 0,
    max_edges: int = 0,
    label_fn: Optional[Callable] = None,
    rankdir: str = 'LR',
) -> str:
    """导出 DesignGraph 为 DOT"""
    G = dg.graph
    lines = []

    all_nodes = list(G.nodes)
    nodes = [n for n in all_nodes if n.startswith(module_prefix)] if module_prefix else all_nodes

    if max_nodes > 0 and len(nodes) > max_nodes:
        nd = {n: G.in_degree(n) + G.out_degree(n) for n in nodes}
        nodes = sorted(nodes, key=lambda n: -nd[n])[:max_nodes]

    node_set = set(nodes)
    all_edges = [(u, v, d) for u, v, d in G.edges(data=True) if u in node_set and v in node_set]

    if max_edges > 0 and len(all_edges) > max_edges:
        es = [(u, v, d, G.in_degree(u) + G.out_degree(u) + G.in_degree(v) + G.out_degree(v))
              for u, v, d in all_edges]
        all_edges = [x[:3] for x in sorted(es, key=lambda x: -x[3])[:max_edges]]

    lines.append('digraph navisv {')
    lines.append(f'  rankdir={rankdir};')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica", fontsize=9];')
    lines.append('')

    for node in nodes:
        attr = dg.node_attr(node)
        short = node.split('.')[-1]
        kind = attr.get('kind', 'Net')
        shape = NODE_SHAPE.get(kind, 'box')
        fc, tc = node_color(node) if node_color else ('#E8E8E8', 'black')
        label = label_fn(node) if label_fn else short

        # 标记 timing=None 的 uncertain 节点 (虚线边框 + ? 后缀)
        if attr.get('timing') is None:
            shape = 'doubleoctagon'
            fc = '#FFE0B0'
            tc = '#CC6600'
            label = label + ' ?'
        # P2-1: 模块边界节点 (层级 >= 4) 用 doublebox 标注
        elif _node_depth(node) >= 4 and attr.get('kind') == 'Port':
            shape = 'doublebox'
            fc = '#E8F4FF'
            tc = '#0066CC'

        lines.append(f'  "{node}" [fillcolor="{fc}", fontcolor="{tc}", '
                     f'shape={shape}, label="{label}"];')

    for src, dst, data in all_edges:
        timing = data.get('timing', 'combinational')
        ek = data.get('edge_kind') or ''
        cond = data.get('condition') or ''
        ec, es = _edge_color(timing, ek, cond)

        # 边标签: 优先显示 true_condition, 其次时序类型
        if cond:
            # 有条件 → 显示条件信号名
            edge_label = cond.split('.')[-1][:15]
        elif timing == 'state':
            edge_label = '(reg)'
        elif timing == 'sequential_input':
            edge_label = '(seq-in)'
        elif timing == 'sequential_output':
            edge_label = '(seq-out)'
        elif ek in ('PosEdge', 'NegEdge'):
            edge_label = f'({ek.lower()})'
        else:
            edge_label = ''

        # P2-4: 边层级标注 — 标注 seq-in 跳数 (寄存器间路径深度)
        depth = 0
        if timing == 'sequential_input':
            # seq-in edge: 标注从起点到终点的寄存器跳数
            # 格式: label="#2" 表示第2个寄存器
            depth = 1

        # P2-1: 跨模块边用虚线区分
        if _is_cross_module(src, dst):
            es = 'dashed'
            edge_label = (edge_label + ' [X]') if edge_label else '[X-module]'

        style = f'color="{ec}", style="{es}"'
        if edge_label:
            style += f', label="{edge_label}"'
        if depth > 0:
            style += f', penwidth=1.5'
        lines.append(f'  "{src}" -> "{dst}" [{style}];')

    lines.append('}')
    return '\n'.join(lines)


# ── 风险图 ───────────────────────────────────────────────────────────────

def export_risk_dot(
    dg,
    module_prefix: str = '',
    max_nodes: int = 150,
    max_edges: int = 300,
    rankdir: str = 'LR',
) -> str:
    """
    DOT 风险图

    参数:
      rankdir: 图方向 (默认 LR, 另支持 TB/TD/BT/RL)
        - LR/RL: 左右排列 (水平)
        - TB/BT: 上下排列 (垂直)

    节点: 🔴red=critical 🟠orange=high 🟡yellow=medium 🟢green=low
          标签: 信号名 + F分数 + T分数 + 主要因素
    边: 🔵蓝虚线=组合  🔴红粗线=寄存器  🟠橙实线=条件
    """
    def node_color(node):
        attr = dg.node_attr(node)
        rl = attr.get('risk_level', 'low')
        return RISK_COLORS.get(rl, RISK_COLORS['low'])

    def label_fn(node):
        attr = dg.node_attr(node)
        short = node.split('.')[-1]
        fc = attr.get('func_complexity', 0)
        tc = attr.get('timing_complexity', 0)
        rl = attr.get('risk_level', 'low')
        label = f"{short}\\nF={fc:.0f} T={tc:.0f}"
        if rl in ('critical', 'high'):
            factors = (attr.get('func_factors', []) + attr.get('timing_factors', []))[:1]
            if factors:
                label += f"\\n{factors[0]}"
        return label

    return export_dg_dot(
        dg, module_prefix=module_prefix,
        node_color=node_color,
        max_nodes=max_nodes, max_edges=max_edges,
        label_fn=label_fn,
        rankdir=rankdir,
    )


def export_risk_mermaid(
    dg,
    module_prefix: str = '',
    max_nodes: int = 100,
    rankdir: str = 'LR',
) -> str:
    """
    Mermaid 风险图

    参数:
      rankdir: 图方向 (默认 LR, 另支持 TB/BT/RL)
        - LR/RL: 左右排列
        - TB/BT: 上下排列

    节点: 🟢🟡🟠🔴 颜色块 + 信号名
    边: --> 组合逻辑  ==> 寄存器  -.- 条件
    """
    G = dg.graph
    lines = []
    lines.append(f'graph {rankdir}')
    lines.append('  %% ════════════════════════════════════════')
    lines.append('  %% navisv Risk Graph  (节点=信号, 边=关系)')
    lines.append('  %% 🔴critical  🟠high  🟡medium  🟢low')
    lines.append('  %% --> 组合  ==> 寄存器  -.- 条件')
    lines.append('  %% ════════════════════════════════════════')
    lines.append('')

    all_nodes = list(G.nodes)
    nodes = [n for n in all_nodes if n.startswith(module_prefix)] if module_prefix else all_nodes

    if max_nodes > 0 and len(nodes) > max_nodes:
        nd = {n: G.in_degree(n) + G.out_degree(n) for n in nodes}
        nodes = sorted(nodes, key=lambda n: -nd[n])[:max_nodes]

    node_set = set(nodes)
    edges = [(u, v, d) for u, v, d in G.edges(data=True) if u in node_set and v in node_set]

    crit, high, med, low_ = [], [], [], []
    for n in nodes:
        rl = dg.node_attr(n).get('risk_level', 'low')
        if rl == 'critical': crit.append(n)
        elif rl == 'high': high.append(n)
        elif rl == 'medium': med.append(n)
        else: low_.append(n)

    def emit_group(label, sym, group, limit=30):
        if not group:
            return
        g = group[:limit]
        lines.append(f'  subgraph _{sym} {{')
        lines.append(f'    label="{label}"; style=filled; fontname="Helvetica";')
        for n in g:
            s = n.split('.')[-1]
            # uncertain 节点: timing=None → 橙色标注 + ? 后缀
            if dg.node_attr(n).get('timing') is None:
                lines.append(f'    {s}["{s} ?⚠️"]')
            else:
                lines.append(f'    {s}["{s}{sym}"]')
        if len(group) > limit:
            lines.append(f'    %% ...还有{len(group)-limit}个')
        lines.append('  }')
        lines.append('')

    emit_group('🔴 Critical', '🔴', crit)
    emit_group('🟠 High',     '🟠', high)
    emit_group('🟡 Medium',   '🟡', med, limit=25)
    emit_group('🟢 Low',      '🟢', low_, limit=15)

    lines.append('  %% ── 信号关系 ──')
    lines.append('  %% 边标签: 条件信号名 / (reg) / (seq-in) / (seq-out)')
    lines.append('')

    # 所有边按类型分组, 显示条件标签
    seq_in  = [(u,v,d) for u,v,d in edges
               if d.get('timing') == 'sequential_input']
    seq_out = [(u,v,d) for u,v,d in edges
               if d.get('timing') == 'sequential_output']
    state_e = [(u,v,d) for u,v,d in edges if d.get('timing') == 'state']
    combo_e = [(u,v,d) for u,v,d in edges
               if not d.get('condition') and d.get('timing') not in ('state','sequential_input','sequential_output')
               and d.get('edge_kind') not in ('PosEdge','NegEdge')]

    ns_names = set(n.split('.')[-1] for n in nodes)

    def mermaid_edge(u, v, d, style):
        us, vs = u.split('.')[-1], v.split('.')[-1]
        if us not in ns_names or vs not in ns_names:
            return None
        cond = (d.get('condition') or '').split('.')[-1][:15]
        timing = d.get('timing', 'combinational')
        # P2-1: cross-module edges → use -.- style
        if _is_cross_module(u, v):
            style = '-.-'
            edge_suffix = ' [X]'
        else:
            edge_suffix = ''
        if cond:
            return f'  {us} {style} {cond} {vs}{edge_suffix}'
        elif timing == 'state':
            return f'  {us} {style} (reg){edge_suffix} {vs}'
        elif timing in ('sequential_input', 'sequential_output'):
            suffix = timing.replace('sequential_', '(seq-') + ')'
            return f'  {us} {style} {suffix}{edge_suffix} {vs}'
        return f'  {us} {style} {vs}{edge_suffix}'


    if seq_in:
        lines.append('  %% ── 时序输入 ──')
        for u,v,d in seq_in[:60]:
            line = mermaid_edge(u, v, d, '-->')
            if line: lines.append(line)
        if len(seq_in) > 60:
            lines.append(f'  %% ...还有{len(seq_in)-60}条')
        lines.append('')

    if seq_out:
        lines.append('  %% ── 时序输出 ──')
        for u,v,d in seq_out[:60]:
            line = mermaid_edge(u, v, d, '-->')
            if line: lines.append(line)
        if len(seq_out) > 60:
            lines.append(f'  %% ...还有{len(seq_out)-60}条')
        lines.append('')

    if state_e:
        lines.append('  %% ── 寄存器 ──')
        for u,v,d in state_e[:40]:
            line = mermaid_edge(u, v, d, '==>')
            if line: lines.append(line)
        if len(state_e) > 40:
            lines.append(f'  %% ...还有{len(state_e)-40}条')
        lines.append('')

    if combo_e:
        lines.append('  %% ── 组合逻辑 ──')
        for u,v,d in combo_e[:60]:
            line = mermaid_edge(u, v, d, '-->')
            if line: lines.append(line)
        if len(combo_e) > 60:
            lines.append(f'  %% ...还有{len(combo_e)-60}条')
        lines.append('')

    return '\n'.join(lines)


# ── 验证覆盖图 ───────────────────────────────────────────────────────────

def _build_status_map(report) -> Dict[str, str]:
    sig2status = {}
    if report and hasattr(report, 'signals'):
        for s in report.signals:
            sig2status[s.signal] = (
                'dual_covered' if s.has_sva and s.has_coverage else
                'sva_only'     if s.has_sva else
                'cg_only'      if s.has_coverage else
                'uncovered'
            )
    return sig2status


def export_verify_dot(
    dg,
    module_prefix: str = '',
    max_nodes: int = 150,
    max_edges: int = 300,
    verify_report=None,
    rankdir: str = 'LR',
) -> str:
    """
    DOT 验证覆盖图

    参数:
      rankdir: 图方向 (默认 LR, 另支持 TB/TD/BT/RL)
        - LR/RL: 左右排列 (水平)
        - TB/BT: 上下排列 (垂直)

    节点: 🟢双覆盖 🟡仅SVA 🔵仅CG 🔴未覆盖
    边: 🔵蓝虚线=组合  🔴红粗线=寄存器  🟠橙实线=条件
    """
    sig2status = _build_status_map(verify_report)

    def node_color(node):
        short = node.split('.')[-1]
        status = sig2status.get(short) or sig2status.get(node, 'uncovered')
        return VERIFY_COLORS.get(status, VERIFY_COLORS['uncovered'])

    def label_fn(node):
        short = node.split('.')[-1]
        status = sig2status.get(short) or sig2status.get(node, 'uncovered')
        return f"{short}\\n{status}"

    return export_dg_dot(
        dg, module_prefix=module_prefix,
        node_color=node_color,
        max_nodes=max_nodes, max_edges=max_edges,
        label_fn=label_fn,
        rankdir=rankdir,
    )


def export_verify_mermaid(
    dg,
    module_prefix: str = '',
    max_nodes: int = 100,
    verify_report=None,
    rankdir: str = 'LR',
) -> str:
    """
    Mermaid 验证覆盖图

    参数:
      rankdir: 图方向 (默认 LR, 另支持 TB/BT/RL)

    节点: 🟢双覆盖 🟡仅SVA 🔵仅CG 🔴未覆盖
    边: --> 组合逻辑  ==> 寄存器
    """
    G = dg.graph
    lines = []
    lines.append(f'graph {rankdir}')
    lines.append('  %% ════════════════════════════════════════')
    lines.append('  %% navisv Verify Coverage Map')
    lines.append('  %% 🟢 双覆盖  🟡 仅SVA  🔵 仅CG  🔴 未覆盖')
    lines.append('  %% --> 组合  ==> 寄存器')
    lines.append('  %% ════════════════════════════════════════')
    lines.append('')

    all_nodes = list(G.nodes)
    nodes = [n for n in all_nodes if n.startswith(module_prefix)] if module_prefix else all_nodes

    if max_nodes > 0 and len(nodes) > max_nodes:
        nd = {n: G.in_degree(n) + G.out_degree(n) for n in nodes}
        nodes = sorted(nodes, key=lambda n: -nd[n])[:max_nodes]

    sig2status = _build_status_map(verify_report)
    dual, sva, cg, unc = [], [], [], []
    for n in nodes:
        short = n.split('.')[-1]
        status = sig2status.get(short) or sig2status.get(n, 'uncovered')
        if status == 'dual_covered': dual.append(n)
        elif status == 'sva_only': sva.append(n)
        elif status == 'cg_only': cg.append(n)
        else: unc.append(n)

    SYMS = {
        'dual_covered': '🟢',
        'sva_only':     '🟡',
        'cg_only':      '🔵',
        'uncovered':     '🔴',
    }

    def emit_group(label, status_key, group, limit=30):
        if not group:
            return
        g = group[:limit]
        lines.append(f'  subgraph _{status_key} {{')
        lines.append(f'    label="{label}"; style=filled; fontname="Helvetica";')
        for n in g:
            s = n.split('.')[-1]
            # uncertain 节点: timing=None → 橙色标注 + ? 后缀
            if dg.node_attr(n).get('timing') is None:
                lines.append(f'    {s}["{s} ?⚠️"]')
            else:
                lines.append(f'    {s}["{s}{SYMS.get(status_key, "🔴")}"]')
        if len(group) > limit:
            lines.append(f'    %% ...还有{len(group)-limit}个')
        lines.append('  }')
        lines.append('')

    emit_group('🟢 双覆盖',  'dual_covered', dual)
    emit_group('🟡 仅SVA',   'sva_only',     sva)
    emit_group('🔵 仅CG',    'cg_only',      cg)
    emit_group('🔴 未覆盖',  'uncovered',    unc)

    node_set = set(nodes)
    edges = [(u, v, d) for u, v, d in G.edges(data=True) if u in node_set and v in node_set]
    seq_in  = [(u,v,d) for u,v,d in edges if d.get('timing') == 'sequential_input']
    seq_out = [(u,v,d) for u,v,d in edges if d.get('timing') == 'sequential_output']
    state_e = [(u,v,d) for u,v,d in edges if d.get('timing') == 'state']
    combo_e = [(u,v,d) for u,v,d in edges
               if not d.get('condition') and d.get('timing') not in ('state','sequential_input','sequential_output')
               and d.get('edge_kind') not in ('PosEdge','NegEdge')]

    def mermaid_edge(u, v, d, style):
        us, vs = u.split('.')[-1], v.split('.')[-1]
        cond = (d.get('condition') or '').split('.')[-1][:15]
        timing = d.get('timing', 'combinational')
        # P2-1: cross-module edges → use -.- style
        if _is_cross_module(u, v):
            style = '-.-'
            edge_suffix = ' [X]'
        else:
            edge_suffix = ''
        if cond:
            return f'  {us} {style} {cond} {vs}{edge_suffix}'
        elif timing == 'state':
            return f'  {us} {style} (reg){edge_suffix} {vs}'
        elif timing in ('sequential_input', 'sequential_output'):
            suffix = timing.replace('sequential_', '(seq-') + ')'
            return f'  {us} {style} {suffix}{edge_suffix} {vs}'
        return f'  {us} {style} {vs}{edge_suffix}'

    for u,v,d in (seq_in + seq_out + state_e + combo_e)[:120]:
        if u.split('.')[-1] in ns and v.split('.')[-1] in ns:
            style = '-->' if d.get('timing') != 'state' else '==>'
            line = mermaid_edge(u, v, d, style)
            if line:
                lines.append(line)
    if len(edges) > 120:
        lines.append(f'  %% ...还有{len(edges)-120}条边')

    return '\n'.join(lines)