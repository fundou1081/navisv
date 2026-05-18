#!/usr/bin/env python3
# cli.py - navisv 命令行工具
# navisv 架构 v0.8 - Phase 4

"""
navisv CLI - 面向 AI Agent 的 SystemVerilog 语义导航工具

用法：
    navisv profile <signal>           # 信号身份证
    navisv impact <signal>           # 影响范围分析
    navisv relate <a> <b>           # 两个信号的关系
    navisv find [description]        # 查找信号
    navisv sample <signal>          # 采样条件查询
    navisv --json ...               # 输出 JSON 格式

环境：
    必须使用 /usr/bin/python3（Python 3.9，slang-netlist）
"""

import argparse
import json
import sys
import os

# ---- 解决 slang ast.py 与 stdlib ast 的冲突 ----
# 在添加 slang 路径前，先让 networkx 缓存 stdlib ast
import networkx as _nx  # noqa: F401

# ---- slang-netlist 路径（必须在导入 navisv 前添加）----
SLANG_PATH = '/Users/fundou/my_dv_proj/slang-netlist/install'
sys.path.insert(0, SLANG_PATH)
sys.path.insert(0, os.path.join(SLANG_PATH, 'lib'))

# ---- 延迟导入（避免 ast 冲突）----
from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import (
    SignalProfileApp,
    ImpactAnalysisApp,
    FindSignalsApp,
    RelationshipApp,
    FsmDetectApp,
    ProtocolInferApp,
    SampleSignalApp,
)


DEFAULT_DESIGN = '/Users/fundou/my_dv_proj/opentitan/hw/ip/i2c/rtl/i2c_core.sv'


def build_graph(design_files):
    """构建 DesignGraph"""
    return DesignGraph(design_files)


def run_profile(args, query):
    """SignalProfileApp"""
    app = SignalProfileApp(query)
    r = app.run(args.signal, max_depth=args.depth)
    return r


def run_impact(args, query):
    """ImpactAnalysisApp"""
    app = ImpactAnalysisApp(query)
    r = app.run(args.signal, max_depth=args.depth)
    return r


def run_relate(args, query):
    """RelationshipApp"""
    app = RelationshipApp(query)
    r = app.run(args.signal_a, args.signal_b)
    return r


def run_find(args, query):
    """FindSignalsApp"""
    app = FindSignalsApp(query)
    r = app.run(
        description=args.description or "",
        name_pattern=args.pattern or "",
        tags=[],
        module=args.module or "",
        limit=args.limit,
    )
    return r


def run_fsm(args, query):
    """FsmDetectApp"""
    app = FsmDetectApp(query)
    r = app.run(signal=args.signal or None, module=args.module or '')
    return r


def run_protocol(args, query):
    """ProtocolInferApp"""
    app = ProtocolInferApp(query)
    r = app.run(signals=args.signals or None, pattern=args.pattern or '')
    return r


def run_sample(args, query):
    """SampleSignalApp"""
    app = SampleSignalApp(query)
    signal = args.signal or None
    module = args.module or ''
    r = app.run(signal=signal, module=module)
    return r


def print_response(r, as_json=False):
    """打印 AppResponse"""
    if as_json:
        print(json.dumps({
            'structured': r.structured,
            'summary': r.summary,
            'confidence': r.confidence,
            'experimental': r.experimental,
        }, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print(r.summary)
        print("-" * 60)
        print(f"置信度：{r.confidence}")
        if r.experimental:
            print("[实验性功能]")
        print()


def main():
    parser = argparse.ArgumentParser(
        prog='navisv',
        description='navisv - SystemVerilog 语义导航中间件',
    )
    parser.add_argument(
        '--design', '-d',
        default=DEFAULT_DESIGN,
        help=f'设计文件（默认：{DEFAULT_DESIGN}）',
    )
    parser.add_argument(
        '--json', '-j',
        action='store_true',
        help='输出 JSON 格式',
    )
    parser.add_argument(
        '--depth',
        type=int,
        default=5,
        help='fanin/fanout 追踪深度（默认：5）',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='find 命令最大返回数量（默认：20）',
    )
    parser.add_argument(
        '--module', '-m',
        default='',
        help='按模块过滤',
    )

    sub = parser.add_subparsers(dest='command', required=True)

    # navisv profile <signal>
    p = sub.add_parser('profile', help='信号身份证')
    p.add_argument('signal', help='信号路径')

    # navisv impact <signal>
    p = sub.add_parser('impact', help='影响范围分析')
    p.add_argument('signal', help='信号路径')

    # navisv relate <a> <b>
    p = sub.add_parser('relate', help='信号关系分析')
    p.add_argument('signal_a', help='信号 A')
    p.add_argument('signal_b', help='信号 B')

    # navisv find [description]
    p = sub.add_parser('find', help='信号查找')
    p.add_argument('description', nargs='?', default='', help='描述或模式')
    p.add_argument('--pattern', '-p', default='', help='名称正则')

    # navisv sample
    p = sub.add_parser('sample', help='采样条件查询')
    p.add_argument('--signal', '-s', default='', help='信号路径')
    p.add_argument('--module', '-m', default='', help='模块名（列出所有 State）')

    # navisv fsm
    p = sub.add_parser('fsm', help='FSM 检测（实验性）')
    p.add_argument('--signal', '-s', default='', help='限定起始信号')
    p.add_argument('--module', '-m', default='', help='限定模块')

    # navisv protocol
    p = sub.add_parser('protocol', help='协议推断（实验性）')
    p.add_argument('--pattern', '-p', default='', help='协议模式（如 valid/ready）')
    p.add_argument('signals', nargs='*', default=[], help='信号列表（可选）')

    args = parser.parse_args()

    # 构建图
    design_files = [args.design]
    if not os.path.exists(args.design):
        print(f"错误：设计文件不存在：{args.design}", file=sys.stderr)
        sys.exit(1)

    print(f"正在构建图：{args.design} ...", file=sys.stderr)
    graph = build_graph(design_files)
    query = QueryService(graph)
    print(f"图已构建：{graph}", file=sys.stderr)
    print(file=sys.stderr)

    # 执行命令
    try:
        if args.command == 'profile':
            r = run_profile(args, query)
        elif args.command == 'impact':
            r = run_impact(args, query)
        elif args.command == 'relate':
            r = run_relate(args, query)
        elif args.command == 'find':
            r = run_find(args, query)
        elif args.command == 'sample':
            r = run_sample(args, query)
        elif args.command == 'fsm':
            r = run_fsm(args, query)
        elif args.command == 'protocol':
            r = run_protocol(args, query)
        else:
            print(f"未知命令：{args.command}", file=sys.stderr)
            sys.exit(1)

        print_response(r, as_json=args.json)

    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        if args.json:
            print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.exit(1)
        if args.json:
            print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()