#!/usr/bin/env python3
# cli.py - navisv 命令行工具
# navisv 架构 v0.9 (JSON-based)

"""
navisv CLI - 面向 AI Agent 的 SystemVerilog 语义导航工具

用法：
    navisv analyze <file>              # 分析设计
    navisv registers <file>           # 报告寄存器
    navisv fanin <file> <signal>     # 扇入分析
    navisv fanout <file> <signal>    # 扇出分析
    navisv find <file> <pattern>     # 查找节点
    navisv dot <file> [output.dot]   # 导出 DOT 图

环境：
    必须使用 /usr/bin/python3（Python 3.9）
"""

import argparse
import json
import sys

from navisv.drivers import SlangDriver, NetlistDriver


def run_analyze(args):
    """分析设计并生成 JSON"""
    driver = NetlistDriver(
        args.files,
        include_dirs=args.include or [],
        top=args.top,
    )
    result = driver.run()
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result['success']:
            print(f"✓ 分析成功: {result['netlist_json']}")
            print(f"  JSON 大小: {result['json_size']} bytes")
        else:
            print(f"✗ 分析失败")
            print(result['stderr'])
    
    return result


def run_registers(args):
    """报告寄存器"""
    driver = NetlistDriver(args.files, top=args.top)
    result = driver.run_report_registers()
    
    if result['success']:
        print(f"找到 {len(result['registers'])} 个寄存器：")
        for reg in result['registers']:
            print(f"  {reg['name']}")
    
    return result


def run_fanin(args):
    """扇入分析"""
    driver = NetlistDriver(args.files, top=args.top)
    result = driver.run_fan_in(args.signal)
    
    if result['success']:
        print(f"信号 {args.signal} 的扇入：")
        for sig in result['fan_in']:
            print(f"  {sig}")
    
    return result


def run_fanout(args):
    """扇出分析"""
    driver = NetlistDriver(args.files, top=args.top)
    result = driver.run_fan_out(args.signal)
    
    if result['success']:
        print(f"信号 {args.signal} 的扇出：")
        for sig in result['fan_out']:
            print(f"  {sig}")
    
    return result


def run_find(args):
    """查找节点"""
    driver = NetlistDriver(args.files, top=args.top)
    result = driver.run_find(args.pattern)
    
    if result['success']:
        print(f"找到 {result['count']} 个节点：")
        for node in result['nodes']:
            print(f"  {node}")
    
    return result


def run_dot(args):
    """导出 DOT"""
    driver = NetlistDriver(args.files, top=args.top)
    result = driver.run_dot(args.output or None)
    
    if result['success']:
        print(f"✓ DOT 已导出: {result['dot_file']}")
    
    return result


def run_ast(args):
    """生成 AST JSON"""
    driver = SlangDriver(
        args.files,
        include_dirs=args.include or [],
        top=args.top,
        source_info=True,
    )
    result = driver.run(scope=args.scope)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result['success']:
            print(f"✓ AST 生成成功: {result['ast_json']}")
            print(f"  JSON 大小: {result['json_size']} bytes")
            if args.scope:
                print(f"  Scope: {args.scope}")
            print(f"  错误: {result['error_count']}, 警告: {result['warning_count']}")
        else:
            print(f"✗ AST 生成失败")
            print(result['stderr'])
    
    return result


def main():
    parser = argparse.ArgumentParser(
        prog='navisv',
        description='navisv - SystemVerilog 语义导航中间件',
    )
    parser.add_argument('--json', '-j', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--top', '-t', help='顶层模块')
    parser.add_argument('--include', '-I', action='append', help='include 目录')
    
    sub = parser.add_subparsers(dest='command', required=True)

    # navisv analyze <files...>
    p = sub.add_parser('analyze', help='分析设计')
    p.add_argument('files', nargs='+', help='设计文件')

    # navisv registers <files...>
    p = sub.add_parser('registers', help='报告寄存器')
    p.add_argument('files', nargs='+', help='设计文件')

    # navisv fanin <files...> <signal>
    p = sub.add_parser('fanin', help='扇入分析')
    p.add_argument('files', nargs='+', help='设计文件')
    p.add_argument('signal', help='信号路径')

    # navisv fanout <files...> <signal>
    p = sub.add_parser('fanout', help='扇出分析')
    p.add_argument('files', nargs='+', help='设计文件')
    p.add_argument('signal', help='信号路径')

    # navisv find <files...> <pattern>
    p = sub.add_parser('find', help='查找节点')
    p.add_argument('files', nargs='+', help='设计文件')
    p.add_argument('pattern', help='通配符模式 (*, ?)')

    # navisv dot <files...> [output.dot]
    p = sub.add_parser('dot', help='导出 DOT')
    p.add_argument('files', nargs='+', help='设计文件')
    p.add_argument('output', nargs='?', help='输出文件')

    # navisv ast <files...>
    p = sub.add_parser('ast', help='生成 AST JSON')
    p.add_argument('files', nargs='+', help='设计文件')
    p.add_argument('--scope', '-s', help='限定 AST 范围')

    args = parser.parse_args()

    try:
        if args.command == 'analyze':
            run_analyze(args)
        elif args.command == 'registers':
            run_registers(args)
        elif args.command == 'fanin':
            run_fanin(args)
        elif args.command == 'fanout':
            run_fanout(args)
        elif args.command == 'find':
            run_find(args)
        elif args.command == 'dot':
            run_dot(args)
        elif args.command == 'ast':
            run_ast(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()