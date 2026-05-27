#!/usr/bin/env python3
"""
navisv SVA 生成器金标准测试

场景:
  1. 从 constraint 生成 assert range
  2. 从 true_condition 生成 assert conditional path
  3. 从 FSM 生成 assert transition
  4. 从信号关系生成 assert implication
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')


@pytest.fixture(scope='module')
def enum_dg():
    dd = DesignDriver([os.path.join(SV_DIR, 'true_condition.sv')])
    dd.build()
    return dd.design_graph


@pytest.fixture(scope='module')
def basic_dd():
    dd = DesignDriver([os.path.join(SV_DIR, 'constraint_basic.sv')])
    dd.build()
    return dd


class TestSVAGeneration:
    """SVA 生成功能测试"""

    def test_generate_from_true_condition(self, enum_dg):
        """从 true_condition 生成 SVA"""
        from navisv.graph.sva_generator import SVAGenerator
        gen = SVAGenerator(enum_dg)
        sva = gen.generate()
        assert len(sva) > 0
        # 应包含 property 声明
        assert 'property' in sva
        assert 'assert' in sva

    def test_generate_contains_signals(self, enum_dg):
        """生成的 SVA 应包含相关信号名"""
        from navisv.graph.sva_generator import SVAGenerator
        gen = SVAGenerator(enum_dg)
        sva = gen.generate()
        # 应包含图中的信号
        assert 'out_if' in sva or 'out_case' in sva or 'out_nested' in sva

    def test_generate_has_disable_iff(self, enum_dg):
        """有 reset 的条件应生成 disable iff"""
        from navisv.graph.sva_generator import SVAGenerator
        gen = SVAGenerator(enum_dg)
        sva = gen.generate()
        assert 'disable iff' in sva

    def test_generate_from_constraint(self, basic_dd):
        """从 constraint 信息生成 SVA"""
        from navisv.graph.sva_generator import SVAGenerator
        gen = SVAGenerator(basic_dd.design_graph, basic_dd.constraint_graph)
        sva = gen.generate()
        assert len(sva) > 0

    def test_generate_valid_sva_syntax(self, enum_dg):
        """生成的 SVA 应为有效语法"""
        from navisv.graph.sva_generator import SVAGenerator
        gen = SVAGenerator(enum_dg)
        props = gen.generate_properties()
        # 每个 property 有 declaration + body + assertion
        for prop in props:
            assert prop['declaration'].strip().startswith('property')
            assert 'endproperty' in prop['assertion']
            assert 'assert property' in prop['assertion']

    def test_generate_multiple_properties(self, enum_dg):
        """应生成多个 property (对应多个边)"""
        from navisv.graph.sva_generator import SVAGenerator
        gen = SVAGenerator(enum_dg)
        props = gen.generate_properties()
        assert len(props) >= 3
