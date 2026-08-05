"""
test_netlist_driver_error.py - Stage 14 修复验证

测试 NetlistDriverError 的存在和 DesignDriver._run_netlist() 在
NetlistDriver.run() 失败时正确抛出异常。

Bug 背景:
- 之前 _run_netlist() 静默吞掉 success=False 结果
- 导致 _netlist_parser=None,下游 GraphBuilder 崩在难懂的 'list index out of range'
- 用户看不到 slang-netlist 工具的真实错误

修复: 在 _run_netlist() 里 raise NetlistDriverError,带 stderr 上下文
"""
import os
import sys
from unittest.mock import patch

import pytest

NAVISV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTER_SV = os.path.join(NAVISV_ROOT, 'tests', 'fixtures', 'elk_counter.sv')


class TestNetlistDriverErrorImport:
    """NetlistDriverError 应该可导入"""

    def test_error_class_exists(self):
        """netlist_driver 模块应该导出 NetlistDriverError"""
        from navisv.drivers.netlist_driver import NetlistDriverError
        assert NetlistDriverError is not None

    def test_error_inherits_exception(self):
        """NetlistDriverError 应该继承 Exception"""
        from navisv.drivers.netlist_driver import NetlistDriverError
        assert issubclass(NetlistDriverError, Exception)

    def test_error_importable_from_design_driver(self):
        """design_driver 应该 re-export NetlistDriverError"""
        from navisv.drivers.design_driver import NetlistDriverError
        from navisv.drivers.netlist_driver import NetlistDriverError as Orig
        assert NetlistDriverError is Orig

    def test_error_can_be_raised(self):
        """NetlistDriverError 应该可以 raise 和 catch"""
        from navisv.drivers.netlist_driver import NetlistDriverError
        with pytest.raises(NetlistDriverError) as exc_info:
            raise NetlistDriverError("test error")
        assert "test error" in str(exc_info.value)


class TestRunNetlistRaises:
    """DesignDriver._run_netlist() 在 NetlistDriver.run() 失败时应该 raise"""

    def test_run_netlist_raises_on_failure(self):
        """当 NetlistDriver.run() 返回 success=False,_run_netlist() 应该 raise"""
        from navisv.drivers.design_driver import DesignDriver
        from navisv.drivers.netlist_driver import NetlistDriverError

        # 模拟 NetlistDriver.run() 返回失败
        fake_failure = {
            'success': False,
            'returncode': 1,
            'stderr': 'fake stderr: cannot find module foo',
            'stdout': '',
            'netlist_json': None,
            'json_size': 0,
            'scope': None,
        }
        with patch(
            'navisv.drivers.netlist_driver.NetlistDriver.run',
            return_value=fake_failure,
        ):
            dd = DesignDriver([COUNTER_SV], cache=False)
            # _run_slang() 也会跑,我们直接调 _run_netlist()
            with pytest.raises(NetlistDriverError) as exc_info:
                dd._run_netlist()
            # 错误消息应包含 stderr 末尾
            err = str(exc_info.value)
            assert "returncode=1" in err
            assert "fake stderr" in err

    def test_run_netlist_does_not_raise_on_success(self):
        """当 NetlistDriver.run() 返回 success=True,_run_netlist() 不应该 raise"""
        from navisv.drivers.design_driver import DesignDriver
        from navisv.drivers.netlist_driver import NetlistDriverError

        fake_success = {
            'success': True,
            'returncode': 0,
            'stderr': '',
            'stdout': '',
            'netlist_json': '/tmp/fake_netlist.json',
            'json_size': 100,
            'scope': None,
        }
        with patch(
            'navisv.drivers.netlist_driver.NetlistDriver.run',
            return_value=fake_success,
        ):
            dd = DesignDriver([COUNTER_SV], cache=False)
            # 应该不抛异常
            dd._run_netlist()
            assert dd._netlist_result == fake_success

    def test_error_includes_stderr_tail(self):
        """错误消息应包含 stderr 末尾 (而不是被截断头部)"""
        from navisv.drivers.design_driver import DesignDriver
        from navisv.drivers.netlist_driver import NetlistDriverError

        long_stderr = 'A' * 1000 + ' TAIL_MARKER_HERE'
        fake_failure = {
            'success': False,
            'returncode': 2,
            'stderr': long_stderr,
            'stdout': '',
            'netlist_json': None,
            'json_size': 0,
            'scope': None,
        }
        with patch(
            'navisv.drivers.netlist_driver.NetlistDriver.run',
            return_value=fake_failure,
        ):
            dd = DesignDriver([COUNTER_SV], cache=False)
            with pytest.raises(NetlistDriverError) as exc_info:
                dd._run_netlist()
            err = str(exc_info.value)
            # 错误消息应包含尾部 marker (说明截取的是末尾 800 字符)
            assert 'TAIL_MARKER_HERE' in err