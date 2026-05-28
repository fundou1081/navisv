#!/usr/bin/env python3
"""
端到端示例：RTL hierarchy → Constraint → Coverage 完整链路

演示 navisv 三大模块的联动：
1. DesignGraph: 从 RTL 信号出发，找到相关信号
2. ConstraintGraph: 找到约束这些信号的随机化约束
3. CoverGroup: 找到覆盖这些信号的 covergroup 和 bins

场景：数据通路中 data_in 信号
  → 找到约束 data 的 constraint (范围、条件)
  → 找到覆盖 data 的 covergroup (bins)
  → 检查约束空间是否被完整覆盖
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'e2e_rtl_to_coverage.sv')


def main():
    print("=" * 70)
    print("navisv 端到端示例: RTL → Constraint → Coverage")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix='navisv_e2e_') as od:
        dd = DesignDriver([SV_FILE], output_dir=od)
        dd.build()

        dg = dd.design_graph
        cg = dd.constraint_graph
        ca = dd._covergroup_analyzer

        # ============================================================
        # Step 1: RTL 信号全景
        # ============================================================
        print("\n📦 Step 1: RTL 信号全景")
        print(f"   节点: {len(dg.graph.nodes)}, 边: {len(dg.graph.edges)}")
        print(f"   输入端口: {dg.get_input_ports()}")
        print(f"   输出端口: {dg.get_output_ports()}")
        print(f"   寄存器:   {dg.get_registers()}")

        # ============================================================
        # Step 2: 从 data_in 出发追踪信号关系
        # ============================================================
        print("\n🔍 Step 2: 信号关系分析 (data_in)")
        src = 'e2e_coverage_demo.data_in'

        # 驱动 & 负载
        drivers = dg.get_drivers(src)
        loads = dg.get_loads(src)
        print(f"   驱动 ({len(drivers)}):")
        for d in drivers:
            print(f"     ← {d}")
        print(f"   负载 ({len(loads)}):")
        for l in loads:
            print(f"     → {l}")

        # Fan-in / Fan-out
        fanin = dg.get_fanin_cone(src, depth=2)
        fanout = dg.get_fanout_cone(src, depth=2)
        print(f"\n   Fan-in ({len(fanin)}):")
        for f in sorted(fanin):
            print(f"     ← {f}")
        print(f"   Fan-out ({len(fanout)}):")
        for f in sorted(fanout):
            print(f"     → {f}")

        # ============================================================
        # Step 3: 路径追踪 (data_in → data_out)
        # ============================================================
        print("\n🚀 Step 3: 路径追踪")
        r = dg.trace_path('e2e_coverage_demo.data_in', 'e2e_coverage_demo.data_out')
        print(f"   data_in → data_out: success={r.get('success')} hops={len(r.get('path', []))}")
        if r.get('path'):
            for p in r['path']:
                print(f"     {p.get('path', p.get('signal', ''))}")

        r2 = dg.trace_path('e2e_coverage_demo.data_in', 'e2e_coverage_demo.overflow')
        print(f"   data_in → overflow:  success={r2.get('success')} hops={len(r2.get('path', []))}")

        # ============================================================
        # Step 4: 条件覆盖率
        # ============================================================
        print("\n📊 Step 4: 条件覆盖率")
        for sig in ['e2e_coverage_demo.data_in', 'e2e_coverage_demo.pipeline_data']:
            cov = dg.get_condition_coverage(sig)
            print(f"   {sig.split('.')[-1]}: {cov.get('total_conditions', 0)} 条件")

        # ============================================================
        # Step 5: ConstraintGraph — 约束分析
        # ============================================================
        print("\n🔗 Step 5: 约束图分析")
        classes = cg.get_classes()
        print(f"   约束类: {len(classes)} 个")

        for cls in classes:
            cls_name = cls['name']
            print(f"\n   ┌─ 类: {cls_name}")

            # 变量
            variables = cg.get_variables_in_class(cls_name)
            print(f"   │  变量 ({len(variables)}):")
            for v in variables:
                print(f"   │    {v['name']:12s}  {v['type_str']:10s}  rand={v['rand_mode']}  [{v['msb']}:{v['lsb']}]")

            # 约束
            constraints = cg.get_constraints_in_class(cls_name)
            print(f"   │  约束 ({len(constraints)}):")
            for c in constraints:
                cond = " [条件]" if c.get('is_conditional') else ""
                print(f"   │    {c['name']:20s}  {c['constraint_body']}{cond}")

            # 变量关系
            print(f"   │  变量关系:")
            for v in variables:
                rels = cg.get_constraints_for_variable(cls_name, v['name'])
                if rels:
                    for r in rels:
                        print(f"   │    {v['name']} ← 约束 '{r['name']}': {r.get('constraint_body', '?')[:50]}")
            print(f"   └─")

        # ============================================================
        # Step 6: CoverGroup — 覆盖分析
        # ============================================================
        print("\n📈 Step 6: CoverGroup 覆盖分析")
        covergroups = ca.get_covergroups()
        print(f"   CoverGroup: {len(covergroups)} 个")

        for cg_info in covergroups:
            cg_name = cg_info['name']
            print(f"\n   ┌─ CoverGroup: {cg_name}")

            cps = ca.get_coverpoints_by_cg(cg_name)
            for cp in cps:
                cp_name = cp['name']
                bins = ca.get_bins(cg_name, cp_name)
                print(f"   │  Coverpoint '{cp_name}': {len(bins)} bins")
                for b in bins:
                    vals = b.get('values', [])
                    kind = b.get('kind', 'normal')
                    print(f"   │    bin {b['name']:12s} = {vals}  [{kind}]")

            # Options
            opts = ca.get_options(cg_name)
            if opts:
                print(f"   │  Options: {opts}")

            crosses = ca.get_crosses(cg_name)
            if crosses:
                print(f"   │  Cross: {len(crosses)} 个")
                for cx in crosses:
                    print(f"   │    {cx.get('name', '?')}: targets={cx.get('targets', [])}")

            print(f"   └─")

        # ============================================================
        # Step 7: 约束-覆盖 交叉分析
        # ============================================================
        print("\n🎯 Step 7: 约束-覆盖 交叉分析")
        print("   检查约束值空间 vs 覆盖 bin 空间:")
        print()

        for cls in classes:
            cls_name = cls['name']
            variables = cg.get_variables_in_class(cls_name)

            for v in variables:
                var_name = v['name']
                var_bits = v['bit_width']
                var_max = (1 << var_bits) - 1

                # 找相关约束
                var_path = v.get('full_path', f"{cls_name}.{var_name}")
                related_constraints = cg.get_constraints_for_variable(var_path)

                # 解析约束范围
                constraint_ranges = []
                constraint_conditions = []
                for c in related_constraints:
                    body = c.get('constraint_body', '')
                    # 解析 inside {lo:hi}
                    if 'inside' in body:
                        import re
                        m = re.search(r'\{\s*(\d+)\s*:\s*(\d+)\s*\}', body)
                        if m:
                            lo, hi = int(m.group(1)), int(m.group(2))
                            constraint_ranges.append((lo, hi))
                    # 解析条件约束
                    if c.get('is_conditional'):
                        constraint_conditions.append(body)
                    # 解析 != 0
                    if '!=' in body and "'0" in body:
                        # data != 0 → 范围 [1, max]
                        if constraint_ranges:
                            last_hi = constraint_ranges[-1][1]
                            constraint_ranges[-1] = (1, last_hi)
                        else:
                            constraint_ranges.append((1, var_max))

                if not constraint_ranges:
                    continue

                print(f"   变量 '{var_name}' ({v['type_str']}):")
                print(f"     类型范围: 0-{var_max}")
                print(f"     约束范围: {constraint_ranges}")
                if constraint_conditions:
                    print(f"     条件约束: {constraint_conditions}")

                # 找相关 coverpoint (按名称模糊匹配)
                matched_cps = []
                for cg_info in covergroups:
                    cg_name = cg_info['name']
                    cps = ca.get_coverpoints_by_cg(cg_name)
                    for cp in cps:
                        cp_name = cp['name']
                        cp_short = cp_name.replace('cp_', '').replace('cx_', '')
                        # 匹配: 变量名在 coverpoint 名中, 或 coverpoint 短名在变量名中
                        if var_name in cp_name or cp_short in var_name or var_name.startswith(cp_short):
                            matched_cps.append((cg_name, cp_name))

                for cg_name, cp_name in matched_cps:
                    bins = ca.get_bins(cg_name, cp_name)

                    # 检查 bin 值是否在约束范围内
                    covered = []
                    gaps = []
                    for b in bins:
                        for lo, hi in b.get('values', []):
                            if any(lo <= cr[1] and hi >= cr[0] for cr in constraint_ranges):
                                covered.append((b['name'], lo, hi))
                            else:
                                gaps.append((b['name'], lo, hi))

                    if covered:
                        print(f"     覆盖 {cg_name}.{cp_name}:")
                        for name, lo, hi in covered:
                            print(f"       ✅ bin '{name}': [{lo}:{hi}]")

                    if gaps:
                        print(f"     ⚠️ 约束外 bin (不需要覆盖):")
                        for name, lo, hi in gaps:
                            print(f"       ⬜ bin '{name}': [{lo}:{hi}]")

                    # 检查约束范围是否被完整覆盖
                    all_covered_ranges = []
                    for b in bins:
                        for lo, hi in b.get('values', []):
                            if any(lo <= cr[1] and hi >= cr[0] for cr in constraint_ranges):
                                all_covered_ranges.append((lo, hi))

                    if all_covered_ranges:
                        all_covered_ranges.sort()
                        merged = [all_covered_ranges[0]]
                        for lo, hi in all_covered_ranges[1:]:
                            if lo <= merged[-1][1] + 1:
                                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
                            else:
                                merged.append((lo, hi))

                        for cr_lo, cr_hi in constraint_ranges:
                            fully_covered = any(lo <= cr_lo and hi >= cr_hi for lo, hi in merged)
                            if fully_covered:
                                print(f"     ✅ 约束范围 [{cr_lo}:{cr_hi}] 完全覆盖")
                            else:
                                print(f"     ❌ 约束范围 [{cr_lo}:{cr_hi}] 未完全覆盖")
                                print(f"        已覆盖: {merged}")
                                gap_start = cr_lo
                                for lo, hi in merged:
                                    if lo > gap_start:
                                        print(f"        缺失: [{gap_start}:{lo-1}]")
                                    gap_start = max(gap_start, hi + 1)
                                if gap_start <= cr_hi:
                                    print(f"        缺失: [{gap_start}:{cr_hi}]")

                print()

        # ============================================================
        # 总结
        # ============================================================
        print("=" * 70)
        print("📋 总结: navisv 完整链路")
        print("=" * 70)
        print("""
  RTL 信号 ──→ DesignGraph ──→ 驱动/负载/Fan-in/Fan-out
      │
      ├──→ 路径追踪 ──→ data_in → pipeline_data → data_out
      │
      ├──→ ConstraintGraph ──→ data inside {0:200}, data != 0
      │                        条件: op_mode==3 → data<100
      │
      ├──→ CoverGroup ──→ bins: low[1:50], mid[51:100], high[101:200]
      │                   bins: extreme[201:255], zero[0]
      │
      └──→ 交叉分析 ──→ 约束 [1:200] vs bins [1:200] ✅ 完全覆盖
                        约束外 bin extreme[201:255] ⬜ 不需要覆盖
""")


if __name__ == '__main__':
    main()
