#!/usr/bin/env python3
"""
场景 3: 从 RTL 自动生成 Coverage

给定一个 RTL hierarchy，自动分析并生成:
1. Control Path Covergroup — FSM 状态、条件分支
2. Data Path Covergroup   — 值范围、位宽、特殊值

用法:
    python3 examples/generate_coverage.py [sv_file]
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv import DesignDriver

SV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coverage_gen_target.sv')


def get_width(attr):
    """获取信号位宽 (正确处理 msb/lsb 顺序)"""
    raw = attr.get('bit_width', (0, 0))
    msb, lsb = max(raw), min(raw)
    return msb - lsb + 1, msb, lsb


def generate_coverage(dg, module_prefix):
    """生成完整 Coverage 代码"""
    
    # 分类信号
    all_nodes = [n for n in dg.graph.nodes if n.startswith(module_prefix)]
    
    ports_in = []
    ports_out = []
    data_regs = []
    fsm_regs = []
    nets = []
    
    for n in all_nodes:
        attr = dg.node_attr(n)
        kind = attr.get('kind', '')
        direction = attr.get('direction', '')
        width, msb, lsb = get_width(attr)
        name = n.split('.')[-1]
        
        if kind == 'Port' and direction == 'In':
            ports_in.append((name, width, msb, lsb))
        elif kind == 'Port' and direction == 'Out':
            ports_out.append((name, width, msb, lsb))
        elif kind == 'State':
            if 2 <= width <= 5:  # FSM 状态
                fsm_regs.append((name, width, msb, lsb))
            else:  # 数据寄存器
                data_regs.append((name, width, msb, lsb))
        elif kind == 'Net':
            nets.append((name, width, msb, lsb))
    
    lines = []
    lines.append(f"// 自动生成的 Coverage 代码")
    lines.append(f"// 源模块: {module_prefix}")
    lines.append(f"//")
    lines.append(f"// Control Path: {len(fsm_regs)} FSM + {len(ports_in)} 输入条件")
    lines.append(f"// Data Path:    {len(ports_in)} 输入 + {len(data_regs)} 寄存器 + {len(ports_out)} 输出")
    lines.append(f"")
    
    # ================================================================
    # Control Path Covergroup
    # ================================================================
    lines.append(f"    // ============================================================")
    lines.append(f"    // Control Path Coverage")
    lines.append(f"    // 覆盖 FSM 状态、条件分支、控制信号")
    lines.append(f"    // ============================================================")
    lines.append(f"")
    lines.append(f"    covergroup cg_control @(posedge clk);")
    
    # FSM 状态覆盖
    for name, width, msb, lsb in fsm_regs:
        lines.append(f"")
        lines.append(f"        // FSM: {name} [{msb}:{lsb}] ({width}-bit, {2**width} 状态)")
        lines.append(f"        cp_{name}: coverpoint {name} {{")
        for i in range(2**width):
            lines.append(f"            bins s{i} = {{{width}'d{i}}};")
        lines.append(f"        }}")
    
    # 控制信号覆盖 (1-bit 输入)
    ctrl_signals = [(n, w, m, l) for n, w, m, l in ports_in if w == 1 and n not in ('clk', 'rst_n')]
    for name, width, msb, lsb in ctrl_signals:
        lines.append(f"")
        lines.append(f"        // 控制信号: {name}")
        lines.append(f"        cp_{name}: coverpoint {name} {{")
        lines.append(f"            bins inactive = {{0}};")
        lines.append(f"            bins active   = {{1}};")
        lines.append(f"        }}")
    
    # 条件覆盖 (从 DesignGraph 分析)
    for name, width, msb, lsb in fsm_regs:
        full_path = f"{module_prefix}.{name}"
        cov = dg.get_condition_coverage(full_path)
        conds = cov.get('conditions', [])
        if conds:
            lines.append(f"")
            lines.append(f"        // {name} 的条件分支:")
            for c in conds[:4]:
                cond_str = c.get('condition', '?')
                lines.append(f"        //   {cond_str}")
    
    lines.append(f"    endgroup")
    
    # ================================================================
    # Data Path Covergroup
    # ================================================================
    lines.append(f"")
    lines.append(f"    // ============================================================")
    lines.append(f"    // Data Path Coverage")
    lines.append(f"    // 覆盖数据值范围、边界值、特殊值")
    lines.append(f"    // ============================================================")
    lines.append(f"")
    lines.append(f"    covergroup cg_data_path @(posedge clk);")
    
    # 输入端口覆盖
    for name, width, msb, lsb in ports_in:
        if name in ('clk', 'rst_n'):
            continue  # 跳过时钟和复位
        
        lines.append(f"")
        lines.append(f"        // 输入: {name} [{msb}:{lsb}] ({width}-bit)")
        lines.append(f"        cp_{name}: coverpoint {name} {{")
        
        if width == 1:
            lines.append(f"            bins low  = {{0}};")
            lines.append(f"            bins high = {{1}};")
        elif width <= 8:
            max_val = (1 << width) - 1
            mid = 1 << (width - 1)
            lines.append(f"            bins zero     = {{0}};")
            lines.append(f"            bins one      = {{1}};")
            lines.append(f"            bins low      = {{[2:{mid-1}]}};")
            lines.append(f"            bins mid      = {{[{mid}:{max_val-1}]}};")
            lines.append(f"            bins max      = {{{max_val}}};")
            # 特殊值
            lines.append(f"            bins alt_aa   = {{{min(0xAA, max_val)}}};  // 1010_1010")
            lines.append(f"            bins alt_55   = {{{min(0x55, max_val)}}};  // 0101_0101")
            if max_val >= 128:
                lines.append(f"            bins msb_set  = {{[{mid}:{max_val}]}};  // MSB=1")
        elif width <= 16:
            max_val = (1 << width) - 1
            mid = 1 << (width - 1)
            lines.append(f"            bins zero   = {{0}};")
            lines.append(f"            bins low    = {{[1:{mid-1}]}};")
            lines.append(f"            bins high   = {{[{mid}:{max_val-1}]}};")
            lines.append(f"            bins max    = {{{max_val}}};")
        else:
            lines.append(f"            bins zero = {{0}};")
            lines.append(f"            bins max  = {{{width}'h{'f'*((width+3)//4)}}};")
        
        lines.append(f"        }}")
    
    # 数据寄存器覆盖
    for name, width, msb, lsb in data_regs:
        lines.append(f"")
        lines.append(f"        // 寄存器: {name} [{msb}:{lsb}] ({width}-bit)")
        lines.append(f"        cp_{name}: coverpoint {name} {{")
        
        if width <= 8:
            max_val = (1 << width) - 1
            mid = 1 << (width - 1)
            lines.append(f"            bins zero     = {{0}};")
            lines.append(f"            bins one      = {{1}};")
            lines.append(f"            bins low      = {{[2:{mid-1}]}};")
            lines.append(f"            bins mid      = {{[{mid}:{max_val-1}]}};")
            lines.append(f"            bins max      = {{{max_val}}};")
            lines.append(f"            bins boundary = {{{max_val}}};  // 边界值")
        else:
            lines.append(f"            bins zero = {{0}};")
            lines.append(f"            bins max  = {{{width}'h{'f'*((width+3)//4)}}};")
        
        lines.append(f"        }}")
    
    # 输出端口覆盖
    for name, width, msb, lsb in ports_out:
        lines.append(f"")
        lines.append(f"        // 输出: {name} [{msb}:{lsb}] ({width}-bit)")
        lines.append(f"        cp_{name}: coverpoint {name} {{")
        
        if width == 1:
            lines.append(f"            bins low  = {{0}};")
            lines.append(f"            bins high = {{1}};")
        elif width <= 8:
            max_val = (1 << width) - 1
            mid = 1 << (width - 1)
            lines.append(f"            bins zero = {{0}};")
            lines.append(f"            bins low  = {{[1:{mid-1}]}};")
            lines.append(f"            bins high = {{[{mid}:{max_val-1}]}};")
            lines.append(f"            bins max  = {{{max_val}}};")
        else:
            lines.append(f"            bins zero = {{0}};")
            lines.append(f"            bins max  = {{{width}'h{'f'*((width+3)//4)}}};")
        
        lines.append(f"        }}")
    
    # error 信号
    error_signals = [(n, w, m, l) for n, w, m, l in all_nodes if 'error' in n.lower() and dg.node_attr(f"{module_prefix}.{n}").get('kind') == 'State']
    for name, width, msb, lsb in error_signals:
        if width == 1:
            lines.append(f"")
            lines.append(f"        // 错误信号: {name}")
            lines.append(f"        cp_{name}: coverpoint {name} {{")
            lines.append(f"            bins no_error = {{0}};")
            lines.append(f"            bins error    = {{1}};")
            lines.append(f"        }}")
    
    lines.append(f"    endgroup")
    
    # ================================================================
    # Cross Coverage
    # ================================================================
    lines.append(f"")
    lines.append(f"    // ============================================================")
    lines.append(f"    // Cross Coverage")
    lines.append(f"    // 覆盖控制×数据的组合")
    lines.append(f"    // ============================================================")
    lines.append(f"")
    lines.append(f"    covergroup cg_cross @(posedge clk);")
    
    # FSM × cmd 交叉
    if fsm_regs:
        fsm_name = fsm_regs[0][0]
        cmd_signals = [(n, w, m, l) for n, w, m, l in ports_in if 'cmd' in n.lower()]
        
        lines.append(f"")
        lines.append(f"        // FSM 状态 × 命令")
        lines.append(f"        cp_{fsm_name}: coverpoint {fsm_name};")
        
        if cmd_signals:
            cmd_name = cmd_signals[0][0]
            lines.append(f"        cp_{cmd_name}: coverpoint {cmd_name};")
            lines.append(f"        cx_{fsm_name}_{cmd_name}: cross cp_{fsm_name}, cp_{cmd_name};")
        
        # FSM × valid
        valid_signals = [(n, w, m, l) for n, w, m, l in ports_in if 'valid' in n.lower()]
        if valid_signals:
            lines.append(f"")
            lines.append(f"        // FSM 状态 × valid")
            lines.append(f"        cp_valid: coverpoint {valid_signals[0][0]};")
            lines.append(f"        cx_{fsm_name}_valid: cross cp_{fsm_name}, cp_valid;")
    
    # valid × ready 握手
    valid_sigs = [(n, w, m, l) for n, w, m, l in ports_in if 'valid' in n.lower()]
    ready_sigs = [(n, w, m, l) for n, w, m, l in all_nodes if 'ready' in n.lower() and dg.node_attr(f"{module_prefix}.{n}").get('kind') == 'State']
    
    if valid_sigs and ready_sigs:
        lines.append(f"")
        lines.append(f"        // valid × ready 握手")
        lines.append(f"        cp_v: coverpoint {valid_sigs[0][0]};")
        lines.append(f"        cp_r: coverpoint {ready_sigs[0][0]};")
        lines.append(f"        cx_handshake: cross cp_v, cp_r;")
    
    lines.append(f"    endgroup")
    
    return lines, {
        'fsm_regs': fsm_regs,
        'data_regs': data_regs,
        'ports_in': ports_in,
        'ports_out': ports_out,
    }


def main():
    sv_file = sys.argv[1] if len(sys.argv) > 1 else SV_FILE
    
    print("=" * 70)
    print("📝 RTL → Coverage 自动生成")
    print("=" * 70)
    
    with tempfile.TemporaryDirectory(prefix='navisv_cg_') as od:
        dd = DesignDriver([sv_file], output_dir=od)
        dd.build()
        dg = dd.design_graph
        
        modules = set()
        for n in dg.graph.nodes:
            parts = n.split('.')
            if len(parts) >= 2:
                modules.add(parts[0])
        module_prefix = list(modules)[0]
        
        print(f"\n模块: {module_prefix}")
        print(f"节点: {len(dg.graph.nodes)}, 边: {len(dg.graph.edges)}")
        
        # 生成 Coverage
        lines, info = generate_coverage(dg, module_prefix)
        
        print(f"\n{'='*70}")
        print(f"📝 生成的 Covergroup 代码")
        print(f"{'='*70}\n")
        print('\n'.join(lines))
        
        # 保存
        out_file = sv_file.replace('.sv', '_coverage.sv')
        with open(out_file, 'w') as f:
            f.write('\n'.join(lines))
        print(f"\n✅ 已保存到: {out_file}")
        
        # 分析报告
        print(f"\n{'='*70}")
        print(f"📊 分析报告")
        print(f"{'='*70}")
        
        print(f"\n  Control Path:")
        print(f"    FSM 状态: {len(info['fsm_regs'])} 个")
        for name, width, msb, lsb in info['fsm_regs']:
            print(f"      {name:15s} [{msb}:{lsb}] {width}-bit  → {2**width} 状态 bins")
        
        ctrl_signals = [(n, w, m, l) for n, w, m, l in info['ports_in'] if w == 1 and n not in ('clk', 'rst_n')]
        print(f"    控制信号: {len(ctrl_signals)} 个")
        for name, width, msb, lsb in ctrl_signals:
            print(f"      {name:15s} 1-bit  → 2 bins (active/inactive)")
        
        print(f"\n  Data Path:")
        print(f"    输入端口: {len(info['ports_in'])} 个")
        for name, width, msb, lsb in info['ports_in']:
            if name in ('clk', 'rst_n'):
                continue
            if width <= 8:
                print(f"      {name:15s} [{msb}:{lsb}] {width}-bit  → zero/one/low/mid/max/alt")
            else:
                print(f"      {name:15s} [{msb}:{lsb}] {width}-bit  → zero/max")
        
        print(f"    数据寄存器: {len(info['data_regs'])} 个")
        for name, width, msb, lsb in info['data_regs']:
            if width <= 8:
                print(f"      {name:15s} [{msb}:{lsb}] {width}-bit  → zero/one/low/mid/max/boundary")
            else:
                print(f"      {name:15s} [{msb}:{lsb}] {width}-bit  → zero/max")
        
        print(f"    输出端口: {len(info['ports_out'])} 个")
        for name, width, msb, lsb in info['ports_out']:
            print(f"      {name:15s} [{msb}:{lsb}] {width}-bit  → zero/low/high/max")


if __name__ == '__main__':
    main()
