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