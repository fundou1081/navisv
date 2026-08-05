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


class TestPanZoomToolbarHtml:
    """Stage 7 - pan/zoom toolbar HTML 元素"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_zoom_in_button_present(self, html):
        """应有 zoom-in 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="zoom-in"' in content

    def test_zoom_out_button_present(self, html):
        """应有 zoom-out 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="zoom-out"' in content

    def test_reset_button_present(self, html):
        """应有 reset-view 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="reset-view"' in content
        assert '>Reset<' in content

    def test_zoom_level_span_present(self, html):
        """应有 zoom-level span (显示当前 zoom %)"""
        with open(html) as f:
            content = f.read()
        assert 'id="zoom-level"' in content
        assert '100%' in content  # 初始值

    def test_buttons_have_zoom_btn_class(self, html):
        """所有 zoom 按钮应有 zoom-btn CSS 类"""
        with open(html) as f:
            content = f.read()
        # 3 个按钮都有 zoom-btn 类
        assert content.count('class="zoom-btn') >= 3


class TestPanZoomJs:
    """Stage 7 - pan/zoom JS 函数"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_setup_pan_zoom_function(self, html):
        """应有 setupPanZoom 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function setupPanZoom' in content

    def test_apply_view_transform_function(self, html):
        """应有 applyViewTransform 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function applyViewTransform' in content

    def test_zoom_at_function(self, html):
        """应有 zoomAt 函数 (保持缩放原点)"""
        with open(html) as f:
            content = f.read()
        assert 'function zoomAt' in content

    def test_reset_view_function(self, html):
        """应有 resetView 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function resetView' in content

    def test_clamp_scale_uses_safe_range(self, html):
        """clampScale 应限制在 [0.1, 5]"""
        with open(html) as f:
            content = f.read()
        assert 'clampScale' in content
        assert '0.1' in content
        assert 'Math.min(5' in content

    def test_wheel_handler_prevents_default(self, html):
        """wheel handler 应 preventDefault (避免页面滚动)"""
        with open(html) as f:
            content = f.read()
        assert "'wheel'" in content and 'preventDefault' in content

    def test_mousedown_excludes_nodes(self, html):
        """mousedown 应只在背景触发, 不在节点/边/legend"""
        with open(html) as f:
            content = f.read()
        assert "'mousedown'" in content
        assert "closest('.node, .edge, .port, .legend')" in content

    def test_mousemove_pan_handler(self, html):
        """mousemove 应在 window 上处理 (拖动即使滑出 svg 也跟随)"""
        with open(html) as f:
            content = f.read()
        assert "'mousemove'" in content
        assert 'panStart' in content

    def test_zoom_in_button_handler(self, html):
        """zoom-in 按钮应绑 click 事件"""
        with open(html) as f:
            content = f.read()
        assert 'zoom-in' in content and '1.25' in content  # 缩放因子

    def test_zoom_out_button_handler(self, html):
        """zoom-out 按钮应绑 click 事件"""
        with open(html) as f:
            content = f.read()
        assert 'zoom-out' in content and '1 / 1.25' in content

    def test_reset_button_handler(self, html):
        """reset 按钮应调 resetView"""
        with open(html) as f:
            content = f.read()
        assert "getElementById('reset-view')" in content
        assert 'resetView' in content

    def test_transform_attribute_format(self, html):
        """applyViewTransform 应使用 SVG transform 属性 (split 多行)"""
        with open(html) as f:
            content = f.read()
        # JS 中 setAttribute 是多行调用: g.setAttribute(\n  'transform',\n  ...
        assert 'setAttribute(' in content
        assert "'transform'" in content
        assert 'translate(' in content
        assert 'scale(' in content


class TestPanZoomCss:
    """Stage 7 - pan/zoom CSS 样式"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_svg_cursor_grab(self, html):
        """#graph svg 应有 cursor: grab (可拖提示)"""
        with open(html) as f:
            content = f.read()
        assert '#graph svg' in content
        assert 'cursor: grab' in content

    def test_panning_cursor_grabbing(self, html):
        """.panning 状态应有 cursor: grabbing"""
        with open(html) as f:
            content = f.read()
        assert '.panning' in content
        assert 'cursor: grabbing' in content

    def test_zoom_btn_style(self, html):
        """zoom-btn 应有 CSS 样式"""
        with open(html) as f:
            content = f.read()
        assert '.zoom-btn' in content
        assert '.zoom-btn:hover' in content

    def test_zoom_level_style(self, html):
        """zoom-level 应有 CSS 样式 (等宽字体 + 居中)"""
        with open(html) as f:
            content = f.read()
        assert '#zoom-level' in content
        assert 'min-width' in content


class TestPanZoomSvg:
    """Stage 7 - SVG 结构支持 pan/zoom"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_graph_svg_id_present(self, html):
        """<svg> 应有 id='graph-svg' (供 setupPanZoom 引用)"""
        with open(html) as f:
            content = f.read()
        assert 'id="graph-svg"' in content

    def test_graph_view_group_present(self, html):
        """应有 <g id='graph-view'> (transform 应用到这个 group)"""
        with open(html) as f:
            content = f.read()
        assert 'id="graph-view"' in content
        assert 'translate(0,0) scale(1)' in content  # 初始 transform

    def test_setup_pan_zoom_called_after_render(self, html):
        """render().then() 后应调 setupPanZoom()"""
        with open(html) as f:
            content = f.read()
        # 找到 render().then(...).catch 链
        assert 'setupPanZoom()' in content


class TestSidebarHtml:
    """Stage 9 - sidebar HTML 结构"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_sidebar_aside_present(self, html):
        """应有 <aside id='sidebar'>"""
        with open(html) as f:
            content = f.read()
        assert '<aside id="sidebar"' in content

    def test_sidebar_default_closed(self, html):
        """sidebar 默认应有 sidebar-closed class (隐藏)"""
        with open(html) as f:
            content = f.read()
        assert 'class="sidebar-closed"' in content

    def test_sidebar_header_present(self, html):
        """应有 .sidebar-header"""
        with open(html) as f:
            content = f.read()
        assert 'class="sidebar-header"' in content

    def test_sidebar_title_present(self, html):
        """应有 #sidebar-title (动态标题)"""
        with open(html) as f:
            content = f.read()
        assert 'id="sidebar-title"' in content

    def test_sidebar_close_button_present(self, html):
        """应有 #sidebar-close 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="sidebar-close"' in content
        assert '×' in content or '&#215;' in content  # × 字符

    def test_sidebar_body_present(self, html):
        """应有 #sidebar-body (内容动态注入)"""
        with open(html) as f:
            content = f.read()
        assert 'id="sidebar-body"' in content


class TestSidebarJs:
    """Stage 9 - sidebar JS 交互逻辑"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_render_node_details_function(self, html):
        """应有 renderNodeDetails 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function renderNodeDetails' in content

    def test_render_edge_details_function(self, html):
        """应有 renderEdgeDetails 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function renderEdgeDetails' in content

    def test_get_incoming_edges_helper(self, html):
        """应有 getIncomingEdges helper (节点入边)"""
        with open(html) as f:
            content = f.read()
        assert 'function getIncomingEdges' in content

    def test_get_outgoing_edges_helper(self, html):
        """应有 getOutgoingEdges helper (节点出边)"""
        with open(html) as f:
            content = f.read()
        assert 'function getOutgoingEdges' in content

    def test_label_for_endpoint_helper(self, html):
        """应有 labelForEndpoint helper (ID → label)"""
        with open(html) as f:
            content = f.read()
        assert 'function labelForEndpoint' in content

    def test_build_source_link_function(self, html):
        """应有 buildSourceLink 函数 (跳转源码)"""
        with open(html) as f:
            content = f.read()
        assert 'function buildSourceLink' in content
        assert 'file://' in content

    def test_prop_row_helper(self, html):
        """应有 propRow helper (key-value 表格行)"""
        with open(html) as f:
            content = f.read()
        assert 'function propRow' in content

    def test_prop_row_html_helper(self, html):
        """应有 propRowHtml helper (HTML 表格行)"""
        with open(html) as f:
            content = f.read()
        assert 'function propRowHtml' in content

    def test_node_click_shows_sidebar(self, html):
        """节点 click handler 应显示 sidebar (移除 sidebar-closed)"""
        with open(html) as f:
            content = f.read()
        # renderNodeDetails 调用后 classList.remove('sidebar-closed')
        assert "classList.remove('sidebar-closed')" in content

    def test_sidebar_close_handler(self, html):
        """close button 应绑 click handler (添加 sidebar-closed)"""
        with open(html) as f:
            content = f.read()
        # getElementById('sidebar-close').addEventListener('click', ...
        assert "getElementById('sidebar-close')" in content
        assert "classList.add('sidebar-closed')" in content

    def test_node_details_includes_incoming(self, html):
        """节点详情应包含 Incoming 边列表"""
        with open(html) as f:
            content = f.read()
        assert 'Incoming (' in content

    def test_node_details_includes_outgoing(self, html):
        """节点详情应包含 Outgoing 边列表"""
        with open(html) as f:
            content = f.read()
        assert 'Outgoing (' in content

    def test_node_details_includes_location(self, html):
        """节点详情应包含 File / Line / source link (用 propRowHtml 因为含 HTML)"""
        with open(html) as f:
            content = f.read()
        assert 'propRowHtml(\'Location\'' in content or 'propRowHtml("Location"' in content
        assert 'source-link' in content
        assert 'view source' in content

    def test_edge_details_includes_path_count(self, html):
        """边详情应包含 Path count"""
        with open(html) as f:
            content = f.read()
        assert 'Path count' in content

    def test_edge_details_includes_cdc_status(self, html):
        """边详情应包含 CDC 状态"""
        with open(html) as f:
            content = f.read()
        assert '跨时钟域' in content or 'cdc' in content.lower()


class TestSidebarCss:
    """Stage 9 - sidebar CSS 样式"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_sidebar_position_fixed(self, html):
        """#sidebar 应 fixed 定位"""
        with open(html) as f:
            content = f.read()
        assert '#sidebar' in content
        assert 'position: fixed' in content

    def test_sidebar_closed_transform(self, html):
        """.sidebar-closed 应 translateX 隐藏 (slide out)"""
        with open(html) as f:
            content = f.read()
        assert '.sidebar-closed' in content
        assert 'translateX' in content

    def test_sidebar_transition(self, html):
        """sidebar 应有 transition 动画"""
        with open(html) as f:
            content = f.read()
        assert 'transition:' in content or 'transition ' in content

    def test_sidebar_header_style(self, html):
        """.sidebar-header 应有 flex 布局 + border-bottom"""
        with open(html) as f:
            content = f.read()
        assert '.sidebar-header' in content
        assert 'border-bottom' in content

    def test_sidebar_props_table(self, html):
        """.sidebar-props 应有 table 样式"""
        with open(html) as f:
            content = f.read()
        assert '.sidebar-props' in content
        assert 'border-collapse' in content

    def test_prop_key_style(self, html):
        """.prop-key 应有等宽字体 + 灰色"""
        with open(html) as f:
            content = f.read()
        assert '.prop-key' in content
        assert 'Menlo' in content or 'Consolas' in content or 'monospace' in content

    def test_edge_list_style(self, html):
        """.edge-list 应无 list-style"""
        with open(html) as f:
            content = f.read()
        assert '.edge-list' in content
        assert 'list-style: none' in content or 'list-style:none' in content

    def test_source_link_style(self, html):
        """.source-link 应有蓝色背景"""
        with open(html) as f:
            content = f.read()
        assert '.source-link' in content
        assert '#3498db' in content  # 蓝色

    def test_sidebar_section_style(self, html):
        """.sidebar-section 应有 border-bottom 分隔"""
        with open(html) as f:
            content = f.read()
        assert '.sidebar-section' in content
        assert 'uppercase' in content or 'text-transform' in content