# tests/test_apps.py - App Layer 测试
# navisv 架构 v0.8

"""
App Layer 单元测试：
- SignalProfileApp
- ImpactAnalysisApp（待实现）
- FindSignalsApp（待实现）
- RelationshipApp（待实现）

运行：pytest tests/test_apps.py -v
"""

import pytest
import sys
import os

# ---- slang-netlist 路径（必须在导入 navisv 前设置）----
SLANG_PATH = '/Users/fundou/my_dv_proj/slang-netlist/install'
sys.path.insert(0, SLANG_PATH)
sys.path.insert(0, os.path.join(SLANG_PATH, 'lib'))

from navisv.graph.design_graph import DesignGraph
from navisv.query.service import QueryService
from navisv.apps.signal_profile import SignalProfileApp


# ---- Fixtures ----

@pytest.fixture
def simple_graph(simple_design_path):
    return DesignGraph([simple_design_path])


@pytest.fixture
def query_service(simple_graph):
    return QueryService(simple_graph)


@pytest.fixture
def signal_profile_app(query_service):
    return SignalProfileApp(query_service)


@pytest.fixture
def i2c_graph():
    """OpenTitan I2C 模块"""
    I2C_PATH = '/Users/fundou/my_dv_proj/opentitan/hw/ip/i2c/rtl/i2c_core.sv'
    if not os.path.exists(I2C_PATH):
        pytest.skip(f"I2C 源码不存在: {I2C_PATH}")
    return DesignGraph([I2C_PATH])


@pytest.fixture
def i2c_query(i2c_graph):
    return QueryService(i2c_graph)


# ---- SignalProfileApp ----

class TestSignalProfileApp:
    """SignalProfileApp 测试"""

    def test_run_returns_appresponse(self, signal_profile_app, simple_graph):
        """run() 返回 AppResponse"""
        nodes = simple_graph.nodes()
        if not nodes:
            pytest.skip("图中无节点")
        response = signal_profile_app.run(nodes[0])
        assert hasattr(response, 'structured'), "AppResponse 缺少 structured"
        assert hasattr(response, 'summary'), "AppResponse 缺少 summary"
        assert hasattr(response, 'confidence'), "AppResponse 缺少 confidence"

    def test_summary_is_non_empty_string(self, signal_profile_app, simple_graph):
        """summary 是非空字符串"""
        nodes = simple_graph.nodes()
        if not nodes:
            pytest.skip("图中无节点")
        response = signal_profile_app.run(nodes[0])
        assert isinstance(response.summary, str)
        assert len(response.summary) > 0, "summary 不应为空"

    def test_confidence_is_valid(self, signal_profile_app, simple_graph):
        """confidence 为 high/medium/uncertain 之一"""
        nodes = simple_graph.nodes()
        if not nodes:
            pytest.skip("图中无节点")
        response = signal_profile_app.run(nodes[0])
        assert response.confidence in ('high', 'medium', 'uncertain'), \
            f"confidence 异常: {response.confidence}"

    def test_structured_contains_drivers_and_loads(self, signal_profile_app, simple_graph):
        """structured 包含 drivers 和 loads"""
        nodes = simple_graph.nodes()
        if not nodes:
            pytest.skip("图中无节点")
        response = signal_profile_app.run(nodes[0])
        assert 'drivers' in response.structured, "缺少 drivers 字段"
        assert 'loads' in response.structured, "缺少 loads 字段"
        assert isinstance(response.structured['drivers'], list)
        assert isinstance(response.structured['loads'], list)

    def test_summary_contains_signal_name(self, signal_profile_app, simple_graph):
        """summary 应提及信号名"""
        nodes = simple_graph.nodes()
        if not nodes:
            pytest.skip("图中无节点")
        node_id = nodes[0]
        name = simple_graph.node_attr(node_id).get('name', '')
        if name:  # 如果能获取到 name
            response = signal_profile_app.run(node_id)
            # summary 中应包含信号名或节点 ID
            assert name in response.summary or node_id in response.summary, \
                f"summary 未提及信号名: {response.summary}"

    def test_run_with_non_existent_signal(self, signal_profile_app):
        """不存在的信号返回 uncertain"""
        response = signal_profile_app.run("non_existent_signal_xyz")
        assert response.confidence == 'uncertain', \
            f"不存在信号应返回 uncertain，实际: {response.confidence}"

    def test_i2c_scl_i_profile(self, i2c_graph):
        """I2C scl_i 信号 profile"""
        query = QueryService(i2c_graph)
        app = SignalProfileApp(query)
        signals = query.search_signals(name_pattern="scl_i")
        if not signals:
            pytest.skip("I2C 无 scl_i 信号")
        response = app.run(signals[0])
        assert response.summary
        assert response.confidence in ('high', 'medium', 'uncertain')

    def test_i2c_reg2hw_profile(self, i2c_graph):
        """I2C reg2hw profile"""
        query = QueryService(i2c_graph)
        app = SignalProfileApp(query)
        signals = query.search_signals(name_pattern="reg2hw")
        if not signals:
            pytest.skip("I2C 无 reg2hw 信号")
        response = app.run(signals[0])
        assert response.summary
        assert 'drivers' in response.structured


# ---- ImpactAnalysisApp（占位，待实现）----

class TestImpactAnalysisApp:
    """ImpactAnalysisApp 测试（占位）"""

    def test_impact_analysis_app_exists(self):
        """ImpactAnalysisApp 应已实现"""
        try:
            from navisv.apps.impact_analysis import ImpactAnalysisApp
        except ImportError:
            pytest.fail("ImpactAnalysisApp 未实现，请参考 IMPLEMENTATION_PLAN.md")

    def test_impact_analysis_run(self, i2c_query):
        """ImpactAnalysisApp 应可运行"""
        try:
            from navisv.apps.impact_analysis import ImpactAnalysisApp
        except ImportError:
            pytest.skip("ImpactAnalysisApp 未实现")
        app = ImpactAnalysisApp(i2c_query)
        signals = i2c_query.search_signals(name_pattern="clk")
        if not signals:
            pytest.skip("I2C 无 clk 信号")
        response = app.run(signals[0])
        assert hasattr(response, 'structured')
        assert hasattr(response, 'summary')


# ---- FindSignalsApp（占位，待实现）----

class TestFindSignalsApp:
    """FindSignalsApp 测试（占位）"""

    def test_find_signals_app_exists(self):
        """FindSignalsApp 应已实现"""
        try:
            from navisv.apps.find_signals import FindSignalsApp
        except ImportError:
            pytest.fail("FindSignalsApp 未实现，请参考 IMPLEMENTATION_PLAN.md")

    def test_find_signals_run(self, i2c_query):
        """FindSignalsApp 应可运行"""
        try:
            from navisv.apps.find_signals import FindSignalsApp
        except ImportError:
            pytest.skip("FindSignalsApp 未实现")
        app = FindSignalsApp(i2c_query)
        response = app.run("clk")
        assert hasattr(response, 'structured')
        assert hasattr(response, 'summary')


# ---- RelationshipApp（占位，待实现）----

class TestRelationshipApp:
    """RelationshipApp 测试（占位）"""

    def test_relationship_app_exists(self):
        """RelationshipApp 应已实现"""
        try:
            from navisv.apps.relationship import RelationshipApp
        except ImportError:
            pytest.fail("RelationshipApp 未实现，请参考 IMPLEMENTATION_PLAN.md")

    def test_relationship_run(self, i2c_query):
        """RelationshipApp 应可运行"""
        try:
            from navisv.apps.relationship import RelationshipApp
        except ImportError:
            pytest.skip("RelationshipApp 未实现")
        app = RelationshipApp(i2c_query)
        signals = i2c_query.search_signals(name_pattern="clk")
        if len(signals) < 2:
            pytest.skip("信号数不足")
        response = app.run(signals[0], signals[1])
        assert hasattr(response, 'structured')
        assert hasattr(response, 'summary')