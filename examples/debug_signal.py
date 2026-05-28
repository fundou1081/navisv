#!/usr/bin/env python3
"""
Debug 实战案例：RTL 信号异常排查

场景：仿真发现 pipeline_data 的值异常
目标：追踪信号来源和影响范围，定位问题根因

用法:
    python3 examples/debug_signal.py [signal_name]
    
    默认调试信号: debug_demo.pipeline_data
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_scenario.sv')
DEFAULT_SIGNAL = 'debug_demo.pipeline_data'


def debug_signal(dg, signal):
    """对指定信号进行全面 Debug 分析"""
    
    print("=" * 70)
    print(f"🔍 Debug 信号: {signal}")
    print("=" * 70)
    
    # 检查信号是否存在
    if not dg.has_node(signal):
        # 尝试模糊匹配
        matches = dg.find_nodes(f'*{signal}*')
        if matches:
            print(f"\n⚠️ 信号 '{signal}' 不存在，找到相似信号:")
            for m in sorted(matches):
                print(f"  → {m}")
            signal = matches[0]
            print(f"\n使用: {signal}")
        else:
            print(f"\n❌ 信号 '{signal}' 不存在，且无相似信号")
            return
    
    attr = dg.node_attr(signal)
    print(f"\n📋 基本属性:")
    print(f"  路径:     {signal}")
    print(f"  类型:     {attr.get('kind', '?')}")
    print(f"  位宽:     [{attr.get('bit_width', (0,0))[0]}:{attr.get('bit_width', (0,0))[1]}]")
    print(f"  模块:     {attr.get('module', '?')}")
    print(f"  位置:     {attr.get('location', {})}")
    print(f"  时序:     {attr.get('timing', '?')}")
    
    # ============================================================
    # 1. 向后追踪：谁影响这个信号？
    # ============================================================
    print(f"\n{'='*70}")
    print(f"⬅️  向后追踪：谁影响这个信号？")
    print(f"{'='*70}")
    
    # 直接驱动
    drivers = list(set(dg.get_drivers(signal)))
    print(f"\n  直接驱动 ({len(drivers)}):")
    for d in sorted(drivers):
        kind = dg.node_attr(d).get('kind', '?')
        print(f"    ← {d}  [{kind}]")
    
    # Fan-in cone (所有上游信号)
    fanin = dg.get_fanin_cone(signal, depth=5)
    print(f"\n  Fan-in cone ({len(fanin)} 个上游信号):")
    
    # 按模块分组
    fanin_by_module = {}
    for f in sorted(fanin):
        parts = f.rsplit('.', 1)
        module = parts[0] if len(parts) > 1 else '(top)'
        fanin_by_module.setdefault(module, []).append(f)
    
    for module, signals in sorted(fanin_by_module.items()):
        print(f"\n    [{module}]")
        for s in signals:
            attr_s = dg.node_attr(s)
            kind = attr_s.get('kind', '?')
            direction = attr_s.get('direction', '')
            marker = "📌" if kind == 'Port' else "  "
            print(f"    {marker} {s.split('.')[-1]:20s}  [{kind} {direction}]")
    
    # 找到模块端口 (影响链的起点)
    print(f"\n  📌 影响此信号的模块端口:")
    input_ports = dg.get_input_ports()
    affecting_ports = []
    for port in input_ports:
        port_fanout = dg.get_fanout_cone(port, depth=5)
        if signal in port_fanout:
            affecting_ports.append(port)
    
    if affecting_ports:
        for port in sorted(affecting_ports):
            print(f"    ← {port}")
            # 追踪路径
            r = dg.trace_path(port, signal)
            if r.get('success'):
                path = r.get('path', [])
                print(f"      路径 ({len(path)} 跳):")
                for p in path:
                    print(f"        {p.get('path', '')}")
    else:
        print(f"    (无直接端口影响，信号由内部逻辑驱动)")
    
    # ============================================================
    # 2. 向前追踪：这个信号影响谁？
    # ============================================================
    print(f"\n{'='*70}")
    print(f"➡️  向前追踪：这个信号影响谁？")
    print(f"{'='*70}")
    
    # 直接负载
    loads = list(set(dg.get_loads(signal)))
    print(f"\n  直接负载 ({len(loads)}):")
    for l in sorted(loads):
        kind = dg.node_attr(l).get('kind', '?')
        print(f"    → {l}  [{kind}]")
    
    # Fan-out cone (所有下游信号)
    fanout = dg.get_fanout_cone(signal, depth=5)
    print(f"\n  Fan-out cone ({len(fanout)} 个下游信号):")
    
    # 按模块分组
    fanout_by_module = {}
    for f in sorted(fanout):
        parts = f.rsplit('.', 1)
        module = parts[0] if len(parts) > 1 else '(top)'
        fanout_by_module.setdefault(module, []).append(f)
    
    for module, signals in sorted(fanout_by_module.items()):
        print(f"\n    [{module}]")
        for s in signals:
            attr_s = dg.node_attr(s)
            kind = attr_s.get('kind', '?')
            direction = attr_s.get('direction', '')
            marker = "📌" if kind == 'Port' else "  "
            print(f"    {marker} {s.split('.')[-1]:20s}  [{kind} {direction}]")
    
    # 找到模块端口 (影响链的终点)
    print(f"\n  📌 此信号影响的模块端口:")
    # 输出端口 + 输出方向的 State
    output_signals = []
    for n in dg.graph.nodes:
        attr_n = dg.node_attr(n)
        kind = attr_n.get('kind', '')
        direction = attr_n.get('direction', '')
        if (kind == 'Port' and direction == 'Out') or \
           (kind == 'State' and n.split('.')[-1] in ('result', 'flag')):
            output_signals.append(n)
    
    affected_ports = []
    for port in output_signals:
        port_fanin = dg.get_fanin_cone(port, depth=5)
        if signal in port_fanin:
            affected_ports.append(port)
    
    if affected_ports:
        for port in sorted(affected_ports):
            print(f"    → {port}")
            # 追踪路径
            r = dg.trace_path(signal, port)
            if r.get('success'):
                path = r.get('path', [])
                print(f"      路径 ({len(path)} 跳):")
                for p in path:
                    print(f"        {p.get('path', '')}")
    else:
        print(f"    (信号不影响任何输出端口)")
    
    # ============================================================
    # 3. 条件分析：什么条件下信号变化？
    # ============================================================
    print(f"\n{'='*70}")
    print(f"📊 条件分析：什么条件下信号变化？")
    print(f"{'='*70}")
    
    # 条件覆盖
    coverage = dg.get_condition_coverage(signal)
    conditions = coverage.get('conditions', [])
    if conditions:
        print(f"\n  条件 ({len(conditions)}):")
        for c in conditions:
            print(f"    • {c.get('condition', '?')}  [{c.get('kind', '?')}]")
    else:
        print(f"\n  (无条件驱动)")
    
    # 相关信号的条件
    for driver in drivers[:3]:
        d_coverage = dg.get_condition_coverage(driver)
        d_conditions = d_coverage.get('conditions', [])
        if d_conditions:
            print(f"\n  驱动信号 {driver.split('.')[-1]} 的条件:")
            for c in d_conditions:
                print(f"    • {c.get('condition', '?')}  [{c.get('kind', '?')}]")
    
    # ============================================================
    # 4. 汇总：Debug 建议
    # ============================================================
    print(f"\n{'='*70}")
    print(f"💡 Debug 建议")
    print(f"{'='*70}")
    
    print(f"\n  1. 检查输入端口值:")
    for port in affecting_ports:
        print(f"     • {port}")
    
    print(f"\n  2. 检查直接驱动信号值:")
    for d in sorted(drivers):
        print(f"     • {d}")
    
    print(f"\n  3. 检查条件信号值:")
    for c in conditions:
        print(f"     • {c.get('condition', '?')}")
    
    print(f"\n  4. 受影响的输出:")
    for port in sorted(affected_ports):
        print(f"     • {port}")
    
    # 检查是否有寄存器 (时序路径)
    registers = dg.get_registers()
    related_regs = [r for r in registers if r in fanin or r == signal]
    if related_regs:
        print(f"\n  5. 相关寄存器 (检查时钟和复位):")
        for r in sorted(related_regs):
            print(f"     • {r}")


def main():
    signal = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIGNAL
    
    print("📦 构建设计图...")
    with tempfile.TemporaryDirectory(prefix='navisv_debug_') as od:
        dd = DesignDriver([SV_FILE], output_dir=od)
        dd.build()
        
        dg = dd.design_graph
        print(f"   节点: {len(dg.graph.nodes)}, 边: {len(dg.graph.edges)}")
        
        debug_signal(dg, signal)
        
        # 如果指定了额外信号，也分析
        if len(sys.argv) > 2:
            for sig in sys.argv[2:]:
                print("\n")
                debug_signal(dg, sig)


if __name__ == '__main__':
    main()
