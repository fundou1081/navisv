#!/usr/bin/env python3
"""
navisv ConstraintGraph 金标准测试

覆盖场景:
  1. 基础类 (simple_packet)
  2. 多层继承 (base -> mid -> eth)
  3. 组合关系 (wrapper -> eth_packet)
  4. 深层组合 (top_env -> wrapper -> eth_packet)
  5. 位精确度 (部分位约束)
  6. 条件约束 (if/else inside constraint)
  7. 边界场景 (无约束变量、同名覆盖、randc、soft、深层继承)
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

# ============================================================
# 测试 SV 文件路径 (slang 编译已验证通过)
# ============================================================
SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
CONSTRAINT_BASIC = os.path.join(SV_DIR, 'constraint_basic.sv')
CONSTRAINT_CONDITIONAL = os.path.join(SV_DIR, 'constraint_conditional.sv')
CONSTRAINT_EDGE = os.path.join(SV_DIR, 'constraint_edge.sv')


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope='module')
def basic_cg():
    """构建 constraint_basic.sv 的 ConstraintGraph"""
    dd = DesignDriver([CONSTRAINT_BASIC])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    cg = dd.constraint_graph
    assert cg is not None, "constraint_graph 未构建"
    return cg


@pytest.fixture(scope='module')
def cond_cg():
    """构建 constraint_conditional.sv 的 ConstraintGraph"""
    dd = DesignDriver([CONSTRAINT_CONDITIONAL])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    cg = dd.constraint_graph
    assert cg is not None, "constraint_graph 未构建"
    return cg


@pytest.fixture(scope='module')
def edge_cg():
    """构建 constraint_edge.sv 的 ConstraintGraph"""
    dd = DesignDriver([CONSTRAINT_EDGE])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    cg = dd.constraint_graph
    assert cg is not None, "constraint_graph 未构建"
    return cg


# ============================================================
# 1. 基础类测试
# ============================================================

class TestBasicClass:
    """simple_packet: 2 个 rand 变量, 1 个 constraint"""

    def test_class_exists(self, basic_cg):
        classes = basic_cg.get_classes()
        names = [c['name'] for c in classes]
        assert 'simple_packet' in names

    def test_variable_count(self, basic_cg):
        vars = basic_cg.get_variables_in_class('constraint_basic_pkg.simple_packet')
        assert len(vars) == 2
        names = {v['name'] for v in vars}
        assert names == {'length', 'data'}

    def test_variable_properties(self, basic_cg):
        vars = basic_cg.get_variables_in_class('constraint_basic_pkg.simple_packet')
        length = next(v for v in vars if v['name'] == 'length')
        assert length['rand_mode'] == 'Rand'
        assert length['bit_width'] == 8
        assert length['msb'] == 7
        assert length['lsb'] == 0

    def test_constraint_count(self, basic_cg):
        constraints = basic_cg.get_constraints_in_class('constraint_basic_pkg.simple_packet')
        assert len(constraints) == 1
        assert constraints[0]['name'] == 'c_simple'

    def test_constraint_binds_variables(self, basic_cg):
        """c_simple 绑定 length 和 data"""
        bound = basic_cg.get_variables_in_constraint('constraint_basic_pkg.simple_packet.c_simple')
        names = {v['name'] for v in bound}
        assert 'length' in names
        assert 'data' in names

    def test_variable_in_which_constraints(self, basic_cg):
        """Q1: length 在哪些 constraint 中"""
        cons = basic_cg.get_constraints_for_variable('constraint_basic_pkg.simple_packet.length')
        names = {c['constraint_name'] for c in cons}
        assert 'c_simple' in names


# ============================================================
# 2. 多层继承测试
# ============================================================

class TestMultiInheritance:
    """base_packet -> mid_packet -> eth_packet (3 层)"""

    def test_inheritance_chain(self, basic_cg):
        """验证继承链"""
        chain = basic_cg.get_inheritance_chain('constraint_basic_pkg.eth_packet')
        assert chain == [
            'constraint_basic_pkg.eth_packet',
            'constraint_basic_pkg.mid_packet',
            'constraint_basic_pkg.base_packet',
        ]

    def test_eth_inherits_base_variables(self, basic_cg):
        """eth_packet 继承 base_packet 的 length"""
        cons = basic_cg.get_constraints_for_variable('constraint_basic_pkg.eth_packet.length')
        c_names = {c['constraint_name'] for c in cons}
        # length 应出现在 3 层的 constraint 中 (共享同一变量地址)
        assert 'c_base' in c_names   # 来自 base_packet
        assert 'c_mid' in c_names    # 来自 mid_packet
        assert 'c_eth_size' in c_names  # 来自 eth_packet 自身

    def test_eth_own_variable(self, basic_cg):
        """eth_packet 自己的 dst_mac"""
        cons = basic_cg.get_constraints_for_variable('constraint_basic_pkg.eth_packet.dst_mac')
        c_names = {c['constraint_name'] for c in cons}
        assert 'c_eth_mac' in c_names
        # 不应出现在父类约束中
        assert 'c_base' not in c_names
        assert 'c_mid' not in c_names

    def test_mid_inherits_base(self, basic_cg):
        """mid_packet 继承 base_packet 的约束"""
        cons = basic_cg.get_constraints_for_variable('constraint_basic_pkg.mid_packet.length')
        c_names = {c['constraint_name'] for c in cons}
        # 共享地址: base + mid 的约束都应出现
        assert 'c_base' in c_names
        assert 'c_mid' in c_names

    def test_base_variable_only_in_base(self, basic_cg):
        """base_packet 的 length 在整个继承链上的约束"""
        cons = basic_cg.get_constraints_for_variable('constraint_basic_pkg.base_packet.length')
        c_names = {c['constraint_name'] for c in cons}
        # 共享地址: 所有引用该变量的约束都应出现
        assert 'c_base' in c_names
        assert 'c_mid' in c_names
        assert 'c_eth_size' in c_names


# ============================================================
# 3. 组合关系测试
# ============================================================

class TestComposition:
    """wrapper 包含 eth_packet 实例"""

    def test_wrapper_has_pkt_member(self, basic_cg):
        """wrapper.pkt 是 eth_packet 类型"""
        vars = basic_cg.get_variables_in_class('constraint_basic_pkg.wrapper')
        pkt = next(v for v in vars if v['name'] == 'pkt')
        assert pkt['type_class'] == 'constraint_basic_pkg.eth_packet'

    def test_wrapper_constraint_references_pkt(self, basic_cg):
        """c_wrap_len 引用 pkt.length 和 header"""
        bound = basic_cg.get_variables_in_constraint('constraint_basic_pkg.wrapper.c_wrap_len')
        names = {v['name'] for v in bound}
        assert 'header' in names
        # pkt.length 也应该被检测到 (跨类引用)
        pkt_vars = [v for v in bound if v.get('access_path')]
        assert any('pkt.length' in v.get('access_path', '') for v in pkt_vars)

    def test_wrapper_constraint_access_path(self, basic_cg):
        """c_wrap_len 的 binds 边应包含 access_path='pkt.length'"""
        bound = basic_cg.get_variables_in_constraint('constraint_basic_pkg.wrapper.c_wrap_len')
        pkt_len = next((v for v in bound if v.get('access_path') == 'pkt.length'), None)
        assert pkt_len is not None
        assert pkt_len['target_class'] == 'constraint_basic_pkg.eth_packet'

    def test_cross_class_query(self, basic_cg):
        """Q1: eth_packet.length 在 wrapper 的约束中也应出现"""
        cons = basic_cg.get_constraints_for_variable(
            'constraint_basic_pkg.eth_packet.length',
            include_composition=True,
        )
        c_names = {c['constraint_name'] for c in cons}
        # wrapper.c_wrap_len 通过 pkt.length 引用
        assert 'c_wrap_len' in c_names


# ============================================================
# 4. 深层组合测试
# ============================================================

class TestDeepComposition:
    """top_env -> wrapper -> eth_packet (3 层穿透)"""

    def test_top_env_constraint(self, basic_cg):
        """c_top 引用 wrp.header (2 层穿透)"""
        bound = basic_cg.get_variables_in_constraint('constraint_basic_pkg.top_env.c_top')
        # 应检测到 global_id 和 wrp.header
        names = {v['name'] for v in bound}
        assert 'global_id' in names
        access_paths = {v.get('access_path') for v in bound if v.get('access_path')}
        assert 'wrp.header' in access_paths

    def test_deep_access_path(self, basic_cg):
        """wrp.header 的 access_path 指向 wrapper 类"""
        bound = basic_cg.get_variables_in_constraint('constraint_basic_pkg.top_env.c_top')
        wrp_header = next((v for v in bound if v.get('access_path') == 'wrp.header'), None)
        assert wrp_header is not None
        assert wrp_header['target_class'] == 'constraint_basic_pkg.wrapper'

    def test_deep_composition_traversal(self, basic_cg):
        """Q1: eth_packet.length 通过深层组合也应可达"""
        cons = basic_cg.get_constraints_for_variable(
            'constraint_basic_pkg.eth_packet.length',
            include_composition=True,
            max_depth=3,
        )
        c_names = {c['constraint_name'] for c in cons}
        # wrapper.c_wrap_len 通过 pkt.length 引用
        assert 'c_wrap_len' in c_names


# ============================================================
# 5. 位精确度测试
# ============================================================

class TestBitPrecision:
    """bit_precision_packet: 全宽/部分位/单 bit 约束"""

    def test_full_width_constraint(self, cond_cg):
        """c_addr_range: addr 全宽约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.bit_precision_packet.addr'
        )
        c = next(c for c in cons if c['constraint_name'] == 'c_addr_range')
        assert c['bit_range'] is None  # 全宽

    def test_range_select_constraint(self, cond_cg):
        """c_ctrl_high: ctrl_word[15:12] 部分位约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.bit_precision_packet.ctrl_word'
        )
        c_high = next(c for c in cons if c['constraint_name'] == 'c_ctrl_high')
        assert c_high['bit_range'] == [15, 12]

    def test_low_range_select(self, cond_cg):
        """c_ctrl_low: ctrl_word[7:0] 部分位约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.bit_precision_packet.ctrl_word'
        )
        c_low = next(c for c in cons if c['constraint_name'] == 'c_ctrl_low')
        assert c_low['bit_range'] == [7, 0]

    def test_element_select(self, cond_cg):
        """c_ctrl_flag: ctrl_word[8] 单 bit 约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.bit_precision_packet.ctrl_word'
        )
        c_flag = next(c for c in cons if c['constraint_name'] == 'c_ctrl_flag')
        assert c_flag['bit_range'] == [8, 8]

    def test_ctrl_word_all_constraints(self, cond_cg):
        """ctrl_word 出现在 3 个约束中"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.bit_precision_packet.ctrl_word'
        )
        c_names = {c['constraint_name'] for c in cons}
        assert c_names == {'c_ctrl_high', 'c_ctrl_low', 'c_ctrl_flag'}


# ============================================================
# 6. 条件约束测试
# ============================================================

class TestConditionalConstraint:
    """conditional_packet: if/else inside constraint"""

    def test_conditional_flag(self, cond_cg):
        """c_mode_len 是条件约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.conditional_packet.length'
        )
        c_mode_len = next(c for c in cons if c['constraint_name'] == 'c_mode_len')
        assert c_mode_len['is_conditional'] is True

    def test_unconditional_flag(self, cond_cg):
        """c_always 是无条件约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.conditional_packet.length'
        )
        c_always = next(c for c in cons if c['constraint_name'] == 'c_always')
        assert c_always['is_conditional'] is False

    def test_conditional_context(self, cond_cg):
        """c_mode_len 的 context 应包含 if 结构"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.conditional_packet.length'
        )
        c_mode_len = next(c for c in cons if c['constraint_name'] == 'c_mode_len')
        ctx = c_mode_len['context']
        assert 'if' in ctx
        assert 'length' in ctx

    def test_conditional_direct_expr(self, cond_cg):
        """c_mode_len 的 direct_expr 应列出命中的直接表达式"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.conditional_packet.length'
        )
        c_mode_len = next(c for c in cons if c['constraint_name'] == 'c_mode_len')
        exprs = c_mode_len['direct_exprs']
        # length 在条件约束中应有直接表达式
        assert len(exprs) >= 1

    def test_inherited_conditional(self, cond_cg):
        """ext_mode 继承 base_mode 的条件约束"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.ext_mode.length'
        )
        c_names = {c['constraint_name'] for c in cons}
        assert 'c_base_mode' in c_names
        assert 'c_ext_mode' in c_names
        # 两者都是条件约束
        for c in cons:
            if c['constraint_name'] in ('c_base_mode', 'c_ext_mode'):
                assert c['is_conditional'] is True

    def test_composition_conditional(self, cond_cg):
        """outer_cls.inner.flag 在条件约束中"""
        cons = cond_cg.get_constraints_for_variable(
            'constraint_conditional_pkg.inner_cls.flag',
            include_composition=True,
        )
        c_names = {c['constraint_name'] for c in cons}
        # c_inner 自身有条件约束
        assert 'c_inner' in c_names
        # c_outer_cond 通过 inner.flag 引用
        assert 'c_outer_cond' in c_names


# ============================================================
# 7. 边界场景测试
# ============================================================

class TestEdgeCases:
    """边界场景"""

    def test_unconstrained_variable(self, edge_cg):
        """free_var 没有被任何 constraint 引用"""
        cons = edge_cg.get_constraints_for_variable(
            'constraint_edge_pkg.unconstrained_cls.free_var'
        )
        assert cons == []

    def test_constrained_variable(self, edge_cg):
        """bounded_var 有约束"""
        cons = edge_cg.get_constraints_for_variable(
            'constraint_edge_pkg.unconstrained_cls.bounded_var'
        )
        assert len(cons) == 1
        assert cons[0]['constraint_name'] == 'c_bounded'

    def test_constraint_override(self, edge_cg):
        """child_cls.c_val 覆盖 parent_cls.c_val"""
        # parent 的 c_val 约束 value
        parent_cons = edge_cg.get_constraints_for_variable(
            'constraint_edge_pkg.parent_cls.value'
        )
        parent_names = {c['constraint_name'] for c in parent_cons}
        assert 'c_val' in parent_names

        # child 继承后，c_val 被覆盖
        child_cons = edge_cg.get_constraints_for_variable(
            'constraint_edge_pkg.child_cls.value'
        )
        child_names = {c['constraint_name'] for c in child_cons}
        assert 'c_val' in child_names
        # c_val 来自 parent 和 child (同名覆盖)
        c_val_entries = [c for c in child_cons if c['constraint_name'] == 'c_val']
        class_names = {c['class_name'] for c in c_val_entries}
        assert 'constraint_edge_pkg.parent_cls' in class_names
        assert 'constraint_edge_pkg.child_cls' in class_names

    def test_multi_constraint_same_var(self, edge_cg):
        """shared_var 出现在 3 个 constraint 中"""
        cons = edge_cg.get_constraints_for_variable(
            'constraint_edge_pkg.multi_constraint_cls.shared_var'
        )
        c_names = {c['constraint_name'] for c in cons}
        assert c_names == {'c_multi_a', 'c_multi_b', 'c_multi_c'}

    def test_deep_inheritance_4_levels(self, edge_cg):
        """4 层继承：level3 继承所有层的约束"""
        cons = edge_cg.get_constraints_for_variable(
            'constraint_edge_pkg.level3.deep_var'
        )
        c_names = {c['constraint_name'] for c in cons}
        assert 'c_l0' in c_names
        assert 'c_l1' in c_names
        assert 'c_l2' in c_names
        assert 'c_l3' in c_names

    def test_deep_inheritance_chain(self, edge_cg):
        """level3 的继承链"""
        chain = edge_cg.get_inheritance_chain('constraint_edge_pkg.level3')
        assert chain == [
            'constraint_edge_pkg.level3',
            'constraint_edge_pkg.level2',
            'constraint_edge_pkg.level1',
            'constraint_edge_pkg.level0',
        ]

    def test_multi_composition(self, edge_cg):
        """multi_comp 包含 comp_a 和 comp_b 两个实例"""
        bound = edge_cg.get_variables_in_constraint('constraint_edge_pkg.multi_comp.c_total')
        access_paths = {v.get('access_path') for v in bound if v.get('access_path')}
        assert 'inst_a.x' in access_paths
        assert 'inst_b.y' in access_paths

    def test_randc_mode(self, cond_cg):
        """randc 变量"""
        vars = cond_cg.get_variables_in_class('constraint_conditional_pkg.randc_packet')
        seq = next(v for v in vars if v['name'] == 'seq_num')
        assert seq['rand_mode'] == 'RandC'

    def test_soft_constraint(self, cond_cg):
        """soft 约束标记"""
        cons = cond_cg.get_constraints_in_class('constraint_conditional_pkg.randc_packet')
        c_seq = next(c for c in cons if c['name'] == 'c_seq')
        assert c_seq['has_soft'] is True


# ============================================================
# 8. Q3: 变量间约束关系
# ============================================================

class TestVariableRelationship:
    """Q3: 两个变量之间的约束关系"""

    def test_direct_relationship(self, basic_cg):
        """simple_packet: length 和 data 直接在同一 constraint 中"""
        rel = basic_cg.get_constraint_relationship(
            'constraint_basic_pkg.simple_packet.length',
            'constraint_basic_pkg.simple_packet.data',
        )
        shared = rel['shared_constraints']
        assert 'c_simple' in shared

    def test_cross_class_relationship(self, basic_cg):
        """wrapper: header 和 eth_packet.length 通过 c_wrap_len 关联"""
        rel = basic_cg.get_constraint_relationship(
            'constraint_basic_pkg.wrapper.header',
            'constraint_basic_pkg.eth_packet.length',
        )
        shared = rel['shared_constraints']
        assert 'c_wrap_len' in shared

    def test_no_relationship(self, basic_cg):
        """simple_packet.length 和 eth_packet.dst_mac 无关系"""
        rel = basic_cg.get_constraint_relationship(
            'constraint_basic_pkg.simple_packet.length',
            'constraint_basic_pkg.eth_packet.dst_mac',
        )
        assert rel['shared_constraints'] == []

    def test_inherited_relationship(self, basic_cg):
        """eth_packet.dst_mac 和 eth_packet.src_mac 通过 c_eth_mac 关联"""
        rel = basic_cg.get_constraint_relationship(
            'constraint_basic_pkg.eth_packet.dst_mac',
            'constraint_basic_pkg.eth_packet.src_mac',
        )
        shared = rel['shared_constraints']
        assert 'c_eth_mac' in shared

    def test_indirect_through_composition(self, basic_cg):
        """wrapper.pri 和 eth_packet.tag 通过 c_wrap_pri 关联"""
        rel = basic_cg.get_constraint_relationship(
            'constraint_basic_pkg.wrapper.pri',
            'constraint_basic_pkg.eth_packet.tag',
        )
        shared = rel['shared_constraints']
        assert 'c_wrap_pri' in shared
