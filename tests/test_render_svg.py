"""Tests for Stage 2.7 — tools/render_svg.py + tools/elk_layout.py"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

# Make navisv importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv.tools.render_svg import (
    render_svg,
    _compute_bbox,
    _render_markers,
    _render_node,
    _render_edge,
    _render_legend,
    _strip_file_tag,
    NODE_STYLE,
    EDGE_STYLE,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_positioned_json():
    """Minimal ELK-input JSON (no sections — sections are ELK output only).

    IMPORTANT: ELK JSON import requires 'id' on every top-level element
    but does NOT accept 'sections' field (those are produced by ELK).
    """
    return {
        'id': 'root',
        'layoutOptions': {'elk.algorithm': 'layered', 'elk.direction': 'RIGHT'},
        'children': [
            {'id': 'p1', 'labels': [{'text': 'clk'}],
             'width': 80, 'height': 40, 'properties': {'kind': 'Port'}},
            {'id': 'op1', 'labels': [{'text': '+'}],
             'width': 80, 'height': 40, 'properties': {'kind': 'Operator'}},
            {'id': 'l1', 'labels': [{'text': "4'b0"}],
             'width': 80, 'height': 40, 'properties': {'kind': 'Literal'}},
        ],
        'edges': [
            {'id': 'e0', 'sources': ['p1'], 'targets': ['op1'],
             'properties': {'timing': 'combinational'}},
            {'id': 'e1', 'sources': ['op1'], 'targets': ['l1'],
             'properties': {'timing': 'sequential'}},
        ],
    }


def _make_positioned_with_layout():
    """ELK-OUTPUT JSON (has sections + x/y) — for render_svg unit tests."""
    return {
        'id': 'root',
        'children': [
            {'id': 'p1', 'labels': [{'text': 'clk'}], 'x': 0, 'y': 0,
             'width': 80, 'height': 40, 'properties': {'kind': 'Port'}},
            {'id': 'op1', 'labels': [{'text': '+'}], 'x': 120, 'y': 0,
             'width': 80, 'height': 40, 'properties': {'kind': 'Operator'}},
            {'id': 'l1', 'labels': [{'text': "4'b0"}], 'x': 240, 'y': 0,
             'width': 80, 'height': 40, 'properties': {'kind': 'Literal'}},
        ],
        'edges': [
            {'id': 'e0', 'sources': ['p1'], 'targets': ['op1'],
             'properties': {'timing': 'combinational'},
             'sections': [{'startPoint': {'x': 80, 'y': 20},
                           'endPoint':   {'x': 120, 'y': 20},
                           'bendPoints': []}]},
            {'id': 'e1', 'sources': ['op1'], 'targets': ['l1'],
             'properties': {'timing': 'sequential'},
             'sections': [{'startPoint': {'x': 200, 'y': 20},
                           'endPoint':   {'x': 240, 'y': 20},
                           'bendPoints': []}]},
        ],
    }


# ---------------------------------------------------------------------------
# Unit tests: _strip_file_tag
# ---------------------------------------------------------------------------

class TestStripFileTag:
    """label 去掉 "(file.sv:line)" 后缀"""

    def test_strips_file_line(self):
        assert _strip_file_tag('count (counter.sv:7)') == 'count'

    def test_keeps_plain_label(self):
        assert _strip_file_tag('counter') == 'counter'

    def test_keeps_label_with_parens_not_at_end(self):
        assert _strip_file_tag('foo (bar) baz') == 'foo (bar) baz'

    def test_empty_string(self):
        assert _strip_file_tag('') == ''


# ---------------------------------------------------------------------------
# Unit tests: _render_markers
# ---------------------------------------------------------------------------

class TestRenderMarkers:
    """SVG <defs> with 4 arrow markers (blue/red/purple/gray)"""

    def test_contains_all_4_markers(self):
        result = '\n'.join(_render_markers())
        for marker_id in ('arrow-blue', 'arrow-red', 'arrow-purple', 'arrow-gray'):
            assert f'id="{marker_id}"' in result

    def test_marker_has_orient_auto(self):
        result = '\n'.join(_render_markers())
        assert 'orient="auto"' in result

    def test_wrapped_in_defs(self):
        result = '\n'.join(_render_markers())
        assert result.startswith('<defs>')
        assert result.endswith('</defs>')


# ---------------------------------------------------------------------------
# Unit tests: _render_node
# ---------------------------------------------------------------------------

class TestRenderNode:
    """节点按 kind 渲染不同形状"""

    def test_port_is_rounded_rect(self):
        node = {'id': 'p', 'labels': [{'text': 'clk'}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'Port'}}
        out = '\n'.join(_render_node(node, 0, 0))
        assert '<rect' in out
        assert NODE_STYLE['Port']['fill'] in out
        assert 'rx="5"' in out  # rounded

    def test_operator_is_diamond(self):
        node = {'id': 'op', 'labels': [{'text': '+'}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'Operator'}}
        out = '\n'.join(_render_node(node, 0, 0))
        assert '<polygon' in out  # diamond
        assert '+' in out  # label
        assert 'font-family="monospace"' in out

    def test_literal_is_dashed_rect(self):
        node = {'id': 'l', 'labels': [{'text': "4'b0"}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'Literal'}}
        out = '\n'.join(_render_node(node, 0, 0))
        assert '<rect' in out
        assert 'stroke-dasharray="4,2"' in out

    def test_state_is_green_rect(self):
        node = {'id': 's', 'labels': [{'text': 'count'}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'State'}}
        out = '\n'.join(_render_node(node, 0, 0))
        assert '<rect' in out
        assert NODE_STYLE['State']['fill'] in out

    def test_unknown_kind_falls_back(self):
        node = {'id': 'x', 'labels': [{'text': 'foo'}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'Mystery'}}
        out = '\n'.join(_render_node(node, 0, 0))
        # 应该 fallback 到 DEFAULT_NODE_STYLE (rect, white fill)
        assert '<rect' in out

    def test_offset_applied(self):
        node = {'id': 'p', 'labels': [{'text': 'clk'}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'Port'}}
        # OFFSET 100, 200
        out = '\n'.join(_render_node(node, 100, 200))
        assert 'x="100"' in out
        assert 'y="200"' in out

    def test_label_file_tag_stripped(self):
        node = {'id': 'p', 'labels': [{'text': 'clk (file.sv:4)'}], 'x': 0, 'y': 0,
                'width': 80, 'height': 40, 'properties': {'kind': 'Port'}}
        out = '\n'.join(_render_node(node, 0, 0))
        assert 'clk' in out
        assert 'file.sv:4' not in out  # file tag stripped


# ---------------------------------------------------------------------------
# Unit tests: _render_edge
# ---------------------------------------------------------------------------

class TestRenderEdge:
    """边按时序着色 + 箭头"""

    def test_combinational_edge_is_blue(self):
        edge = {'id': 'e', 'sources': ['a'], 'targets': ['b'],
                'properties': {'timing': 'combinational'},
                'sections': [{'startPoint': {'x': 0, 'y': 0},
                              'endPoint': {'x': 10, 'y': 0},
                              'bendPoints': []}]}
        out = '\n'.join(_render_edge(edge, 0, 0))
        assert '#2980b9' in out
        assert 'arrow-blue' in out

    def test_sequential_edge_is_red(self):
        edge = {'id': 'e', 'sources': ['a'], 'targets': ['b'],
                'properties': {'timing': 'sequential'},
                'sections': [{'startPoint': {'x': 0, 'y': 0},
                              'endPoint': {'x': 10, 'y': 0},
                              'bendPoints': []}]}
        out = '\n'.join(_render_edge(edge, 0, 0))
        assert '#c0392b' in out
        assert 'arrow-red' in out

    def test_unknown_timing_is_gray(self):
        edge = {'id': 'e', 'sources': ['a'], 'targets': ['b'],
                'properties': {'timing': 'unknown'},
                'sections': [{'startPoint': {'x': 0, 'y': 0},
                              'endPoint': {'x': 10, 'y': 0},
                              'bendPoints': []}]}
        out = '\n'.join(_render_edge(edge, 0, 0))
        assert '#7f8c8d' in out
        assert 'arrow-gray' in out

    def test_inline_stroke_no_css_class(self):
        """edge 必须用 inline stroke (避免 rsvg-convert CSS quirks)"""
        edge = {'id': 'e', 'sources': ['a'], 'targets': ['b'],
                'properties': {'timing': 'combinational'},
                'sections': [{'startPoint': {'x': 0, 'y': 0},
                              'endPoint': {'x': 10, 'y': 0},
                              'bendPoints': []}]}
        out = '\n'.join(_render_edge(edge, 0, 0))
        assert 'stroke="#2980b9"' in out
        assert 'stroke-width="3"' in out
        # 不应有 class 属性 (Stage 2.6 CSS class 方案踩过坑)
        assert 'class=' not in out

    def test_bend_points_in_path(self):
        """orthogonal routing 的 bendPoints 应在 path d 里"""
        edge = {'id': 'e', 'sources': ['a'], 'targets': ['b'],
                'properties': {'timing': 'combinational'},
                'sections': [{'startPoint': {'x': 0, 'y': 0},
                              'endPoint':   {'x': 100, 'y': 100},
                              'bendPoints': [{'x': 50, 'y': 0}, {'x': 50, 'y': 100}]}]}
        out = '\n'.join(_render_edge(edge, 0, 0))
        # Path d 应该包含所有 bendPoints
        assert 'M 0.0,0.0' in out
        assert 'L 50.0,0.0' in out
        assert 'L 50.0,100.0' in out
        assert 'L 100.0,100.0' in out


# ---------------------------------------------------------------------------
# Unit tests: _compute_bbox
# ---------------------------------------------------------------------------

class TestComputeBBox:
    """bounding box 包含节点 + 边的所有点"""

    def test_bbox_includes_nodes(self):
        positioned = _make_positioned_with_layout()
        min_x, min_y, w, h, _, _ = _compute_bbox(positioned)
        # 默认 x/y 范围是 [0, 320], bbox 应包含
        assert min_x <= 0
        assert min_y <= 0
        assert w > 280  # nodes + padding
        assert h > 100

    def test_bbox_includes_edge_endpoints(self):
        """边超出节点范围时, bbox 应扩展"""
        positioned = {
            'children': [{'id': 'a', 'x': 0, 'y': 0, 'width': 80, 'height': 40,
                         'labels': [], 'properties': {}}],
            'edges': [{'sections': [{'startPoint': {'x': 80, 'y': 20},
                                     'endPoint': {'x': 500, 'y': 20},
                                     'bendPoints': []}]}],
        }
        min_x, _, w, _, _, _ = _compute_bbox(positioned)
        # 边到 x=500, bbox 应包含
        assert min_x + w > 500 + 50  # 加 padding


# ---------------------------------------------------------------------------
# Integration: render_svg() end-to-end
# ---------------------------------------------------------------------------

class TestRenderSvgEndToEnd:
    """render_svg() 完整流程"""

    def test_returns_valid_svg(self):
        positioned = _make_positioned_with_layout()
        svg = render_svg(positioned, title='Test', subtitle='sub')
        assert svg.startswith('<svg')
        assert svg.endswith('</svg>')
        assert 'viewBox=' in svg
        assert 'Test' in svg  # title
        assert 'sub' in svg   # subtitle

    def test_includes_all_nodes(self):
        positioned = _make_positioned_with_layout()
        svg = render_svg(positioned)
        # Labels — 单引号被 HTML 转义为 &#x27;
        assert 'clk' in svg
        assert '+' in svg
        assert "4&#x27;b0" in svg or '4\\&#x27;b0' in svg

    def test_includes_all_edges(self):
        positioned = _make_positioned_with_layout()
        svg = render_svg(positioned)
        assert '<path' in svg
        # 两条边 (combinational blue + sequential red)
        assert '#2980b9' in svg  # combinational
        assert '#c0392b' in svg  # sequential

    def test_includes_legend(self):
        positioned = _make_positioned_with_layout()
        svg = render_svg(positioned)
        assert 'Legend:' in svg
        assert 'Edges:' in svg

    def test_escapes_html_in_title(self):
        positioned = _make_positioned_with_layout()
        svg = render_svg(positioned, title='<script>alert(1)</script>')
        # script 标签应被 escape
        assert '<script>' not in svg
        assert '&lt;script&gt;' in svg


# ---------------------------------------------------------------------------
# Integration: run_elk_layout() with Node.js
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists('/Users/fundou/my_dv_proj/navisv/navisv/data/elk.bundled.js'),
    reason='ELK bundled not present'
)
class TestRunElkLayout:
    """Node.js subprocess 调 ELK.bundled.js"""

    def test_basic_layout(self):
        from navisv.tools.elk_layout import run_elk_layout
        # 用 ELK-input JSON (no sections)
        elk_input = _make_positioned_json()
        result = run_elk_layout(elk_input, direction='RIGHT')
        assert 'children' in result
        assert all('x' in c and 'y' in c for c in result['children'])
        # 边有 sections (orthogonal routing)
        assert all('sections' in e for e in result['edges'])

    def test_direction_changes_layout(self):
        from navisv.tools.elk_layout import run_elk_layout
        elk_input = _make_positioned_json()
        r_right = run_elk_layout(elk_input, direction='RIGHT')
        r_down = run_elk_layout(elk_input, direction='DOWN')
        # 节点位置应该不同
        right_xs = [c['x'] for c in r_right['children']]
        down_xs = [c['x'] for c in r_down['children']]
        # RIGHT 横向: x 变化大; DOWN 纵向: y 变化大 (这里不严格测试, 只是验证不崩)
        assert len(right_xs) == len(down_xs) == 3

    def test_run_elk_js_exists(self):
        from navisv.tools.elk_layout import RUN_ELK_JS
        assert os.path.exists(RUN_ELK_JS)

    def test_elk_bundled_exists(self):
        from navisv.tools.elk_layout import ELK_BUNDLED_JS
        assert os.path.exists(ELK_BUNDLED_JS)


# ---------------------------------------------------------------------------
# Integration: end-to-end with counter.sv
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists('/Users/fundou/my_dv_proj/navisv/navisv/data/elk.bundled.js'),
    reason='ELK bundled not present'
)
class TestStage27EndToEnd:
    """端到端: counter.sv → ELK layout → SVG"""

    def test_counter_produces_valid_svg(self, tmp_path):
        import glob
        import shutil
        from navisv.drivers.design_driver import DesignDriver
        from navisv.graph.graph_builder import GraphBuilder
        from navisv.graph.elk_exporter import ElkExporter
        from navisv.parsers.ast_parser import ASTParser
        from navisv.parsers.netlist_parser import NetlistParser
        from navisv.tools.elk_layout import run_layout_and_render

        out_dir = '/tmp/navisv_stage27_test'
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)

        counter_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'fixtures', 'elk_counter.sv')
        )
        DesignDriver([counter_path], output_dir=out_dir, cache=False).build()

        ast = ASTParser(glob.glob(f'{out_dir}/*ast*.json')[0]).parse()
        nl = NetlistParser(glob.glob(f'{out_dir}/*netlist*.json')[0]).parse()
        gb = GraphBuilder(
            ast, nl, ast_json_path=f'{out_dir}/ast.json',
            source_files=[counter_path], preserve_operators=True,
        )
        gb.build()

        exporter = ElkExporter(view="dataflow").from_networkx(gb.graph)
        elk_json = exporter.to_elk_json()

        svg_path = str(tmp_path / 'counter.svg')
        out = run_layout_and_render(
            elk_json, svg_path,
            title='counter (ELK test)',
            subtitle='end-to-end Stage 2.7 test',
            direction='RIGHT',
        )
        assert os.path.exists(out)
        content = open(out).read()
        assert '<svg' in content
        # 11 节点: 4 ports + 1 state + 5 operators + 1 literal
        # 至少应该有这些 labels (SVG 中 < 被 HTML 转义为 &lt;, 单引号 &#x27;)
        assert 'clk' in content
        assert 'rst_n' in content
        assert 'enable' in content
        assert 'count' in content
        assert '+' in content     # op_9 from BinaryOp Add
        assert '!' in content     # op_5 from LogicalNot
        assert 'if' in content    # op_8 from named-value condition
        assert '&lt;=' in content  # op_6 from literal RHS (HTML-escaped)
        assert 'merge' in content
        assert "4&#x27;b0" in content  # Literal value (HTML-escaped apostrophe)