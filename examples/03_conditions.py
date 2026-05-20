#!/usr/bin/env python3
"""
示例 3: 条件分析 (conditions)

展示如何获取和分析信号的所有条件，包括：
- 条件类型 (if/case/ternary/plain)
- 位置信息 (line, column)
- 时序属性 (target_kind, clock_domain, reset_kind)
- 源码文本 (statement)

运行: /usr/bin/python3 examples/03_conditions.py
"""

import tempfile
import shutil
from navisv import DesignDriver

TEST_FILE = '/tmp/test_signal_attrs.sv'


def main():
    output_dir = tempfile.mkdtemp(prefix='navisv_example3_')
    try:
        print("=" * 60)
        print("示例 3: 条件分析")
        print("=" * 60)
        
        print(f"\n[1] 加载设计: {TEST_FILE}")
        dd = DesignDriver([TEST_FILE], output_dir=output_dir)
        dd.build()
        dg = dd.design_graph
        
        # 分析 case_out 信号
        signal = 'test_signal_attributes.case_out'
        print(f"\n[2] 分析信号: {signal}")
        
        conds = dg.get_all_conditions(signal)
        print(f"    → 找到 {len(conds)} 个条件")
        
        # 按类型分组
        by_kind = {}
        for c in conds:
            kind = c.get('kind', 'unknown')
            if kind not in by_kind:
                by_kind[kind] = []
            by_kind[kind].append(c)
        
        print(f"\n[3] 条件类型分布:")
        for kind, items in sorted(by_kind.items()):
            print(f"    {kind}: {len(items)} 个")
        
        # 详细列出每个条件
        print(f"\n[4] 详细条件:")
        for i, c in enumerate(conds, 1):
            print(f"\n    条件 {i}:")
            print(f"      条件表达式: {c.get('condition', 'N/A')}")
            print(f"      类型: {c.get('kind', 'N/A')}")
            
            # 时序属性
            if c.get('target_kind'):
                print(f"      目标类型: {c['target_kind']}")
            if c.get('clock_domain'):
                print(f"      时钟域: {c['clock_domain']}")
            if c.get('reset_kind'):
                print(f"      Reset类型: {c['reset_kind']}")
            
            # 语句文本
            if c.get('statement'):
                stmt = c['statement']
                if len(stmt) > 60:
                    stmt = stmt[:60] + '...'
                print(f"      语句: {stmt}")
            
            # 边类型
            if c.get('edges'):
                print(f"      边: {c['edges']}")
        
        print(f"\n[5] 所有条件的时序属性汇总:")
        target_kinds = set(c.get('target_kind') for c in conds if c.get('target_kind'))
        clocks = set(c.get('clock_domain') for c in conds if c.get('clock_domain'))
        resets = set(c.get('reset_kind') for c in conds if c.get('reset_kind'))
        print(f"    target_kind: {target_kinds}")
        print(f"    clock_domain: {clocks}")
        print(f"    reset_kind: {resets}")
        
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    main()