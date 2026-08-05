"""
test_elk_exporter.py - Unit tests for ElkExporter (Stage 1)

测试范围:
- 基本构造 + from_networkx 入口
- to_elk_json() 输出结构 (children/edges/layoutOptions)
- 节点类型映射 (kind → color/port)
- 边类型映射 (timing/edge_kind → color)
- scope 过滤
- max_nodes 截断
- CDC 高亮
- self-loop 跳过
- properties 字段 (给 viewer 交互层用)

Stage 1 测试策略: 不依赖 slang binary,只用合成 networkx.MultiDiGraph。
设计驱动集成测试留到 Stage 5 (用 picorv32 / counter.sv 端到端验证)。
"""
import json
import os
from pathlib import Path

import networkx as nx
import pytest

from navisv.graph.elk_exporter import (
    ElkExporter,
    LAYOUT_OPTIONS,
    KIND_COLORS,
    TIMING_COLORS,
    EDGE_KIND_COLORS,
    elk_from_design_driver,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_counter_graph() -> nx.MultiDiGraph:
    """构造一个最小 counter 图 (dataflow 视图,符合 tests/fixtures/elk_counter.sv)

    节点:
        - counter.clk     (Port, input)
        - counter.rst_n   (Port, input)
        - counter.enable  (Port, input)
        - counter.count   (Port, output, [3:0])
        - counter.count_q (State/Reg, [3:0])

    边:
        - count_q -> count (sequential, AlwaysFF)
        - clk -> count_q   (sequential, AlwaysFF clock)
        - enable -> count_q (combinational, AlwaysComb)
    """
    g = nx.MultiDiGraph()

    # 节点
    g.add_node("counter.clk", kind="Port", name="clk", direction="input",
               bit_width=(0, 0), module="counter", timing="combinational",
               location={"file": "elk_counter.sv", "line": 3})
    g.add_node("counter.rst_n", kind="Port", name="rst_n", direction="input",
               bit_width=(0, 0), module="counter", timing="combinational",
               location={"file": "elk_counter.sv", "line": 4})
    g.add_node("counter.enable", kind="Port", name="enable", direction="input",
               bit_width=(0, 0), module="counter", timing="combinational",
               location={"file": "elk_counter.sv", "line": 5})
    g.add_node("counter.count", kind="Port", name="count", direction="output",
               bit_width=(3, 0), module="counter", timing="combinational",
               location={"file": "elk_counter.sv", "line": 6})
    g.add_node("counter.count_q", kind="State", name="count_q",
               bit_width=(3, 0), module="counter", timing="sequential",
               location={"file": "elk_counter.sv", "line": 11})

    # 边
    g.add_edge("counter.count_q", "counter.count", key=0,
               timing="sequential", edge_kind="AlwaysFF",
               condition="if (!rst_n)", condition_kind="if",
               condition_signals=["rst_n"], path_count=1)
    g.add_edge("counter.clk", "counter.count_q", key=0,
               timing="sequential", edge_kind="AlwaysFF", condition="",
               condition_kind="", condition_signals=[], path_count=1)
    g.add_edge("counter.enable", "counter.count_q", key=0,
               timing="combinational", edge_kind="AlwaysComb", condition="enable",
               condition_kind="if", condition_signals=["enable"], path_count=1)
    # 纯 sequential 边(无 edge_kind),用于测试 timing 颜色优先级
    g.add_edge("counter.rst_n", "counter.count_q", key=1,
               timing="sequential", edge_kind="", condition="if (!rst_n)",
               condition_kind="if", condition_signals=["rst_n"], path_count=1)

    return g


def make_nested_graph() -> nx.MultiDiGraph:
    """构造模块嵌套图 (modules 视图)

    top.u_alu 是 Instance,内部有 u_alu.op_a 等子节点。
    """
    g = nx.MultiDiGraph()

    g.add_node("top", kind="Module", name="top", location={"file": "top.sv", "line": 1})
    g.add_node("top.u_alu", kind="Instance", name="u_alu", module="alu",
               location={"file": "top.sv", "line": 5})
    g.add_node("top.u_alu.op_a", kind="Net", name="op_a", module="alu",
               location={"file": "alu.sv", "line": 10})
    g.add_node("top.u_alu.op_b", kind="Net", name="op_b", module="alu",
               location={"file": "alu.sv", "line": 11})
    g.add_node("top.u_alu.result", kind="State", name="result", module="alu",
               location={"file": "alu.sv", "line": 12})

    g.add_edge("top.u_alu.op_a", "top.u_alu.result", key=0,
               timing="combinational", edge_kind="Assign", condition="",
               condition_kind="", condition_signals=[])
    g.add_edge("top.u_alu.op_b", "top.u_alu.result", key=0,
               timing="combinational", edge_kind="Assign", condition="",
               condition_kind="", condition_signals=[])

    return g


@pytest.fixture
def counter_graph() -> nx.MultiDiGraph:
    return make_counter_graph()


@pytest.fixture
def nested_graph() -> nx.MultiDiGraph:
    return make_nested_graph()


@pytest.fixture
def exporter(counter_graph) -> ElkExporter:
    return ElkExporter(view="dataflow").from_networkx(counter_graph)


# ---------------------------------------------------------------------------
# Tests: 构造 + 基本结构
# ---------------------------------------------------------------------------

class TestElkExporterBasic:
    def test_construction_defaults(self):
        """默认参数: dataflow view, 500 max nodes, 无 CDC 高亮"""
        e = ElkExporter()
        assert e.view == "dataflow"
        assert e.cdc_highlight is False
        assert e.max_nodes == 500
        assert e.scope is None
        assert e.graph is None

    def test_from_networkx_loads_nodes(self, counter_graph):
        """from_networkx 应正确加载所有节点"""
        e = ElkExporter().from_networkx(counter_graph)
        assert e.graph is counter_graph
        assert len(e.node_data) == 5
        assert "counter.count_q" in e.node_data
        assert e.node_data["counter.count_q"]["kind"] == "State"

    def test_from_networkx_loads_edges(self, counter_graph):
        """from_networkx 应正确加载所有边"""
        e = ElkExporter().from_networkx(counter_graph)
        assert len(e.edge_data) == 4

    def test_to_elk_json_has_root_and_layout_options(self, exporter):
        """to_elk_json 输出含 root id 和 layoutOptions"""
        result = exporter.to_elk_json()
        assert result["id"] == "root"
        assert "layoutOptions" in result
        assert result["layoutOptions"]["elk.algorithm"] == "layered"
        assert result["layoutOptions"]["elk.direction"] == "DOWN"
        assert "children" in result
        assert "edges" in result

    def test_to_elk_json_children_count(self, exporter):
        """5 个节点 → 5 个 children"""
        result = exporter.to_elk_json()
        assert len(result["children"]) == 5

    def test_to_elk_json_edges_count(self, exporter):
        """4 条边 → 4 条 edges (无 self-loop)"""
        result = exporter.to_elk_json()
        assert len(result["edges"]) == 4

    def test_to_elk_json_no_self_loops(self):
        """self-loop 应被跳过"""
        g = nx.MultiDiGraph()
        g.add_node("a", kind="Net")
        g.add_node("b", kind="Net")
        g.add_edge("a", "b", key=0, timing="combinational")
        g.add_edge("a", "a", key=0, timing="combinational")  # self-loop

        e = ElkExporter().from_networkx(g)
        result = e.to_elk_json()
        assert len(result["edges"]) == 1
        assert result["edges"][0]["sources"] == ["a"]
        assert result["edges"][0]["targets"] == ["b"]


# ---------------------------------------------------------------------------
# Tests: 节点映射
# ---------------------------------------------------------------------------

class TestNodeMapping:
    def test_state_node_color(self, exporter):
        """State 类型节点颜色应为绿"""
        result = exporter.to_elk_json()
        count_q = next(c for c in result["children"] if c["id"] == "counter.count_q")
        assert count_q["properties"]["kind"] == "State"
        assert count_q["properties"]["color"] == KIND_COLORS["State"]

    def test_port_input_has_west_port(self, exporter):
        """input Port 应有 WEST 固定端口"""
        result = exporter.to_elk_json()
        clk = next(c for c in result["children"] if c["id"] == "counter.clk")
        assert "ports" in clk
        assert clk["ports"][0]["layoutOptions"]["portConstraints.fixedSide"] == "WEST"
        assert clk["properties"]["portSide"] == "WEST"

    def test_port_output_has_east_port(self, exporter):
        """output Port 应有 EAST 固定端口"""
        result = exporter.to_elk_json()
        count = next(c for c in result["children"] if c["id"] == "counter.count")
        assert "ports" in count
        assert count["ports"][0]["layoutOptions"]["portConstraints.fixedSide"] == "EAST"
        assert count["properties"]["portSide"] == "EAST"

    def test_state_node_has_no_port(self, exporter):
        """State/Reg 节点不应有 port (不是 Port kind)"""
        result = exporter.to_elk_json()
        count_q = next(c for c in result["children"] if c["id"] == "counter.count_q")
        assert "ports" not in count_q

    def test_label_includes_file_and_line(self, exporter):
        """节点 label 应包含文件名:行号"""
        result = exporter.to_elk_json()
        clk = next(c for c in result["children"] if c["id"] == "counter.clk")
        label_text = clk["labels"][0]["text"]
        assert "clk" in label_text
        assert "elk_counter.sv" in label_text
        assert ":3" in label_text

    def test_label_no_file_fallback(self):
        """无 location 时 label 只用 name"""
        g = nx.MultiDiGraph()
        g.add_node("orphan", kind="Net", name="orphan")

        result = ElkExporter().from_networkx(g).to_elk_json()
        assert result["children"][0]["labels"][0]["text"] == "orphan"


# ---------------------------------------------------------------------------
# Tests: 边映射
# ---------------------------------------------------------------------------

class TestEdgeMapping:
    def test_sequential_edge_blue(self, exporter):
        """sequential timing 边应使用蓝色 (无 edge_kind 时)"""
        result = exporter.to_elk_json()
        # counter.rst_n -> counter.count_q 是 sequential, edge_kind=''
        rst_edge = next(e for e in result["edges"] if "counter.rst_n" in e["sources"])
        assert rst_edge["properties"]["timing"] == "sequential"
        assert rst_edge["layoutOptions"]["elk.edge.color"] == TIMING_COLORS["sequential"]

    def test_combinational_edge_dark(self, exporter):
        """combinational timing 边应使用深色"""
        result = exporter.to_elk_json()
        en_edge = next(e for e in result["edges"] if "counter.enable" in e["sources"])
        assert en_edge["properties"]["timing"] == "combinational"

    def test_edge_kind_overrides_timing(self):
        """edge_kind 颜色优先于 timing"""
        g = nx.MultiDiGraph()
        g.add_node("a", kind="State")
        g.add_node("b", kind="State")
        # AlwaysFF + combinational 组合 - AlwaysFF 颜色应胜出
        g.add_edge("a", "b", key=0, timing="combinational", edge_kind="AlwaysFF")

        result = ElkExporter().from_networkx(g).to_elk_json()
        assert result["edges"][0]["layoutOptions"]["elk.edge.color"] == EDGE_KIND_COLORS["AlwaysFF"]

    def test_edge_label_contains_condition(self, exporter):
        """有 condition 的边 label 应包含条件信息"""
        result = exporter.to_elk_json()
        # counter.count_q -> counter.count 有 condition 'if (!rst_n)'
        cond_edge = next(e for e in result["edges"]
                         if e["sources"] == ["counter.count_q"])
        assert len(cond_edge["labels"]) == 1
        assert "rst_n" in cond_edge["labels"][0]["text"]

    def test_edge_label_fallback_to_timing(self):
        """无 condition 时 label 用 edge_kind 或 timing"""
        g = nx.MultiDiGraph()
        g.add_node("a", kind="State")
        g.add_node("b", kind="State")
        g.add_edge("a", "b", key=0, timing="sequential", edge_kind="AlwaysFF",
                   condition="", condition_kind="")

        result = ElkExporter().from_networkx(g).to_elk_json()
        # AlwaysFF 不是 "None", 应优先
        assert result["edges"][0]["labels"][0]["text"] == "AlwaysFF"

    def test_edge_properties_complete(self, exporter):
        """边 properties 应包含 timing/edge_kind/condition/cdc/color/path_count"""
        edge = exporter.to_elk_json()["edges"][0]
        props = edge["properties"]
        assert "timing" in props
        assert "edge_kind" in props
        assert "condition" in props
        assert "cdc" in props
        assert "color" in props
        assert "path_count" in props


# ---------------------------------------------------------------------------
# Tests: Scope 过滤
# ---------------------------------------------------------------------------

class TestScopeFiltering:
    def test_scope_none_returns_all(self, counter_graph):
        """scope=None 应返回所有节点"""
        e = ElkExporter(scope=None).from_networkx(counter_graph)
        assert len(e.to_elk_json()["children"]) == 5

    def test_scope_filters_by_prefix(self, counter_graph):
        """scope='counter' 应匹配所有 counter.* 节点"""
        e = ElkExporter(scope="counter").from_networkx(counter_graph)
        result = e.to_elk_json()
        ids = {c["id"] for c in result["children"]}
        assert ids == {"counter.clk", "counter.rst_n", "counter.enable",
                       "counter.count", "counter.count_q"}

    def test_scope_partial_match(self, nested_graph):
        """scope='top.u_alu' 应只包含 top.u_alu.* 节点"""
        e = ElkExporter(scope="top.u_alu").from_networkx(nested_graph)
        result = e.to_elk_json()
        ids = {c["id"] for c in result["children"]}
        assert "top.u_alu.op_a" in ids
        assert "top.u_alu.op_b" in ids
        assert "top.u_alu.result" in ids
        assert "top" not in ids  # 'top' 不在 'top.u_alu.*' 范围内

    def test_scope_edges_filtered(self, nested_graph):
        """scope 过滤后,边只保留 source/target 都在范围内的"""
        # 加一条跨 scope 的边
        nested_graph.add_edge("top.u_alu.op_a", "top", key=0, timing="combinational")

        e = ElkExporter(scope="top.u_alu").from_networkx(nested_graph)
        result = e.to_elk_json()
        # 'top' 不在 scope 中,所以跨 scope 边应被过滤
        for edge in result["edges"]:
            assert "top" not in edge["targets"]


# ---------------------------------------------------------------------------
# Tests: 节点截断
# ---------------------------------------------------------------------------

class TestNodeTruncation:
    def test_max_nodes_truncates(self):
        """max_nodes=3 应截断到 3 个节点"""
        g = nx.MultiDiGraph()
        for i in range(10):
            g.add_node(f"n{i}", kind="Net", name=f"n{i}")

        e = ElkExporter(max_nodes=3).from_networkx(g)
        result = e.to_elk_json()
        assert len(result["children"]) == 3

    def test_max_nodes_zero_means_no_limit(self):
        """max_nodes=0 应不截断"""
        g = nx.MultiDiGraph()
        for i in range(20):
            g.add_node(f"n{i}", kind="Net", name=f"n{i}")

        e = ElkExporter(max_nodes=0).from_networkx(g)
        result = e.to_elk_json()
        assert len(result["children"]) == 20

    def test_truncation_prints_warning(self, caplog):
        """截断应打印 WARNING (用 caplog 捕获)"""
        import logging
        g = nx.MultiDiGraph()
        for i in range(10):
            g.add_node(f"n{i}", kind="Net", name=f"n{i}")

        with caplog.at_level(logging.WARNING):
            ElkExporter(max_nodes=3).from_networkx(g).to_elk_json()
        assert any("truncated" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: CDC 高亮
# ---------------------------------------------------------------------------

class TestCDCHighlight:
    def test_cdc_edge_red_when_enabled(self):
        """cdc_highlight=True + edge in cdc_edge_set → 红色"""
        g = nx.MultiDiGraph()
        g.add_node("clk1", kind="Net")
        g.add_node("clk2", kind="Net")
        g.add_edge("clk1", "clk2", key=0, timing="sequential", edge_kind="Assign")

        e = ElkExporter(cdc_highlight=True).from_networkx(g)
        e.cdc_edge_set = {("clk1", "clk2")}

        result = e.to_elk_json()
        edge = result["edges"][0]
        assert edge["layoutOptions"]["elk.edge.color"] == EDGE_KIND_COLORS["CDC"]
        assert edge["properties"]["cdc"] is True

    def test_cdc_not_highlighted_when_disabled(self):
        """cdc_highlight=False + edge in cdc_edge_set → 不特殊着色"""
        g = nx.MultiDiGraph()
        g.add_node("a", kind="Net")
        g.add_node("b", kind="Net")
        g.add_edge("a", "b", key=0, timing="sequential", edge_kind="Assign")

        e = ElkExporter(cdc_highlight=False).from_networkx(g)
        e.cdc_edge_set = {("a", "b")}

        result = e.to_elk_json()
        edge = result["edges"][0]
        # 颜色应是 timing/edge_kind 默认,不是 CDC 红
        assert edge["layoutOptions"]["elk.edge.color"] != EDGE_KIND_COLORS["CDC"]


# ---------------------------------------------------------------------------
# Tests: 视图配置
# ---------------------------------------------------------------------------

class TestViewConfig:
    def test_dataflow_uses_layered(self):
        """dataflow 视图应使用 layered 算法 + DOWN 方向"""
        opts = LAYOUT_OPTIONS["dataflow"]
        assert opts["elk.algorithm"] == "layered"
        assert opts["elk.direction"] == "DOWN"

    def test_modules_uses_stress(self):
        """modules 视图应使用 stress (force) 算法"""
        opts = LAYOUT_OPTIONS["modules"]
        assert opts["elk.algorithm"] == "stress"

    def test_controlflow_uses_layered(self):
        """controlflow 视图应使用 layered 算法"""
        opts = LAYOUT_OPTIONS["controlflow"]
        assert opts["elk.algorithm"] == "layered"


# ---------------------------------------------------------------------------
# Tests: 序列化
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_export_json_file(self, exporter, tmp_path):
        """export_json 应写有效 JSON 文件"""
        out = tmp_path / "out.json"
        result = exporter.export_json(str(out))

        assert result == out
        assert out.exists()

        loaded = json.loads(out.read_text())
        assert loaded["id"] == "root"
        assert len(loaded["children"]) == 5

    def test_to_json_string(self, exporter):
        """to_json_string 应返回有效 JSON 字符串"""
        s = exporter.to_json_string()
        loaded = json.loads(s)
        assert loaded["id"] == "root"

    def test_export_creates_parent_dirs(self, exporter, tmp_path):
        """export_json 应自动创建父目录"""
        out = tmp_path / "nested" / "deep" / "out.json"
        exporter.export_json(str(out))
        assert out.exists()


# ---------------------------------------------------------------------------
# Tests: 错误处理
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_to_elk_json_without_graph_raises(self):
        """未加载图就调用 to_elk_json 应报错"""
        e = ElkExporter()
        with pytest.raises(ValueError, match="No graph loaded"):
            e.to_elk_json()

    def test_from_graph_builder_requires_build(self):
        """GraphBuilder 未 build() 就传给 from_graph_builder 应报错"""
        class FakeGB:
            graph = None
        with pytest.raises(ValueError, match="build"):
            ElkExporter().from_graph_builder(FakeGB())

    def test_from_design_graph_requires_graph(self):
        """DesignGraph.graph 为 None 应报错"""
        class FakeDG:
            graph = None
        with pytest.raises(ValueError, match="DesignGraph.graph is None"):
            ElkExporter().from_design_graph(FakeDG())


# ---------------------------------------------------------------------------
# Tests: export_html (Stage 2)
# ---------------------------------------------------------------------------

class TestExportHTML:
    def test_export_html_creates_file(self, exporter, tmp_path):
        """export_html 应生成有效 HTML 文件"""
        out = tmp_path / "out.html"
        result = exporter.export_html(str(out))

        assert result == out
        assert out.exists()

    def test_export_html_contains_bundled_elkjs(self, exporter, tmp_path):
        """HTML 应含 bundled elkjs.js 代码 (不依赖 CDN)"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        html = out.read_text()

        # elk.bundled.js 包含 ELK 全局对象
        assert "ELK" in html
        # 不应引用外部 CDN
        assert "unpkg.com" not in html
        assert "cdn.jsdelivr" not in html

    def test_export_html_contains_embedded_json(self, exporter, tmp_path):
        """HTML 应含嵌入的 GRAPH_DATA JSON"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        html = out.read_text()

        assert "const GRAPH_DATA = " in html
        # JSON 应含节点 (counter.clk 等)
        assert "counter.clk" in html
        assert "counter.count_q" in html

    def test_export_html_contains_viewer_js(self, exporter, tmp_path):
        """HTML 应含 viewer 交互 JS"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        html = out.read_text()

        # viewer.js 中的关键函数/标记
        assert "setupClickHandlers" in html
        assert "ELK.layout" in html
        assert "data-node-id" in html
        assert "data-edge-id" in html

    def test_export_html_contains_css(self, exporter, tmp_path):
        """HTML 应含嵌入 CSS"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        html = out.read_text()

        assert "elk_viewer" in html or "#header" in html
        assert ".node-rect" in html

    def test_export_html_title_default(self, exporter, tmp_path):
        """默认 title 应包含 view 和节点/边数"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        html = out.read_text()

        assert "<title>" in html
        assert "dataflow" in html
        # 默认 title: 'navisv: dataflow (5 nodes / 4 edges)'
        assert "5 nodes" in html
        assert "4 edges" in html

    def test_export_html_title_custom(self, exporter, tmp_path):
        """自定义 title 应覆盖默认"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out), title="My Custom Title")
        html = out.read_text()

        assert "My Custom Title" in html

    def test_export_html_size_includes_bundled_elkjs(self, exporter, tmp_path):
        """HTML 文件大小应包含 bundled elkjs (≥1.5MB)"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        size = out.stat().st_size
        # bundled elkjs ≈ 1.6MB + viewer.js + viewer.css + JSON
        assert size > 1_500_000, f"HTML too small: {size} bytes"

    def test_export_html_is_single_file(self, exporter, tmp_path):
        """HTML 应是单文件,不创建额外依赖"""
        out = tmp_path / "out.html"
        before = set(tmp_path.iterdir())
        exporter.export_html(str(out))
        after = set(tmp_path.iterdir())

        # 只多了一个 .html 文件,没有 .js / .css 副文件
        new_files = after - before
        assert new_files == {out}, f"Unexpected files: {new_files}"

    def test_export_html_meta_includes_view_and_counts(self, exporter, tmp_path):
        """meta 应包含 view 名和节点/边数"""
        out = tmp_path / "out.html"
        exporter.export_html(str(out))
        html = out.read_text()

        # meta 区域
        assert "view: dataflow" in html
        assert "5 nodes" in html
        assert "4 edges" in html


# ---------------------------------------------------------------------------
# Tests: Stage 2.5 - Operator / Literal 节点映射
# ---------------------------------------------------------------------------

def _make_graph_with_ops() -> nx.MultiDiGraph:
    """构造一个含 Operator / Literal / State / Port 的图"""
    g = nx.MultiDiGraph()
    # Ports
    g.add_node("m.clk", kind="Port", name="clk", direction="input",
               location={"file": "x.sv", "line": 1})
    g.add_node("m.rst_n", kind="Port", name="rst_n", direction="input",
               location={"file": "x.sv", "line": 2})
    g.add_node("m.q", kind="State", name="q",
               location={"file": "x.sv", "line": 3})
    # Operators (菱形)
    g.add_node("op_1", kind="Operator", name="if", timing="combinational",
               location={"file": "x.sv", "line": 4},
               attributes={"operator_kind": "Conditional", "netlist_id": 1})
    g.add_node("op_2", kind="Operator", name="<=", timing="combinational",
               location={"file": "x.sv", "line": 5},
               attributes={"operator_kind": "Assignment", "netlist_id": 2})
    # Literal (虚线小矩形)
    g.add_node("const_3", kind="Literal", name="8'h00", timing="combinational",
               location={"file": "x.sv", "line": 6},
               attributes={"value": "8'h00", "netlist_id": 3})

    # Edges (rst -> if -> <= -> q; const -> <=)
    g.add_edge("m.rst_n", "op_1", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_1", "op_2", key=0, timing="combinational", edge_kind="None")
    g.add_edge("const_3", "op_2", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_2", "m.q", key=0, timing="sequential", edge_kind="AlwaysFF")
    g.add_edge("m.clk", "m.q", key=0, timing="sequential", edge_kind="PosEdge")
    return g


@pytest.fixture
def ops_graph() -> nx.MultiDiGraph:
    return _make_graph_with_ops()


@pytest.fixture
def ops_exporter(ops_graph) -> ElkExporter:
    return ElkExporter(view="dataflow").from_networkx(ops_graph)


class TestOperatorNode:
    """Stage 2.5 - Operator 节点映射"""

    def test_operator_uses_orange_color(self, ops_exporter):
        """Operator 应使用橙色 (#e67e22)"""
        result = ops_exporter.to_elk_json()
        op = next(c for c in result["children"] if c["id"] == "op_1")
        assert op["properties"]["kind"] == "Operator"
        assert op["properties"]["color"] == "#e67e22"

    def test_operator_uses_smaller_size(self, ops_exporter):
        """Operator 应使用 90x50 (小于默认 160x50)"""
        result = ops_exporter.to_elk_json()
        op = next(c for c in result["children"] if c["id"] == "op_1")
        assert op["width"] == 90
        assert op["height"] == 50

    def test_operator_has_diamond_shape_hint(self, ops_exporter):
        """Operator 应有 shape='diamond' 提示, 告诉 viewer 画菱形"""
        result = ops_exporter.to_elk_json()
        op = next(c for c in result["children"] if c["id"] == "op_1")
        assert op.get("shape") == "diamond"

    def test_operator_kind_in_properties(self, ops_exporter):
        """Operator 的 operator_kind (Conditional/Assignment/Case/Merge) 应嵌入 properties"""
        result = ops_exporter.to_elk_json()
        op_conditional = next(c for c in result["children"] if c["id"] == "op_1")
        op_assignment = next(c for c in result["children"] if c["id"] == "op_2")
        assert op_conditional["properties"].get("operator_kind") == "Conditional"
        assert op_assignment["properties"].get("operator_kind") == "Assignment"


class TestLiteralNode:
    """Stage 2.5 - Literal 节点映射"""

    def test_literal_uses_gray_color(self, ops_exporter):
        """Literal 应使用灰色 (#7f8c8d)"""
        result = ops_exporter.to_elk_json()
        lit = next(c for c in result["children"] if c["id"] == "const_3")
        assert lit["properties"]["kind"] == "Literal"
        assert lit["properties"]["color"] == "#7f8c8d"

    def test_literal_uses_smaller_size(self, ops_exporter):
        """Literal 应使用 80x36 (最小)"""
        result = ops_exporter.to_elk_json()
        lit = next(c for c in result["children"] if c["id"] == "const_3")
        assert lit["width"] == 80
        assert lit["height"] == 36

    def test_literal_value_in_label_and_props(self, ops_exporter):
        """Literal 的 value 应同时在 label 和 properties 中"""
        result = ops_exporter.to_elk_json()
        lit = next(c for c in result["children"] if c["id"] == "const_3")
        # label 含 value + 文件:行号
        assert "8'h00" in lit["labels"][0]["text"]
        assert lit["properties"].get("value") == "8'h00"


class TestKindColorsExtended:
    """Stage 2.5 - KIND_COLORS 扩展"""

    def test_operator_color_in_kind_colors(self):
        from navisv.graph.elk_exporter import KIND_COLORS
        assert "Operator" in KIND_COLORS
        assert KIND_COLORS["Operator"] == "#e67e22"

    def test_literal_color_in_kind_colors(self):
        from navisv.graph.elk_exporter import KIND_COLORS
        assert "Literal" in KIND_COLORS
        assert KIND_COLORS["Literal"] == "#7f8c8d"

    def test_kind_sizes_for_operator_literal(self):
        from navisv.graph.elk_exporter import KIND_SIZES
        assert KIND_SIZES["Operator"] == (90, 50)
        assert KIND_SIZES["Literal"] == (80, 36)


class TestViewerRendersOperatorAndLiteral:
    """Stage 2.5 - HTML viewer 包含 Operator/Literal 渲染逻辑"""

    def test_viewer_js_handles_diamond_polygon(self):
        """viewer.js 应含 polygon 渲染逻辑 (diamond shape)"""
        viewer_path = Path(__file__).parent.parent / "navisv" / "data" / "elk_viewer.js"
        content = viewer_path.read_text()
        assert "polygon" in content, "viewer.js should render <polygon>"
        assert "operator" in content.lower(), "viewer.js should have operator handling"
        assert "isOperator" in content or "kind === 'Operator'" in content

    def test_viewer_js_handles_literal_dashed_rect(self):
        """viewer.js 应含 Literal 虚线矩形渲染"""
        viewer_path = Path(__file__).parent.parent / "navisv" / "data" / "elk_viewer.js"
        content = viewer_path.read_text()
        assert "stroke-dasharray" in content, "viewer.js should use dashed border for Literal"

    def test_viewer_legend_includes_operator_and_literal(self):
        """viewer.js 的 legend 应包含 Operator 和 Literal"""
        viewer_path = Path(__file__).parent.parent / "navisv" / "data" / "elk_viewer.js"
        content = viewer_path.read_text()
        assert "Operator" in content, "legend should mention Operator"
        assert "Literal" in content, "legend should mention Literal"

    def test_viewer_css_has_operator_styles(self):
        """viewer.css 应含 Operator/Literal 样式"""
        css_path = Path(__file__).parent.parent / "navisv" / "data" / "elk_viewer.css"
        content = css_path.read_text()
        assert ".node-shape.operator" in content
        assert ".node-shape.literal" in content


class TestGraphBuilderPreserveOperators:
    """Stage 2.5 - GraphBuilder.preserve_operators 选项"""

    def test_default_preserve_operators_is_false(self):
        """默认 preserve_operators=False (保持向后兼容)"""
        from navisv.graph.graph_builder import GraphBuilder
        import inspect
        sig = inspect.signature(GraphBuilder.__init__)
        param = sig.parameters.get("preserve_operators")
        assert param is not None, "GraphBuilder 应该支持 preserve_operators 参数"
        assert param.default is False

    def test_add_intermediate_nodes_method_exists(self):
        """GraphBuilder 应有 _add_intermediate_nodes() 方法"""
        from navisv.graph.graph_builder import GraphBuilder
        assert hasattr(GraphBuilder, "_add_intermediate_nodes")

    def test_add_intermediate_nodes_skipped_when_disabled(self, monkeypatch):
        """preserve_operators=False 时 _add_intermediate_nodes 直接返回"""
        from navisv.graph.graph_builder import GraphBuilder

        gb = GraphBuilder.__new__(GraphBuilder)
        gb.preserve_operators = False
        gb.graph = nx.MultiDiGraph()
        gb.netlist = type("N", (), {"nodes": []})()
        gb._node_attrs = {}
        # 应直接 return, 不创建任何节点
        gb._add_intermediate_nodes()
        assert len(gb.graph.nodes) == 0


# ---------------------------------------------------------------------------
# Tests: Stage 2.8 - PORT_IN/OUT layerConstraint FIRST/LAST
# ---------------------------------------------------------------------------

def _make_graph_with_directional_ports() -> nx.MultiDiGraph:
    """Graph with explicit input/output ports."""
    g = nx.MultiDiGraph()
    g.add_node("m.clk", kind="Port", name="clk", direction="In",
               location={"file": "x.sv", "line": 1})
    g.add_node("m.enable", kind="Port", name="enable", direction="In",
               location={"file": "x.sv", "line": 2})
    g.add_node("m.q", kind="State", name="q",
               location={"file": "x.sv", "line": 3})
    g.add_node("m.data_out", kind="Port", name="data_out", direction="Out",
               location={"file": "x.sv", "line": 4})
    g.add_node("op_1", kind="Operator", name="+", timing="combinational",
               location={"file": "x.sv", "line": 5},
               attributes={"operator_kind": "BinaryOp"})
    g.add_edge("m.clk", "m.q", key=0, timing="sequential", edge_kind="PosEdge")
    g.add_edge("m.enable", "op_1", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_1", "m.data_out", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_1", "m.q", key=0, timing="combinational", edge_kind="AlwaysFF")
    return g


@pytest.fixture
def port_graph() -> nx.MultiDiGraph:
    return _make_graph_with_directional_ports()


@pytest.fixture
def port_exporter(port_graph) -> ElkExporter:
    return ElkExporter(view="dataflow").from_networkx(port_graph)


class TestPortLayerConstraint:
    """Stage 2.8 - Port layerConstraint FIRST (input) / LAST (output)"""

    def test_input_port_has_first_constraint(self, port_exporter):
        """direction='In' 节点 → elk.layered.layering.layerConstraint = 'FIRST'"""
        result = port_exporter.to_elk_json()
        clk = next(c for c in result["children"] if c["id"] == "m.clk")
        assert clk["layoutOptions"]["elk.layered.layering.layerConstraint"] == "FIRST"

    def test_output_port_has_last_constraint(self, port_exporter):
        """direction='Out' 节点 → layerConstraint = 'LAST'"""
        result = port_exporter.to_elk_json()
        data_out = next(c for c in result["children"] if c["id"] == "m.data_out")
        assert data_out["layoutOptions"]["elk.layered.layering.layerConstraint"] == "LAST"

    def test_input_direction_variants(self, port_exporter):
        """direction in {'input', 'inout', 'In'} 都识别为 FIRST"""
        # 重设一个 fixture 用 lowercase direction
        g = nx.MultiDiGraph()
        g.add_node("p1", kind="Port", name="p1", direction="input")
        g.add_node("p2", kind="Port", name="p2", direction="inout")
        g.add_node("p3", kind="Port", name="p3", direction="In")
        exporter = ElkExporter(view="dataflow").from_networkx(g)
        result = exporter.to_elk_json()
        for nid in ("p1", "p2", "p3"):
            n = next(c for c in result["children"] if c["id"] == nid)
            assert n["layoutOptions"]["elk.layered.layering.layerConstraint"] == "FIRST", \
                f"{nid} (direction={n['properties']['direction']}) should be FIRST"

    def test_state_node_has_no_layer_constraint(self, port_exporter):
        """State/Operator/Literal 不应有 layerConstraint (保持普通节点)"""
        result = port_exporter.to_elk_json()
        q = next(c for c in result["children"] if c["id"] == "m.q")
        lo = q.get("layoutOptions", {})
        assert "elk.layered.layering.layerConstraint" not in lo

    def test_port_also_has_west_east_side(self, port_exporter):
        """Port 应同时有 portConstraints.fixedSide WEST/EAST"""
        result = port_exporter.to_elk_json()
        clk = next(c for c in result["children"] if c["id"] == "m.clk")
        clk_port = clk["ports"][0]
        assert clk_port["layoutOptions"]["portConstraints.fixedSide"] == "WEST"

        data_out = next(c for c in result["children"] if c["id"] == "m.data_out")
        out_port = data_out["ports"][0]
        assert out_port["layoutOptions"]["portConstraints.fixedSide"] == "EAST"


class TestStage28EndToEnd:
    """Stage 2.8 - end-to-end on counter.sv, verify ports are pinned"""

    @pytest.fixture(scope="class")
    def counter_elk_json(self):
        import glob, os, shutil
        from navisv.drivers.design_driver import DesignDriver
        from navisv.parsers.ast_parser import ASTParser
        from navisv.parsers.netlist_parser import NetlistParser
        from navisv.graph.graph_builder import GraphBuilder
        from navisv.graph.elk_exporter import ElkExporter

        out = '/tmp/navisv_stage28_test'
        if os.path.exists(out):
            shutil.rmtree(out)
        counter_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'fixtures', 'elk_counter.sv')
        )
        DesignDriver([counter_path], output_dir=out, cache=False).build()
        ast = ASTParser(glob.glob(f'{out}/*ast*.json')[0]).parse()
        nl = NetlistParser(glob.glob(f'{out}/*netlist*.json')[0]).parse()
        gb = GraphBuilder(
            ast, nl, ast_json_path=f'{out}/ast.json',
            source_files=[counter_path], preserve_operators=True,
        )
        gb.build()
        exporter = ElkExporter(view="dataflow").from_networkx(gb.graph)
        return exporter.to_elk_json()

    def test_all_counter_inputs_pinned_first(self, counter_elk_json):
        """counter.sv 三个 input port (clk/rst_n/enable) 都应是 FIRST"""
        inputs = ['counter.clk', 'counter.rst_n', 'counter.enable']
        for nid in inputs:
            n = next(c for c in counter_elk_json["children"] if c["id"] == nid)
            assert n["layoutOptions"]["elk.layered.layering.layerConstraint"] == "FIRST", \
                f"{nid} should be FIRST (it's an input port)"

    def test_count_state_not_pinned(self, counter_elk_json):
        """count 是 State (output port 但 navisv 当 State), 不应被当作 output port 钉住"""
        # count 在 counter.sv 是 output port (logic[3:0]), 但 navisv classify 成 State
        # 所以它的 layerConstraint 应不存在 (跟其他 State 一样)
        n = next(c for c in counter_elk_json["children"] if c["id"] == "counter.count")
        lo = n.get("layoutOptions", {})
        assert "elk.layered.layering.layerConstraint" not in lo, \
            "State 不应有 layerConstraint (让 ELK 自由放置)"

    @pytest.mark.skipif(
        not os.path.exists('/Users/fundou/my_dv_proj/navisv/navisv/data/elk.bundled.js'),
        reason='ELK bundled not present'
    )
    def test_counter_inputs_at_leftmost_x(self, counter_elk_json):
        """跑真 ELK layout, 三个 input port 应在最小 x 位置 (FIRST 层)"""
        from navisv.tools.elk_layout import run_elk_layout
        positioned = run_elk_layout(counter_elk_json, direction='RIGHT')

        # 收集 input port 的 x 位置 + 找最小 x
        input_xs = []
        for c in positioned['children']:
            if c['id'] in ['counter.clk', 'counter.rst_n', 'counter.enable']:
                input_xs.append(c['x'])

        all_xs = [c['x'] for c in positioned['children']]

        # input port x 应在最小 3 个 x 之内 (FIRST 强制在最左层)
        all_xs_sorted = sorted(all_xs)
        for x in input_xs:
            # 每个 input x 应接近最小 x (容许 100px 范围, 因为 FIRST 层可能有 padding)
            assert x - all_xs_sorted[0] < 200, \
                f"Input port x={x} not near leftmost x={all_xs_sorted[0]}"


# ---------------------------------------------------------------------------
# Tests: Stage 2.9 - Edge filter (CLOCK/RESET/self-loop/loop-back)
# ---------------------------------------------------------------------------


def _make_counter_like_graph() -> nx.MultiDiGraph:
    """合成一个 counter.sv 风格的图: clk/rst_n/enable + dataflow operators + count State"""
    g = nx.MultiDiGraph()
    # 输入端口
    g.add_node("m.clk", kind="Port", name="clk", direction="In",
               location={"file": "x.sv", "line": 1})
    g.add_node("m.rst_n", kind="Port", name="rst_n", direction="In",
               location={"file": "x.sv", "line": 2})
    g.add_node("m.enable", kind="Port", name="enable", direction="In",
               location={"file": "x.sv", "line": 3})
    # 数据流算子
    g.add_node("op_not", kind="Operator", name="!", timing="combinational",
               location={"file": "x.sv", "line": 10},
               attributes={"operator_kind": "UnaryNot"})
    g.add_node("op_4b0", kind="Literal", name="4'b0", timing="combinational",
               location={"file": "x.sv", "line": 11},
               attributes={"value": "4'b0"})
    g.add_node("op_le", kind="Operator", name="<=", timing="combinational",
               location={"file": "x.sv", "line": 12},
               attributes={"operator_kind": "BinaryLE"})
    g.add_node("op_if", kind="Operator", name="if", timing="combinational",
               location={"file": "x.sv", "line": 13},
               attributes={"operator_kind": "If"})
    g.add_node("op_add", kind="Operator", name="+", timing="combinational",
               location={"file": "x.sv", "line": 14},
               attributes={"operator_kind": "BinaryOp"})
    g.add_node("op_merge1", kind="Operator", name="merge", timing="combinational",
               location={"file": "x.sv", "line": 15},
               attributes={"operator_kind": "Merge"})
    g.add_node("op_merge2", kind="Operator", name="merge", timing="combinational",
               location={"file": "x.sv", "line": 16},
               attributes={"operator_kind": "Merge"})
    # 状态 (FF output)
    g.add_node("m.count", kind="State", name="count",
               location={"file": "x.sv", "line": 5})

    # 数据流 (combinational, 保留)
    g.add_edge("m.rst_n", "op_not", key=0, timing="combinational", edge_kind="None")
    g.add_edge("m.enable", "op_if", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_4b0", "op_le", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_not", "op_le", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_le", "op_merge1", key=0, timing="combinational", edge_kind="None")
    g.add_edge("m.count", "op_add", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_add", "op_merge2", key=0, timing="combinational", edge_kind="None")
    g.add_edge("op_if", "op_merge2", key=0, timing="combinational", edge_kind="None")

    # 时序触发 (CLOCK/RESET/loop, 过滤)
    g.add_edge("m.clk", "m.count", key=0, timing="sequential_input", edge_kind="PosEdge")
    g.add_edge("m.rst_n", "m.count", key=0, timing="sequential_input", edge_kind="NegEdge")
    g.add_edge("m.count", "m.count", key=0, timing="sequential_output", edge_kind="None")  # self-loop
    g.add_edge("op_merge1", "m.count", key=0, timing="sequential_input", edge_kind="None")
    g.add_edge("op_merge2", "m.count", key=0, timing="sequential_input", edge_kind="None")

    return g


@pytest.fixture
def counter_like_graph() -> nx.MultiDiGraph:
    return _make_counter_like_graph()


class TestStage29EdgeFilter:
    """Stage 2.9 - 借鉴 sv_query DATAFLOW_VIZ_SPEC.md §4: 过滤 CLOCK/RESET/self-loop"""

    def test_default_keeps_all_edges(self, counter_like_graph):
        """filter_clock_reset=False (默认) 时保留所有非 self-loop 边, 跟旧版兼容"""
        exporter = ElkExporter(view="dataflow").from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        # 13 总边 - 1 self-loop = 12 (跟 Stage 2.7 行为一致)
        assert len(result["edges"]) == 12
        # 默认 filtered_edges == 0 (只有 self_loops_removed > 0)
        assert result["properties"]["filtered_edges"] == 0
        assert result["properties"]["self_loops_removed"] == 1

    def test_filter_clock_reset_removes_clock_edge(self, counter_like_graph):
        """filter_clock_reset=True 时 clk → count (PosEdge) 被过滤"""
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        # ELK edge 格式: sources/targets 是数组
        for e in result["edges"]:
            assert "m.clk" not in e["sources"], "CLOCK edge should be filtered"

    def test_filter_clock_reset_removes_reset_edge(self, counter_like_graph):
        """rst_n → count (NegEdge) 被过滤, 但 rst_n → op_not 保留"""
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        rst_n_edges = [e for e in result["edges"] if "m.rst_n" in e["sources"]]
        assert len(rst_n_edges) == 1
        assert "op_not" in rst_n_edges[0]["targets"]

    def test_filter_clock_reset_removes_self_loop(self, counter_like_graph):
        """self-loop 永远被过滤"""
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        # 所有边的 src 和 tgt 必不同
        for e in result["edges"]:
            assert e["sources"][0] != e["targets"][0], "self-loop should be filtered"

    def test_filter_keeps_combinational_edges(self, counter_like_graph):
        """所有 combinational 边应保留"""
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        comb_edges = [
            ("m.rst_n", "op_not"),
            ("m.enable", "op_if"),
            ("op_4b0", "op_le"),
            ("op_not", "op_le"),
            ("op_le", "op_merge1"),
            ("m.count", "op_add"),
            ("op_add", "op_merge2"),
            ("op_if", "op_merge2"),
        ]
        actual_pairs = {(e["sources"][0], e["targets"][0]) for e in result["edges"]}
        for src, tgt in comb_edges:
            assert (src, tgt) in actual_pairs, f"Missing combinational edge {src} → {tgt}"

    def test_orphan_nodes_removed_after_filter(self, counter_like_graph):
        """过滤后没有任何边的节点应被删除 (sv_query 要求 0 orphan)"""
        counter_like_graph.add_node("m.isolated", kind="Port", name="isolated",
                                     direction="In",
                                     location={"file": "x.sv", "line": 99})
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        node_ids = {c["id"] for c in result["children"]}
        assert "m.isolated" not in node_ids, "孤立节点应被移除"
        # m.clk 也是 orphan (只有被过滤的边)
        assert "m.clk" not in node_ids
        assert result["properties"]["orphan_nodes_removed"] >= 2

    def test_filter_metadata(self, counter_like_graph):
        """properties.filtered_edges + self_loops_removed 应分别记录"""
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_networkx(counter_like_graph)
        result = exporter.to_elk_json()
        # 4 条 sequential_input (clk, rst_n, merge1→count, merge2→count)
        assert result["properties"]["filtered_edges"] == 4
        assert result["properties"]["self_loops_removed"] == 1


class TestStage29EndToEnd:
    """Stage 2.9 - counter.sv end-to-end with filter"""

    @pytest.fixture(scope="class")
    def counter_filtered_json(self):
        """Build counter.sv and export with filter_clock_reset=True"""
        import glob, os, shutil
        from navisv.drivers.design_driver import DesignDriver
        from navisv.parsers.ast_parser import ASTParser
        from navisv.parsers.netlist_parser import NetlistParser
        from navisv.graph.graph_builder import GraphBuilder
        from navisv.graph.elk_exporter import ElkExporter

        out = '/tmp/navisv_stage29_test'
        if os.path.exists(out):
            shutil.rmtree(out)
        counter_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'fixtures', 'elk_counter.sv')
        )
        DesignDriver([counter_path], output_dir=out, cache=False).build()
        ast = ASTParser(glob.glob(f'{out}/*ast*.json')[0]).parse()
        nl = NetlistParser(glob.glob(f'{out}/*netlist*.json')[0]).parse()
        gb = GraphBuilder(
            ast, nl, ast_json_path=f'{out}/ast.json',
            source_files=[counter_path], preserve_operators=True,
        )
        gb.build()
        exporter = ElkExporter(
            view="dataflow", filter_clock_reset=True
        ).from_graph_builder(gb)
        return exporter.to_elk_json()

    def test_no_clock_edge_in_output(self, counter_filtered_json):
        """counter.clk → counter.count 不应在 output 中"""
        for e in counter_filtered_json["edges"]:
            assert "counter.clk" not in e["sources"], \
                "CLOCK edge should be filtered"

    def test_no_self_loop(self, counter_filtered_json):
        """0 个 self-loop"""
        for e in counter_filtered_json["edges"]:
            assert e["sources"][0] != e["targets"][0]

    def test_filtered_count_in_metadata(self, counter_filtered_json):
        """filtered_edges > 0 (counter.sv 至少有 clk + rst_n + self-loop)"""
        assert counter_filtered_json["properties"]["filtered_edges"] >= 2

    def test_dataflow_still_connected(self, counter_filtered_json):
        """过滤后图仍连通 — 关键 dataflow 边都保留"""
        pairs = {(e["sources"][0], e["targets"][0]) for e in counter_filtered_json["edges"]}
        # 关键数据流: rst_n 应流向 combinational op
        rst_targets = {tgt for src, tgt in pairs if src == "counter.rst_n"}
        assert rst_targets, "rst_n 应至少有 1 个 combinational 目标"
        # enable 应流向 combinational op
        enable_targets = {tgt for src, tgt in pairs if src == "counter.enable"}
        assert enable_targets, "enable 应至少有 1 个 combinational 目标"


# ---------------------------------------------------------------------------
# Tests: Stage 2.6 - AST op symbol extraction
# ---------------------------------------------------------------------------

class TestASTOpSymbolMap:
    """Stage 2.6 - AST op enum -> human-readable symbol"""

    def test_binary_op_addition(self):
        from navisv.graph.graph_builder import AST_OP_TO_SYMBOL
        assert AST_OP_TO_SYMBOL['Add'] == '+'

    def test_binary_op_subtraction(self):
        from navisv.graph.graph_builder import AST_OP_TO_SYMBOL
        assert AST_OP_TO_SYMBOL['Subtract'] == '-'

    def test_logical_not(self):
        from navisv.graph.graph_builder import AST_OP_TO_SYMBOL
        assert AST_OP_TO_SYMBOL['LogicalNot'] == '!'

    def test_logical_and(self):
        from navisv.graph.graph_builder import AST_OP_TO_SYMBOL
        assert AST_OP_TO_SYMBOL['LogicalAnd'] == '&&'

    def test_equality(self):
        from navisv.graph.graph_builder import AST_OP_TO_SYMBOL
        assert AST_OP_TO_SYMBOL['Equality'] == '=='

    def test_assignment_kind_in_map_as_fallback(self):
        """Assignment kind 在表里作为 fallback '<=' (实际用 isNonBlocking 区分 = / <=)"""
        from navisv.graph.graph_builder import AST_OP_TO_SYMBOL
        # Assignment 在表里, 但 _ast_match_to_info 会优先看 isNonBlocking
        assert AST_OP_TO_SYMBOL.get('Assignment') == '<='


class TestGraphBuilderStage26Counter:
    """Stage 2.6 - end-to-end on counter.sv: operator labels show specific symbols"""

    @pytest.fixture(scope="class")
    def gb(self):
        """端到端跑 counter.sv, 拿 GraphBuilder"""
        from navisv.drivers.design_driver import DesignDriver
        import glob, shutil, os
        out = '/tmp/navisv_stage26_test'
        if os.path.exists(out):
            shutil.rmtree(out)
        DesignDriver(['tests/fixtures/elk_counter.sv'], output_dir=out, cache=False).build()

        from navisv.parsers.ast_parser import ASTParser
        from navisv.parsers.netlist_parser import NetlistParser
        ast = ASTParser(glob.glob(f'{out}/*ast*.json')[0]).parse()
        nl = NetlistParser(glob.glob(f'{out}/*netlist*.json')[0]).parse()

        from navisv.graph.graph_builder import GraphBuilder
        gb = GraphBuilder(ast, nl, ast_json_path=f'{out}/ast.json',
                          source_files=['tests/fixtures/elk_counter.sv'],
                          preserve_operators=True)
        gb.build()
        return gb

    def test_unary_not_in_conditional(self, gb):
        """`if (!rst_n)` -> Conditional 节点 label 应为 '!'"""
        op_5 = gb._node_attrs.get('op_5')
        assert op_5 is not None
        assert op_5.kind == 'Operator'
        assert op_5.name == '!'
        assert op_5.attributes['ast_kind'] == 'Conditional'
        assert op_5.attributes['ast_op'] == 'LogicalNot'

    def test_plain_conditional_falls_back_to_if(self, gb):
        """`if (enable)` -> Conditional 节点 label 应为 'if' (无具体 operator)"""
        op_8 = gb._node_attrs.get('op_8')
        assert op_8 is not None
        assert op_8.kind == 'Operator'
        assert op_8.name == 'if'
        assert op_8.attributes['ast_kind'] == 'Conditional'

    def test_assignment_with_binary_op_rhs(self, gb):
        """`count <= count + 1` -> Assignment 节点 label 应为 '+'"""
        op_9 = gb._node_attrs.get('op_9')
        assert op_9 is not None
        assert op_9.kind == 'Operator'
        assert op_9.name == '+'
        assert op_9.attributes['ast_kind'] == 'Assignment'
        assert op_9.attributes['ast_op'] == 'Add'

    def test_assignment_with_literal_rhs_falls_back_to_le(self, gb):
        """`count <= 0` -> Assignment 节点 label 应为 '<=' (无具体 RHS operator)"""
        op_6 = gb._node_attrs.get('op_6')
        assert op_6 is not None
        assert op_6.kind == 'Operator'
        assert op_6.name == '<='
        assert op_6.attributes['ast_kind'] == 'Assignment'

    def test_constant_uses_ast_value(self, gb):
        """Constant 节点 label 用 AST Conversion.value"""
        const = gb._node_attrs.get('const_7')
        assert const is not None
        assert const.kind == 'Literal'
        assert const.name == "4'b0"
        assert const.attributes['ast_kind'] == 'Conversion'

    def test_merge_nodes_fall_back(self, gb):
        """Merge 节点无 AST 对应, fallback 到 'merge'"""
        op_10 = gb._node_attrs.get('op_10')
        op_11 = gb._node_attrs.get('op_11')
        assert op_10.kind == 'Operator'
        assert op_10.name == 'merge'
        assert op_11.kind == 'Operator'
        assert op_11.name == 'merge'


class TestFindFirstOperatorHelper:
    """Stage 2.6 - _find_first_operator 严格限制 walk 范围"""

    def test_conditional_does_not_walk_into_iftrue_iffalse(self):
        """Conditional 只看 conditions[*].expr, 不进 ifTrue/ifFalse"""
        # Mock AST node 类似: Conditional(conditions=[{expr: UnaryOp}],
        #                                 ifTrue=Assignment(BinaryOp))
        from navisv.graph.graph_builder import GraphBuilder

        cond = {
            'kind': 'Conditional',
            'conditions': [{'expr': {'kind': 'UnaryOp', 'op': 'LogicalNot'}}],
            'ifTrue': {
                'kind': 'ExpressionStatement',
                'expr': {
                    'kind': 'Assignment',
                    'right': {'kind': 'BinaryOp', 'op': 'Add'},
                },
            },
        }
        # Mock object 类似 ASTNode
        class FakeNode:
            def __init__(self, d):
                self.attributes = d
                self.kind = d.get('kind', '')
                self.children = []

        gb = GraphBuilder.__new__(GraphBuilder)
        op = gb._find_first_operator(FakeNode(cond))
        assert op == 'LogicalNot', f"Expected 'LogicalNot', got {op!r}"

    def test_assignment_only_walks_right_not_left(self):
        """Assignment 只看 right, 不看 left"""
        from navisv.graph.graph_builder import GraphBuilder

        assign = {
            'kind': 'Assignment',
            'left': {'kind': 'BinaryOp', 'op': 'Add'},  # 不应被 walk
            'right': {'kind': 'Conversion', 'operand': {'kind': 'IntegerLiteral', 'value': "4'b0"}},
            'isNonBlocking': True,
        }
        class FakeNode:
            def __init__(self, d):
                self.attributes = d
                self.kind = d.get('kind', '')
                self.children = []

        gb = GraphBuilder.__new__(GraphBuilder)
        op = gb._find_first_operator(FakeNode(assign))
        # left 是 BinaryOp 但不应被 walk, Conversion 又没 op, 结果是 None
        assert op is None, f"Expected None (no op in right), got {op!r}"

    def test_assignment_with_binary_op_right(self):
        """Assignment.right 是 BinaryOp -> 返回 op"""
        from navisv.graph.graph_builder import GraphBuilder

        assign = {
            'kind': 'Assignment',
            'left': {'kind': 'NamedValue'},
            'right': {'kind': 'BinaryOp', 'op': 'Add'},
            'isNonBlocking': True,
        }
        class FakeNode:
            def __init__(self, d):
                self.attributes = d
                self.kind = d.get('kind', '')
                self.children = []

        gb = GraphBuilder.__new__(GraphBuilder)
        op = gb._find_first_operator(FakeNode(assign))
        assert op == 'Add'