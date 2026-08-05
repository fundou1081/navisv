"""render_svg.py - Render ELK-positioned JSON to SVG (Stage 2.7+)

Reads ELK-positioned JSON (output of tools/run_elk.js), produces SVG with:
  - Layered layout (real ELK orthogonal routing)
  - Inline stroke attributes (avoid rsvg-convert CSS quirks)
  - Arrow markers per edge color (combinational/sequential/clock/unknown)
  - Node shapes by kind (Operator=diamond, Literal=dashed rect, etc.)
  - Two-column legend (nodes + edges)

Usage:
  python -m navisv.tools.render_svg <positioned.json> <out.svg> [--title=...]
"""
import json
import sys
import os
import html as html_lib
import argparse
from typing import Any, Dict, List, Tuple


EDGE_STYLE = {
    'combinational': ('#2980b9', 'arrow-blue'),
    'sequential':    ('#c0392b', 'arrow-red'),
    'clock':         ('#8e44ad', 'arrow-purple'),
}

NODE_STYLE = {
    'Port':     {'fill': '#ebf5fb', 'stroke': '#2980b9', 'shape': 'rect'},
    'State':    {'fill': '#eafaf1', 'stroke': '#27ae60', 'shape': 'rect'},
    'Operator': {'fill': '#fef9e7', 'stroke': '#d35400', 'shape': 'diamond'},
    'Literal':  {'fill': '#f8f9fa', 'stroke': '#7f8c8d', 'shape': 'rect-dashed'},
    'Net':      {'fill': '#ffffff', 'stroke': '#95a5a6', 'shape': 'rect'},
    'Instance': {'fill': '#fdf2e9', 'stroke': '#e67e22', 'shape': 'rect'},
}

DEFAULT_NODE_STYLE = {'fill': '#ffffff', 'stroke': '#34495e', 'shape': 'rect'}


def _strip_file_tag(label: str) -> str:
    """Remove trailing '(file.sv:line)' from label for cleaner rendering."""
    if ' (' in label and label.endswith(')'):
        return label.rsplit(' (', 1)[0]
    return label


def _compute_bbox(positioned: Dict) -> Tuple[float, float, float, float, float, float]:
    """Compute bounding box from nodes + edges.

    Returns: (min_x, min_y, max_x, max_y, OFFSET_X, OFFSET_Y)
    """
    xs, ys = [], []
    for c in positioned.get('children', []):
        x = c.get('x', 0); y = c.get('y', 0)
        w = c.get('width', 80); h = c.get('height', 40)
        xs.extend([x, x + w]); ys.extend([y, y + h])
    for e in positioned.get('edges', []):
        for sec in e.get('sections', []):
            for pt in [sec.get('startPoint', {}), sec.get('endPoint', {})] + sec.get('bendPoints', []):
                if 'x' in pt and 'y' in pt:
                    xs.append(pt['x']); ys.append(pt['y'])
    if not xs:
        return 0, 0, 100, 100, 0, 0
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    padding = 50
    title_h = 70  # (Stage 2.9) title (y=35) + subtitle (y=55) 留空间
    legend_h = 110
    w = int(max_x - min_x + 2 * padding)
    h = int(max_y - min_y + 2 * padding + legend_h + title_h)
    return min_x, min_y, w, h, -min_x + padding, -min_y + padding + title_h


def _render_markers() -> List[str]:
    """SVG <defs> with arrow markers per edge color."""
    markers = ['<defs>']
    for name, color in [
        ('arrow-blue',   '#2980b9'),
        ('arrow-red',    '#c0392b'),
        ('arrow-purple', '#8e44ad'),
        ('arrow-gray',   '#7f8c8d'),
    ]:
        markers.append(
            f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="8" markerHeight="8" orient="auto">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>'
        )
    markers.append('</defs>')
    return markers


def _render_node(c: Dict, offset_x: float, offset_y: float) -> List[str]:
    """Render a single node (rect / diamond / dashed rect) by kind."""
    x = c.get('x', 0) + offset_x
    y = c.get('y', 0) + offset_y
    w = c.get('width', 80)
    h = c.get('height', 40)
    kind = (c.get('properties') or {}).get('kind', '')
    style = NODE_STYLE.get(kind, DEFAULT_NODE_STYLE)

    label = ''
    if c.get('labels'):
        label = str(c['labels'][0].get('text', c.get('id', '?')))
    else:
        label = c.get('id', '?')
    label_esc = html_lib.escape(_strip_file_tag(label))

    parts = []
    if style['shape'] == 'diamond':
        cx = x + w / 2; cy = y + h / 2
        pts = f"{cx},{cy - h/2} {x+w},{cy} {cx},{cy + h/2} {x},{cy}"
        parts.append(
            f'<polygon points="{pts}" fill="{style["fill"]}" '
            f'stroke="{style["stroke"]}" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{cx}" y="{cy + 6}" font-size="18" font-weight="bold" '
            f'text-anchor="middle" fill="{style["stroke"]}" '
            f'font-family="monospace">{label_esc}</text>'
        )
    elif style['shape'] == 'rect-dashed':
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" '
            f'fill="{style["fill"]}" stroke="{style["stroke"]}" '
            f'stroke-width="2" stroke-dasharray="4,2"/>'
        )
        parts.append(
            f'<text x="{x + w/2}" y="{y + h/2 + 4}" font-size="14" '
            f'font-weight="500" text-anchor="middle" fill="#2c3e50">{label_esc}</text>'
        )
    else:  # rect
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" '
            f'fill="{style["fill"]}" stroke="{style["stroke"]}" '
            f'stroke-width="2.5"/>'
        )
        parts.append(
            f'<text x="{x + w/2}" y="{y + h/2 + 4}" font-size="14" '
            f'font-weight="500" text-anchor="middle" fill="#2c3e50">{label_esc}</text>'
        )
    return parts


def _render_edge(e: Dict, offset_x: float, offset_y: float) -> List[str]:
    """Render an edge as orthogonal path with arrow marker."""
    props = e.get('properties', {}) or {}
    timing = props.get('timing', 'unknown')
    color, marker_id = EDGE_STYLE.get(timing, ('#7f8c8d', 'arrow-gray'))

    parts = []
    for sec in e.get('sections', []):
        start = sec.get('startPoint', {})
        end = sec.get('endPoint', {})
        bend_points = sec.get('bendPoints', [])
        if not start or not end:
            continue
        pts = [(start.get('x', 0), start.get('y', 0))]
        for bp in bend_points:
            pts.append((bp.get('x', 0), bp.get('y', 0)))
        pts.append((end.get('x', 0), end.get('y', 0)))
        pts_off = [(x + offset_x, y + offset_y) for x, y in pts]
        d = 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in pts_off)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" '
            f'opacity="0.9" marker-end="url(#{marker_id})"/>'
        )
    return parts


def _render_legend(W: int, H: int, padding: int) -> List[str]:
    """Two-column legend (nodes + edges)."""
    LY = H - 100
    parts = [
        f'<text x="{padding}" y="{LY}" font-size="13" font-weight="bold" fill="#2c3e50">Legend:</text>',
    ]
    legend_items = [
        ('Port (input/output)', '#2980b9', 'rect', '#ebf5fb'),
        ('State (Reg)', '#27ae60', 'rect', '#eafaf1'),
        ('Operator (logic)', '#d35400', 'diamond', '#fef9e7'),
        ('Literal (value)', '#7f8c8d', 'rect-dashed', '#f8f9fa'),
    ]
    for i, (name, color, shape, fill) in enumerate(legend_items):
        ly = LY + 18 + i * 15
        if shape == 'diamond':
            cx = padding + 14; cy = ly - 4
            pts = f"{cx},{cy-6} {cx+12},{cy} {cx},{cy+6} {cx-12},{cy}"
            parts.append(f'<polygon points="{pts}" fill="{fill}" stroke="{color}" stroke-width="2.5"/>')
        elif shape == 'rect-dashed':
            parts.append(
                f'<rect x="{padding}" y="{ly-7}" width="26" height="12" rx="2" '
                f'fill="{fill}" stroke="{color}" stroke-width="1.5" stroke-dasharray="4,2"/>'
            )
        else:
            parts.append(
                f'<rect x="{padding}" y="{ly-7}" width="26" height="12" rx="3" '
                f'fill="{fill}" stroke="{color}" stroke-width="2.5"/>'
            )
        parts.append(f'<text x="{padding+36}" y="{ly}" font-size="12" fill="#2c3e50">{name}</text>')

    # Edge legend
    EX = padding + 280
    parts.append(f'<text x="{EX}" y="{LY}" font-size="13" font-weight="bold" fill="#2c3e50">Edges:</text>')
    for i, (name, color, marker) in enumerate([
        ('Combinational (data flow)', '#2980b9', 'arrow-blue'),
        ('Sequential (reg update)', '#c0392b', 'arrow-red'),
    ]):
        ly = LY + 18 + i * 15
        parts.append(
            f'<line x1="{EX}" y1="{ly-3}" x2="{EX+30}" y2="{ly-3}" '
            f'stroke="{color}" stroke-width="3" marker-end="url(#{marker})"/>'
        )
        parts.append(f'<text x="{EX+44}" y="{ly}" font-size="12" fill="#2c3e50">{name}</text>')
    return parts


def render_svg(positioned: Dict, title: str = 'navisv — ELK layered',
               subtitle: str = '') -> str:
    """Render ELK-positioned JSON to SVG string."""
    _, _, W, H, OFFSET_X, OFFSET_Y = _compute_bbox(positioned)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        *_render_markers(),
        f'<rect width="100%" height="100%" fill="#fafbfc"/>',
        f'<text x="50" y="35" font-size="18" font-weight="bold" fill="#2c3e50">{html_lib.escape(title)}</text>',
    ]
    if subtitle:
        parts.append(
            f'<text x="50" y="55" font-size="11" font-style="italic" fill="#7f8c8d">'
            f'{html_lib.escape(subtitle)}</text>'
        )

    # Edges first (so nodes render on top)
    for e in positioned.get('edges', []):
        parts.extend(_render_edge(e, OFFSET_X, OFFSET_Y))

    # Nodes
    for c in positioned.get('children', []):
        parts.extend(_render_node(c, OFFSET_X, OFFSET_Y))

    # Legend
    parts.extend(_render_legend(W, H, 50))

    parts.append('</svg>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description='Render ELK-positioned JSON to SVG')
    parser.add_argument('input', help='ELK-positioned JSON file')
    parser.add_argument('output', help='Output SVG path')
    parser.add_argument('--title', default='navisv — ELK layered')
    parser.add_argument('--subtitle', default='')
    args = parser.parse_args()

    with open(args.input) as f:
        positioned = json.load(f)
    svg = render_svg(positioned, args.title, args.subtitle)
    with open(args.output, 'w') as f:
        f.write(svg)
    print(f"✅ SVG written: {args.output} ({len(svg)} bytes)")


if __name__ == '__main__':
    main()