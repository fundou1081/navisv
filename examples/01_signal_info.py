#!/usr/bin/env python3
"""
示例 1: 信号完整信息查询 (get_signal_info)

展示如何使用 navisv 获取信号的完整信息，包括：
- 驱动源 (drivers)
- 负载 (loads)
- 时序属性 (target_kind, clock_domain, reset_kind)
- 条件列表 (conditions)

运行: /usr/bin/python3 examples/01_signal_info.py
"""

import tempfile
import shutil
from navisv import DesignDriver

# 测试文件
TEST_FILE = '/tmp/test_signal_attrs.sv'


def main():
    output_dir = tempfile.mkdtemp(prefix='navisv_example1_')
    try:
        print("=" * 60)
        print("示例 1: 信号完整信息查询")
        print("=" * 60)
        
        # 构建设计图
        print(f"\n[1] 加载设计: {TEST_FILE}")
        dd = DesignDriver([TEST_FILE], output_dir=output_dir)
        dd.build()
        dg = dd.design_graph
        print(f"    → 加载成功，共 {len(dg._signal_conditions)} 个信号")
        
        # 查询 result 信号
        signal = 'test_signal_attributes.result'
        print(f"\n[2] 查询信号: {signal}")
        
        info = dg.get_signal_info(signal, source='both')
        
        print(f"\n[3] 信号属性:")
        print(f"    类型: {info.get('target_kind', set())}")
        print(f"    时钟域: {info.get('clock_domain', set())}")
        print(f"    Reset类型: {info.get('reset_kind', set())}")
        
        # 条件列表
        conds = info.get('conditions', [])
        print(f"\n[4] 条件列表 ({len(conds)} 个):")
        for i, c in enumerate(conds, 1):
            print(f"    {i}. {c.get('condition', 'unknown')}")
            if c.get('kind'):
                print(f"       类型: {c['kind']}")
            if c.get('statement'):
                print(f"       语句: {c['statement'][:50]}...")
        
        # 驱动源
        drivers = info.get('drivers', [])
        print(f"\n[5] 驱动源 ({len(drivers)} 个):")
        for d in drivers[:3]:
            print(f"    - {d.get('from', 'unknown')}")
        
        # 负载
        loads = info.get('loads', [])
        print(f"\n[6] 负载 ({len(loads)} 个):")
        for l in loads[:3]:
            print(f"    - {l.get('to', 'unknown')}")
        
        print(f"\n[7] 完整 JSON 输出:")
        import json
        print(json.dumps(info, indent=4, default=str)[:800] + "...")
        
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    main()