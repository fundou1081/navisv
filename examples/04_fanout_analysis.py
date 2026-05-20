#!/usr/bin/env python3
"""
示例 4: fan-out 分析增强 (P2-1)

展示如何使用 get_fanout_analysis 分析信号的负载时序属性：
- 统计寄存器和组合逻辑
- 识别跨时钟域路径
- 标记异步路径

运行: /usr/bin/python3 examples/04_fanout_analysis.py
"""

import tempfile
import shutil
from navisv import DesignDriver

TEST_FILE = '/tmp/test_signal_attrs.sv'


def main():
    output_dir = tempfile.mkdtemp(prefix='navisv_example4_')
    try:
        print("=" * 60)
        print("示例 4: fan-out 分析增强")
        print("=" * 60)
        
        print(f"\n[1] 加载设计: {TEST_FILE}")
        dd = DesignDriver([TEST_FILE], output_dir=output_dir)
        dd.build()
        dg = dd.design_graph
        print(f"    → 加载成功")
        
        # 分析 clk 的 fan-out
        print(f"\n[2] 分析 clk 的 fan-out:")
        result = dg.get_fanout_analysis('test_signal_attributes.clk')
        
        print(f"\n    统计摘要:")
        print(f"      负载总数: {result['summary']['total']}")
        print(f"      寄存器: {result['summary']['registers']}")
        print(f"      组合逻辑: {result['summary']['combinational']}")
        print(f"      跨时钟域: {result['summary']['cross_clock']}")
        print(f"      异步路径: {result['summary']['async_paths']}")
        print(f"      时钟域: {result['summary']['clocks']}")
        
        print(f"\n    详细负载:")
        for load in result['loads']:
            short = load['signal'].split('.')[-1]
            print(f"\n      {short}:")
            print(f"        timing: clock={load['timing']['clock_domain']}, "
                  f"reset={load['timing']['reset_kind']}")
            print(f"        target_kind: {load['timing']['target_kind']}")
            print(f"        cross_clock: {load['cross_clock']}")
            print(f"        async_path: {load['async_path']}")
        
        # 分析 clk2 (不同频率时钟)
        print(f"\n[3] 分析 clk2 的 fan-out:")
        result2 = dg.get_fanout_analysis('test_signal_attributes.clk2')
        
        print(f"\n    统计摘要:")
        print(f"      负载总数: {result2['summary']['total']}")
        print(f"      时钟域: {result2['summary']['clocks']}")
        
        if result2['loads']:
            for load in result2['loads']:
                short = load['signal'].split('.')[-1]
                print(f"      {short}: clock={load['timing']['clock_domain']}")
        
        print("\n[4] CDC 分析结论:")
        if result['summary']['cross_clock'] > 0:
            print(f"    ⚠️ 存在跨时钟域路径，需要 CDC 防护")
        else:
            print(f"    ✅ 无跨时钟域路径")
        
        if result['summary']['async_paths'] > 0:
            print(f"    ⚠️ 存在 {result['summary']['async_paths']} 个异步路径")
        else:
            print(f"    ✅ 无异步路径风险")
            
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    main()