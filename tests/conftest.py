# tests/conftest.py - pytest fixtures for navisv
# navisv 架构 v0.8

"""
所有测试共享的 fixtures：
- simple_assign.sv: 最简 assign + always_ff 设计
- simple_concat.sv: 拼接 assign 设计
- simple_class.sv: class 方法调用设计
"""

import pytest
import sys
import os

# slang-netlist 路径
SLANG_PATH = '/Users/fundou/my_dv_proj/slang-netlist/install'
sys.path.insert(0, SLANG_PATH)
sys.path.insert(0, os.path.join(SLANG_PATH, 'lib'))


@pytest.fixture(scope="session")
def slang_modules():
    """延迟加载 slang-netlist 模块"""
    import pyslang_netlist as nl
    from pyslang import driver as sl_driver
    return nl, sl_driver


@pytest.fixture(scope="session")
def fixture_dir():
    """测试 fixture 文件目录"""
    return os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture(scope="session")
def simple_design_path(fixture_dir):
    """最简 assign + always_ff 设计"""
    return os.path.join(fixture_dir, 'simple_assign.sv')


@pytest.fixture(scope="session")
def concat_design_path(fixture_dir):
    """拼接 assign 设计"""
    return os.path.join(fixture_dir, 'simple_concat.sv')