#!/usr/bin/env python3
"""
navisv bin-constraint 一致性检查 金标准测试

场景:
  1. 死 bin: bin 范围被 constraint 排除
  2. 遗漏 bin: constraint 允许但无 bin 覆盖
  3. missing illegal bin: constraint 禁止但没标 illegal
  4. 完全一致: bin 和 constraint 匹配
  5. 条件约束下的检查
  6. 部分重叠: bin 范围与 constraint 部分重叠
  7. 多 coverpoint 独立检查
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
CG_CHECK = os.path.join(SV_DIR, 'covergroup_constraint_check.sv')


@pytest.fixture(scope='module')
def check_data():
    """构建 covergroup + constraint 数据"""
    dd = DesignDriver([CG_CHECK])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    return {
        'cg': dd.covergroups,
        'constraint': dd.constraint_graph,
    }


@pytest.fixture(scope='module')
def analyzer(check_data):
    """构建一致性分析器"""
    from navisv.graph.covergroup_analyzer import CovergroupAnalyzer
    # 重新获取以确保类型正确
    dd = DesignDriver([CG_CHECK])
    dd.build()
    return dd


# ============================================================
# 1. 死 bin 检测
# ============================================================

class TestDeadBin:
    """dead_bin_cls: constraint [0:100], bin high=[101:200], max=255"""

    def test_dead_bin_detected(self, analyzer):
        cg = analyzer.covergroups
        cons = analyzer.constraint_graph
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.dead_bin_cls.data',
            'dead_bin_cls.cg', 'cp_data',
        )
        dead = [r for r in result if r['type'] == 'dead_bin']
        names = {r['bin_name'] for r in dead}
        assert 'high' in names
        assert 'max' in names

    def test_dead_bin_reason(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.dead_bin_cls.data',
            'dead_bin_cls.cg', 'cp_data',
        )
        dead = next(r for r in result if r['bin_name'] == 'high')
        assert dead['type'] == 'dead_bin'
        assert 'constraint' in dead['reason'].lower() or '排除' in dead['reason']

    def test_valid_bins_not_reported(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.dead_bin_cls.data',
            'dead_bin_cls.cg', 'cp_data',
        )
        dead_names = {r['bin_name'] for r in result if r['type'] == 'dead_bin'}
        assert 'low' not in dead_names
        assert 'mid' not in dead_names


# ============================================================
# 2. 遗漏 bin 检测
# ============================================================

class TestMissingBin:
    """missing_bin_cls: constraint [0:255], bins only 0 and 1"""

    def test_missing_bin_detected(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.missing_bin_cls.addr',
            'missing_bin_cls.cg', 'cp_addr',
        )
        missing = [r for r in result if r['type'] == 'missing_bin']
        assert len(missing) > 0

    def test_missing_bin_range(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.missing_bin_cls.addr',
            'missing_bin_cls.cg', 'cp_addr',
        )
        missing = [r for r in result if r['type'] == 'missing_bin']
        # 2-254 没有 bin 覆盖
        assert any(r.get('uncovered_range') for r in missing)


# ============================================================
# 3. missing illegal bin
# ============================================================

class TestMissingIllegal:
    """missing_illegal_cls: constraint 禁止 101-199, 但没标 illegal"""

    def test_missing_illegal_detected(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.missing_illegal_cls.val',
            'missing_illegal_cls.cg', 'cp_val',
        )
        missing = [r for r in result if r['type'] == 'missing_illegal_bin']
        assert len(missing) > 0

    def test_missing_illegal_range(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.missing_illegal_cls.val',
            'missing_illegal_cls.cg', 'cp_val',
        )
        missing = next(r for r in result if r['type'] == 'missing_illegal_bin')
        # 101-199 应该标 illegal
        assert missing.get('forbidden_range') or missing.get('range')


# ============================================================
# 4. 完全一致
# ============================================================

class TestConsistent:
    """consistent_cls: bin 和 constraint 完全匹配"""

    def test_no_issues(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.consistent_cls.data',
            'consistent_cls.cg', 'cp_data',
        )
        # 不应该有 dead_bin 或 missing_illegal_bin
        issues = [r for r in result if r['type'] in ('dead_bin', 'missing_illegal_bin')]
        assert len(issues) == 0


# ============================================================
# 5. 条件约束
# ============================================================

class TestConditionalConstraint:
    """conditional_cls: if/else 约束"""

    def test_conditional_check(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.conditional_cls.data',
            'conditional_cls.cg', 'cp_data',
        )
        # 条件约束下, lo 和 hi 都应该是有效的
        dead = [r for r in result if r['type'] == 'dead_bin']
        assert len(dead) == 0


# ============================================================
# 6. 部分重叠
# ============================================================

class TestPartialOverlap:
    """partial_overlap_cls: constraint [30:200], bins 部分超出"""

    def test_partial_dead_detected(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.partial_overlap_cls.data',
            'partial_overlap_cls.cg', 'cp_data',
        )
        dead = [r for r in result if r['type'] == 'dead_bin']
        # low [0:50] 的 0-29 部分和 high [151:255] 的 201-255 部分是死 bin
        assert len(dead) >= 1


# ============================================================
# 7. 多 coverpoint
# ============================================================

class TestMultiCoverpoint:
    """multi_cp_cls: a 和 b 各自有约束"""

    def test_cp_a_ok(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.multi_cp_cls.a',
            'multi_cp_cls.cg', 'cp_a',
        )
        dead = [r for r in result if r['type'] == 'dead_bin']
        assert len(dead) == 0

    def test_cp_b_dead(self, analyzer):
        cg = analyzer.covergroups
        result = cg.check_bin_constraint_consistency(
            'cg_check_pkg.multi_cp_cls.b',
            'multi_cp_cls.cg', 'cp_b',
        )
        dead = [r for r in result if r['type'] == 'dead_bin']
        # b.high [9:15] 是死 bin (constraint 只允许 0-8)
        assert len(dead) >= 1
        names = {r['bin_name'] for r in dead}
        assert 'high' in names
