"""
test_elk_viewer.py - HTML viewer 内容验证 (Stage 4)

测试内容:
- Toolbar HTML 结构 (search input, filter checkboxes, CDC toggle)
- JS 函数 (applyFilters, bindFilterControls)
- CSS 状态类 (.highlighted, .dimmed, .hidden, .cdc-highlighted, .cdc-dimmed)
- 节点类型过滤覆盖 (Port/State/Operator/Literal)
- 搜索框 substring match (case-insensitive)
"""
import os
import sys

import pytest

NAVISV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTER_SV = os.path.join(NAVISV_ROOT, 'tests', 'fixtures', 'elk_counter.sv')


def _build_html(tmp_path, view='dataflow', **kwargs):
    """调用 ElkExporter.export_html 返回 HTML 字符串"""
    import glob, shutil
    from navisv.drivers.design_driver import DesignDriver
    from navisv.parsers.ast_parser import ASTParser
    from navisv.parsers.netlist_parser import NetlistParser
    from navisv.graph.graph_builder import GraphBuilder
    from navisv.graph.elk_exporter import ElkExporter

    out = tmp_path / 'build'
    if out.exists():
        shutil.rmtree(out)
    DesignDriver([str(COUNTER_SV)], output_dir=str(out), cache=False).build()
    ast = ASTParser(glob.glob(f'{out}/*ast*.json')[0]).parse()
    nl = NetlistParser(glob.glob(f'{out}/*netlist*.json')[0]).parse()
    gb = GraphBuilder(
        ast, nl, ast_json_path=f'{out}/ast.json',
        source_files=[str(COUNTER_SV)], preserve_kwargs_=False, preserve_operators=True,
    ) if False else GraphBuilder(  # simpler path
        ast, nl, ast_json_path=f'{out}/ast.json',
        source_files=[str(COUNTER_SV)], preserve_operators=True,
    )
    gb.build()
    exporter = ElkExporter(view=view, **kwargs).from_graph_builder(gb)
    return exporter.export_html(str(tmp_path / 'viewer.html'))


class TestToolbarHtml:
    """Stage 4 - toolbar HTML 结构"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_toolbar_div_present(self, html):
        """HTML 应包含 <div id='toolbar'>"""
        with open(html) as f:
            content = f.read()
        assert '<div id="toolbar">' in content

    def test_search_input_present(self, html):
        """应包含搜索 input"""
        with open(html) as f:
            content = f.read()
        assert '<input type="search" id="search-input"' in content
        assert 'Search nodes' in content or 'search' in content.lower()

    def test_filter_checkboxes_present(self, html):
        """应有 Port/State/Operator/Literal 4 个复选框"""
        with open(html) as f:
            content = f.read()
        for kind in ('show-port', 'show-state', 'show-operator', 'show-literal'):
            assert f'id="{kind}"' in content, f"Missing checkbox #{kind}"

    def test_cdc_toggle_button_present(self, html):
        """应有 CDC toggle 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="toggle-cdc"' in content
        assert 'CDC: off' in content  # 初始状态

    def test_match_count_span_present(self, html):
        """应有匹配计数 span"""
        with open(html) as f:
            content = f.read()
        assert 'id="match-count"' in content


class TestToolbarJs:
    """Stage 4 - JS 交互函数"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_apply_filters_function(self, html):
        """JS 应定义 applyFilters 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function applyFilters' in content

    def test_bind_filter_controls_function(self, html):
        """JS 应定义 bindFilterControls 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function bindFilterControls' in content

    def test_search_input_handler(self, html):
        """搜索 input 应绑 input 事件"""
        with open(html) as f:
            content = f.read()
        assert "search-input" in content and "'input'" in content

    def test_cdc_button_click_handler(self, html):
        """CDC 按钮应绑 click 事件"""
        with open(html) as f:
            content = f.read()
        assert 'toggle-cdc' in content and 'click' in content

    def test_kind_filter_logic(self, html):
        """应包含 kind 过滤逻辑 (Port/State/Operator/Literal)"""
        with open(html) as f:
            content = f.read()
        for kind in ('Port', 'State', 'Operator', 'Literal'):
            assert kind in content, f"Missing kind {kind} in JS"

    def test_cdc_toggle_toggles_dataset(self, html):
        """CDC button 应切换 dataset.on"""
        with open(html) as f:
            content = f.read()
        assert 'dataset.on' in content


class TestToolbarCss:
    """Stage 4 - CSS 状态类"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_search_input_style(self, html):
        """搜索 input 应有 CSS 样式"""
        with open(html) as f:
            content = f.read()
        assert '#search-input' in content

    def test_filter_group_style(self, html):
        """filter-group 应有 CSS 样式"""
        with open(html) as f:
            content = f.read()
        assert '.filter-group' in content

    def test_toggle_button_style(self, html):
        """toggle-button 应有 CSS 样式"""
        with open(html) as f:
            content = f.read()
        assert '.toggle-button' in content
        assert '.toggle-button.active' in content  # active state

    def test_highlighted_state(self, html):
        """应有 .highlighted 状态 (search 命中)"""
        with open(html) as f:
            content = f.read()
        assert '.highlighted' in content
        assert 'stroke: #f39c12' in content or '#f39c12' in content  # 高亮色

    def test_dimmed_state(self, html):
        """应有 .dimmed 状态 (被过滤掉)"""
        with open(html) as f:
            content = f.read()
        assert '.dimmed' in content
        assert 'opacity: 0.15' in content or 'opacity:0.15' in content

    def test_hidden_state(self, html):
        """应有 .hidden 状态 (完全隐藏)"""
        with open(html) as f:
            content = f.read()
        assert '.hidden' in content
        assert 'display: none' in content or 'display:none' in content

    def test_cdc_highlighted_state(self, html):
        """应有 .cdc-highlighted 状态"""
        with open(html) as f:
            content = f.read()
        assert '.cdc-highlighted' in content
        assert '#e74c3c' in content  # CDC 高亮红色

    def test_cdc_dimmed_state(self, html):
        """应有 .cdc-dimmed 状态"""
        with open(html) as f:
            content = f.read()
        assert '.cdc-dimmed' in content


class TestToolbarBehavior:
    """Stage 4 - 行为文档 (实际行为需浏览器测试, 这里只验证代码完整性)"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_search_uses_lowercase_match(self, html):
        """搜索匹配应小写化 (case-insensitive)"""
        with open(html) as f:
            content = f.read()
        assert 'toLowerCase' in content

    def test_endpoint_visibility_logic(self, html):
        """边过滤: 当任一端节点隐藏时边也隐藏"""
        with open(html) as f:
            content = f.read()
        assert 'visibleNodes' in content or 'endpointsVisible' in content

    def test_match_count_format(self, html):
        """匹配计数格式: 'N/M match' 或 'N/M visible'"""
        with open(html) as f:
            content = f.read()
        assert 'match' in content or 'visible' in content

    def test_filter_applied_on_init(self, html):
        """render 后应自动调用 applyFilters (初始化 CDC dimmed 状态)"""
        with open(html) as f:
            content = f.read()
        # render().then(...) 里调用 applyFilters
        assert '.then(' in content and 'applyFilters()' in content