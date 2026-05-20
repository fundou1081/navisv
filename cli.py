#!/usr/bin/env python3
# cli.py - navisv 命令行工具

"""
navisv CLI - SystemVerilog 语义导航工具

用法：
    navisv info <file> <signal>     # 获取信号完整信息
    navisv registers <file>         # 报告所有寄存器
    navisv ast <file>               # 生成 AST JSON
    navisv tools                    # 检查依赖工具

环境变量：
    NAVISV_SLANG_BIN    slang 二进制路径
    NAVISV_NETLIST_BIN  slang-netlist 二进制路径
    NAVISV_CACHE_DIR    缓存目录

示例：
    navisv info design.sv top.clk
    navisv registers design.sv
    navisv tools
    navisv --json info design.sv top.clk
"""

import argparse
import json
import sys
import tempfile
import os

from navisv import DesignDriver
from navisv.config import check_tools


def format_signal_info(info, verbose=False):
    """格式化信号信息"""
    signal = info.get('signal', 'unknown')
    
    # 标题
    print(f"\n{'='*60}")
    print(f"信号: {signal}")
    print(f"{'='*60}")
    
    # 基本属性
    if info.get('target_kind'):
        kinds = info.get('target_kind', set())
        print(f"  类型: {', '.join(kinds) if kinds else 'unknown'}")
    
    clocks = info.get('clock_domain', set())
    if clocks:
        print(f"  时钟域: {', '.join(clocks)}")
    
    resets = info.get('reset_kind', set())
    if resets:
        print(f"  Reset类型: {', '.join(resets)}")
    
    # 驱动源
    drivers = info.get('drivers', [])
    if drivers:
        print(f"\n  驱动源 ({len(drivers)}):")
        for d in drivers[:5]:
            print(f"    - {d.get('from', 'unknown')}")
            if d.get('condition'):
                print(f"      条件: {d['condition']}")
        if len(drivers) > 5:
            print(f"    ... 还有 {len(drivers) - 5} 个")
    
    # 负载
    loads = info.get('loads', [])
    if loads:
        print(f"\n  负载 ({len(loads)}):")
        for l in loads[:5]:
            print(f"    - {l.get('to', 'unknown')}")
        if len(loads) > 5:
            print(f"    ... 还有 {len(loads) - 5} 个")
    
    # 条件列表
    conditions = info.get('conditions', [])
    if conditions:
        print(f"\n  条件 ({len(conditions)}):")
        for c in conditions[:5]:
            kind = c.get('kind', '')
            cond = c.get('condition', '')
            stmt = c.get('statement', '')
            if len(stmt) > 40:
                stmt = stmt[:40] + '...'
            print(f"    - [{kind}] {cond} → {stmt}")
        if len(conditions) > 5:
            print(f"    ... 还有 {len(conditions) - 5} 个")


def run_info(args):
    """获取信号完整信息"""
    errors = check_tools()
    if errors:
        for e in errors:
            print(f"错误: {e}", file=sys.stderr)
        return {'success': False, 'error': 'tools missing'}
    
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        dg = dd.design_graph
        
        info = dg.get_signal_info(args.signal, source=args.source or 'both')
        
        if args.json:
            print(json.dumps(info, indent=2, default=str))
        else:
            format_signal_info(info)
        
        return {'success': True, 'info': info}
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


def run_registers(args):
    """报告所有寄存器"""
    errors = check_tools()
    if errors:
        for e in errors:
            print(f"错误: {e}", file=sys.stderr)
        return {'success': False}
    
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        dg = dd.design_graph
        
        registers = []
        for sig, conds in dg._signal_conditions.items():
            kinds = set(c.get('target_kind') for c in conds if c.get('target_kind'))
            if 'register_output' in kinds:
                clocks = set(c.get('clock_domain') for c in conds if c.get('clock_domain'))
                resets = set(c.get('reset_kind') for c in conds if c.get('reset_kind'))
                registers.append({
                    'signal': sig,
                    'clock': list(clocks)[0] if clocks else '-',
                    'reset': list(resets)[0] if resets else 'none',
                })
        
        if args.json:
            print(json.dumps(registers, indent=2, default=str))
        else:
            print(f"\n寄存器列表 ({len(registers)} 个):\n")
            print(f"  {'信号':<35} {'时钟':<10} {'Reset':<8}")
            print(f"  {'-'*35} {'-'*10} {'-'*8}")
            for r in sorted(registers, key=lambda x: x['signal']):
                short = r['signal'].split('.')[-1]
                print(f"  {short:<35} {r['clock']:<10} {r['reset']:<8}")
            
            # 统计
            async_cnt = sum(1 for r in registers if r['reset'] == 'async')
            sync_cnt = sum(1 for r in registers if r['reset'] == 'sync')
            none_cnt = sum(1 for r in registers if r['reset'] == 'none')
            print(f"\n  统计: async={async_cnt}, sync={sync_cnt}, no_reset={none_cnt}")
        
        return {'success': True, 'registers': registers}
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


def run_ast(args):
    """生成 AST JSON"""
    errors = check_tools()
    if errors:
        for e in errors:
            print(f"错误: {e}", file=sys.stderr)
        return {'success': False}
    
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        
        ast_json = os.path.join(output_dir, 'ast.json')
        
        if args.json:
            with open(ast_json) as f:
                print(f.read())
        else:
            size = os.path.getsize(ast_json)
            print(f"AST 已生成: {ast_json}")
            print(f"大小: {size} bytes")
        
        return {'success': True, 'ast_json': ast_json}
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


def run_tools(args):
    """检查依赖工具"""
    from navisv.config import SLANG_BIN, NETLIST_BIN
    
    print(f"\n工具路径:")
    print(f"  SLANG_BIN: {SLANG_BIN}")
    print(f"  NETLIST_BIN: {NETLIST_BIN}")
    
    errors = check_tools()
    if errors:
        print(f"\n状态: ❌")
        for e in errors:
            print(f"  - {e}")
        return {'success': False, 'errors': errors}
    else:
        print(f"\n状态: ✅ 所有工具可用")
        return {'success': True}


def main():
    parser = argparse.ArgumentParser(
        prog='navisv',
        description='navisv - SystemVerilog 语义导航工具',
    )
    parser.add_argument('--json', '-j', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--include', '-I', action='append', help='include 目录')
    
    sub = parser.add_subparsers(dest='command', required=True)

    # navisv info <file> <signal>
    p = sub.add_parser('info', help='获取信号完整信息')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', help='信号路径')
    p.add_argument('--source', '-s', choices=['ast', 'netlist', 'both'], 
                   default='both', help='数据源')

    # navisv registers <file>
    p = sub.add_parser('registers', help='报告所有寄存器')
    p.add_argument('file', help='设计文件')

    # navisv ast <file>
    p = sub.add_parser('ast', help='生成 AST JSON')
    p.add_argument('file', help='设计文件')

    # navisv tools
    p = sub.add_parser('tools', help='检查依赖工具')

    args = parser.parse_args()

    try:
        if args.command == 'info':
            run_info(args)
        elif args.command == 'registers':
            run_registers(args)
        elif args.command == 'ast':
            run_ast(args)
        elif args.command == 'tools':
            run_tools(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()