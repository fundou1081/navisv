#!/usr/bin/env python3
"""
navisv SVA Parser 金标准测试

从语义 AST 直接提取 SVA，验证:
  1. assert/assume/cover/restrict 类型
  2. 时钟和边沿
  3. disable iff 条件
  4. 信号引用
  5. property/sequence 定义
  6. 复杂表达式
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

TEST_SVA = '/tmp/test_sva.sv'


@pytest.fixture(scope='module')
def sva():
    dd = DesignDriver([TEST_SVA])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    parser = dd.sva
    assert parser is not None, "SVAParser 未构建"
    return parser


# ============================================================
# 1. assertion 类型
# ============================================================

class TestAssertionTypes:
    """assert/assume/cover/restrict"""

    def test_assert_count(self, sva):
        asserts = [a for a in sva.assertions if a.kind == 'Assert']
        assert len(asserts) >= 3

    def test_assume_exists(self, sva):
        assumes = [a for a in sva.assertions if a.kind == 'Assume']
        assert len(assumes) >= 1

    def test_cover_exists(self, sva):
        covers = [a for a in sva.assertions if a.kind == 'CoverProperty']
        assert len(covers) >= 1

    def test_restrict_exists(self, sva):
        restricts = [a for a in sva.assertions if a.kind == 'Restrict']
        assert len(restricts) >= 1

    def test_total_count(self, sva):
        assert len(sva.assertions) >= 5


# ============================================================
# 2. 时钟和边沿
# ============================================================

class TestClocking:
    """时钟信号和边沿"""

    def test_clock_name(self, sva):
        a = sva.assertions[0]
        assert a.clock == 'clk'

    def test_edge_type(self, sva):
        a = sva.assertions[0]
        assert a.edge == 'PosEdge'


# ============================================================
# 3. disable iff
# ============================================================

class TestDisableIff:
    """disable iff 条件"""

    def test_disable_exists(self, sva):
        disabled = [a for a in sva.assertions if a.disable_condition]
        assert len(disabled) >= 1

    def test_disable_signal(self, sva):
        disabled = [a for a in sva.assertions if a.disable_condition]
        assert any('rst_n' in a.disable_condition for a in disabled)


# ============================================================
# 4. 信号引用
# ============================================================

class TestSignals:
    """涉及的信号"""

    def test_assertion_signals(self, sva):
        a = sva.assertions[0]
        assert len(a.signals) >= 1

    def test_signals_not_empty(self, sva):
        for a in sva.assertions:
            if a.kind != 'Restrict':
                assert len(a.signals) >= 1, f'{a.kind} assertion has no signals'


# ============================================================
# 5. property/sequence 定义
# ============================================================

class TestDefinitions:
    """property 和 sequence 定义"""

    def test_property_count(self, sva):
        assert len(sva.properties) >= 2

    def test_property_names(self, sva):
        names = set(sva.properties.keys())
        assert 'p_data_stable' in names
        assert 'p_state_check' in names

    def test_sequence_count(self, sva):
        assert len(sva.sequences) >= 2

    def test_sequence_names(self, sva):
        names = set(sva.sequences.keys())
        assert 's_valid_ready' in names
        assert 's_req_ack' in names


# ============================================================
# 6. 表达式
# ============================================================

class TestExpressions:
    """表达式解析"""

    def test_implication_operator(self, sva):
        """assert 使用 |-> 操作符"""
        asserts = [a for a in sva.assertions if a.kind == 'Assert']
        assert any('|->' in a.expression or '|=>' in a.expression for a in asserts)

    def test_expression_not_empty(self, sva):
        for a in sva.assertions:
            if a.kind != 'CoverProperty':
                assert len(a.expression) > 0, f'{a.kind} assertion has empty expression'
