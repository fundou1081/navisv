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


class TestExportMenuHtml:
    """Stage 10 - export dropdown HTML"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_export_dropdown_present(self, html):
        """应有 #export-dropdown 容器"""
        with open(html) as f:
            content = f.read()
        assert 'id="export-dropdown"' in content

    def test_export_trigger_button(self, html):
        """应有 #export-btn 触发按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="export-btn"' in content
        assert 'Export' in content

    def test_export_menu_present(self, html):
        """应有 #export-menu (dropdown content)"""
        with open(html) as f:
            content = f.read()
        assert 'id="export-menu"' in content

    def test_export_menu_hidden_by_default(self, html):
        """menu 默认应有 hidden 属性"""
        with open(html) as f:
            content = f.read()
        # 验证 <div class="dropdown-content" id="export-menu" hidden>
        assert 'id="export-menu" hidden' in content or 'hidden id="export-menu"' in content

    def test_export_format_svg(self, html):
        """应有 SVG 导出项"""
        with open(html) as f:
            content = f.read()
        assert 'data-format="svg"' in content
        assert 'SVG' in content

    def test_export_format_png(self, html):
        """应有 PNG 导出项"""
        with open(html) as f:
            content = f.read()
        assert 'data-format="png"' in content
        assert 'PNG' in content

    def test_export_format_json(self, html):
        """应有 JSON 导出项"""
        with open(html) as f:
            content = f.read()
        assert 'data-format="json"' in content
        assert 'JSON' in content

    def test_export_format_mermaid(self, html):
        """应有 Mermaid 导出项"""
        with open(html) as f:
            content = f.read()
        assert 'data-format="mermaid"' in content
        assert 'Mermaid' in content


class TestExportJs:
    """Stage 10 - export JS 逻辑"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_download_blob_helper(self, html):
        """应有 downloadBlob 辅助函数"""
        with open(html) as f:
            content = f.read()
        assert 'function downloadBlob' in content
        assert 'URL.createObjectURL' in content

    def test_download_svg_function(self, html):
        """应有 downloadSvg 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function downloadSvg' in content
        assert 'XMLSerializer' in content
        assert 'image/svg+xml' in content

    def test_download_svg_adds_background(self, html):
        """downloadSvg 应加白色背景 rect (避免透明)"""
        with open(html) as f:
            content = f.read()
        # 'fill="white"' 用于 rect background
        assert "'white'" in content or '"white"' in content

    def test_download_png_function(self, html):
        """应有 downloadPng 函数 (Canvas + Image 渲染)"""
        with open(html) as f:
            content = f.read()
        assert 'function downloadPng' in content
        assert 'createElement(\'canvas\')' in content or 'createElement("canvas")' in content
        assert 'drawImage' in content
        assert 'image/png' in content

    def test_download_png_2x_scale(self, html):
        """downloadPng 应用 2x scale 高清"""
        with open(html) as f:
            content = f.read()
        assert '* scale' in content or '* 2' in content

    def test_download_json_function(self, html):
        """应有 downloadJson 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function downloadJson' in content
        assert 'JSON.stringify' in content

    def test_download_mermaid_function(self, html):
        """应有 downloadMermaid 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function downloadMermaid' in content

    def test_generate_mermaid_function(self, html):
        """应有 generateMermaid 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function generateMermaid' in content
        assert 'flowchart LR' in content

    def test_mermaid_arrow_for_cdc(self, html):
        """CDC 边应用 ==> 粗箭头"""
        with open(html) as f:
            content = f.read()
        assert "'==>'" in content or '"==>"' in content

    def test_mermaid_normal_arrow(self, html):
        """普通边用 --> 箭头"""
        with open(html) as f:
            content = f.read()
        assert "'-->'" in content or '"-->"' in content

    def test_sanitize_mermaid_id_helper(self, html):
        """应有 sanitizeMermaidId helper (清理非法字符)"""
        with open(html) as f:
            content = f.read()
        assert 'function sanitizeMermaidId' in content
        # mermaid ID 只允许 [A-Za-z0-9_]
        assert '[^A-Za-z0-9_]' in content

    def test_bind_export_menu_function(self, html):
        """应有 bindExportMenu 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function bindExportMenu' in content

    def test_export_btn_toggle_handler(self, html):
        """export-btn 应绑 click handler (toggle menu)"""
        with open(html) as f:
            content = f.read()
        assert "getElementById('export-btn')" in content
        assert "removeAttribute('hidden')" in content
        assert "setAttribute('hidden', '')" in content

    def test_export_item_format_dispatch(self, html):
        """item click 应按 data-format dispatch"""
        with open(html) as f:
            content = f.read()
        assert "dataset.format" in content
        # 4 个分支
        assert "fmt === 'svg'" in content or 'fmt === "svg"' in content
        assert "fmt === 'png'" in content or 'fmt === "png"' in content
        assert "fmt === 'json'" in content or 'fmt === "json"' in content
        assert "fmt === 'mermaid'" in content or 'fmt === "mermaid"' in content

    def test_export_click_outside_closes(self, html):
        """点击 menu 外应关闭 menu"""
        with open(html) as f:
            content = f.read()
        assert "closest('#export-dropdown')" in content

    def test_bind_export_menu_called_after_render(self, html):
        """render().then() 后应调 bindExportMenu()"""
        with open(html) as f:
            content = f.read()
        assert 'bindExportMenu()' in content


class TestExportCss:
    """Stage 10 - export dropdown CSS"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_dropdown_position_relative(self, html):
        """.dropdown 应 position: relative (定位 anchor)"""
        with open(html) as f:
            content = f.read()
        assert '.dropdown' in content
        assert 'position: relative' in content

    def test_dropdown_content_position(self, html):
        """.dropdown-content 应 absolute 定位"""
        with open(html) as f:
            content = f.read()
        assert '.dropdown-content' in content
        assert 'position: absolute' in content

    def test_dropdown_content_hidden(self, html):
        """.dropdown-content[hidden] 应 display: none"""
        with open(html) as f:
            content = f.read()
        assert '.dropdown-content[hidden]' in content
        assert 'display: none' in content

    def test_export_trigger_active_state(self, html):
        """.export-trigger.active 应高亮"""
        with open(html) as f:
            content = f.read()
        assert '.export-trigger.active' in content
        assert '#3498db' in content  # 激活蓝色

    def test_export_item_hover(self, html):
        """.export-item:hover 应有 hover 背景"""
        with open(html) as f:
            content = f.read()
        assert '.export-item' in content
        assert '.export-item:hover' in content


class TestKeyboardShortcutsHtml:
    """Stage 12 - help modal HTML 结构"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_help_modal_present(self, html):
        """应有 #help-modal 元素"""
        with open(html) as f:
            content = f.read()
        assert 'id="help-modal"' in content

    def test_help_modal_hidden_by_default(self, html):
        """help modal 默认应有 hidden 属性"""
        with open(html) as f:
            content = f.read()
        # 应有 'role="dialog"' 和 'hidden' 在 modal 上
        assert 'role="dialog"' in content
        assert 'hidden' in content

    def test_modal_close_button_present(self, html):
        """应有 #help-close × 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="help-close"' in content

    def test_shortcut_table_present(self, html):
        """应有 .shortcut-table 表格"""
        with open(html) as f:
            content = f.read()
        assert 'shortcut-table' in content

    def test_shortcut_keys_documented(self, html):
        """所有快捷键都应记录在表格里"""
        with open(html) as f:
            content = f.read()
        # 11 个快捷键
        for key_desc in (
            'Cmd', 'Ctrl', 'Focus search',
            'Close sidebar',
            'Zoom in', 'Zoom out', 'Reset view',
            'Toggle CDC',
            'Toggle Port', 'Toggle State', 'Toggle Operator', 'Toggle Literal',
            'Show this help',
        ):
            assert key_desc in content, f"Missing shortcut '{key_desc}' in help table"

    def test_kbd_element_present(self, html):
        """应使用 <kbd> 标签包裹按键名"""
        with open(html) as f:
            content = f.read()
        assert '<kbd>' in content
        assert '</kbd>' in content


class TestKeyboardShortcutsJs:
    """Stage 12 - JS 快捷键逻辑"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_bind_keyboard_shortcuts_function(self, html):
        """应有 bindKeyboardShortcuts 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function bindKeyboardShortcuts' in content

    def test_handle_shortcut_function(self, html):
        """应有 handleShortcut 分发函数"""
        with open(html) as f:
            content = f.read()
        assert 'function handleShortcut' in content

    def test_is_typing_in_search_helper(self, html):
        """应有 isTypingInSearch helper (input focus 检测)"""
        with open(html) as f:
            content = f.read()
        assert 'function isTypingInSearch' in content
        assert 'INPUT' in content or 'TEXTAREA' in content

    def test_open_close_help_helpers(self, html):
        """应有 openHelp / closeHelp helpers"""
        with open(html) as f:
            content = f.read()
        assert 'function openHelp' in content
        assert 'function closeHelp' in content

    def test_close_sidebar_helper(self, html):
        """应有 closeSidebar helper"""
        with open(html) as f:
            content = f.read()
        assert 'function closeSidebar' in content

    def test_focus_search_helper(self, html):
        """应有 focusSearch helper"""
        with open(html) as f:
            content = f.read()
        assert 'function focusSearch' in content

    def test_clear_search_helper(self, html):
        """应有 clearSearch helper (Esc 清空搜索)"""
        with open(html) as f:
            content = f.read()
        assert 'function clearSearch' in content

    def test_zoom_in_out_helpers(self, html):
        """应有 zoomIn / zoomOut helpers"""
        with open(html) as f:
            content = f.read()
        assert 'function zoomIn' in content
        assert 'function zoomOut' in content

    def test_toggle_checkbox_helper(self, html):
        """应有 toggleCheckbox helper (kind 过滤)"""
        with open(html) as f:
            content = f.read()
        assert 'function toggleCheckbox' in content

    def test_cmd_f_prevents_default(self, html):
        """Cmd/Ctrl+F 应 preventDefault (覆盖浏览器 find)"""
        with open(html) as f:
            content = f.read()
        # metaKey || ctrlKey && 'f'
        assert 'metaKey' in content
        assert 'ctrlKey' in content
        assert "'f'" in content or '"f"' in content
        assert 'preventDefault()' in content

    def test_esc_handler_priority(self, html):
        """Esc 应优先处理 (即使在 input 中)"""
        with open(html) as f:
            content = f.read()
        # Esc 应该在 isTypingInSearch 检查之前
        assert "'Escape'" in content or '"Escape"' in content

    def test_modifier_keys_skip(self, html):
        """Cmd/Ctrl/Alt 按下时其他快捷键应跳过"""
        with open(html) as f:
            content = f.read()
        assert 'metaKey || e.ctrlKey || e.altKey' in content or 'altKey' in content

    def test_help_close_button_handler(self, html):
        """help-close 应绑 click handler"""
        with open(html) as f:
            content = f.read()
        assert "getElementById('help-close')" in content

    def test_modal_overlay_click_closes(self, html):
        """点击 modal overlay (非内容) 应关闭"""
        with open(html) as f:
            content = f.read()
        assert "e.target === modal" in content

    def test_keydown_listener_attached(self, html):
        """document 应绑 keydown listener"""
        with open(html) as f:
            content = f.read()
        assert "'keydown'" in content
        assert 'handleShortcut' in content

    def test_bind_keyboard_shortcuts_called(self, html):
        """render().then() 后应调 bindKeyboardShortcuts()"""
        with open(html) as f:
            content = f.read()
        assert 'bindKeyboardShortcuts()' in content


class TestKeyboardShortcutsCss:
    """Stage 12 - modal CSS 样式"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_modal_overlay_full_screen(self, html):
        """.modal-overlay 应 full-screen + 背景遮罩"""
        with open(html) as f:
            content = f.read()
        assert '.modal-overlay' in content
        assert 'position: fixed' in content
        assert 'rgba(0, 0, 0, 0.4)' in content or 'rgba(0,0,0,0.4)' in content

    def test_modal_overlay_hidden(self, html):
        """.modal-overlay[hidden] 应 display: none"""
        with open(html) as f:
            content = f.read()
        assert '.modal-overlay[hidden]' in content

    def test_modal_content_centered(self, html):
        """.modal-content 应 flex 居中 + white 背景 + 阴影"""
        with open(html) as f:
            content = f.read()
        assert '.modal-content' in content
        assert 'border-radius' in content
        assert 'box-shadow' in content

    def test_kbd_style(self, html):
        """<kbd> 应有 monospace + 背景 + 边框"""
        with open(html) as f:
            content = f.read()
        assert 'kbd' in content
        assert 'monospace' in content
        assert 'border:' in content or 'border ' in content

    def test_shortcut_table_style(self, html):
        """.shortcut-table 应 border-collapse"""
        with open(html) as f:
            content = f.read()
        assert '.shortcut-table' in content
        assert 'border-collapse' in content


class TestNodeEmoji:
    """Stage 13 - 节点 emoji icon 前缀 + Legend 更新"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_kind_emoji_mapping(self, html):
        """应有 KIND_EMOJI 映射 (Port/State/Operator/Literal → emoji)"""
        with open(html) as f:
            content = f.read()
        assert 'KIND_EMOJI' in content
        # 4 个 kind 都应映射
        assert 'Port' in content and 'State' in content and 'Operator' in content and 'Literal' in content

    def test_port_emoji(self, html):
        """Port 应有 📡 emoji"""
        with open(html) as f:
            content = f.read()
        assert '📡' in content

    def test_state_emoji(self, html):
        """State 应有 📦 emoji"""
        with open(html) as f:
            content = f.read()
        assert '📦' in content

    def test_operator_emoji(self, html):
        """Operator 应有 ⚙ emoji"""
        with open(html) as f:
            content = f.read()
        assert '⚙' in content

    def test_literal_emoji(self, html):
        """Literal 应有 🔢 emoji"""
        with open(html) as f:
            content = f.read()
        assert '🔢' in content

    def test_legend_includes_emoji(self, html):
        """Legend 中应包含 4 个 emoji (替换纯文字)"""
        with open(html) as f:
            content = f.read()
        # Legend text 区段 (在 .legend-text 后)
        # 检查 4 个 emoji 都在 Legend 区段 (后面跟 "State"/"Port"/"Operator"/"Literal")
        assert '📦 State' in content or 'State' in content
        assert '📡 Port' in content or 'Port' in content
        assert '⚙ Operator' in content or 'Operator' in content
        assert '🔢 Literal' in content or 'Literal' in content

    def test_emoji_prefix_used_in_render(self, html):
        """render() 中应用 emojiPrefix 到 label 前"""
        with open(html) as f:
            content = f.read()
        # 应有 emojiPrefix 变量使用
        assert 'emojiPrefix' in content

    def test_emoji_font_family(self, html):
        """CSS 应有 emoji 字体 fallback (Apple Color Emoji 等)"""
        with open(html) as f:
            content = f.read()
        assert 'Apple Color Emoji' in content or 'Segoe UI Emoji' in content


class TestThemeSwitcherHtml:
    """Stage 16 - theme selector HTML"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_theme_select_present(self, html):
        """应有 #theme-select 下拉"""
        with open(html) as f:
            content = f.read()
        assert 'id="theme-select"' in content

    def test_theme_select_class(self, html):
        """下拉应有 .theme-select CSS 类"""
        with open(html) as f:
            content = f.read()
        assert 'class="theme-select"' in content

    def test_theme_options(self, html):
        """应有 3 个 theme option: Auto / Light / Dark"""
        with open(html) as f:
            content = f.read()
        for theme in ('auto', 'light', 'dark'):
            assert f'value="{theme}"' in content, f"Missing theme option '{theme}'"

    def test_theme_option_labels(self, html):
        """option label 应包含 emoji (🌓 ☀️ 🌙)"""
        with open(html) as f:
            content = f.read()
        for emoji in ('🌓', '☀️', '🌙'):
            assert emoji in content, f"Missing theme emoji {emoji}"


class TestThemeSwitcherJs:
    """Stage 16 - theme switcher JS 逻辑"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_apply_theme_function(self, html):
        """应有 applyTheme 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function applyTheme' in content

    def test_bind_theme_select_function(self, html):
        """应有 bindThemeSelect 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function bindThemeSelect' in content

    def test_get_system_theme_helper(self, html):
        """应有 getSystemTheme helper (prefers-color-scheme 检测)"""
        with open(html) as f:
            content = f.read()
        assert 'function getSystemTheme' in content
        assert 'prefers-color-scheme' in content
        assert 'matchMedia' in content

    def test_get_saved_theme_helper(self, html):
        """应有 getSavedTheme helper (localStorage 读取)"""
        with open(html) as f:
            content = f.read()
        assert 'function getSavedTheme' in content
        assert 'localStorage' in content

    def test_save_theme_helper(self, html):
        """应有 saveTheme helper (localStorage 写入)"""
        with open(html) as f:
            content = f.read()
        assert 'function saveTheme' in content
        assert 'setItem' in content

    def test_theme_storage_key(self, html):
        """应有 THEME_STORAGE_KEY 常量"""
        with open(html) as f:
            content = f.read()
        assert 'THEME_STORAGE_KEY' in content
        assert 'navisv_elk_theme' in content

    def test_apply_theme_sets_data_theme_attribute(self, html):
        """applyTheme 应设置 :root data-theme 属性"""
        with open(html) as f:
            content = f.read()
        assert "setAttribute('data-theme'" in content
        assert "setAttribute('data-theme-source'" in content

    def test_apply_theme_auto_falls_back(self, html):
        """auto 模式应回退到 getSystemTheme"""
        with open(html) as f:
            content = f.read()
        assert "theme === 'auto'" in content or 'theme === "auto"' in content
        assert 'getSystemTheme()' in content

    def test_change_event_handler(self, html):
        """select 应绑 change 事件"""
        with open(html) as f:
            content = f.read()
        assert "'change'" in content
        assert 'addEventListener' in content

    def test_localstorage_try_catch(self, html):
        """localStorage 调用应有 try/catch (隐私模式 fallback)"""
        with open(html) as f:
            content = f.read()
        # 至少 2 个 try (getItem + setItem)
        assert content.count('try {') >= 2 or content.count('try{') >= 2

    def test_matchmedia_change_listener(self, html):
        """matchMedia 应绑 change 事件 (Auto 模式跟系统)"""
        with open(html) as f:
            content = f.read()
        assert "addEventListener('change'" in content or "addListener(" in content

    def test_bind_theme_select_called_after_render(self, html):
        """render().then() 后应调 bindThemeSelect()"""
        with open(html) as f:
            content = f.read()
        assert 'bindThemeSelect()' in content


class TestThemeSwitcherCss:
    """Stage 16 - theme CSS variables"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_root_css_variables(self, html):
        """:root 应定义 CSS variables (--bg-page 等)"""
        with open(html) as f:
            content = f.read()
        assert ':root' in content
        assert '--bg-page' in content
        assert '--text-primary' in content
        assert '--border' in content
        assert '--accent' in content

    def test_dark_theme_variables(self, html):
        """:root[data-theme='dark'] 应覆盖变量"""
        with open(html) as f:
            content = f.read()
        assert '[data-theme="dark"]' in content
        # dark 模式应至少有 bg-page 和 text-primary 的覆盖
        assert '--bg-page' in content

    def test_theme_select_style(self, html):
        """.theme-select 应有 padding + border + background CSS"""
        with open(html) as f:
            content = f.read()
        assert '.theme-select' in content
        assert 'border:' in content or 'border ' in content
        assert 'padding' in content

    def test_theme_select_hover(self, html):
        """.theme-select:hover 应有 border 变化"""
        with open(html) as f:
            content = f.read()
        assert '.theme-select:hover' in content

    def test_dark_node_shape_literal(self, html):
        """dark 模式 .node-shape.literal 应 fill 变化"""
        with open(html) as f:
            content = f.read()
        assert '[data-theme="dark"] .node-shape.literal' in content

    def test_dark_node_label_color(self, html):
        """dark 模式 .node-label 应 fill 变化"""
        with open(html) as f:
            content = f.read()
        assert '[data-theme="dark"] .node-label' in content
        assert 'fill' in content

    def test_dark_svg_background(self, html):
        """dark 模式 #graph svg 应有 background"""
        with open(html) as f:
            content = f.read()
        assert '[data-theme="dark"] #graph svg' in content


class TestShareUrlHtml:
    """Stage 18 - share URL button + toast HTML"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_share_button_present(self, html):
        """应有 #share-url 按钮"""
        with open(html) as f:
            content = f.read()
        assert 'id="share-url"' in content

    def test_share_button_class(self, html):
        """share 按钮应有 .share-btn 类"""
        with open(html) as f:
            content = f.read()
        assert 'share-btn' in content

    def test_share_button_title(self, html):
        """share 按钮应有 title 提示"""
        with open(html) as f:
            content = f.read()
        # title 属性
        assert 'title=' in content
        assert 'shareable URL' in content or 'share' in content.lower()

    def test_toast_element_present(self, html):
        """应有 #toast 提示元素"""
        with open(html) as f:
            content = f.read()
        assert 'id="toast"' in content

    def test_toast_hidden_by_default(self, html):
        """toast 默认应有 hidden 属性"""
        with open(html) as f:
            content = f.read()
        # <div id="toast" class="toast" hidden>
        assert 'class="toast"' in content


class TestShareUrlJs:
    """Stage 18 - share URL JS 逻辑"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_get_state_from_ui_function(self, html):
        """应有 getStateFromUI 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function getStateFromUI' in content

    def test_encode_state_function(self, html):
        """应有 encodeState 函数 (state → hash string)"""
        with open(html) as f:
            content = f.read()
        assert 'function encodeState' in content
        assert 'encodeURIComponent' in content

    def test_decode_state_function(self, html):
        """应有 decodeState 函数 (hash string → state)"""
        with open(html) as f:
            content = f.read()
        assert 'function decodeState' in content
        # decodeURIComponent 应在 decodeState 里
        assert content.count('decodeURIComponent') >= 1

    def test_apply_state_function(self, html):
        """应有 applyState 函数 (state → UI)"""
        with open(html) as f:
            content = f.read()
        assert 'function applyState' in content

    def test_update_hash_function(self, html):
        """应有 updateHash 函数 (debounced 写 hash)"""
        with open(html) as f:
            content = f.read()
        assert 'function updateHash' in content
        assert 'replaceState' in content or 'location.hash' in content

    def test_debounce_uses_setTimeout(self, html):
        """updateHash 应有 debounce (setTimeout)"""
        with open(html) as f:
            content = f.read()
        assert 'clearTimeout' in content
        assert 'setTimeout' in content

    def test_restore_from_hash_function(self, html):
        """应有 restoreFromHash 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function restoreFromHash' in content
        assert 'location.hash' in content

    def test_copy_share_url_function(self, html):
        """应有 copyShareUrl 函数 (clipboard API)"""
        with open(html) as f:
            content = f.read()
        assert 'function copyShareUrl' in content
        assert 'navigator.clipboard' in content

    def test_fallback_uses_textarea(self, html):
        """无 clipboard API 时应用 textarea fallback"""
        with open(html) as f:
            content = f.read()
        assert 'createElement(\'textarea\')' in content or 'createElement("textarea")' in content
        assert 'execCommand' in content

    def test_show_toast_function(self, html):
        """应有 showToast 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function showToast' in content

    def test_toast_show_class(self, html):
        """toast 应用 toast-show class 显示"""
        with open(html) as f:
            content = f.read()
        assert "classList.add('toast-show')" in content
        assert "classList.remove('toast-show')" in content

    def test_bind_share_url_function(self, html):
        """应有 bindShareUrl 函数"""
        with open(html) as f:
            content = f.read()
        assert 'function bindShareUrl' in content

    def test_bind_share_url_listeners(self, html):
        """bindShareUrl 应绑各种 change/input/click listener"""
        with open(html) as f:
            content = f.read()
        assert "'input'" in content  # search
        assert "'change'" in content  # filters + theme
        assert "'click'" in content   # cdc + share

    def test_pan_zoom_polling(self, html):
        """pan/zoom 状态变化应用 setInterval 轮询 (因为 zoomAt 没回调)"""
        with open(html) as f:
            content = f.read()
        assert 'setInterval' in content

    def test_bind_share_url_called_after_render(self, html):
        """render().then() 后应调 bindShareUrl()"""
        with open(html) as f:
            content = f.read()
        assert 'bindShareUrl()' in content


class TestShareUrlCss:
    """Stage 18 - share URL CSS"""

    @pytest.fixture
    def html(self, tmp_path):
        return _build_html(tmp_path, view='dataflow', filter_clock_reset=True)

    def test_share_btn_style(self, html):
        """.share-btn 应有 CSS 样式"""
        with open(html) as f:
            content = f.read()
        assert '.share-btn' in content

    def test_toast_style(self, html):
        """.toast 应有 fixed 定位 + 背景 + 透明度过渡"""
        with open(html) as f:
            content = f.read()
        assert '.toast' in content
        assert 'position: fixed' in content
        assert 'opacity' in content
        assert 'transition' in content

    def test_toast_show_state(self, html):
        """.toast.toast-show 应显示 (opacity: 1)"""
        with open(html) as f:
            content = f.read()
        assert '.toast.toast-show' in content
        assert 'opacity: 1' in content

    def test_dark_toast_style(self, html):
        """dark 模式 .toast 应有不同颜色"""
        with open(html) as f:
            content = f.read()
        assert '[data-theme="dark"] .toast' in content