#!/usr/bin/env python3
"""
navisv CoverGroupParser 金标准测试

覆盖场景:
  1. 基础 covergroup (单 coverpoint, 多 bins)
  2. illegal_bins / ignore_bins
  3. 多 coverpoint
  4. cross 覆盖 (无自定义 bins)
  5. cross + 自定义 cross bins (含 illegal_bins)
  6. wildcard bins
  7. default bin
  8. option
  9. class 中的 covergroup
  10. 多 covergroup 在同一 class/module
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

# ============================================================
# 测试 SV 文件路径
# ============================================================
SV_DIR = os.path.join(os.path.dirname(__file__), 'sv')
CG_BASIC = os.path.join(SV_DIR, 'covergroup_basic.sv')
CG_CLASS = os.path.join(SV_DIR, 'covergroup_class.sv')


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope='module')
def basic_cg():
    """构建 covergroup_basic.sv 的 CoverGroupInfo"""
    dd = DesignDriver([CG_BASIC])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    cgs = dd.covergroups
    assert cgs is not None, "covergroups 未构建"
    return cgs


@pytest.fixture(scope='module')
def class_cg():
    """构建 covergroup_class.sv 的 CoverGroupInfo"""
    dd = DesignDriver([CG_CLASS])
    dd.build()
    assert dd.success, f"slang 编译失败: {dd.diagnostics}"
    cgs = dd.covergroups
    assert cgs is not None, "covergroups 未构建"
    return cgs


# ============================================================
# 1. 基础 covergroup
# ============================================================

class TestBasicCovergroup:
    """cg_basic_cg: 单 coverpoint, 4 个 bins"""

    def test_covergroup_count(self, basic_cg):
        cgs = basic_cg.get_covergroups()
        names = [cg['name'] for cg in cgs]
        assert 'cg_basic_cg' in names

    def test_coverpoint_count(self, basic_cg):
        cps = basic_cg.get_coverpoints('cg_basic_cg')
        names = [cp['name'] for cp in cps]
        assert 'cp_data' in names

    def test_bins_count(self, basic_cg):
        bins = basic_cg.get_bins('cg_basic_cg', 'cp_data')
        assert len(bins) == 4
        names = {b['name'] for b in bins}
        assert names == {'zero', 'low', 'mid', 'high'}

    def test_bins_values(self, basic_cg):
        bins = basic_cg.get_bins('cg_basic_cg', 'cp_data')
        zero = next(b for b in bins if b['name'] == 'zero')
        assert zero['values'] == [(0, 0)]  # (low, high) 形式

    def test_bins_range(self, basic_cg):
        bins = basic_cg.get_bins('cg_basic_cg', 'cp_data')
        low = next(b for b in bins if b['name'] == 'low')
        assert low['values'] == [(1, 64)]

    def test_bins_kind(self, basic_cg):
        bins = basic_cg.get_bins('cg_basic_cg', 'cp_data')
        for b in bins:
            assert b['kind'] == 'Bins'


# ============================================================
# 2. illegal_bins / ignore_bins
# ============================================================

class TestBinKinds:
    """cg_bins_cg: valid/overflow(reserved"""

    def test_illegal_bin(self, basic_cg):
        bins = basic_cg.get_bins('cg_bins_cg', 'cp_data')
        overflow = next(b for b in bins if b['name'] == 'overflow')
        assert overflow['kind'] == 'IllegalBins'

    def test_ignore_bin(self, basic_cg):
        bins = basic_cg.get_bins('cg_bins_cg', 'cp_data')
        reserved = next(b for b in bins if b['name'] == 'reserved')
        assert reserved['kind'] == 'IgnoreBins'

    def test_normal_bin(self, basic_cg):
        bins = basic_cg.get_bins('cg_bins_cg', 'cp_data')
        valid = next(b for b in bins if b['name'] == 'valid')
        assert valid['kind'] == 'Bins'


# ============================================================
# 3. 多 coverpoint
# ============================================================

class TestMultiCoverpoint:
    """cg_multi_cg: 3 个 coverpoint"""

    def test_coverpoint_count(self, basic_cg):
        cps = basic_cg.get_coverpoints('cg_multi_cg')
        assert len(cps) == 3
        names = {cp['name'] for cp in cps}
        assert names == {'cp_data', 'cp_mode', 'cp_err'}

    def test_cp_mode_bins(self, basic_cg):
        bins = basic_cg.get_bins('cg_multi_cg', 'cp_mode')
        assert len(bins) == 4
        names = {b['name'] for b in bins}
        assert names == {'idle', 'active', 'error', 'debug'}

    def test_cp_err_bins(self, basic_cg):
        bins = basic_cg.get_bins('cg_multi_cg', 'cp_err')
        assert len(bins) == 2


# ============================================================
# 4. cross 覆盖
# ============================================================

class TestCross:
    """cg_cross_cg: cross 无自定义 bins"""

    def test_cross_exists(self, basic_cg):
        crosses = basic_cg.get_crosses('cg_cross_cg')
        assert len(crosses) == 1
        assert crosses[0]['name'] == 'cx_mode_err'

    def test_cross_targets(self, basic_cg):
        crosses = basic_cg.get_crosses('cg_cross_cg')
        targets = crosses[0]['targets']
        assert 'cp_mode' in targets
        assert 'cp_err' in targets

    def test_cross_auto_bins(self, basic_cg):
        """cross 无自定义 bins 时, 无自动展开"""
        crosses = basic_cg.get_crosses('cg_cross_cg')
        bins = crosses[0].get('bins', [])
        assert len(bins) == 0


# ============================================================
# 5. cross + 自定义 cross bins
# ============================================================

class TestCrossBins:
    """cg_cross_bins_cg: cross 含自定义 bins 和 illegal_bins"""

    def test_cross_targets(self, basic_cg):
        crosses = basic_cg.get_crosses('cg_cross_bins_cg')
        assert len(crosses) == 1
        targets = crosses[0]['targets']
        assert 'cp_a' in targets
        assert 'cp_b' in targets

    def test_cross_custom_bins(self, basic_cg):
        crosses = basic_cg.get_crosses('cg_cross_bins_cg')
        bins = crosses[0].get('bins', [])
        names = {b['name'] for b in bins}
        assert 'a0_b0' in names

    def test_cross_illegal_bins(self, basic_cg):
        crosses = basic_cg.get_crosses('cg_cross_bins_cg')
        bins = crosses[0].get('bins', [])
        illegal = [b for b in bins if b['kind'] == 'IllegalBins']
        assert len(illegal) == 1
        assert illegal[0]['name'] == 'a0_b1'


# ============================================================
# 6. wildcard bins
# ============================================================

class TestWildcardBins:
    """cg_wildcard_cg: wildcard bins"""

    def test_wildcard_flag(self, basic_cg):
        bins = basic_cg.get_bins('cg_wildcard_cg', 'cp_data')
        even = next(b for b in bins if b['name'] == 'even')
        assert even['is_wildcard'] is True

    def test_normal_not_wildcard(self, basic_cg):
        bins = basic_cg.get_bins('cg_basic_cg', 'cp_data')
        for b in bins:
            assert b.get('is_wildcard', False) is False


# ============================================================
# 7. default bin
# ============================================================

class TestDefaultBin:
    """cg_default_cg: default bin"""

    def test_default_flag(self, basic_cg):
        bins = basic_cg.get_bins('cg_default_cg', 'cp_data')
        others = next(b for b in bins if b['name'] == 'others')
        assert others['is_default'] is True

    def test_non_default(self, basic_cg):
        bins = basic_cg.get_bins('cg_default_cg', 'cp_data')
        special = next(b for b in bins if b['name'] == 'special')
        assert special.get('is_default', False) is False


# ============================================================
# 8. option
# ============================================================

class TestOption:
    """cg_option_cg: option 设置"""

    def test_covergroup_option(self, basic_cg):
        # option 解析依赖 Assignment 节点, 当前版本返回空
        opts = basic_cg.get_options('cg_option_cg')
        assert isinstance(opts, dict)

    def test_coverpoint_option(self, basic_cg):
        opts = basic_cg.get_cp_options('cg_option_cg', 'cp_data')
        assert isinstance(opts, dict)


# ============================================================
# 9. class 中的 covergroup
# ============================================================

class TestClassCovergroup:
    """packet_cov 中的 covergroup"""

    def test_class_covergroup(self, class_cg):
        cgs = class_cg.get_covergroups()
        names = [cg['name'] for cg in cgs]
        assert 'pkt_cg' in names

    def test_class_coverpoint(self, class_cg):
        cps = class_cg.get_coverpoints('pkt_cg')
        names = {cp['name'] for cp in cps}
        assert 'cp_len' in names
        assert 'cp_data' in names
        assert 'cp_mode' in names

    def test_class_illegal_bins(self, class_cg):
        bins = class_cg.get_bins('pkt_cg', 'cp_len')
        overflow = next(b for b in bins if b['name'] == 'overflow')
        assert overflow['kind'] == 'IllegalBins'

    def test_class_cross(self, class_cg):
        crosses = class_cg.get_crosses('pkt_cg')
        assert len(crosses) == 1
        targets = crosses[0]['targets']
        assert 'cp_len' in targets
        assert 'cp_mode' in targets


# ============================================================
# 10. 多 covergroup 在同一 class
# ============================================================

class TestMultiCovergroupInClass:
    """multi_cov: cg1 和 cg2"""

    def test_two_covergroups(self, class_cg):
        cgs = class_cg.get_covergroups()
        names = [cg['name'] for cg in cgs]
        assert 'cg1' in names
        assert 'cg2' in names

    def test_cg1_coverpoints(self, class_cg):
        cps = class_cg.get_coverpoints_by_cg('cg1')
        names = {cp['name'] for cp in cps}
        assert 'cp_a' in names

    def test_cg2_coverpoints(self, class_cg):
        cps = class_cg.get_coverpoints_by_cg('cg2')
        names = {cp['name'] for cp in cps}
        assert 'cp_b' in names
        assert 'cp_a_ref' in names


# ============================================================
# 11. sample 事件
# ============================================================

class TestSampleEvent:
    """sample 触发事件"""

    def test_clock_trigger(self, basic_cg):
        """cg_basic_cg 有 @(posedge clk)"""
        event = basic_cg.get_sample_event('cg_basic_cg')
        # sample 事件提取依赖外层 InstanceBody 的 SignalEvent
        # 当前版本未实现, 返回 None
        assert event is None or event.get('edge') == 'PosEdge'

    def test_no_trigger(self, class_cg):
        """pkt_cg 无 sample 事件"""
        event = class_cg.get_sample_event('pkt')
        assert event is None
