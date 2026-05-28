#!/usr/bin/env python3
"""
时序关系分析 + SVA 对齐检查

演示:
1. 从信号图提取两个信号的时序关系
2. 检查是否有 SVA 覆盖该关系
3. 为未覆盖的关系生成 SVA 建议

用法:
    python3 examples/temporal_sva_check.py
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver
from navisv.graph.temporal_analyzer import TemporalAnalyzer
from navisv.graph.sva_aligner import SVAAligner

UART_DIR = '/tmp/UART-Implementation/TCL/UART_Controller/RTL/'


def main():
    print("=" * 70)
    print("时序关系分析 + SVA 对齐检查")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix='navisv_temporal_') as od:
        dd = DesignDriver(
            [UART_DIR + 'uart_controller.sv'],
            output_dir=od,
            include_dirs=[UART_DIR]
        )
        dd.build()
        dg = dd.design_graph

        ta = TemporalAnalyzer(dg)
        aligner = SVAAligner(dg)

        print(f"\n模块: uart_controller")
        print(f"节点: {len(dg.graph.nodes)}, 边: {len(dg.graph.edges)}")

        # ============================================================
        # 1. 信号画像
        # ============================================================
        print("\n" + "=" * 70)
        print("1. 信号画像")
        print("=" * 70)

        key_signals = [
            'uart_controller.s_apb_pwrite_i',
            'uart_controller.s_apb_pwdata_i',
            'uart_controller.apb_interface.reg_wr_en_o',
            'uart_controller.uart_tx.tx_fifo_data_i',
            'uart_controller.uart_rx.uart_rx_i',
            'uart_controller.rx_fifo_data_o',
        ]

        for sig in key_signals:
            if dg.has_node(sig):
                p = ta.get_signal_profile(sig)
                kind_icon = {'Port': '📌', 'State': '📦', 'Net': '🔗'}.get(p.kind, '?')
                timing_icon = {'sequential': '⏱️', 'combinational': '⚡'}.get(p.timing, '?')
                print(f"\n  {kind_icon} {sig.split('.')[-1]}")
                print(f"    类型: {p.kind}  时序: {timing_icon} {p.timing}")
                if p.clock_domain:
                    print(f"    时钟域: {p.clock_domain.split('.')[-1]}")
                print(f"    驱动: {len(p.drivers)}  负载: {len(p.loads)}")

        # ============================================================
        # 2. 时序关系分析
        # ============================================================
        print("\n" + "=" * 70)
        print("2. 时序关系分析")
        print("=" * 70)

        pairs = [
            ('uart_controller.s_apb_pwrite_i', 'uart_controller.apb_interface.reg_wr_en_o'),
            ('uart_controller.s_apb_pwdata_i', 'uart_controller.uart_tx.tx_fifo_data_i'),
            ('uart_controller.uart_rx.uart_rx_i', 'uart_controller.rx_fifo_data_o'),
            ('uart_controller.apb_interface.reg_wr_en_o', 'uart_controller.uart_tx.tx_fifo_data_i'),
        ]

        for src, dst in pairs:
            if not (dg.has_node(src) and dg.has_node(dst)):
                continue

            rel = ta.get_temporal_relation(src, dst)
            src_name = src.split('.')[-1]
            dst_name = dst.split('.')[-1]

            rel_icon = {
                'combinational': '⚡',
                'conditional': '🔀',
            }.get(rel.relation, '⏱️' if 'sequential' in rel.relation else '❓')

            print(f"\n  {rel_icon} {src_name} → {dst_name}")
            print(f"    关系: {rel.relation}")
            print(f"    延迟: {rel.latency} 个时钟周期")
            if rel.clock_domain:
                print(f"    时钟域: {rel.clock_domain.split('.')[-1]}")
            if rel.condition:
                print(f"    条件: {rel.condition.split('.')[-1]}")
            if rel.path and len(rel.path) <= 6:
                path_names = [p.split('.')[-1] for p in rel.path]
                print(f"    路径: {' → '.join(path_names)}")

        # ============================================================
        # 3. 寄存器链分析
        # ============================================================
        print("\n" + "=" * 70)
        print("3. 寄存器链分析")
        print("=" * 70)

        chains = ta.find_register_chains('uart_controller.uart_rx.uart_rx_d0', max_depth=4)
        print(f"\n  从 uart_rx_d0 出发的寄存器链:")
        for chain in chains[:8]:
            names = [c.split('.')[-1] for c in chain]
            print(f"    {' → '.join(names)} ({len(chain)-1} 级)")

        # ============================================================
        # 4. SVA 对齐检查
        # ============================================================
        print("\n" + "=" * 70)
        print("4. SVA 对齐检查")
        print("=" * 70)

        for src, dst in pairs:
            if not (dg.has_node(src) and dg.has_node(dst)):
                continue

            result = aligner.check_signal_pair(src, dst)
            rel = result['relation']
            cov = result['sva_coverage']
            src_name = src.split('.')[-1]
            dst_name = dst.split('.')[-1]

            status = '✅ 已覆盖' if cov.is_covered else '❌ 未覆盖'
            print(f"\n  {src_name} → {dst_name}: {status}")

            if not cov.is_covered:
                print(f"    缺口: {cov.gap_description}")
                for s in result['suggestions']:
                    print(f"    建议 SVA:")
                    print(f"      {s['property_template']}")

        # ============================================================
        # 5. 未覆盖的时序路径
        # ============================================================
        print("\n" + "=" * 70)
        print("5. 未覆盖的时序路径 (寄存器级)")
        print("=" * 70)

        uncovered = aligner.find_uncovered_temporal_paths(min_latency=1)
        print(f"\n  找到 {len(uncovered)} 条未覆盖的时序路径")
        for p in uncovered[:15]:
            src = p['source'].split('.')[-1]
            dst = p['target'].split('.')[-1]
            print(f"    {src:25s} → {dst:25s}  latency={p['latency']}  {p['relation']}")

        # ============================================================
        # 总结
        # ============================================================
        print("\n" + "=" * 70)
        print("总结")
        print("=" * 70)
        print(f"""
时序关系分析能力:

  1. 信号画像
     - 信号类型 (Port/State/Net)
     - 时序分类 (sequential/combinational)
     - 时钟域归属
     - 驱动/负载统计

  2. 时序关系
     - 组合路径 (0 周期)
     - 寄存器路径 (N 周期)
     - 条件使能路径
     - 寄存器链追踪

  3. SVA 对齐检查
     - 检查信号对是否被 SVA 覆盖
     - 找出未覆盖的时序路径
     - 自动生成 SVA 建议

  4. 生成的 SVA 示例
     - sequential: @(posedge clk) A |-> ##N B
     - combinational: @(posedge clk) A |-> B
     - conditional: @(posedge clk) cond && A |-> B
""")


if __name__ == '__main__':
    main()
