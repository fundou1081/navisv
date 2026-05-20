#!/usr/bin/env python3
"""
示例 2: 寄存器报告 (registers)

展示如何生成完整的寄存器列表，包含：
- 寄存器名称
- 时钟域 (clock)
- Reset 类型 (sync/async/none)

运行: /usr/bin/python3 examples/02_registers.py
"""

import tempfile
import shutil
from navisv import DesignDriver

TEST_FILE = '/tmp/test_signal_attrs.sv'


def main():
    output_dir = tempfile.mkdtemp(prefix='navisv_example2_')
    try:
        print("=" * 60)
        print("示例 2: 寄存器报告")
        print("=" * 60)
        
        print(f"\n[1] 加载设计: {TEST_FILE}")
        dd = DesignDriver([TEST_FILE], output_dir=output_dir)
        dd.build()
        dg = dd.design_graph
        
        # 收集所有寄存器
        registers = []
        for sig, conds in dg._signal_conditions.items():
            kinds = set(c.get('target_kind') for c in conds if c.get('target_kind'))
            if 'register_output' in kinds:
                clocks = set(c.get('clock_domain') for c in conds if c.get('clock_domain'))
                resets = set(c.get('reset_kind') for c in conds if c.get('reset_kind'))
                registers.append({
                    'signal': sig,
                    'clock': list(clocks)[0] if clocks else 'unknown',
                    'reset': list(resets)[0] if resets else 'none',
                })
        
        print(f"    → 找到 {len(registers)} 个寄存器")
        
        # 按时钟域分组
        by_clock = {}
        for r in registers:
            clk = r['clock']
            if clk not in by_clock:
                by_clock[clk] = []
            by_clock[clk].append(r)
        
        print(f"\n[2] 按时钟域分组:")
        for clk, regs in sorted(by_clock.items()):
            print(f"\n    时钟域: {clk} ({len(regs)} 个寄存器)")
            print(f"    {'信号':<35} {'Reset':<8}")
            print(f"    {'-'*35} {'-'*8}")
            for r in sorted(regs, key=lambda x: x['signal']):
                short = r['signal'].split('.')[-1]
                print(f"    {short:<35} {r['reset']:<8}")
        
        # 统计
        print(f"\n[3] 统计:")
        print(f"    总寄存器数: {len(registers)}")
        async_cnt = sum(1 for r in registers if r['reset'] == 'async')
        sync_cnt = sum(1 for r in registers if r['reset'] == 'sync')
        none_cnt = sum(1 for r in registers if r['reset'] == 'none')
        print(f"    Async reset: {async_cnt}")
        print(f"    Sync reset: {sync_cnt}")
        print(f"    No reset: {none_cnt}")
        
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    main()