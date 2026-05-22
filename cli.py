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



def run_check(args):
    """检查源码编译状态"""
    from navisv.drivers import SlangDriver
    
    # 处理 filelist 参数
    if args.filelist:
        result = SlangDriver.compile_check(
            filelist=args.filelist,
            include_dirs=args.include or [],
            std=args.std or '1800-2017',
            top=args.top,
            ignore_unknown_modules=args.ignore_unknown,
        )
    else:
        files = args.file if isinstance(args.file, list) else [args.file]
        result = SlangDriver.compile_check(
            files=files,
            include_dirs=args.include or [],
            std=args.std or '1800-2017',
            top=args.top,
            ignore_unknown_modules=args.ignore_unknown,
        )
    
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result['success']:
            print("\n✅ 编译检查通过 (error=0, warning={warning})".format(warning=result['warning_count']))
        else:
            print("\n❌ 编译检查失败")
            print(f"   error: {result['error_count']}, warning: {result['warning_count']}")
            
            if result['errors']:
                print("\n   错误详情:")
                for e in result['errors'][:10]:
                    file = e.get('file', '')
                    line = e.get('line', '?')
                    # 简化文件路径显示
                    if '/' in file:
                        file = file.split('/')[-1]
                    msg = e.get('message', '')[:60]
                    print(f"     {file}:{line} - {msg}")
                
                if len(result['errors']) > 10:
                    print(f"     ... 还有 {len(result['errors']) - 10} 个错误")
    
    return result


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

    # navisv trace <file> <src> <dst>
    p = sub.add_parser('trace', help='路径追踪')
    p.add_argument('file', help='设计文件')
    p.add_argument('src', help='起始信号')
    p.add_argument('dst', help='目标信号')

    # navisv batch-trace <file> <path1> <path2> ...
    p = sub.add_parser('batch-trace', help='批量路径追踪')
    p.add_argument('file', help='设计文件')
    p.add_argument('paths', nargs='+', help='路径对，格式: src->dst')

    # navisv timing <file>
    p = sub.add_parser('timing', help='时序报告')
    p.add_argument('file', help='设计文件')
    p.add_argument('--format', '-f', choices=['text', 'markdown', 'json'], help='输出格式')

    # navisv fanout <file> <signal>
    p = sub.add_parser('fanout', help='Fan-out 时序分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', help='信号路径')

    # navisv coverage <file> [signal]
    p = sub.add_parser('coverage', help='条件覆盖率分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', nargs='?', help='信号路径 (省略则批量分析)')

    # navisv dot <file>
    p = sub.add_parser('dot', help='DOT 导出')
    p.add_argument('file', help='设计文件')
    p.add_argument('--subgraph', '-s', help='子图过滤模式 (如 module.*)')
    p.add_argument('--output', '-o', help='输出文件路径')

    # navisv check <file> or <filelist>
    p = sub.add_parser('check', help='检查源码编译状态')
    p.add_argument('file', nargs='*', help='设计文件 (可多个, 或与 -F 互斥)')
    p.add_argument('--filelist', '-F', help='filelist 文件路径')
    p.add_argument('--std', '-s', help='语言标准 (1800-2017, 1800-2023, latest)')
    p.add_argument('--top', '-t', help='顶层模块名')
    p.add_argument('--ignore-unknown', '-i', action='store_true', help='忽略未知模块')

    # navisv fanin-cone <file> <signal>
    p = sub.add_parser('fanin-cone', help='Fan-in 锥分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', help='信号路径')
    p.add_argument('--depth', '-d', type=int, help='深度 (默认 3)')

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
        elif args.command == 'check':
            run_check(args)
        elif args.command == 'trace':
            run_trace(args)
        elif args.command == 'batch-trace':
            run_batch_trace(args)
        elif args.command == 'timing':
            run_timing(args)
        elif args.command == 'fanout':
            run_fanout(args)
        elif args.command == 'coverage':
            run_coverage(args)
        elif args.command == 'dot':
            run_dot(args)
        elif args.command == 'fanin-cone':
            run_fanin_cone(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()

# ========== 新增 CLI 命令 ==========

def run_trace(args):
    """路径追踪"""
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
        
        result = dg.trace_full_path(args.src, args.dst)
        
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result['success']:
                print(f"\n路径: {' → '.join([n['signal'].split('.')[-1] for n in result['path']])}")
                print(f"成功: ✅")
                print(f"寄存器数: {result['summary'].get('register_count', 0)}")
                print(f"跨时钟域: {result['summary'].get('cross_clock', False)}")
                conf = result['summary'].get('path_confidence', {})
                if conf:
                    print(f"置信度: {conf.get('score', 0):.3f}")
            else:
                print(f"\n路径追踪失败 ❌")
                print(f"  from: {args.src}")
                print(f"  to: {args.dst}")
        
        return result
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_batch_trace(args):
    """批量路径追踪"""
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
        
        # 解析路径对
        path_specs = []
        for pair in args.paths:
            parts = pair.split('->')
            if len(parts) == 2:
                path_specs.append((parts[0].strip(), parts[1].strip()))
        
        result = dg.trace_paths_batch(path_specs)
        
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            summary = result['summary']
            print(f"\n批量路径追踪结果:")
            print(f"  总路径数: {summary['total_paths']}")
            print(f"  成功: {summary['successful_paths']}")
            print(f"  失败: {summary['failed_paths']}")
            
            for i, p in enumerate(result['paths']):
                status = "✅" if p['success'] else "❌"
                src_short = p['from'].split('.')[-1]
                dst_short = p['to'].split('.')[-1]
                if p['success']:
                    conf = p['summary'].get('path_confidence', {}).get('score', '?')
                    print(f"  {status} {src_short} → {dst_short} (conf={conf})")
                else:
                    print(f"  {status} {src_short} → {dst_short}")
        
        return result
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_timing(args):
    """时序报告"""
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
        
        report = dg.generate_timing_report(format=args.format or 'text')
        
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            if args.format == 'markdown':
                md = dg._generate_markdown_report(report)
                print(md)
            else:
                print(report.get('report_text', ''))
        
        return report
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_fanout(args):
    """Fan-out 时序分析"""
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
        
        loads = dg.get_loads_with_timing(args.signal)
        
        if args.json:
            print(json.dumps(loads, indent=2, default=str))
        else:
            print(f"\n信号 {args.signal.split('.')[-1]} 的 fan-out ({len(loads)} 负载):\n")
            
            # 分类
            registers = [l for l in loads if l['timing'].get('target_kind') == 'register_output']
            combinational = [l for l in loads if l['timing'].get('target_kind') == 'combinational']
            cross_clock = [l for l in loads if l.get('cross_clock')]
            
            print(f"  寄存器负载: {len(registers)}")
            print(f"  组合逻辑负载: {len(combinational)}")
            print(f"  跨时钟域: {len(cross_clock)}")
            
            if loads:
                print(f"\n  负载详情:")
                for l in loads[:10]:
                    tgt = l['signal'].split('.')[-1]
                    clk = l['timing'].get('clock_domain', '?')
                    clk_short = clk.split('.')[-1] if clk else '?'
                    kind = l['timing'].get('target_kind', '?')
                    cc = " ⚠️ CDC" if l.get('cross_clock') else ""
                    print(f"    → {tgt} [{clk_short}] {kind}{cc}")
                
                if len(loads) > 10:
                    print(f"    ... 还有 {len(loads) - 10} 个")
        
        return {'success': True, 'loads': loads}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_coverage(args):
    """条件覆盖率分析"""
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
        
        if args.signal:
            # 单信号分析
            coverage = dg.get_condition_coverage(args.signal)
            
            if args.json:
                print(json.dumps(coverage, indent=2, default=str))
            else:
                sig = args.signal.split('.')[-1]
                print(f"\n信号 {sig} 的条件覆盖率:")
                print(f"  总条件数: {coverage['total_conditions']}")
                
                s = coverage['coverage_summary']
                print(f"  if: {s.get('if', 0)}, case: {s.get('case', 0)}, plain: {s.get('plain', 0)}, ternary: {s.get('ternary', 0)}")
                
                if coverage['conditions']:
                    print(f"\n  条件详情:")
                    for c in coverage['conditions']:
                        kind = c['kind']
                        cond = c['condition'][:30] if c['condition'] else ''
                        stmt = c['statement'][:40] if c['statement'] else ''
                        print(f"    [{kind}] {cond} → {stmt}")
                
                if coverage['warnings']:
                    print(f"\n  警告:")
                    for w in coverage['warnings']:
                        print(f"    ⚠️ {w}")
        else:
            # 批量分析
            analysis = dg.analyze_condition_coverage()
            
            if args.json:
                print(json.dumps(analysis, indent=2, default=str))
            else:
                print(f"\n条件覆盖率批量分析:")
                print(f"  总信号数: {analysis['total_signals']}")
                print(f"  总条件数: {analysis['total_conditions']}")
                print(f"  有冗余的信号: {analysis['signals_with_redundancy']}")
                print(f"  可能有死代码的信号: {len(analysis['dead_code_signals'])}")
                
                if analysis['dead_code_signals']:
                    print(f"\n  死代码风险信号:")
                    for sig in analysis['dead_code_signals'][:5]:
                        print(f"    - {sig.split('.')[-1]}")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_dot(args):
    """DOT 导出"""
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
        
        dot = dg.export_to_dot(subgraph=args.subgraph)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(dot)
            print(f"\nDOT 已导出: {args.output}")
        elif args.json:
            print(dot)
        else:
            lines = dot.split('\n')
            print(f"\nDOT 内容 ({len(lines)} 行):")
            for line in lines[:30]:
                print(f"  {line}")
            if len(lines) > 30:
                print(f"  ... 还有 {len(lines) - 30} 行")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_fanin_cone(args):
    """Fan-in 锥分析"""
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
        
        depth = args.depth or 3
        cone = dg.get_fanin_cone(args.signal, depth=depth)
        
        if args.json:
            print(json.dumps(list(cone), indent=2))
        else:
            sig = args.signal.split('.')[-1]
            print(f"\n信号 {sig} 的 fan-in 锥 (深度 {depth}):")
            print(f"  影响信号数: {len(cone)}")
            for s in sorted(cone)[:20]:
                print(f"    ← {s.split('.')[-1]}")
            if len(cone) > 20:
                print(f"    ... 还有 {len(cone) - 20} 个")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)

# ========== 注册新命令到 main() ==========

# 在 main() 函数的 subparsers 定义之后添加:

