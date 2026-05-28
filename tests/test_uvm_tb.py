#!/usr/bin/env python3
"""
navisv UVM Testbench 静态结构提取 金标准测试

场景:
  1. 组件层级 (env → agent → driver/monitor, env → scoreboard)
  2. Sequence 继承关系
  3. 组件继承关系 (extends uvm_driver 等)
  4. build_phase 中的创建关系
  5. Sequence → Driver 关联
  6. Phase 方法识别
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
UVM_TB = os.path.join(SV_DIR, 'uvm_testbench.sv')


@pytest.fixture(scope='module')
def dd():
    d = DesignDriver([UVM_TB])
    d.build()
    assert d.success, f"slang 编译失败: {d.diagnostics}"
    return d


@pytest.fixture(scope='module')
def uvm(dd):
    parser = dd.uvm_tb
    assert parser is not None, "UVMTestbenchParser 未构建"
    return parser


# ============================================================
# 1. 组件发现
# ============================================================

class TestComponentDiscovery:
    """发现 UVM 组件"""

    def test_env_found(self, uvm):
        comps = uvm.get_components()
        names = {c['name'] for c in comps}
        assert 'my_env' in names

    def test_agent_found(self, uvm):
        comps = uvm.get_components()
        names = {c['name'] for c in comps}
        assert 'my_agent' in names

    def test_driver_found(self, uvm):
        comps = uvm.get_components()
        names = {c['name'] for c in comps}
        assert 'my_driver' in names

    def test_monitor_found(self, uvm):
        comps = uvm.get_components()
        names = {c['name'] for c in comps}
        assert 'my_monitor' in names

    def test_scoreboard_found(self, uvm):
        comps = uvm.get_components()
        names = {c['name'] for c in comps}
        assert 'my_scoreboard' in names

    def test_component_type(self, uvm):
        comps = uvm.get_components()
        env = next(c for c in comps if c['name'] == 'my_env')
        assert env['uvm_type'] == 'uvm_env'

    def test_driver_type(self, uvm):
        comps = uvm.get_components()
        drv = next(c for c in comps if c['name'] == 'my_driver')
        assert drv['uvm_type'] == 'uvm_driver'


# ============================================================
# 2. 组件层级 (build_phase 中的 new/create)
# ============================================================

class TestComponentHierarchy:
    """组件层级关系"""

    def test_env_contains_agent(self, uvm):
        children = uvm.get_children('uvm_tb_pkg.my_env')
        names = {c['child'] for c in children}
        assert 'my_agent' in names

    def test_env_contains_scoreboard(self, uvm):
        children = uvm.get_children('uvm_tb_pkg.my_env')
        names = {c['child'] for c in children}
        assert 'my_scoreboard' in names

    def test_agent_contains_driver(self, uvm):
        children = uvm.get_children('uvm_tb_pkg.my_agent')
        names = {c['child'] for c in children}
        assert 'my_driver' in names

    def test_agent_contains_monitor(self, uvm):
        children = uvm.get_children('uvm_tb_pkg.my_agent')
        names = {c['child'] for c in children}
        assert 'my_monitor' in names

    def test_full_hierarchy(self, uvm):
        """env → agent → driver/monitor, env → scoreboard"""
        tree = uvm.get_hierarchy('uvm_tb_pkg.my_env')
        assert 'my_agent' in tree
        assert 'my_scoreboard' in tree
        # agent 的子组件
        agent_children = tree.get('my_agent', [])
        assert 'my_driver' in agent_children
        assert 'my_monitor' in agent_children


# ============================================================
# 3. Sequence 继承关系
# ============================================================

class TestSequenceInheritance:
    """Sequence 继承"""

    def test_sequences_found(self, uvm):
        seqs = uvm.get_sequences()
        names = {s['name'] for s in seqs}
        assert 'base_sequence' in names
        assert 'write_sequence' in names
        assert 'read_sequence' in names

    def test_write_extends_base(self, uvm):
        seqs = uvm.get_sequences()
        wr = next(s for s in seqs if s['name'] == 'write_sequence')
        assert 'base_sequence' in wr['base_class']

    def test_read_extends_base(self, uvm):
        seqs = uvm.get_sequences()
        rd = next(s for s in seqs if s['name'] == 'read_sequence')
        assert 'base_sequence' in rd['base_class']

    def test_base_extends_uvm_sequence(self, uvm):
        seqs = uvm.get_sequences()
        base = next(s for s in seqs if s['name'] == 'base_sequence')
        assert 'uvm_sequence' in base['base_class']

    def test_sequence_item_found(self, uvm):
        items = uvm.get_sequence_items()
        names = {i['name'] for i in items}
        assert 'my_transaction' in names


# ============================================================
# 4. 组件继承关系
# ============================================================

class TestComponentInheritance:
    """组件继承"""

    def test_env_extends_uvm_env(self, uvm):
        comps = uvm.get_components()
        env = next(c for c in comps if c['name'] == 'my_env')
        assert 'uvm_env' in env['base_class']

    def test_driver_extends_uvm_driver(self, uvm):
        comps = uvm.get_components()
        drv = next(c for c in comps if c['name'] == 'my_driver')
        assert 'uvm_driver' in drv['base_class']

    def test_agent_extends_uvm_agent(self, uvm):
        comps = uvm.get_components()
        agent = next(c for c in comps if c['name'] == 'my_agent')
        assert 'uvm_agent' in agent['base_class']


# ============================================================
# 5. Phase 方法
# ============================================================

class TestPhaseMethods:
    """Phase 方法识别"""

    def test_build_phase(self, uvm):
        phases = uvm.get_phases('uvm_tb_pkg.my_env')
        names = {p['name'] for p in phases}
        assert 'build_phase' in names

    def test_run_phase(self, uvm):
        phases = uvm.get_phases('uvm_tb_pkg.my_driver')
        names = {p['name'] for p in phases}
        assert 'run_phase' in names

    def test_test_has_run_phase(self, uvm):
        phases = uvm.get_phases('uvm_tb_pkg.my_test')
        names = {p['name'] for p in phases}
        assert 'run_phase' in names


# ============================================================
# 6. Sequence → Driver 关联
# ============================================================

class TestSequenceDriver:
    """Sequence 使用"""

    def test_test_uses_sequences(self, uvm):
        """my_test.run_phase 中创建了 write_sequence 和 read_sequence"""
        usages = uvm.get_sequence_usages()
        test_usages = [u for u in usages if u['user'] == 'my_test']
        names = {u['sequence'] for u in test_usages}
        assert 'write_sequence' in names
        assert 'read_sequence' in names


# ============================================================
# 7. Graph 导出
# ============================================================

class TestGraphExport:
    """图导出"""

    def test_to_dot(self, uvm):
        dot = uvm.to_dot()
        assert 'digraph' in dot
        assert 'my_env' in dot
        assert 'my_driver' in dot

    def test_to_mermaid(self, uvm):
        mermaid = uvm.to_mermaid()
        assert 'graph' in mermaid
        assert 'my_env' in mermaid
