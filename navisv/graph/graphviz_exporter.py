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


# ── 核心导出 ───────────────────────────────────────────────────────────────

def export_dg_dot(
    dg,
    module_prefix: str = '',
    node_color: Optional[Callable] = None,
    max_nodes: int = 0,
    max_edges: int = 0,
    label_fn: Optional[Callable] = None,
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
    lines.append('  rankdir=LR;')
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
        lines.append(f'  "{node}" [fillcolor="{fc}", fontcolor="{tc}", '
                     f'shape={shape}, label="{label}"];')

    for src, dst, data in all_edges:
        timing = data.get('timing', 'combinational')
        ek = data.get('edge_kind') or ''
        cond = data.get('condition') or ''
        ec, es = _edge_color(timing, ek, cond)
        edge_label = ''
        if timing == 'state':
            edge_label = '(reg)'
        elif cond:
            edge_label = cond.split('.')[-1][:12]
        style = f'color="{ec}", style="{es}"'
        if edge_label:
            style += f', label="{edge_label}"'
        lines.append(f'  "{src}" -> "{dst}" [{style}];')

    lines.append('}')
    return '\n'.join(lines)


# ── 风险图 ───────────────────────────────────────────────────────────────

def export_risk_dot(
    dg,
    module_prefix: str = '',
    max_nodes: int = 150,
    max_edges: int = 300,
) -> str:
    """
    DOT 风险图

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
    )


def export_risk_mermaid(
    dg,
    module_prefix: str = '',
    max_nodes: int = 100,
) -> str:
    """
    Mermaid 风险图

    节点: 🟢🟡🟠🔴 颜色块 + 信号名
    边: --> 组合逻辑  ==> 寄存器  -.- 条件
    """
    G = dg.graph
    lines = []
    lines.append('graph LR')
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
            lines.append(f'    {s}["{s}{sym}"]')
        if len(group) > limit:
            lines.append(f'    %% ...还有{len(group)-limit}个')
        lines.append('  }')
        lines.append('')

    emit_group('🔴 Critical', '🔴', crit)
    emit_group('🟠 High',     '🟠', high)
    emit_group('🟡 Medium',   '🟡', med, limit=25)
    emit_group('🟢 Low',      '🟢', low_, limit=15)

    combo = [(u,v,d) for u,v,d in edges
             if d.get('timing') != 'state' and d.get('edge_kind') not in ('PosEdge','NegEdge')]
    state  = [(u,v,d) for u,v,d in edges if d.get('timing') == 'state']
    cond   = [(u,v,d) for u,v,d in edges if d.get('condition') or d.get('edge_kind') == 'condition']
    ns_names = [n.split('.')[-1] for n in nodes]

    lines.append('  %% ── 信号关系 ──')
    for u, v, _ in combo[:60]:
        us, vs = u.split('.')[-1], v.split('.')[-1]
        if us in ns_names and vs in ns_names:
            lines.append(f'  {us} --> {vs}')
    if len(combo) > 60:
        lines.append(f'  %% ...还有{len(combo)-60}条组合边')

    for u, v, _ in state[:40]:
        us, vs = u.split('.')[-1], v.split('.')[-1]
        if us in ns_names and vs in ns_names:
            lines.append(f'  {us} ==> {vs}')
    if len(state) > 40:
        lines.append(f'  %% ...还有{len(state)-40}条寄存器边')

    for u, v, d in cond[:20]:
        us, vs = u.split('.')[-1], v.split('.')[-1]
        c = (d.get('condition') or '').split('.')[-1][:8]
        if us in ns_names and vs in ns_names:
            lines.append(f'  {us} -.->|{c}| {vs}')

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
) -> str:
    """
    DOT 验证覆盖图

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
    )


def export_verify_mermaid(
    dg,
    module_prefix: str = '',
    max_nodes: int = 100,
    verify_report=None,
) -> str:
    """
    Mermaid 验证覆盖图

    节点: 🟢双覆盖 🟡仅SVA 🔵仅CG 🔴未覆盖
    边: --> 组合逻辑  ==> 寄存器
    """
    G = dg.graph
    lines = []
    lines.append('graph LR')
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
    combo = [t for t in edges
             if t[2].get('timing') != 'state' and t[2].get('edge_kind') not in ('PosEdge','NegEdge')]
    state = [t for t in edges if t[2].get('timing') == 'state']

    lines.append('  %% ── 信号关系 ──')
    for u, v, _ in combo[:60]:
        lines.append(f'  {u.split(".")[-1]} --> {v.split(".")[-1]}')
    for u, v, _ in state[:40]:
        lines.append(f'  {u.split(".")[-1]} ==> {v.split(".")[-1]}')

    return '\n'.join(lines)