#!/usr/bin/env python3
"""
navisv true_condition 金标准测试
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
TRUE_COND = os.path.join(SV_DIR, 'true_condition.sv')


@pytest.fixture(scope='module')
def dg():
    dd = DesignDriver([TRUE_COND])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    return dd.design_graph


def get_in_edges(dg, node):
    """获取指向 node 的所有边, 返回 [(src, dst, data), ...]"""
    return list(dg.graph.in_edges(node, data=True))


class TestSimpleIfElse:
    """out_if: rst → sel==00 → sel==01 → else"""

    def test_reset_edge(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_if')
        rst_edges = [e for e in edges if 'rst_n' in e[2].get('true_condition', '')]
        assert len(rst_edges) >= 1

    def test_sel_00_edge(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_if')
        sel_edges = [e for e in edges if 'sel' in e[2].get('true_condition', '')]
        assert len(sel_edges) >= 1

    def test_has_multiple_conditions(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_if')
        tcs = [e[2].get('true_condition', '') for e in edges if e[2].get('true_condition')]
        assert len(tcs) >= 2


class TestCaseStmt:
    """out_case: case(sel) 00→a, 01→b, 10→c, default→0"""

    def test_case_has_conditions(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_case')
        tcs = [e[2].get('true_condition', '') for e in edges if e[2].get('true_condition')]
        assert len(tcs) >= 2

    def test_case_references_sel(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_case')
        assert any('sel' in e[2].get('true_condition', '') for e in edges)


class TestTernary:
    """out_tern = cond ? a : b"""

    def test_ternary_has_conditions(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_tern')
        tcs = [e[2].get('true_condition', '') for e in edges if e[2].get('true_condition')]
        assert len(tcs) >= 1


class TestNestedIf:
    """out_nested: if(sel[1]) if(sel[0]) a else b else c"""

    def test_nested_has_multiple_edges(self, dg):
        edges = get_in_edges(dg, 'true_condition.out_nested')
        assert len(edges) >= 3


class TestEdgeAttribute:
    """true_condition 字段应该存在于边上"""

    def test_has_true_condition(self, dg):
        edges_with_tc = []
        for src, dst, data in dg.graph.edges(data=True):
            if data.get('true_condition'):
                edges_with_tc.append((src, dst, data['true_condition']))
        assert len(edges_with_tc) > 0

    def test_true_condition_not_empty(self, dg):
        for src, dst, data in dg.graph.edges(data=True):
            tc = data.get('true_condition', '')
            if tc:
                assert len(tc.strip()) > 0
