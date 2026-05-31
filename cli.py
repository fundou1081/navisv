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
import shutil

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

def run_cache(args):
    """缓存管理: info / clear / sweep"""
    from navisv.drivers.cache_manager import CacheManager

    action = args.action

    if action == 'info':
        stats = CacheManager.cache_stats()
        print(f"\n=== navisv 缓存状态 ===")
        print(f"缓存目录: {stats.get('cache_dir', 'N/A')}")
        print(f"数据库:  {stats.get('db_path', 'N/A')}")
        print(f"缓存条目: {stats.get('entries', 0)}")
        size_kb = (stats.get('size_bytes', 0) or 0) // 1024
        print(f"数据大小: {size_kb} KB")
        return

    elif action == 'clear':
        count = CacheManager.clear_cache()
        print(f"\n已清除 {count} 条缓存")
        return

    elif action == 'sweep':
        count = CacheManager.sweep(max_age_days=args.days)
        print(f"\n已清除 {count} 条过期缓存 (>{args.days}天)")
        return


def main():
    parser = argparse.ArgumentParser(
        prog='navisv',
        description='navisv - SystemVerilog 语义导航工具',
    )
    parser.add_argument('--json', '-j', action='store_true', help='输出 JSON 格式 (等价于 --format json)')
    parser.add_argument('--format', '-f', choices=['text', 'json', 'dot', 'mermaid', 'all'],
                       help='输出格式: text(默认), json, dot, mermaid, all(同时生成json+图)')
    parser.add_argument('--output', '-o', help='输出文件路径 (all 模式下为目录或前缀)')
    parser.add_argument('--include', '-I', action='append', help='include 目录')
    parser.add_argument('--rankdir', '-d', choices=['LR', 'TB', 'BT', 'RL'], default='LR',
                       help='图方向: LR=左右(默认), TB=上下, BT=下上, RL=右左')
    
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

    # navisv cache [info|clear|sweep]
    p = sub.add_parser('cache', help='缓存管理')
    p.add_argument('action', nargs='?', default='info',
                   choices=['info', 'clear', 'sweep'],
                   help='info=显示统计, clear=清除所有, sweep=清除7天前')
    p.add_argument('--days', type=float, default=7, help='sweep 模式下的过期天数 (默认: 7)')

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

    # navisv fanout <file> <signal>
    p = sub.add_parser('fanout', help='Fan-out 时序分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', help='信号路径')

    # navisv coverage <file> [signal]
    p = sub.add_parser('coverage', help='条件覆盖率分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('signal', nargs='?', help='信号路径 (省略则批量分析)')

    # navisv dot <file>
    p = sub.add_parser('dot', help='DOT 导出 (模块聚类 + CDC 高亮 + 图例)')
    p.add_argument('file', help='设计文件')
    p.add_argument('--subgraph', '-s', help='子图过滤模式 (如 module.*)')
    p.add_argument('--cdc-highlight', action='store_true',
                   help='CDC 路径用粉红粗边高亮')
    p.add_argument('--no-legend', action='store_true',
                   help='隐藏图例面板')
    p.add_argument('--cluster-depth', type=int, default=2,
                   help='模块聚类深度 (默认2, 即子模块级别)')
    p.add_argument('--rankdir', choices=['LR', 'TB', 'BT', 'RL'], default='LR',
                   help='图方向 (默认 LR)')

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

    # navisv constraints <file>
    p = sub.add_parser('constraints', help='列出所有 class 和 constraint')
    p.add_argument('file', help='设计文件')
    p.add_argument('--verbose', '-v', action='store_true', help='显示约束体内容')

    # navisv cvar <file> <variable>
    p = sub.add_parser('cvar', help='Q1: 变量在哪些 constraint 中')
    p.add_argument('file', help='设计文件')
    p.add_argument('variable', help='变量路径 (如 pkg.Class.var)')
    p.add_argument('--composition', '-c', action='store_true', help='包含组合关系')
    p.add_argument('--verbose', '-v', action='store_true', help='显示约束体')

    # navisv ccons <file> <constraint>
    p = sub.add_parser('ccons', help='Q2: 约束影响哪些变量')
    p.add_argument('file', help='设计文件')
    p.add_argument('constraint', help='约束路径 (如 pkg.Class.constraint)')

    # navisv crel <file> <var1> <var2>
    p = sub.add_parser('crel', help='Q3: 两变量间的约束关系')
    p.add_argument('file', help='设计文件')
    p.add_argument('var1', help='变量1路径')
    p.add_argument('var2', help='变量2路径')

    # navisv cg-list <file>
    p = sub.add_parser('cg-list', help='列出所有 covergroup/coverpoint/bins')
    p.add_argument('file', help='设计文件')
    p.add_argument('--verbose', '-v', action='store_true', help='显示 bins 详情')

    # navisv cg-check <file> <variable> <cg> <cp>
    p = sub.add_parser('cg-check', help='bin-constraint 一致性检查')
    p.add_argument('file', help='设计文件')
    p.add_argument('variable', help='变量路径')
    p.add_argument('cg', help='covergroup 名')
    p.add_argument('cp', help='coverpoint 名')

    # navisv cg-quality <file> <variable> <cg> <cp> [--type data|control]
    p = sub.add_parser('cg-quality', help='coverage 质量评估')
    p.add_argument('file', help='设计文件')
    p.add_argument('variable', nargs='?', help='变量路径 (省略则 cg 级别评估)')
    p.add_argument('cg', nargs='?', help='covergroup 名')
    p.add_argument('cp', nargs='?', help='coverpoint 名')
    p.add_argument('--type', '-t', choices=['data', 'control'], default='data', help='信号类型')

    # navisv temporal <file> <src> <dst>
    p = sub.add_parser('temporal', help='时序关系分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('src', nargs='?', help='源信号 (省略则批量分析)')
    p.add_argument('dst', nargs='?', help='目标信号')
    p.add_argument('--depth', '-d', type=int, default=3, help='寄存器链深度')

    # navisv sva-align <file>
    p = sub.add_parser('sva-align', help='SVA 时序对齐检查')
    p.add_argument('file', help='设计文件')
    p.add_argument('--min-latency', '-l', type=int, default=1, help='最小延迟级数')
    p.add_argument('--limit', '-n', type=int, default=20, help='显示数量')

    # navisv verify-map <file>
    p = sub.add_parser('verify-map', help='模块验证覆盖率地图')
    p.add_argument('file', help='设计文件')
    p.add_argument('--module', '-m', help='模块前缀 (省略则自动检测)')
    p.add_argument('--limit', '-n', type=int, default=50, help='未覆盖信号显示数量')

    # navisv cdc <file>
    p = sub.add_parser('cdc', help='CDC 跨时钟域检测')
    p.add_argument('file', help='设计文件')
    p.add_argument('--module', '-m', help='模块前缀 (省略则自动检测)')
    p.add_argument('--limit', '-n', type=int, default=50, help='最多显示路径数')
    p.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                    help='输出格式')

    # navisv clock-stats <file>
    p = sub.add_parser('clock-stats', help='时钟/复位 fan-out 统计')
    p.add_argument('file', help='设计文件')
    p.add_argument('--module', '-m', help='模块前缀 (省略则自动检测)')
    p.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                    help='输出格式')

    # navisv eco <file>
    p = sub.add_parser('eco', help='ECO 影响分析 (diff 或 before/after)')
    p.add_argument('file', help='设计文件')
    p.add_argument('--diff', help='git diff 文件路径')
    p.add_argument('--before', help='改动前文件路径 (CDC 模式)')
    p.add_argument('--after', help='改动后文件路径 (CDC 模式)')
    p.add_argument('--mode', choices=['impact', 'cdc'], default='impact',
                    help='分析模式: impact=影响范围, cdc=CDC 变化对比')
    p.add_argument('--depth', type=int, default=3, help='最大影响深度 (默认 3)')
    p.add_argument('--include', '-I', action='append', help='include 目录')

    # navisv risk <file>
    p = sub.add_parser('risk', help='信号风险/复杂度分析')
    p.add_argument('file', help='设计文件')
    p.add_argument('--module', '-m', help='模块前缀 (省略则自动检测)')
    p.add_argument('--limit', '-n', type=int, default=20, help='高风险信号显示数量')

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
        elif args.command == 'cache':
            run_cache(args)
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
        elif args.command == 'constraints':
            run_constraints(args)
        elif args.command in ('cvar', 'ccons', 'crel'):
            run_constraint_query(args)
        elif args.command == 'cg-list':
            run_cg_list(args)
        elif args.command == 'cg-check':
            run_cg_check(args)
        elif args.command == 'cg-quality':
            run_cg_quality(args)
        elif args.command == 'temporal':
            run_temporal(args)
        elif args.command == 'sva-align':
            run_sva_align(args)
        elif args.command == 'verify-map':
            run_verify_map(args)
        elif args.command == 'cdc':
            from navisv.graph.cdc_analyzer import run_cdc as run_cdc_fn
            run_cdc_fn(args)
        elif args.command == 'clock-stats':
            from navisv.graph.clock_stats import run_clock_stats as run_clock_stats_fn
            run_clock_stats_fn(args)
        elif args.command == 'eco':
            from navisv.graph.eco_analyzer import run_eco as run_eco_fn
            run_eco_fn(args)
        elif args.command == 'risk':
            run_risk(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({'error': str(e)}))
        sys.exit(1)


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
    """DOT 导出（增强版：模块聚类 + CDC 高亮 + 图例）"""
    errors = check_tools()
    if errors:
        for e in errors:
            print(f"错误: {e}", file=sys.stderr)
        return {'success': False}
    
    from navisv.graph.graphviz_exporter import export_risk_dot
    
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, 
                         include_dirs=args.include or [], cache=True)
        dd.build()
        dg = dd.design_graph
        
        # 从 --subgraph 提取 module_prefix
        module_prefix = args.subgraph if args.subgraph else ''
        
        dot = export_risk_dot(
            dg,
            module_prefix=module_prefix,
            max_nodes=200,
            max_edges=500,
            rankdir=args.rankdir,
            cdc_highlight=args.cdc_highlight,
            show_legend=not args.no_legend,
            cluster_depth=args.cluster_depth,
        )
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(dot)
            print(f"\nDOT 已导出: {args.output}")
            print(f"  - 模块聚类: depth={args.cluster_depth}")
            print(f"  - CDC 高亮: {'是' if args.cdc_highlight else '否'}")
            print(f"  - 图例: {'显示' if not args.no_legend else '隐藏'}")
        elif args.json:
            print(dot)
        else:
            lines = dot.split('\n')
            print(f"\nDOT 内容 ({len(lines)} 行):")
            for line in lines[:50]:
                print(f"  {line}")
            if len(lines) > 50:
                print(f"  ... 还有 {len(lines) - 50} 行")
        
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


def run_constraints(args):
    """列出所有类和约束"""
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        cg = dd.constraint_graph
        if not cg:
            print('错误: ConstraintGraph 未构建', file=sys.stderr)
            return {'success': False}
        
        if args.json:
            classes = cg.get_classes()
            result = []
            for cls in classes:
                cons = cg.get_constraints_in_class(cls['full_path'])
                vars_list = cg.get_variables_in_class(cls['full_path'])
                result.append({
                    'class': cls['name'],
                    'full_path': cls['full_path'],
                    'base_class': cls.get('base_class'),
                    'variables': vars_list,
                    'constraints': cons,
                })
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            classes = cg.get_classes()
            print(f'\n类 ({len(classes)}):')
            for cls in classes:
                chain = cg.get_inheritance_chain(cls['full_path'])
                chain_str = ' -> '.join(c.split('.')[-1] for c in chain)
                print(f'  {cls["name"]}')
                if len(chain) > 1:
                    print(f'    继承: {chain_str}')
                
                vars_list = cg.get_variables_in_class(cls['full_path'])
                if vars_list:
                    print(f'    变量 ({len(vars_list)}):')
                    for v in vars_list:
                        rm = v.get('rand_mode', 'none')
                        bw = v.get('bit_width', '')
                        bw_str = f' [{bw}b]' if bw else ''
                        tc = v.get('type_class', '')
                        tc_str = f' -> {tc.split(".")[-1]}' if tc else ''
                        print(f'      {v["name"]:20s} {rm:6s}{bw_str}{tc_str}')
                
                cons = cg.get_constraints_in_class(cls['full_path'])
                if cons:
                    print(f'    约束 ({len(cons)}):')
                    for c in cons:
                        flags = []
                        if c.get('has_soft'):
                            flags.append('soft')
                        if c.get('is_conditional'):
                            flags.append('cond')
                        flag_str = f' [{",".join(flags)}]' if flags else ''
                        print(f'      {c["name"]}{flag_str}')
                        if args.verbose:
                            body = c.get('constraint_body', '')
                            for line in body.split('; '):
                                print(f'        {line}')
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_constraint_query(args):
    """Q1: 变量在哪些约束中 / Q2: 约束影响哪些变量 / Q3: 变量关系"""
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        cg = dd.constraint_graph
        if not cg:
            print('错误: ConstraintGraph 未构建', file=sys.stderr)
            return {'success': False}
        
        if args.command == 'cvar':
            # Q1: 变量在哪些约束中
            cons = cg.get_constraints_for_variable(
                args.variable,
                include_composition=args.composition,
            )
            if args.json:
                print(json.dumps(cons, indent=2, ensure_ascii=False))
            else:
                var_name = args.variable.split('.')[-1]
                print(f'\n变量 {var_name} 的约束 ({len(cons)}):')
                for c in cons:
                    cls = c['class_name'].split('.')[-1]
                    acc = f' via {c["access_path"]}' if c.get('access_path') else ''
                    br = c.get('bit_range')
                    br_str = f' [{br[0]}:{br[1]}]' if br else ''
                    cond = ' [cond]' if c.get('is_conditional') else ''
                    print(f'\n  {cls}::{c["constraint_name"]}{br_str}{cond}{acc}')
                    if c.get('context'):
                        print(f'    context: {c["context"]}')
                    if c.get('direct_exprs'):
                        for expr in c['direct_exprs']:
                            print(f'    expr: {expr}')
                    if args.verbose and c.get('constraint_body'):
                        print(f'    body: {c["constraint_body"]}')
        
        elif args.command == 'ccons':
            # Q2: 约束影响哪些变量
            vars_list = cg.get_variables_in_constraint(args.constraint)
            if args.json:
                print(json.dumps(vars_list, indent=2, ensure_ascii=False))
            else:
                cons_name = args.constraint.split('.')[-1]
                print(f'\n约束 {cons_name} 影响的变量 ({len(vars_list)}):')
                for v in vars_list:
                    acc = f' via {v["access_path"]}' if v.get('access_path') else ''
                    br = v.get('bit_range')
                    br_str = f' [{br[0]}:{br[1]}]' if br else ''
                    print(f'  {v["name"]}{br_str}{acc}')
        
        elif args.command == 'crel':
            # Q3: 变量关系
            rel = cg.get_constraint_relationship(args.var1, args.var2)
            if args.json:
                print(json.dumps(rel, indent=2, ensure_ascii=False))
            else:
                shared = rel['shared_constraints']
                print(f'\n变量关系:')
                print(f'  {args.var1.split(".")[-1]} <-> {args.var2.split(".")[-1]}')
                if shared:
                    print(f'  共享约束 ({len(shared)}):')
                    for name in shared:
                        print(f'    - {name}')
                else:
                    print(f'  无共享约束')
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_cg_list(args):
    """列出所有 covergroup/coverpoint/bins"""
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        cg = dd.covergroups
        if not cg:
            print('错误: CovergroupAnalyzer 未构建', file=sys.stderr)
            return {'success': False}
        
        if args.json:
            cgs = cg.get_covergroups()
            result = []
            for info in cgs:
                cps = cg.get_coverpoints(info['name'])
                cp_data = []
                for cp in cps:
                    bins = cg.get_bins(info['name'], cp['name'])
                    cp_data.append({**cp, 'bins': bins})
                crosses = cg.get_crosses(info['name'])
                result.append({**info, 'coverpoints': cp_data, 'crosses': crosses})
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            cgs = cg.get_covergroups()
            print(f'\nCoverGroup ({len(cgs)}):')
            for info in cgs:
                print(f'  {info["name"]} (loc={info["location"]})')
                cps = cg.get_coverpoints(info['name'])
                for cp in cps:
                    bins = cg.get_bins(info['name'], cp['name'])
                    print(f'    {cp["name"]}: {len(bins)} bins')
                    if args.verbose:
                        for b in bins:
                            kind_str = f' [{b["kind"]}]' if b['kind'] != 'Bins' else ''
                            wild = ' [wildcard]' if b.get('is_wildcard') else ''
                            deflt = ' [default]' if b.get('is_default') else ''
                            vals = ', '.join(f'{lo}:{hi}' if lo != hi else str(lo) for lo, hi in b.get('values', []))
                            print(f'      {b["name"]}{kind_str}{wild}{deflt} = {vals}')
                crosses = cg.get_crosses(info['name'])
                for c in crosses:
                    print(f'    cross {c["name"]}: {" x ".join(c["targets"])}')
                    if args.verbose and c.get('bins'):
                        for b in c['bins']:
                            print(f'      {b["name"]} [{b["kind"]}]')
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_cg_check(args):
    """bin-constraint 一致性检查"""
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        cg = dd.covergroups
        if not cg:
            print('错误: CovergroupAnalyzer 未构建', file=sys.stderr)
            return {'success': False}
        
        result = cg.check_bin_constraint_consistency(args.variable, args.cg, args.cp)
        
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            var_name = args.variable.split('.')[-1]
            print(f'\n{var_name} 的一致性检查:')
            if not result:
                print('  ✅ 无问题')
            for r in result:
                icon = '⚠️ ' if r['type'] != 'info' else 'ℹ️ '
                print(f'  {icon} {r["type"]}: {r["reason"]}')
                if r.get('range'):
                    lo, hi = r['range']
                    print(f'      range: [{lo}:{hi}]')
                if r.get('uncovered_range'):
                    ranges = ', '.join(f'[{lo}:{hi}]' for lo, hi in r['uncovered_range'])
                    print(f'      uncovered: {ranges}')
                if r.get('forbidden_range'):
                    ranges = ', '.join(f'[{lo}:{hi}]' for lo, hi in r['forbidden_range'])
                    print(f'      forbidden: {ranges}')
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_cg_quality(args):
    """coverage 质量评估"""
    output_dir = tempfile.mkdtemp(prefix='navisv_cli_')
    try:
        dd = DesignDriver([args.file], output_dir=output_dir, include_dirs=args.include or [])
        dd.build()
        cg = dd.covergroups
        if not cg:
            print('错误: CovergroupAnalyzer 未构建', file=sys.stderr)
            return {'success': False}
        
        if args.variable and args.cg and args.cp:
            # coverpoint 级别
            result = cg.check_coverage_quality(
                args.variable, args.cg, args.cp, signal_type=args.type
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                var_name = args.variable.split('.')[-1]
                score = next((r for r in result if r['type'] == 'score'), {})
                print(f'\n{var_name} 的质量评估 (score={score.get("value", "?")})')
                for r in result:
                    if r['type'] == 'warning':
                        print(f'  ⚠️  {r["reason"]}')
                    elif r['type'] == 'info':
                        print(f'  ℹ️  {r["reason"]}')
        elif args.cg:
            # covergroup 级别
            result = cg.check_cg_quality(args.cg)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                score = next((r for r in result if r['type'] == 'score'), {})
                print(f'\n{args.cg} 的质量评估 (score={score.get("value", "?")})')
                for r in result:
                    if r['type'] == 'warning':
                        print(f'  ⚠️  {r["reason"]}')
                    elif r['type'] == 'info':
                        print(f'  ℹ️  {r["reason"]}')
        else:
            print('错误: 需要指定 cg 名称', file=sys.stderr)
            return {'success': False}
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _resolve_format(args):
    """解析输出格式 (统一处理 --json 和 --format)"""
    if hasattr(args, 'format') and args.format:
        return args.format
    if hasattr(args, 'json') and args.json:
        return 'json'
    return 'text'


def _write_multi_output(json_data, mermaid_content, dot_content, args, prefix='navisv'):
    """同时输出 JSON + 图文件
    
    Args:
        json_data: dict/list JSON 数据
        mermaid_content: Mermaid 图内容
        dot_content: DOT 图内容
        args: 命令行参数
        prefix: 文件名前缀
    """
    import os
    
    output = getattr(args, 'output', None)
    
    if output:
        # 指定了输出路径
        if os.path.isdir(output):
            # 目录模式: 在目录下生成多个文件
            base = os.path.join(output, prefix)
        else:
            # 前缀模式
            base = output
        
        json_path = base + '.json'
        mmd_path = base + '.mmd'
        dot_path = base + '.dot'
        
        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False, default=str)
        with open(mmd_path, 'w') as f:
            f.write(mermaid_content)
        with open(dot_path, 'w') as f:
            f.write(dot_content)
        
        print(f'JSON:     {json_path}')
        print(f'Mermaid:  {mmd_path}')
        print(f'DOT:      {dot_path}')
    else:
        # 无输出路径: JSON 打印到 stdout，图打印到 stdout
        print('=== JSON ===')
        print(json.dumps(json_data, indent=2, ensure_ascii=False, default=str))
        print()
        print('=== Mermaid ===')
        print(mermaid_content)
        print()
        print('=== DOT ===')
        print(dot_content)


def _write_output(content, args, default_ext='.txt'):
    """写输出到文件或标准输出"""
    output = getattr(args, 'output', None)
    if output:
        with open(output, 'w') as f:
            f.write(content)
        print(f"已保存到: {output}")
    else:
        print(content)


def _export_temporal_dot(dg, relations, title='temporal'):
    """生成时序关系 DOT 图"""
    lines = []
    lines.append(f'digraph {title} {{')
    lines.append('  rankdir=LR;')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica", fontsize=10];')
    lines.append('')
    
    # 节点分类
    ports = set()
    regs = set()
    nets = set()
    for r in relations:
        src, dst = r['source'].split('.')[-1], r['target'].split('.')[-1]
        if r.get('source_kind') == 'Port':
            ports.add(src)
        elif r.get('source_kind') == 'State':
            regs.add(src)
        else:
            nets.add(src)
        if r.get('target_kind') == 'Port':
            ports.add(dst)
        elif r.get('target_kind') == 'State':
            regs.add(dst)
        else:
            nets.add(dst)
    
    for n in sorted(ports):
        lines.append(f'  "{n}" [fillcolor=lightblue, shape=parallelogram];')
    for n in sorted(regs):
        lines.append(f'  "{n}" [fillcolor=lightyellow];')
    for n in sorted(nets):
        lines.append(f'  "{n}" [fillcolor=lightgray];')
    lines.append('')
    
    # 边
    seen = set()
    for r in relations:
        src = r['source'].split('.')[-1]
        dst = r['target'].split('.')[-1]
        rel = r['relation']
        edge_key = (src, dst, rel)
        if edge_key in seen:
            continue
        seen.add(edge_key)
        
        if 'sequential' in rel:
            color = 'red'
            style = 'bold'
            label = f"seq#{r.get('latency',1)}"
        elif rel == 'combinational':
            color = 'blue'
            style = 'dashed'
            label = 'comb'
        elif rel == 'conditional':
            color = 'orange'
            style = 'bold'
            label = f"cond#{r.get('latency',1)}"
        else:
            color = 'gray'
            style = 'solid'
            label = rel
        
        lines.append(f'  "{src}" -> "{dst}" [color={color}, style={style}, label="{label}"];')
    
    lines.append('}')
    return '\n'.join(lines)


def _export_temporal_mermaid(dg, relations, title='temporal'):
    """生成时序关系 Mermaid 图"""
    lines = []
    lines.append('graph LR')
    lines.append('')
    
    # 节点分类
    ports = set()
    regs = set()
    for r in relations:
        src, dst = r['source'].split('.')[-1], r['target'].split('.')[-1]
        if r.get('source_kind') == 'Port':
            ports.add(src)
        else:
            regs.add(src)
        if r.get('target_kind') == 'Port':
            ports.add(dst)
        else:
            regs.add(dst)
    
    lines.append('  %% 输入端口')
    for n in sorted(ports):
        lines.append(f'  {n}[/{n}/]')
    lines.append('')
    lines.append('  %% 寄存器/内部信号')
    for n in sorted(regs - ports):
        lines.append(f'  {n}[{n}]')
    lines.append('')
    
    # 组合路径
    comb_edges = [(r['source'].split('.')[-1], r['target'].split('.')[-1], r.get('condition',''))
                  for r in relations if r['relation'] == 'combinational']
    if comb_edges:
        lines.append('  %% 组合路径 (0周期)')
        for src, dst, cond in comb_edges:
            label = f'comb [{cond.split(".")[-1]}]' if cond else 'comb'
            lines.append(f'  {src} -.->|{label}| {dst}')
        lines.append('')
    
    # 条件路径
    cond_edges = [(r['source'].split('.')[-1], r['target'].split('.')[-1], r.get('condition',''), r.get('latency',1))
                  for r in relations if r['relation'] == 'conditional']
    if cond_edges:
        lines.append('  %% 条件路径')
        for src, dst, cond, lat in cond_edges:
            label = f'cond#{lat} [{cond.split(".")[-1]}]' if cond else f'cond#{lat}'
            lines.append(f'  {src} ==>|{label}| {dst}')
        lines.append('')
    
    # 寄存器路径
    seq_edges = [(r['source'].split('.')[-1], r['target'].split('.')[-1], r.get('latency',1))
                 for r in relations if 'sequential' in r['relation']]
    if seq_edges:
        lines.append('  %% 寄存器路径 (N周期)')
        for src, dst, lat in seq_edges:
            lines.append(f'  {src} ==>|seq#{lat}| {dst}')
    
    return '\n'.join(lines)


def _export_sva_align_dot(uncovered, suggestions):
    """生成 SVA 对齐检查 DOT 图"""
    lines = []
    lines.append('digraph sva_alignment {')
    lines.append('  rankdir=LR;')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica", fontsize=10];')
    lines.append('')
    
    # 节点
    all_nodes = set()
    for p in uncovered:
        all_nodes.add(p['source'].split('.')[-1])
        all_nodes.add(p['target'].split('.')[-1])
    
    for n in sorted(all_nodes):
        lines.append(f'  "{n}" [fillcolor=lightyellow];')
    lines.append('')
    
    # 边 (标记未覆盖)
    seen = set()
    for p in uncovered:
        src = p['source'].split('.')[-1]
        dst = p['target'].split('.')[-1]
        edge_key = (src, dst)
        if edge_key in seen:
            continue
        seen.add(edge_key)
        
        rel = p['relation']
        lat = p['latency']
        if 'sequential' in rel:
            label = f"seq#{lat} ❌"
            color = 'red'
        elif rel == 'conditional':
            label = f"cond#{lat} ❌"
            color = 'orange'
        else:
            label = f"{rel} ❌"
            color = 'gray'
        
        lines.append(f'  "{src}" -> "{dst}" [color={color}, style=bold, label="{label}"];')
    
    lines.append('}')
    return '\n'.join(lines)


def _export_sva_align_mermaid(uncovered, suggestions):
    """生成 SVA 对齐检查 Mermaid 图"""
    lines = []
    lines.append('graph LR')
    lines.append('')
    
    # 节点
    all_nodes = set()
    for p in uncovered:
        all_nodes.add(p['source'].split('.')[-1])
        all_nodes.add(p['target'].split('.')[-1])
    
    for n in sorted(all_nodes):
        lines.append(f'  {n}[{n}]')
    lines.append('')
    
    # 边
    seen = set()
    for p in uncovered:
        src = p['source'].split('.')[-1]
        dst = p['target'].split('.')[-1]
        edge_key = (src, dst)
        if edge_key in seen:
            continue
        seen.add(edge_key)
        
        rel = p['relation']
        lat = p['latency']
        if 'sequential' in rel:
            lines.append(f'  {src} ==>|seq#{lat} ❌| {dst}')
        elif rel == 'conditional':
            lines.append(f'  {src} ==>|cond#{lat} ❌| {dst}')
        else:
            lines.append(f'  {src} -->|{rel} ❌| {dst}')
    
    return '\n'.join(lines)


def _write_output(content, args, default_ext='.txt'):
    """写输出到文件或标准输出"""
    if hasattr(args, 'output') and args.output:
        with open(args.output, 'w') as f:
            f.write(content)
        print(f"已保存到: {args.output}")
    else:
        print(content)


def run_temporal(args):
    """时序关系分析"""
    from navisv.graph.temporal_analyzer import TemporalAnalyzer
    
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
        ta = TemporalAnalyzer(dg)
        fmt = _resolve_format(args)
        
        if args.src and args.dst:
            # 单对信号分析
            if not dg.has_node(args.src):
                print(f"错误: 信号 '{args.src}' 不存在", file=sys.stderr)
                return {'success': False}
            if not dg.has_node(args.dst):
                print(f"错误: 信号 '{args.dst}' 不存在", file=sys.stderr)
                return {'success': False}
            
            rel = ta.get_temporal_relation(args.src, args.dst)
            src_attr = dg.node_attr(args.src)
            dst_attr = dg.node_attr(args.dst)
            
            json_data = {
                'source': rel.source, 'target': rel.target,
                'relation': rel.relation, 'latency': rel.latency,
                'clock_domain': rel.clock_domain, 'condition': rel.condition,
                'path': rel.path,
            }
            relations = [{
                'source': rel.source, 'target': rel.target,
                'relation': rel.relation, 'latency': rel.latency,
                'condition': rel.condition,
                'source_kind': src_attr.get('kind', ''),
                'target_kind': dst_attr.get('kind', ''),
            }]
            
            if fmt == 'all':
                _write_multi_output(json_data, _export_temporal_mermaid(dg, relations),
                    _export_temporal_dot(dg, relations), args, 'temporal_pair')
            elif fmt == 'json':
                print(json.dumps(json_data, indent=2, ensure_ascii=False))
            elif fmt == 'dot':
                _write_output(_export_temporal_dot(dg, relations), args)
            elif fmt == 'mermaid':
                _write_output(_export_temporal_mermaid(dg, relations), args)
            else:
                src_name = rel.source.split('.')[-1]
                dst_name = rel.target.split('.')[-1]
                rel_icon = {'combinational': '⚡', 'conditional': '🔀'}.get(rel.relation, '⏱️')
                print(f"\n{rel_icon} {src_name} → {dst_name}")
                print(f"  关系: {rel.relation}  延迟: {rel.latency} 个时钟周期")
                if rel.clock_domain:
                    print(f"  时钟域: {rel.clock_domain.split('.')[-1]}")
                if rel.condition:
                    print(f"  条件: {rel.condition.split('.')[-1]}")
                if rel.path and len(rel.path) <= 10:
                    path_names = [p.split('.')[-1] for p in rel.path]
                    print(f"  路径: {' → '.join(path_names)}")
                chains = ta.find_register_chains(args.src, max_depth=args.depth)
                if chains:
                    print(f"\n  寄存器链 (从 {src_name}):")
                    for chain in chains[:10]:
                        names = [c.split('.')[-1] for c in chain]
                        print(f"    {' → '.join(names)} ({len(chain)-1} 级)")
        
        elif args.src:
            if not dg.has_node(args.src):
                print(f"错误: 信号 '{args.src}' 不存在", file=sys.stderr)
                return {'success': False}
            profile = ta.get_signal_profile(args.src)
            json_data = {
                'signal': profile.signal, 'kind': profile.kind,
                'timing': profile.timing, 'clock_domain': profile.clock_domain,
                'is_register': profile.is_register,
                'drivers': profile.drivers, 'loads': profile.loads,
            }
            relations = []
            for d in profile.drivers:
                d_attr = dg.node_attr(d)
                rel = ta.get_temporal_relation(d, args.src)
                relations.append({'source': d, 'target': args.src, 'relation': rel.relation,
                    'latency': rel.latency, 'condition': rel.condition,
                    'source_kind': d_attr.get('kind', ''), 'target_kind': profile.kind})
            for l in profile.loads:
                l_attr = dg.node_attr(l)
                rel = ta.get_temporal_relation(args.src, l)
                relations.append({'source': args.src, 'target': l, 'relation': rel.relation,
                    'latency': rel.latency, 'condition': rel.condition,
                    'source_kind': profile.kind, 'target_kind': l_attr.get('kind', '')})
            
            if fmt == 'all':
                _write_multi_output(json_data, _export_temporal_mermaid(dg, relations),
                    _export_temporal_dot(dg, relations), args, f'temporal_{args.src.split(".")[-1]}')
            elif fmt == 'json':
                print(json.dumps(json_data, indent=2, ensure_ascii=False))
            elif fmt == 'dot':
                _write_output(_export_temporal_dot(dg, relations), args)
            elif fmt == 'mermaid':
                _write_output(_export_temporal_mermaid(dg, relations), args)
            else:
                kind_icon = {'Port': '📌', 'State': '📦', 'Net': '🔗'}.get(profile.kind, '?')
                timing_icon = {'sequential': '⏱️', 'combinational': '⚡'}.get(profile.timing, '?')
                print(f"\n{kind_icon} {args.src.split('.')[-1]}")
                print(f"  类型: {profile.kind}  时序: {timing_icon} {profile.timing}")
                if profile.clock_domain:
                    print(f"  时钟域: {profile.clock_domain.split('.')[-1]}")
                print(f"  驱动: {len(profile.drivers)}")
                for d in sorted(profile.drivers)[:5]:
                    print(f"    ← {d.split('.')[-1]}")
                print(f"  负载: {len(profile.loads)}")
                for l in sorted(profile.loads)[:5]:
                    print(f"    → {l.split('.')[-1]}")
                chains = ta.find_register_chains(args.src, max_depth=args.depth)
                if chains:
                    print(f"\n  寄存器链:")
                    for chain in chains[:10]:
                        names = [c.split('.')[-1] for c in chain]
                        print(f"    {' → '.join(names)} ({len(chain)-1} 级)")
        
        else:
            registers = dg.get_registers()
            json_data = []
            for reg in registers:
                profile = ta.get_signal_profile(reg)
                json_data.append({'signal': reg.split('.')[-1], 'full_path': reg,
                    'timing': profile.timing, 'clock_domain': profile.clock_domain,
                    'drivers': len(profile.drivers), 'loads': len(profile.loads)})
            relations = []
            for reg in registers:
                profile = ta.get_signal_profile(reg)
                for l in profile.loads:
                    if l in registers:
                        l_attr = dg.node_attr(l)
                        rel = ta.get_temporal_relation(reg, l)
                        if rel.relation != 'unrelated':
                            relations.append({'source': reg, 'target': l, 'relation': rel.relation,
                                'latency': rel.latency, 'condition': rel.condition,
                                'source_kind': 'State', 'target_kind': 'State'})
            
            if fmt == 'all':
                _write_multi_output(json_data, _export_temporal_mermaid(dg, relations),
                    _export_temporal_dot(dg, relations), args, 'temporal_registers')
            elif fmt == 'json':
                print(json.dumps(json_data, indent=2, ensure_ascii=False))
            elif fmt == 'dot':
                _write_output(_export_temporal_dot(dg, relations), args)
            elif fmt == 'mermaid':
                _write_output(_export_temporal_mermaid(dg, relations), args)
            else:
                print(f"\n寄存器时序画像 ({len(registers)} 个):")
                for reg in sorted(registers):
                    profile = ta.get_signal_profile(reg)
                    clock = profile.clock_domain.split('.')[-1] if profile.clock_domain else '-'
                    print(f"  {reg.split('.')[-1]:30s}  clock={clock:20s}  drivers={len(profile.drivers)}  loads={len(profile.loads)}")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def run_sva_align(args):
    """SVA 时序对齐检查"""
    from navisv.graph.temporal_analyzer import TemporalAnalyzer
    from navisv.graph.sva_aligner import SVAAligner
    
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
        
        sva_parser = None
        sva_file = args.file.replace('.sv', '_sva.sv')
        if os.path.exists(sva_file):
            from navisv.parsers.sva_parser import SVAParser
            sva_parser = SVAParser(sva_file).parse()
        
        aligner = SVAAligner(dg, sva_parser)
        fmt = _resolve_format(args)
        uncovered = aligner.find_uncovered_temporal_paths(min_latency=args.min_latency)
        
        json_data = {
            'total_uncovered': len(uncovered),
            'paths': uncovered[:args.limit],
        }
        
        # 生成 SVA 建议
        suggestions = []
        for p in uncovered[:5]:
            result = aligner.check_signal_pair(p['source'], p['target'])
            suggestions.extend(result['suggestions'])
        json_data['suggestions'] = suggestions
        
        if fmt == 'all':
            _write_multi_output(json_data, _export_sva_align_mermaid(uncovered[:args.limit], suggestions),
                _export_sva_align_dot(uncovered[:args.limit], suggestions), args, 'sva_alignment')
        elif fmt == 'json':
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
        elif fmt == 'dot':
            _write_output(_export_sva_align_dot(uncovered[:args.limit], suggestions), args)
        elif fmt == 'mermaid':
            _write_output(_export_sva_align_mermaid(uncovered[:args.limit], suggestions), args)
        else:
            print(f"\n未覆盖的时序路径 (延迟>={args.min_latency}级, 共 {len(uncovered)} 条):")
            print()
            for p in uncovered[:args.limit]:
                src = p['source'].split('.')[-1]
                dst = p['target'].split('.')[-1]
                print(f"  {src:30s} → {dst:30s}  latency={p['latency']}  {p['relation']}")
            if len(uncovered) > args.limit:
                print(f"\n  ... 还有 {len(uncovered) - args.limit} 条")
            print(f"\nSVA 建议:")
            for s in suggestions[:10]:
                print(f"  {s['property_template']}")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)




def run_verify_map(args):
    """模块验证覆盖率地图"""
    from navisv.graph.verify_mapper import VerifyMapper, export_verify_json, export_verify_dot, export_verify_mermaid
    from navisv.graph.temporal_analyzer import TemporalAnalyzer
    
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
        
        # 加载 SVA
        sva_parser = None
        sva_file = args.file.replace('.sv', '_sva.sv')
        if os.path.exists(sva_file):
            from navisv.parsers.sva_parser import SVAParser
            sva_parser = SVAParser(sva_file).parse()
        
        # 加载 CoverGroup
        cg_analyzer = dd._covergroup_analyzer
        
        # 创建 TemporalAnalyzer
        ta = TemporalAnalyzer(dg)
        
        # 创建 VerifyMapper
        mapper = VerifyMapper(dg, sva_parser, cg_analyzer, ta)
        
        # 确定模块前缀
        module_prefix = args.module
        if not module_prefix:
            # 自动检测: 取第一个模块
            for n in dg.graph.nodes:
                parts = n.split('.')
                if len(parts) >= 2:
                    module_prefix = parts[0]
                    break
        
        # 分析
        report = mapper.analyze(module_prefix)
        fmt = _resolve_format(args)
        
        json_data = export_verify_json(report)
        dot_content = export_verify_dot(report, rankdir=args.rankdir)
        mermaid_content = export_verify_mermaid(report, rankdir=args.rankdir)
        
        if fmt == 'all':
            _write_multi_output(json_data, mermaid_content, dot_content, args, 'verify_map')
        elif fmt == 'json':
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
        elif fmt == 'dot':
            _write_output(dot_content, args)
        elif fmt == 'mermaid':
            _write_output(mermaid_content, args)
        else:
            # text
            summary = json_data['summary']
            print(f"\n{'='*60}")
            print(f"模块验证覆盖率地图: {report.module}")
            print(f"{'='*60}")
            print(f"  总信号: {summary['total_signals']}")
            print(f"  SVA 覆盖: {summary['sva_covered']}")
            print(f"  Coverage 覆盖: {summary['coverage_covered']}")
            print(f"  双覆盖: {summary['both_covered']}")
            print(f"  未覆盖: {summary['neither_covered']}")
            print(f"  验证率: {summary['verify_rate']}%")
            
            # 按等级分组显示
            full = [s for s in report.signals if s.verify_level == 'full']
            sva_only = [s for s in report.signals if s.has_sva and not s.has_coverage]
            cov_only = [s for s in report.signals if s.has_coverage and not s.has_sva]
            none_list = [s for s in report.signals if s.verify_level == 'none']
            
            if full:
                print(f"\n✅ 双覆盖 ({len(full)}):")
                for s in full[:10]:
                    print(f"  {s.signal.split('.')[-1]:30s}  SVA={s.sva_properties}  CG={s.covergroups}")
            
            if sva_only:
                print(f"\n⚠️  仅SVA ({len(sva_only)}):")
                for s in sva_only[:10]:
                    print(f"  {s.signal.split('.')[-1]:30s}  SVA={s.sva_properties}")
            
            if cov_only:
                print(f"\n⚠️  仅Coverage ({len(cov_only)}):")
                for s in cov_only[:10]:
                    print(f"  {s.signal.split('.')[-1]:30s}  CG={s.covergroups}")
            
            if none_list:
                print(f"\n❌ 未覆盖 ({len(none_list)}):")
                for s in none_list[:args.limit]:
                    kind_icon = {'Port': '📌', 'State': '📦', 'Net': '🔗'}.get(s.kind, '?')
                    print(f"  {kind_icon} {s.signal.split('.')[-1]:30s}  {s.kind}  {s.timing}")
                if len(none_list) > args.limit:
                    print(f"  ... 还有 {len(none_list) - args.limit} 个")
            
            # SVA 属性列表
            if report.sva_properties:
                print(f"\nSVA 属性 ({len(report.sva_properties)}):")
                for p in report.sva_properties[:10]:
                    print(f"  {p['name']:30s}  signals={p.get('signals', [])[:3]}")
            
            # CoverGroup 列表
            if report.covergroups:
                print(f"\nCoverGroup ({len(report.covergroups)}):")
                for cg in report.covergroups:
                    print(f"  {cg['name']:30s}  cp={cg.get('coverpoint_count', 0)}  cx={cg.get('cross_count', 0)}")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)



def run_risk(args):
    """信号风险/复杂度分析"""
    from navisv.graph.risk_analyzer import RiskAnalyzer, export_risk_json, export_risk_dot, export_risk_mermaid
    
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
        
        # 确定模块前缀
        module_prefix = args.module
        if not module_prefix:
            for n in dg.graph.nodes:
                parts = n.split('.')
                if len(parts) >= 2:
                    module_prefix = parts[0]
                    break
        
        analyzer = RiskAnalyzer(dg, module_prefix)
        report = analyzer.analyze()
        fmt = _resolve_format(args)
        
        json_data = export_risk_json(report)
        dot_content = export_risk_dot(report, rankdir=args.rankdir)
        mermaid_content = export_risk_mermaid(report, rankdir=args.rankdir)
        
        if fmt == 'all':
            _write_multi_output(json_data, mermaid_content, dot_content, args, 'risk_analysis')
        elif fmt == 'json':
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
        elif fmt == 'dot':
            _write_output(dot_content, args)
        elif fmt == 'mermaid':
            _write_output(mermaid_content, args)
        else:
            # text
            gm = json_data['graph_metrics']
            print(f"\n{'='*70}")
            print(f"信号风险/复杂度分析: {report.module}")
            print(f"{'='*70}")
            print(f"  节点: {gm['nodes']}  边: {gm['edges']}")
            print(f"  强连通分量: {gm['scc_count']} (最大: {gm['scc_max_size']})")
            print(f"  是否DAG: {gm['is_dag']}")
            print(f"  平均入度: {gm['avg_in_degree']}  平均出度: {gm['avg_out_degree']}")
            print(f"  最大入度: {gm['max_in_degree']}  最大出度: {gm['max_out_degree']}")
            
            print(f"\n风险分布:")
            print(f"  🔴 关键: {report.critical_nodes}")
            print(f"  🟠 高:   {report.high_risk_nodes}")
            print(f"  🟡 中:   {report.medium_risk_nodes}")
            print(f"  🟢 低:   {report.low_risk_nodes}")
            
            # 高风险信号
            high_risk = [n for n in report.nodes if n.risk_level in ('critical', 'high')]
            if high_risk:
                print(f"\n🔴 高风险信号 (前 {min(args.limit, len(high_risk))} 个):")
                print(f"  {'信号':25s} {'综合':>6s} {'功能':>6s} {'时序':>6s} {'等级':8s} {'入度':>5s} {'出度':>5s} {'fan-in':>7s} {'位宽':>5s} {'因素'}")
                for n in high_risk[:args.limit]:
                    short = n.signal.split('.')[-1]
                    factors = ', '.join(n.func_factors[:1] + n.timing_factors[:1])
                    print(f"  {short:25s} {n.total_score:>6.1f} {n.func_complexity:>6.1f} {n.timing_complexity:>6.1f} {n.risk_level:8s} {n.in_degree:>5} {n.out_degree:>5} {n.fanin_size:>7} {n.bit_width:>5} {factors}")
            
            # 中风险信号
            med_risk = [n for n in report.nodes if n.risk_level == 'medium']
            if med_risk:
                print(f"\n🟡 中风险信号 (前 {min(10, len(med_risk))} 个):")
                print(f"  {'信号':25s} {'综合':>6s} {'功能':>6s} {'时序':>6s} {'因素'}")
                for n in med_risk[:10]:
                    short = n.signal.split('.')[-1]
                    factors = ', '.join(n.func_factors[:1] + n.timing_factors[:1])
                    print(f"  {short:25s} {n.total_score:>6.1f} {n.func_complexity:>6.1f} {n.timing_complexity:>6.1f} {factors}")
            
            # 关键路径
            if json_data.get('critical_paths'):
                print(f"\n⏱️ 时序关键路径:")
                for i, cp in enumerate(json_data['critical_paths']):
                    names = [p.split('.')[-1] for p in cp['path']]
                    print(f"  路径 {i+1}: {' → '.join(names)} (深度={cp['depth']})")
            
            # 二维分布
            print(f"\n二维分布:")
            print(f"  {'':20s} {'时序低(<40)':>12s} {'时序中(40-60)':>12s} {'时序高(≥60)':>12s}")
            func_low = [n for n in report.nodes if n.func_complexity < 40]
            func_mid = [n for n in report.nodes if 40 <= n.func_complexity < 60]
            func_high = [n for n in report.nodes if n.func_complexity >= 60]
            for label, group in [('功能低(<40)', func_low), ('功能中(40-60)', func_mid), ('功能高(≥60)', func_high)]:
                t_low = len([n for n in group if n.timing_complexity < 40])
                t_mid = len([n for n in group if 40 <= n.timing_complexity < 60])
                t_high = len([n for n in group if n.timing_complexity >= 60])
                print(f"  {label:20s} {t_low:>12} {t_mid:>12} {t_high:>12}")
        
        return {'success': True}
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
