#!/usr/bin/env python3
# cli.py - navisv 命令行工具

"""
navisv CLI - SystemVerilog 语义导航工具

用法：
    navisv info <file> <signal>     # 获取信号完整信息
    navisv conditions <file> <signal>  # 获取信号条件列表
    navisv registers <file>       # 报告所有寄存器
    navisv ast <file>             # 生成 AST JSON
    navisv analyze <file>         # 完整分析

环境变量：
    NAVISV_SLANG_BIN    slang 二进制路径
    NAVISV_NETLIST_BIN  slang-netlist 二进制路径
    NAVISV_CACHE_DIR    缓存目录

示例：
    navisv info design.sv top.clk
    navisv registers design.sv
    NAVISV_SLANG_BIN=/custom/slang navisv ast design.sv
"""

import argparse
import json
import sys
import tempfile
import os

from navisv import DesignDriver
from navisv.config import check_tools


def format_signal_info(info, json_output=False):
    """格式化信号信息"""
    if json_output:
        print(json.dumps(info, indent=2, default=str))
        return
    
    signal = info.get('signal', 'unknown')
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
            loc = d.get('location', '')
            cond = d.get('condition', '')
            print(f"    - {d.get('from', 'unknown')}")
            if loc:
                print(f"      位置: {loc}")
            if cond:
                print(f"      条件: {cond}")
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
    
    # 条件
    conditions = info.get('conditions', [])
    if conditions:
        print(f"\n  条件 ({len(conditions)}):")
        for c in conditions[:5]:
            print(f"    - {c.get('condition', 'unknown')}")
            kind = c.get('kind', '')
            if kind:
                print(f"      类型: {kind}")
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
        dd = DesignDriver(args.files, output_dir=output_dir, include_dirs=args.include or [])
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


def run_conditions(args):
    """获取信号的所有条件"""
    errors = check_tools()
    if errors:
        for e in errors:
            print(f"错误: {e}", file=sys.stderr)
        return {'success': False}
    
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver(args.files, output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        dg = dd.design_graph
        
        conds = dg.get_all_conditions(args.signal)
        
        if args.json:
            print(json.dumps(conds, indent=2, default=str))
        else:
            print(f"\n信号 {args.signal} 的条件 ({len(conds)} 个):\n")
            for i, c in enumerate(conds, 1):
                print(f"  {i}. {c.get('condition', 'unknown')}")
                kind = c.get('kind', '')
                if kind:
                    print(f"     类型: {kind}")
                edges = c.get('edges', [])
                if edges:
                    print(f"     边: {edges}")
        
        return {'success': True, 'conditions': conds}
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
        dd = DesignDriver(args.files, output_dir=output_dir, include_dirs=args.include or [])
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
                    'clock': list(clocks)[0] if clocks else 'unknown',
                    'reset': list(resets)[0] if resets else 'none',
                })
        
        if args.json:
            print(json.dumps(registers, indent=2, default=str))
        else:
            print(f"\n寄存器列表 ({len(registers)} 个):\n")
            print(f"  {'信号':<30} {'时钟':<10} {'Reset':<8}")
            print(f"  {'-'*30} {'-'*10} {'-'*8}")
            for r in sorted(registers, key=lambda x: x['signal']):
                print(f"  {r['signal']:<30} {r['clock']:<10} {r['reset']:<8}")
        
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
        dd = DesignDriver(args.files, output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        
        # 输出 AST JSON 路径
        ast_json = os.path.join(output_dir, 'ast.json')
        
        if args.json:
            with open(ast_json) as f:
                print(f.read())
        else:
            print(f"AST 已生成: {ast_json}")
        
        return {'success': True, 'ast_json': ast_json}
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


def run_analyze(args):
    """完整分析"""
    errors = check_tools()
    if errors:
        for e in errors:
            print(f"错误: {e}", file=sys.stderr)
        return {'success': False}
    
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver(args.files, output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        dg = dd.design_graph
        
        stats = {
            'signals': len(dg._signal_conditions),
            'registers': sum(1 for c in dg._signal_conditions.values() 
                          if any('register_output' in str(cond.get('target_kind', '')) for cond in c)),
            'combinational': sum(1 for c in dg._signal_conditions.values()
                                if any('combinational' in str(cond.get('target_kind', '')) for cond in c)),
        }
        
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(f"\n分析结果:\n")
            print(f"  信号总数: {stats['signals']}")
            print(f"  寄存器: {stats['registers']}")
            print(f"  组合逻辑: {stats['combinational']}")
        
        return {'success': True, 'stats': stats}
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


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

    # navisv conditions <file> <signal>
    p = sub.add_parser('conditions', help='获取信号的所有条件')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', help='信号路径')

    # navisv registers <files...>
    p = sub.add_parser('registers', help='报告所有寄存器')
    p.add_argument('files', nargs='+', help='设计文件')

    # navisv ast <file>
    p = sub.add_parser('ast', help='生成 AST JSON')
    p.add_argument('file', help='设计文件')

    # navisv analyze <files...>
    p = sub.add_parser('analyze', help='完整分析')
    p.add_argument('files', nargs='+', help='设计文件')

    # navisv tools
    p = sub.add_parser('tools', help='检查依赖工具')
    p.add_argument('--check', '-c', action='store_true', help='检查工具状态')

    args = parser.parse_args()

    try:
        if args.command == 'info':
            run_info(args)
        elif args.command == 'conditions':
            run_conditions(args)
        elif args.command == 'registers':
            run_registers(args)
        elif args.command == 'ast':
            run_ast(args)
        elif args.command == 'analyze':
            run_analyze(args)
        elif args.command == 'tools':
            from navisv.config import SLANG_BIN, NETLIST_BIN, check_tools
            print(f"SLANG_BIN: {SLANG_BIN}")
            print(f"NETLIST_BIN: {NETLIST_BIN}")
            errors = check_tools()
            if errors:
                print("状态: ❌")
                for e in errors:
                    print(f"  - {e}")
            else:
                print("状态: ✅ 所有工具可用")
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()