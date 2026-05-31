"""
navisv 图形可视化导出器

支持 DOT (Graphviz) 和 Mermaid 格式，核心特性：
- 节点样式：风险等级着色 / 验证覆盖状态着色
- 边样式：边类型着色（数据/寄存器/条件）+ 时序标注
- 可裁剪：大图只显示高风险/高度数区域
- label_fn：自定义标签，可显示多维分数
- 模块聚类（Module Cluster）：每个子模块一个 cluster subgraph
- CDC 高亮层：跨时钟域路径用粉红粗边标注
- 图例面板：左上角 Legend 说明颜色/形状含义
- 语义化边标签：→寄存器 / 跨模块 等直观描述

使用方式:
    from navisv.graph.graphviz_exporter import (
        export_risk_dot, export_risk_mermaid,
        export_verify_dot, export_verify_mermaid,
    )

    dot = export_risk_dot(dg, module_prefix='top', max_nodes=100, max_edges=200)
    mmd = export_risk_mermaid(dg, module_prefix='top', max_nodes=80)
"""

import networkx as nx
from typing import Dict, Any, List, Optional, Callable, Tuple, Set, Set


# ── 颜色常量 ────────────────────────────────────────────────────────────────

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

# 模块 Cluster 背景色轮换（每个子模块不同颜色，便于视觉区分）
MODULE_CLUSTER_COLORS = [
    '#E8F0FE', '#E8FDF0', '#FEF0E8', '#F0E8FE',
    '#E8FEF0', '#FEF8E8', '#E8E8FE', '#F0F8E8',
]

EDGE_STYLE = {
    'combinational': ('#4472C4', 'dashed'),
    'state':         ('#C00000', 'bold'),
    'condition':     ('#FF8C00', 'solid'),
    'clock':         ('#888888', 'dashed'),
}

# CDC 边专用样式
CDC_COLOR = '#FF1493'
CDC_WIDTH = 2.0

NODE_SHAPE = {
    'Port':  'parallelogram',
    'State': 'box',
    'Net':   'ellipse',
}


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _edge_color(timing: str, edge_kind: str, condition: str) -> Tuple[str, str]:
    if edge_kind in ('PosEdge', 'NegEdge'):
        return EDGE_STYLE['clock']
    if timing == 'state':
        return EDGE_STYLE['state']
    if edge_kind == 'condition' or condition:
        return EDGE_STYLE['condition']
    return EDGE_STYLE['combinational']


def _is_cross_module(src: str, dst: str) -> bool:
    """检查边是否跨模块边界 (top-level module 不同)"""
    sp = src.split('.')
    dp = dst.split('.')
    return sp[0] != dp[0] if sp and dp else False


def _node_depth(node: str) -> int:
    """返回节点层级 (module hierarchy 深度)"""
    return len(node.split('.'))


def _extract_module(node: str, depth: int = 2) -> str:
    """
    从节点路径提取模块前缀（用于 cluster 分组）
    
    depth=2: uart_controller.uart_tx.curr_state → uart_controller.uart_tx
    depth=1: uart_controller.uart_tx.curr_state → uart_controller
    
    目的是让同个子模块的节点放入同一个 cluster subgraph
    """
    parts = node.split('.')
    if len(parts) <= depth:
        return parts[0] if parts else node
    return '.'.join(parts[:depth])


def _build_module_clusters(nodes: List[str], depth: int = 2) -> Dict[str, List[str]]:
    """
    将节点按 module 分组，返回 {module_path: [node, ...]}
    
    depth 控制聚类粒度：
    - 2: 细分到子模块（uart_tx, uart_rx, ...）
    - 1: 只按顶层模块分组
    """
    clusters: Dict[str, List[str]] = {}
    for n in nodes:
        mod = _extract_module(n, depth)
        clusters.setdefault(mod, []).append(n)
    return clusters


def _semantic_edge_label(timing: str, edge_kind: str, condition: str) -> str:
    """
    生成工程师友好的边标签。
    
    映射规则：
    - state (register) → 边指向寄存器，用 ▶ 符号表示数据流入
    - sequential_input → 数据进入寄存器阶段，用 ▶FF
    - sequential_output → 寄存器输出，用 ▶ 符号
    - combinational → 无标签（隐式）
    - 有 condition → 显示触发条件，用「」包裹
    - cross-module → 显示"跨模块"
    """
    if condition:
        # 条件边：提取最后一个分段作为简称
        cond_short = condition.split('.')[-1]
        return f'「{cond_short}」'
    if timing == 'state':
        return '▶'
    if timing == 'sequential_input':
        return '▶FF'
    if timing == 'sequential_output':
        return '▶'
    if edge_kind in ('PosEdge', 'NegEdge'):
        return f'⌚{edge_kind.lower()}'
    return ''


# ── CDC 路径辅助 ──────────────────────────────────────────────────────────

def _get_cdc_edge_pairs(dg, module_prefix: str = '') -> Set[Tuple[str, str]]:
    """
    从 DesignGraph 获取 CDC 路径上的所有边对。
    返回 {(src, dst), ...}，用于在 DOT 中高亮 CDC 边。
    """
    try:
        from navisv.graph.cdc_analyzer import CDCAnalyzer
        analyzer = CDCAnalyzer(dg, module_prefix=module_prefix)
        report = analyzer.analyze()
        edge_pairs: Set[Tuple[str, str]] = set()
        for path in report.cross_clock_paths:
            # CDC path: src_reg -> [intermediate nodes] -> dst_reg
            # The direct edge from src to first intermediate (or dst if depth==1)
            src = path.src_reg
            dst = path.dst_reg
            if path.intermediate:
                # Multi-hop: add all sequential edges in the path
                all_nodes = [src] + path.intermediate + [dst]
                for i in range(len(all_nodes) - 1):
                    edge_pairs.add((all_nodes[i], all_nodes[i + 1]))
            else:
                # Single-hop: direct edge from src to dst
                edge_pairs.add((src, dst))
        return edge_pairs
    except Exception as e:
        return set()


def _get_cdc_node_set(dg, module_prefix: str = '') -> Set[str]:
    """
    获取 CDC 路径中涉及的所有寄存器节点集合。
    用于在图中高亮 CDC 源/目标寄存器（节点标记）。
    返回所有在 CDC 路径上的 src_reg 和 dst_reg。
    """
    try:
        from navisv.graph.cdc_analyzer import CDCAnalyzer
        analyzer = CDCAnalyzer(dg, module_prefix=module_prefix)
        report = analyzer.analyze()
        nodes: Set[str] = set()
        for path in report.cross_clock_paths:
            if path.src_reg:
                nodes.add(path.src_reg)
            if path.dst_reg:
                nodes.add(path.dst_reg)
            for n in path.intermediate:
                nodes.add(n)
        return nodes
    except Exception:
        return set()


# ── 图例面板 ────────────────────────────────────────────────────────────────

def _make_legend() -> str:
    """生成 DOT 图例节点（放在右上角）"""
    legend = (
        '<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4"'
        ' BGCOLOR="#F8F8F8">'
        '<TR><TD COLSPAN="3" BGCOLOR="#DDDDDD"><B>navisv 图例</B></TD></TR>'
        # 节点风险
        '<TR><TD><B>节点颜色</B></TD><TD BGCOLOR="#FF4444"><FONT COLOR="white">■</FONT></TD><TD>Critical</TD></TR>'
        '<TR><TD></TD><TD BGCOLOR="#FF8833"><FONT COLOR="#FF8833">■</FONT></TD><TD>High</TD></TR>'
        '<TR><TD></TD><TD BGCOLOR="#FFCC00"><FONT COLOR="#FFCC00">■</FONT></TD><TD>Medium</TD></TR>'
        '<TR><TD></TD><TD BGCOLOR="#44CC44"><FONT COLOR="white">■</FONT></TD><TD>Low</TD></TR>'
        # 边类型
        '<TR><TD><B>边类型</B></TD><TD><FONT COLOR="#4472C4">— —</FONT></TD><TD>组合逻辑</TD></TR>'
        '<TR><TD></TD><TD><FONT COLOR="#C00000"><B>━━</B></FONT></TD><TD>寄存器</TD></TR>'
        '<TR><TD></TD><TD><FONT COLOR="#FF8C00">—</FONT></TD><TD>条件/控制</TD></TR>'
        '<TR><TD></TD><TD><FONT COLOR="#FF1493"><B>━━</B></FONT></TD><TD>CDC 路径</TD></TR>'
        # 形状
        '<TR><TD><B>形状</B></TD><TD>▭</TD><TD>寄存器/状态</TD></TR>'
        '<TR><TD></TD><TD>⬡</TD><TD>Port 接口</TD></TR>'
        '<TR><TD></TD><TD>◯</TD><TD>Net 信号</TD></TR>'
        # 标签
        '<TR><TD><B>边标签</B></TD><TD>▶FF</TD><TD>寄存器输入</TD></TR>'
        '<TR><TD></TD><TD>▶</TD><TD>寄存器输出</TD></TR>'
        '<TR><TD></TD><TD>「条件」</TD><TD>条件触发</TD></TR>'
        '</TABLE>>'
    )
    return legend


# ── 核心导出函数 ────────────────────────────────────────────────────────────

def export_dg_dot(
    dg,
    module_prefix: str = '',
    node_color: Optional[Callable] = None,
    max_nodes: int = 0,
    max_edges: int = 0,
    label_fn: Optional[Callable] = None,
    rankdir: str = 'LR',
    cdc_highlight: bool = False,
    show_legend: bool = True,
    cluster_depth: int = 2,
) -> str:
    """
    导出 DesignGraph 为 DOT 格式。
    
    新增参数:
      cdc_highlight: True 时，CDC 路径上的边用粉红色粗边高亮
      show_legend:   True 时，左上角输出图例节点
      cluster_depth: 模块聚类深度（默认2，即细分到子模块）
    
    DOT 结构:
      1. Graph 属性（rankdir, splines 等）
      2. Legend 节点（如启用）
      3. Module cluster subgraphs（每个子模块一个）
      4. 节点定义
      5. 边定义（CDC 边单独高亮）
    """
    G = dg.graph
    lines: List[str] = []

    # ── 节点过滤 ──────────────────────────────────────────────────
    all_nodes = list(G.nodes)
    nodes = [n for n in all_nodes if n.startswith(module_prefix)] if module_prefix else all_nodes

    if max_nodes > 0 and len(nodes) > max_nodes:
        nd = {n: G.in_degree(n) + G.out_degree(n) for n in nodes}
        nodes = sorted(nodes, key=lambda n: -nd[n])[:max_nodes]

    node_set = set(nodes)

    # ── 边过滤 ────────────────────────────────────────────────────
    all_edges = [(u, v, d) for u, v, d in G.edges(data=True) if u in node_set and v in node_set]

    if max_edges > 0 and len(all_edges) > max_edges:
        es = [(u, v, d, G.in_degree(u) + G.out_degree(u) + G.in_degree(v) + G.out_degree(v))
              for u, v, d in all_edges]
        all_edges = [x[:3] for x in sorted(es, key=lambda x: -x[3])[:max_edges]]

    # ── CDC 高亮：收集 CDC 边对 ──────────────────────────────────
    cdc_edge_pairs: Set[Tuple[str, str]] = set()
    if cdc_highlight:
        cdc_edge_pairs = _get_cdc_edge_pairs(dg, module_prefix)

    # ── 模块聚类 ─────────────────────────────────────────────────
    clusters = _build_module_clusters(nodes, depth=cluster_depth)

    # ── DOT Header ────────────────────────────────────────────────
    lines.append('digraph navisv {')
    lines.append(f'  rankdir={rankdir};')
    lines.append('  splines=polyline;')
    lines.append('  nodesep=0.5;')
    lines.append('  ranksep=0.7;')
    lines.append('  fontname="Helvetica";')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica", fontsize=9];')
    # Keep square-ish aspect ratio
    lines.append('  size="10,10!";')
    lines.append('  ratio=compress;')
    lines.append('')

    # ── Legend 节点（右上角固定）──────────────────────────────────
    if show_legend:
        lines.append('  Legend [shape=none, margin=0, label=' + _make_legend() + '];')
        lines.append('')

    # ── Module Clusters ───────────────────────────────────────────
    cluster_items = sorted(clusters.items(), key=lambda x: x[0])
    color_cycle = MODULE_CLUSTER_COLORS
    for idx, (mod, mod_nodes) in enumerate(cluster_items):
        bg = color_cycle[idx % len(color_cycle)]
        # cluster ID: 只能包含字母、数字、下划线，且不能以数字开头
        safe_id = mod.replace('.', '_').replace('-', '_')
        lines.append(f'  subgraph "cluster_{safe_id}" {{')
        lines.append(f'    label="🟦 {mod}";')
        lines.append(f'    style=filled; fillcolor="{bg}";')
        lines.append(f'    color="#AAAAAA";')
        lines.append(f'    fontname="Helvetica"; fontsize=11;')
        lines.append(f'    // {len(mod_nodes)} 个节点')
        lines.append('  }')
    if clusters:
        lines.append('')

    # ── Port 对齐（左右布局时 input 左，output 右）──────────────
    if rankdir == 'LR':
        # 找所有 Port 节点，分 input/output
        input_ports = []
        output_ports = []
        for node in nodes:
            attr = dg.node_attr(node)
            if attr.get('kind') == 'Port':
                dir_val = attr.get('direction', attr.get('dir', ''))
                short = node.split('.')[-1]
                if dir_val in ('In', 'input'):
                    input_ports.append(f'"{node}"')
                elif dir_val in ('Out', 'output'):
                    output_ports.append(f'"{node}"')
        if input_ports:
            lines.append(f'  {{ rank=source; {"; " .join(input_ports)}; }}')
        if output_ports:
            lines.append(f'  {{ rank=sink; {"; " .join(output_ports)}; }}')
        lines.append('')

    # ── 节点定义 ──────────────────────────────────────────────────
    for node in nodes:
        attr = dg.node_attr(node)
        short = node.split('.')[-1]
        kind = attr.get('kind', 'Net')
        shape = NODE_SHAPE.get(kind, 'box')
        fc, tc = node_color(node) if node_color else ('#E8E8E8', 'black')
        label = label_fn(node) if label_fn else short

        # Uncertain 节点：timing=None → doubleoctagon + 橙色
        if attr.get('timing') is None:
            shape = 'doubleoctagon'
            fc = '#FFE0B0'
            tc = '#CC6600'
            label = label + ' ?'
        # 模块边界 Port 节点
        elif _node_depth(node) >= 4 and attr.get('kind') == 'Port':
            shape = 'doublebox'
            fc = '#E8F4FF'
            tc = '#0066CC'

        lines.append(f'  "{node}" [fillcolor="{fc}", fontcolor="{tc}", '
                     f'shape={shape}, label="{label}"];')

    # ── 边定义 ────────────────────────────────────────────────────
    for src, dst, data in all_edges:
        timing = data.get('timing', 'combinational')
        ek = data.get('edge_kind') or ''
        cond = data.get('condition') or ''

        # 判断是否为 CDC 边
        is_cdc = (src, dst) in cdc_edge_pairs

        # 决定颜色和线型
        if is_cdc:
            ec, es = CDC_COLOR, 'bold'
            edge_label = '⚡CDC'
            penwidth = CDC_WIDTH
        else:
            ec, es = _edge_color(timing, ek, cond)
            edge_label = _semantic_edge_label(timing, ek, cond)
            penwidth = 1.0

        # 跨模块边：虚线 + "跨模块"标签
        if _is_cross_module(src, dst):
            es = 'dashed'
            if edge_label:
                edge_label += ' 跨模块'
            else:
                edge_label = '跨模块'

        style = f'color="{ec}", style="{es}"'
        if edge_label:
            style += f', label="{edge_label}"'
        if penwidth > 1.0:
            style += f', penwidth={penwidth}'

        lines.append(f'  "{src}" -> "{dst}" [{style}];')

    lines.append('}')
    return '\n'.join(lines)


# ── 风险图 ────────────────────────────────────────────────────────────────

def export_risk_dot(
    dg,
    module_prefix: str = '',
    max_nodes: int = 150,
    max_edges: int = 300,
    rankdir: str = 'LR',
    cdc_highlight: bool = False,
    show_legend: bool = True,
    cluster_depth: int = 2,
) -> str:
    """
    DOT 风险图（增强版）
    
    新增参数:
      cdc_highlight: CDC 路径高亮（粉红粗边 + ⚡CDC 标签）
      show_legend:   显示图例面板
    
    节点: 🔴red=critical 🟠orange=high 🟡yellow=medium 🟢green=low
          标签: 信号名 + F分数 + T分数 + 主要因素
    边: 🔵蓝虚线=组合  🔴红粗线=寄存器  🟠橙实线=条件  ⚡粉红=CDC
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
        cdc_highlight=cdc_highlight,
        show_legend=show_legend,
        cluster_depth=cluster_depth,
    )


def export_risk_mermaid(
    dg,
    module_prefix: str = '',
    max_nodes: int = 100,
    rankdir: str = 'LR',
    cdc_highlight: bool = False,
) -> str:
    """
    Mermaid 风险图（改进版：按模块分组 subgraph + CDC 高亮）
    
    不再按 risk level 分组，而是保留模块语义：
    - 同模块节点归入同一个 subgraph
    - risk level 通过节点颜色后缀 🔴🟠🟡🟢 表示
    - CDC 路径用 ==> 双线 + ⚡CDC 标签高亮
    - 边类型：--> 组合  ==> 寄存器  ==  CDC
    
    参数:
      rankdir: 图方向 (默认 LR, 另支持 TB/BT/RL)
      cdc_highlight: True 时 CDC 边用双线 ==> + ⚡CDC 标注
    """
    G = dg.graph
    lines: List[str] = []

    all_nodes = list(G.nodes)
    nodes = [n for n in all_nodes if n.startswith(module_prefix)] if module_prefix else all_nodes

    if max_nodes > 0 and len(nodes) > max_nodes:
        nd = {n: G.in_degree(n) + G.out_degree(n) for n in nodes}
        nodes = sorted(nodes, key=lambda n: -nd[n])[:max_nodes]

    node_set = set(nodes)
    edges = [(u, v, d) for u, v, d in G.edges(data=True) if u in node_set and v in node_set]

    # CDC 高亮：收集 CDC 边对
    cdc_edge_pairs: Set[Tuple[str, str]] = set()
    if cdc_highlight:
        cdc_edge_pairs = _get_cdc_edge_pairs(dg, module_prefix)

    # 按模块分组，而不是按 risk 分组
    clusters = _build_module_clusters(nodes, depth=2)

    # 颜色后缀映射
    RISK_SUFFIX = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}

    lines.append(f'graph {rankdir}')
    lines.append('  %% ═══════════════════════════════════════════')
    lines.append('  %% navisv Risk Graph  (模块分组, 风险着色)')
    lines.append('  %% → 组合逻辑  ⇒ 寄存器  == CDC 路径')
    if cdc_highlight:
        lines.append('  %% ⚡ CDC 边用双线 == 标注')
    lines.append('  %% ═══════════════════════════════════════════')
    lines.append('')

    # 按模块输出 subgraph
    for mod, mod_nodes in sorted(clusters.items(), key=lambda x: x[0]):
        safe = mod.replace('.', '_')
        # 统计各风险等级数量
        rl_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for n in mod_nodes:
            rl = dg.node_attr(n).get('risk_level', 'low')
            if rl in rl_counts:
                rl_counts[rl] += 1
        tag = ''.join(f'{k[0].upper()}:{v}' for k, v in rl_counts.items() if v > 0)
        
        lines.append(f'  subgraph cluster_{safe} {{')
        lines.append(f'    label="🟦 {mod} ({tag})"; style=filled; fillcolor=#F0F4FF;')
        
        for n in mod_nodes[:40]:  # 限制每个 cluster 最多 40 节点
            s = n.split('.')[-1]
            rl = dg.node_attr(n).get('risk_level', 'low')
            suf = RISK_SUFFIX.get(rl, '🟢')
            if dg.node_attr(n).get('timing') is None:
                lines.append(f'    {s}["{s} ?⚠️"]')
            else:
                lines.append(f'    {s}["{s} {suf}"]')
        
        if len(mod_nodes) > 40:
            lines.append(f'    %% ... 还有 {len(mod_nodes) - 40} 个节点')
        lines.append('  }')
        lines.append('')

    lines.append('  %% ── 信号关系 ──')
    lines.append('')

    # 边按类型分组
    ns_names = set(n.split('.')[-1] for n in nodes)

    seq_in  = [(u,v,d) for u,v,d in edges if d.get('timing') == 'sequential_input']
    state_e = [(u,v,d) for u,v,d in edges if d.get('timing') == 'state']
    combo_e = [(u,v,d) for u,v,d in edges
               if not d.get('condition') and d.get('timing') not in ('state','sequential_input')
               and d.get('edge_kind') not in ('PosEdge','NegEdge')]
    cond_e  = [(u,v,d) for u,v,d in edges if d.get('condition') or d.get('edge_kind') == 'condition']

    def mermaid_label(u, v, d) -> Optional[str]:
        us, vs = u.split('.')[-1], v.split('.')[-1]
        if us not in ns_names or vs not in ns_names:
            return None
        timing = d.get('timing', 'combinational')
        cond = (d.get('condition') or '').split('.')[-1][:12]
        cross = _is_cross_module(u, v)
        is_cdc = (u, v) in cdc_edge_pairs
        
        if is_cdc:
            # CDC 边：双线 + ⚡CDC 标注
            suf = ' [跨]' if cross else ''
            return f'  {us} == ⚡CDC{vs}{suf}'
        if cond:
            suf = ' [跨]' if cross else ''
            return f'  {us} --> 「{cond}」{vs}{suf}'
        if timing == 'state':
            suf = ' [跨]' if cross else ''
            return f'  {us} ==> ▶ {vs}{suf}'
        if timing == 'sequential_input':
            suf = ' [跨]' if cross else ''
            return f'  {us} --> ▶FF {vs}{suf}'
        suf = ' [跨]' if cross else ''
        return f'  {us} --> {vs}{suf}'

    if seq_in:
        lines.append('  %% ── 寄存器输入 ──')
        for u,v,d in seq_in[:50]:
            ln = mermaid_label(u, v, d)
            if ln: lines.append(ln)
        if len(seq_in) > 50:
            lines.append(f'  %% ... 还有 {len(seq_in) - 50} 条')
        lines.append('')

    if state_e:
        lines.append('  %% ── 寄存器 ──')
        for u,v,d in state_e[:40]:
            ln = mermaid_label(u, v, d)
            if ln: lines.append(ln)
        if len(state_e) > 40:
            lines.append(f'  %% ... 还有 {len(state_e) - 40} 条')
        lines.append('')

    if combo_e:
        lines.append('  %% ── 组合逻辑 ──')
        for u,v,d in combo_e[:60]:
            ln = mermaid_label(u, v, d)
            if ln: lines.append(ln)
        if len(combo_e) > 60:
            lines.append(f'  %% ... 还有 {len(combo_e) - 60} 条')
        lines.append('')

    if cond_e:
        lines.append('  %% ── 条件/控制 ──')
        for u,v,d in cond_e[:40]:
            ln = mermaid_label(u, v, d)
            if ln: lines.append(ln)
        if len(cond_e) > 40:
            lines.append(f'  %% ... 还有 {len(cond_e) - 40} 条')
        lines.append('')

    return '\n'.join(lines)


# ── 验证覆盖图 ────────────────────────────────────────────────────────────

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
    cdc_highlight: bool = False,
    show_legend: bool = True,
) -> str:
    """
    DOT 验证覆盖图（增强版）
    
    节点: 🟢双覆盖 🟡仅SVA 🔵仅CG 🔴未覆盖
    边: 🔵蓝虚线=组合  🔴红粗线=寄存器  🟠橙实线=条件  ⚡粉红=CDC
    """
    sig2status = _build_status_map(verify_report)

    def node_color(node):
        short = node.split('.')[-1]
        status = sig2status.get(short) or sig2status.get(node, 'uncovered')
        return VERIFY_COLORS.get(status, VERIFY_COLORS['uncovered'])

    def label_fn(node):
        short = node.split('.')[-1]
        status = sig2status.get(short) or sig2status.get(node, 'uncovered')
        status_label = {'dual_covered': '双覆盖', 'sva_only': '仅SVA',
                        'cg_only': '仅CG', 'uncovered': '未覆盖'}.get(status, status)
        bw = dg.node_attr(node).get('bit_width')
        bw_str = f' [{bw}bit]' if bw else ''
        return f"{short}{bw_str}\\n{status_label}"

    return export_dg_dot(
        dg, module_prefix=module_prefix,
        node_color=node_color,
        max_nodes=max_nodes, max_edges=max_edges,
        label_fn=label_fn,
        rankdir=rankdir,
        cdc_highlight=cdc_highlight,
        show_legend=show_legend,
    )


def export_verify_mermaid(
    dg,
    module_prefix: str = '',
    max_nodes: int = 100,
    verify_report=None,
    rankdir: str = 'LR',
) -> str:
    """
    Mermaid 验证覆盖图（改进版：按模块分组）
    
    节点: 🟢双覆盖 🟡仅SVA 🔵仅CG 🔴未覆盖
    边: --> 组合逻辑  ==> 寄存器
    """
    G = dg.graph
    lines: List[str] = []

    all_nodes = list(G.nodes)
    nodes = [n for n in all_nodes if n.startswith(module_prefix)] if module_prefix else all_nodes

    if max_nodes > 0 and len(nodes) > max_nodes:
        nd = {n: G.in_degree(n) + G.out_degree(n) for n in nodes}
        nodes = sorted(nodes, key=lambda n: -nd[n])[:max_nodes]

    sig2status = _build_status_map(verify_report)
    clusters = _build_module_clusters(nodes, depth=2)

    SYMS = {
        'dual_covered': '🟢',
        'sva_only':     '🟡',
        'cg_only':      '🔵',
        'uncovered':     '🔴',
    }

    lines.append(f'graph {rankdir}')
    lines.append('  %% ════════════════════════════════════════')
    lines.append('  %% navisv Verify Coverage Map')
    lines.append('  %% 🟢 双覆盖  🟡 仅SVA  🔵 仅CG  🔴 未覆盖')
    lines.append('  %% --> 组合  ==> 寄存器')
    lines.append('  %% ════════════════════════════════════════')
    lines.append('')

    for mod, mod_nodes in sorted(clusters.items(), key=lambda x: x[0]):
        safe = mod.replace('.', '_')
        lines.append(f'  subgraph cluster_{safe} {{')
        lines.append(f'    label="🟦 {mod}"; style=filled; fillcolor=#F0FFF0;')
        for n in mod_nodes[:40]:
            s = n.split('.')[-1]
            short = n.split('.')[-1]
            status = sig2status.get(short) or sig2status.get(n, 'uncovered')
            suf = SYMS.get(status, '🔴')
            if dg.node_attr(n).get('timing') is None:
                lines.append(f'    {s}["{s} ?⚠️"]')
            else:
                lines.append(f'    {s}["{s} {suf}"]')
        if len(mod_nodes) > 40:
            lines.append(f'    %% ... 还有 {len(mod_nodes) - 40} 个节点')
        lines.append('  }')
        lines.append('')

    node_set = set(nodes)
    edges = [(u, v, d) for u, v, d in G.edges(data=True) if u in node_set and v in node_set]
    ns_names = set(n.split('.')[-1] for n in nodes)

    def mermaid_edge(u, v, d, style):
        us, vs = u.split('.')[-1], v.split('.')[-1]
        if us not in ns_names or vs not in ns_names:
            return None
        cond = (d.get('condition') or '').split('.')[-1][:12]
        timing = d.get('timing', 'combinational')
        cross = _is_cross_module(u, v)
        if cond:
            return f'  {us} {style} 「{cond}」{vs}{" [跨]" if cross else ""}'
        if timing == 'state':
            return f'  {us} ==> ▶ {vs}{" [跨]" if cross else ""}'
        if timing == 'sequential_input':
            return f'  {us} {style} ▶FF {vs}{" [跨]" if cross else ""}'
        return f'  {us} {style} {vs}{" [跨]" if cross else ""}'

    seq_in  = [(u,v,d) for u,v,d in edges if d.get('timing') == 'sequential_input']
    state_e = [(u,v,d) for u,v,d in edges if d.get('timing') == 'state']
    combo_e = [(u,v,d) for u,v,d in edges
               if not d.get('condition') and d.get('timing') not in ('state', 'sequential_input')
               and d.get('edge_kind') not in ('PosEdge', 'NegEdge')]
    cond_e  = [(u,v,d) for u,v,d in edges if d.get('condition')]

    for group, edge_list, limit in [
        ('%% ── 寄存器输入 ──', seq_in, 50),
        ('%% ── 寄存器 ──', state_e, 40),
        ('%% ── 组合逻辑 ──', combo_e, 60),
        ('%% ── 条件/控制 ──', cond_e, 40),
    ]:
        if edge_list:
            lines.append(f'  {group}')
            for u,v,d in edge_list[:limit]:
                ln = mermaid_edge(u, v, d, '-->' if d.get('timing') != 'state' else '==>')
                if ln: lines.append(ln)
            if len(edge_list) > limit:
                lines.append(f'  %% ... 还有 {len(edge_list) - limit} 条')
            lines.append('')

    return '\n'.join(lines)