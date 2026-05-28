#!/usr/bin/env python3
"""
navisv CallGraph 金标准测试

场景:
  1. 基础函数调用链
  2. 继承 + super 调用
  3. fork/join (join / join_any / join_none)
  4. new() 构造调用
  5. 函数调用函数
  6. randomize() 标记
  7. 多层调用链
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
CALLGRAPH_BASIC = os.path.join(SV_DIR, 'callgraph_basic.sv')


@pytest.fixture(scope='module')
def dd():
    d = DesignDriver([CALLGRAPH_BASIC])
    d.build()
    assert d.success, f"slang 编译失败: {d.diagnostics}"
    return d


@pytest.fixture(scope='module')
def cg(dd):
    parser = dd.call_graph
    assert parser is not None, "CallGraph 未构建"
    return parser


# ============================================================
# 1. 基础调用链
# ============================================================

class TestBasicCalls:
    """basic_seq: body → do_init, body → do_send"""

    def test_has_methods(self, cg):
        methods = cg.get_methods('cg_pkg.basic_seq')
        names = {m['name'] for m in methods}
        assert 'body' in names
        assert 'do_init' in names
        assert 'do_send' in names

    def test_body_calls(self, cg):
        calls = cg.get_calls_from('cg_pkg.basic_seq.body')
        names = {c['callee'] for c in calls}
        assert 'do_init' in names
        assert 'do_send' in names

    def test_do_init_no_calls(self, cg):
        calls = cg.get_calls_from('cg_pkg.basic_seq.do_init')
        assert len(calls) == 0


# ============================================================
# 2. 继承 + super
# ============================================================

class TestInheritance:
    """ext_seq extends basic_seq: body → super.body + do_tag"""

    def test_ext_calls(self, cg):
        calls = cg.get_calls_from('cg_pkg.ext_seq.body')
        names = {c['callee'] for c in calls}
        assert 'body' in names      # super.body()
        assert 'do_tag' in names

    def test_super_flag(self, cg):
        calls = cg.get_calls_from('cg_pkg.ext_seq.body')
        super_call = next(c for c in calls if c['callee'] == 'body')
        assert super_call['is_super'] is True

    def test_ext_inherits_methods(self, cg):
        methods = cg.get_methods('cg_pkg.ext_seq')
        names = {m['name'] for m in methods}
        # 继承自 basic_seq 的方法也应出现
        assert 'do_init' in names
        assert 'do_send' in names
        assert 'do_tag' in names


# ============================================================
# 3. fork/join
# ============================================================

class TestFork:
    """fork_seq: fork task_a() task_b() join_any"""

    def test_fork_detected(self, cg):
        forks = cg.get_forks('cg_pkg.fork_seq')
        assert len(forks) >= 1

    def test_fork_join_type(self, cg):
        forks = cg.get_forks('cg_pkg.fork_seq')
        f = forks[0]
        assert f['join_type'] == 'join_any'

    def test_fork_branches(self, cg):
        forks = cg.get_forks('cg_pkg.fork_seq')
        f = forks[0]
        branch_names = {b['callee'] for b in f['branches']}
        assert 'task_a' in branch_names
        assert 'task_b' in branch_names

    def test_fork_none(self, cg):
        forks = cg.get_forks('cg_pkg.fork_none_seq')
        assert len(forks) >= 1
        assert forks[0]['join_type'] == 'join_none'


# ============================================================
# 4. new() 构造
# ============================================================

class TestNewCall:
    """my_driver: seq = new()"""

    def test_new_detected(self, cg):
        calls = cg.get_calls_from('cg_pkg.my_driver.run_phase')
        new_calls = [c for c in calls if c['is_constructor']]
        assert len(new_calls) >= 1
        assert new_calls[0]['target_class'] == 'cg_pkg.ext_seq'


# ============================================================
# 5. 函数调用函数
# ============================================================

class TestFuncCallsFunc:
    """func_cls: compute → add"""

    def test_compute_calls_add(self, cg):
        calls = cg.get_calls_from('cg_pkg.func_cls.compute')
        names = {c['callee'] for c in calls}
        assert 'add' in names

    def test_add_no_calls(self, cg):
        calls = cg.get_calls_from('cg_pkg.func_cls.add')
        assert len(calls) == 0


# ============================================================
# 6. randomize 标记
# ============================================================

class TestRandomize:
    """randomize() 调用标记"""

    def test_randomize_detected(self, cg):
        calls = cg.get_calls_from('cg_pkg.basic_seq.do_send')
        rand_calls = [c for c in calls if c['is_randomize']]
        assert len(rand_calls) >= 1

    def test_randomize_in_fork(self, cg):
        calls = cg.get_calls_from('cg_pkg.fork_seq.task_a')
        rand_calls = [c for c in calls if c['is_randomize']]
        assert len(rand_calls) >= 1


# ============================================================
# 7. 多层调用
# ============================================================

class TestMultiLevel:
    """multi_level: run → level1 → level2 → randomize"""

    def test_call_chain(self, cg):
        calls = cg.get_calls_from('cg_pkg.multi_level.run')
        names = {c['callee'] for c in calls}
        assert 'level1' in names

    def test_level2_calls_randomize(self, cg):
        calls = cg.get_calls_from('cg_pkg.multi_level.level2')
        rand_calls = [c for c in calls if c['is_randomize']]
        assert len(rand_calls) >= 1
