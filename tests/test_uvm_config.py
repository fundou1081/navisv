#!/usr/bin/env python3
"""
navisv UVM config_db + plusargs 金标准测试

场景:
  1. config_db::set 检测
  2. config_db::get 检测
  3. set → get 配置流匹配
  4. plusargs ($value$plusargs / $test$plusargs)
  5. plusargs 影响 config_db 设置
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
UVM_CP = os.path.join(SV_DIR, 'uvm_config_plusargs.sv')


@pytest.fixture(scope='module')
def dd():
    d = DesignDriver([UVM_CP])
    d.build()
    assert d.success, f"slang 编译失败: {d.diagnostics}"
    return d


@pytest.fixture(scope='module')
def uvm(dd):
    parser = dd.uvm_tb
    assert parser is not None, "UVMTestbenchParser 未构建"
    return parser


# ============================================================
# 1. config_db::set 检测
# ============================================================

class TestConfigDBSet:
    """config_db::set 调用检测"""

    def test_set_count(self, uvm):
        sets = uvm.get_config_db_sets()
        assert len(sets) >= 4

    def test_set_baud_rate(self, uvm):
        sets = uvm.get_config_db_sets()
        baud_sets = [s for s in sets if s['field'] == 'baud_rate']
        assert len(baud_sets) >= 1

    def test_set_has_context(self, uvm):
        sets = uvm.get_config_db_sets()
        for s in sets:
            assert 'context' in s
            assert 'inst_name' in s
            assert 'field' in s
            assert 'value' in s

    def test_set_from_env(self, uvm):
        sets = uvm.get_config_db_sets()
        env_sets = [s for s in sets if s['context'] == 'my_env']
        assert len(env_sets) >= 3

    def test_set_from_test(self, uvm):
        sets = uvm.get_config_db_sets()
        test_sets = [s for s in sets if s['context'] == 'my_test']
        assert len(test_sets) >= 1


# ============================================================
# 2. config_db::get 检测
# ============================================================

class TestConfigDBGet:
    """config_db::get 调用检测"""

    def test_get_count(self, uvm):
        gets = uvm.get_config_db_gets()
        assert len(gets) >= 3

    def test_get_in_driver(self, uvm):
        gets = uvm.get_config_db_gets()
        drv_gets = [g for g in gets if g['context'] == 'my_driver']
        assert len(drv_gets) >= 2

    def test_get_in_monitor(self, uvm):
        gets = uvm.get_config_db_gets()
        mon_gets = [g for g in gets if g['context'] == 'my_monitor']
        assert len(mon_gets) >= 1


# ============================================================
# 3. set → get 配置流
# ============================================================

class TestConfigFlow:
    """set → get 配置流匹配"""

    def test_baud_rate_flow(self, uvm):
        flows = uvm.get_config_flows()
        baud_flows = [f for f in flows if f['field'] == 'baud_rate']
        assert len(baud_flows) >= 1
        # set 和 get 应该匹配
        assert baud_flows[0]['setter'] is not None
        assert baud_flows[0]['getter'] is not None

    def test_flow_has_setter_getter(self, uvm):
        flows = uvm.get_config_flows()
        for f in flows:
            assert 'field' in f
            assert 'setter' in f
            assert 'getter' in f


# ============================================================
# 4. plusargs 检测
# ============================================================

class TestPlusargs:
    """$value$plusargs / $test$plusargs 检测"""

    def test_plusargs_count(self, uvm):
        plusargs = uvm.get_plusargs()
        assert len(plusargs) >= 3

    def test_value_plusargs(self, uvm):
        plusargs = uvm.get_plusargs()
        value_args = [p for p in plusargs if p['kind'] == 'value']
        assert len(value_args) >= 2

    def test_test_plusargs(self, uvm):
        plusargs = uvm.get_plusargs()
        test_args = [p for p in plusargs if p['kind'] == 'test']
        assert len(test_args) >= 1

    def test_plusargs_has_name(self, uvm):
        plusargs = uvm.get_plusargs()
        for p in plusargs:
            assert 'name' in p
            assert len(p['name']) > 0

    def test_plusargs_in_driver(self, uvm):
        plusargs = uvm.get_plusargs()
        drv_args = [p for p in plusargs if p['context'] == 'my_driver']
        assert len(drv_args) >= 2


# ============================================================
# 5. plusargs 影响 config_db
# ============================================================

class TestPlusargsImpact:
    """plusargs 影响 config_db 设置"""

    def test_plusargs_affects_config(self, uvm):
        """test 中 plusargs 影响 config_db::set"""
        impacts = uvm.get_plusargs_impacts()
        assert len(impacts) >= 1

    def test_plusargs_impact_has_field(self, uvm):
        impacts = uvm.get_plusargs_impacts()
        for imp in impacts:
            assert 'plusarg' in imp
            assert 'config_field' in imp
