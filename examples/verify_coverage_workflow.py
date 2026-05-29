#!/usr/bin/env python3
"""
navisv 验证覆盖工作流

使用方式:
    python3 examples/verify_coverage_workflow.py <design.sv> [-m MODULE] [--high-risk-only]

工作流程:
    1. navisv risk        → 找出 critical/high 风险信号
    2. navisv verify-map  → 检查这些信号有没有被 SVA 或 CoverGroup 覆盖
    3. 输出待验证清单      → "这 N 个关键信号完全没有覆盖"

示例:
    python3 examples/verify_coverage_workflow.py uart_controller.sv -I ./RTL/
    python3 examples/verify_coverage_workflow.py top.sv -m top --high-risk-only
"""

import sys
import os
import argparse
import json
import subprocess
import tempfile

# ── 内部 import ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from navisv import DesignDriver
from navisv.graph.risk_analyzer import RiskAnalyzer, export_risk_json
from navisv.graph.verify_mapper import VerifyMapper, export_verify_json


def run_cmd(cmd, cwd=None):
    """执行 CLI 命令，返回 stdout"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return result.stdout, result.stderr


def analyze_risk(design_path, module_prefix, include_dirs, limit=20):
    """执行 risk 分析，返回高风险信号列表"""
    # cwd 固定为 navisv 目录,这样 CLI 能找到
    navisv_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inc_opt = f'-I "{include_dirs}"' if include_dirs else ''
    mod_opt = f'-m {module_prefix}' if module_prefix else ''
    cmd = f'python3 cli.py {inc_opt} --json risk "{design_path}" {mod_opt} -n {limit}'
    stdout, stderr = run_cmd(cmd, cwd=navisv_dir)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"[risk] JSON 解析失败:\n{stderr[:200]}")
        return None, None

    nodes = data.get('nodes', [])
    critical_paths = data.get('critical_paths', [])
    graph_metrics = data.get('graph_metrics', {})

    # 过滤 critical + high
    high_risk = [n for n in nodes if n.get('risk_level') in ('critical', 'high')]
    return high_risk, {
        'summary': data.get('summary', {}),
        'critical_paths': critical_paths,
        'graph_metrics': graph_metrics
    }


def analyze_verify_map(design_path, module_prefix, include_dirs, limit=50):
    """执行 verify-map 分析，返回未覆盖信号列表"""
    navisv_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inc_opt = f'-I "{include_dirs}"' if include_dirs else ''
    mod_opt = f'-m {module_prefix}' if module_prefix else ''
    cmd = f'python3 cli.py {inc_opt} --json verify-map "{design_path}" {mod_opt} -n {limit}'
    stdout, stderr = run_cmd(cmd, cwd=navisv_dir)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"[verify-map] JSON 解析失败:\n{stderr[:200]}")
        return None

    return data


def main():
    parser = argparse.ArgumentParser(
        description='navisv 验证覆盖工作流: risk 分析 → 覆盖缺口检测',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python3 examples/verify_coverage_workflow.py uart_controller.sv -I ./RTL/
    python3 examples/verify_coverage_workflow.py top.sv -m top --high-risk-only
        """
    )
    parser.add_argument('design', help='设计文件 (.sv)')
    parser.add_argument('-I', '--include', default='', help='include 目录')
    parser.add_argument('-m', '--module', default='', help='模块前缀 (省略则自动检测)')
    parser.add_argument('-n', '--limit', type=int, default=20, help='高风险信号显示数量 (默认: 20)')
    parser.add_argument('--high-risk-only', action='store_true', help='只显示 high/critical 风险信号')
    parser.add_argument('-o', '--output', default='/tmp/navisv_verify_workflow', help='输出目录 (默认: /tmp/navisv_verify_workflow)')
    parser.add_argument('--uncovered-only', action='store_true', help='只显示未覆盖信号')
    args = parser.parse_args()

    if not os.path.exists(args.design):
        print(f"错误: 文件不存在 {args.design}")
        sys.exit(1)

    include_dirs = args.include.rstrip('/')
    module = args.module if args.module else ''  # 不默认用文件名

    print("=" * 70)
    print("navisv 验证覆盖工作流")
    print("=" * 70)
    print(f"设计: {args.design}")
    print(f"模块: {module}")
    print(f"include: {include_dirs or '(无)'}")
    print()

    # ── Step 1: Risk 分析 ──────────────────────────────────────────────────
    print("⏱️ Step 1: 风险分析 (navisv risk)")
    print("-" * 40)
    high_risk, risk_meta = analyze_risk(args.design, module, include_dirs, args.limit)
    if high_risk is None:
        print("risk 分析失败, 退出")
        sys.exit(1)

    s = risk_meta['summary']
    print(f"风险分布: 🔴{s['critical_nodes']} 🟠{s['high_risk_nodes']} "
          f"🟡{s['medium_risk_nodes']} 🟢{s['low_risk_nodes']}")

    gm = risk_meta['graph_metrics']
    print(f"图规模: {gm['nodes']}N {gm['edges']}E")

    if high_risk:
        print(f"\n高风险信号 ({len(high_risk)} 个):")
        print(f"  {'信号':30s} {'综合':>6s} {'功能':>6s} {'时序':>6s} {'等级':8s} 风险因素")
        for n in sorted(high_risk, key=lambda x: -x['total_score'])[:args.limit]:
            factors = n.get('func_factors', [])[:2]
            print(f"  {n['signal']:30s} {n['total_score']:>6.1f} "
                  f"{n['func_complexity']:>6.1f} {n['timing_complexity']:>6.1f} "
                  f"{n['risk_level']:8s}  {', '.join(factors)}")

    # 关键路径
    cp = risk_meta.get('critical_paths', [])
    if cp:
        print(f"\n时序关键路径 (Top 3):")
        for i, p in enumerate(cp[:3]):
            names = [n.split('.')[-1] for n in p['path']]
            print(f"  {i+1}: {' → '.join(names)} (深度={p['depth']})")

    print()

    # ── Step 2: Verify-Map 覆盖缺口检测 ──────────────────────────────────
    print("🔍 Step 2: 覆盖缺口检测 (navisv verify-map)")
    print("-" * 40)
    verify_data = analyze_verify_map(args.design, module, include_dirs, 100)
    if verify_data is None:
        print("verify-map 分析失败, 跳过 Step 2")
        verify_data = {}

    vm_summary = verify_data.get('summary', {})
    uncovered_signals = [n for n in verify_data.get('nodes', [])
                         if n.get('verify_status') == 'uncovered']
    sva_only = [n for n in verify_data.get('nodes', [])
               if n.get('verify_status') == 'sva_only']
    cg_only = [n for n in verify_data.get('nodes', [])
               if n.get('verify_status') == 'cg_only']
    dual_covered = [n for n in verify_data.get('nodes', [])
                    if n.get('verify_status') == 'dual_covered']

    print(f"覆盖状态分布:")
    print(f"  🔴 未覆盖: {len(uncovered_signals)}")
    print(f"  🟡 仅 SVA: {len(sva_only)}")
    print(f"  🔵 仅 CG:  {len(cg_only)}")
    print(f"  🟢 双覆盖: {len(dual_covered)}")

    print()

    # ── Step 3: 关键信号覆盖缺口分析 ──────────────────────────────────────
    print("📋 Step 3: 高风险信号覆盖状态")
    print("-" * 40)

    # 收集高风险信号名
    risk_signal_names = set()
    for n in high_risk:
        # 用 signal 字段和 full_path 匹配
        risk_signal_names.add(n['signal'])
        risk_signal_names.add(n.get('full_path', ''))

    # 在 verify_data 中查找覆盖状态
    if verify_data.get('nodes'):
        covered_count = 0
        uncovered_count = 0
        sva_only_count = 0
        cg_only_count = 0
        uncovered_detail = []

        for n in verify_data['nodes']:
            sig = n.get('signal', '')
            full = n.get('full_path', '')
            # 检查是否是高风险信号
            is_risk = any(r in sig or r in full for r in risk_signal_names)
            if not is_risk and args.high_risk_only:
                continue

            status = n.get('verify_status', 'unknown')
            if status == 'uncovered':
                uncovered_count += 1
                if is_risk:
                    uncovered_detail.append(n)
            elif status == 'sva_only':
                sva_only_count += 1
            elif status == 'cg_only':
                cg_only_count += 1
            elif status == 'dual_covered':
                covered_count += 1

        print(f"高风险信号覆盖状态:")
        print(f"  🟢 已覆盖 (双覆盖): {covered_count}")
        print(f"  🟡 仅 SVA:         {sva_only_count}")
        print(f"  🔵 仅 CG:          {cg_only_count}")
        print(f"  🔴 未覆盖:         {uncovered_count}")

        # 未覆盖的高风险信号清单
        if uncovered_detail:
            print(f"\n🚨 未覆盖的高风险信号 ({len(uncovered_detail)} 个, 需优先补验证):")
            print(f"  {'信号':35s} {'风险等级':10s} {'综合分':>8s}")
            for n in sorted(uncovered_detail, key=lambda x: -x.get('total_score', 0))[:20]:
                print(f"  {n['signal']:35s} {n.get('risk_level',''):10s} {n.get('total_score', 0):>8.1f}")
        elif uncovered_count > 0:
            print(f"\n🚨 还有 {uncovered_count} 个高风险信号未覆盖,但不在 top {args.limit} 中")

    # ── Step 4: 输出未覆盖清单 ─────────────────────────────────────────────
    print()
    print("📋 Step 4: 待验证清单")
    print("-" * 40)

    if uncovered_signals:
        if args.uncovered_only:
            target = uncovered_signals
        else:
            target = uncovered_detail if uncovered_detail else uncovered_signals

        output_file = args.output + '_uncovered.txt'
        with open(output_file, 'w') as f:
            f.write(f"# navisv 验证覆盖工作流\n")
            f.write(f"# 设计: {args.design}\n")
            f.write(f"# 生成时间: \n")
            f.write(f"# 总计: {len(target)} 个未覆盖信号\n")
            f.write(f"\n")
            f.write(f"{'# 信号':<35} {'覆盖状态':<15} {'风险等级':<10}\n")
            f.write(f"{'#' + '='*60}\n")
            for n in target:
                f.write(f"{n['signal']:<35} {n.get('verify_status',''):<15} {n.get('risk_level',''):<10}\n")
        print(f"已保存到: {output_file}")

        # 也输出 JSON
        json_file = args.output + '_uncovered.json'
        with open(json_file, 'w') as f:
            json.dump(target, f, indent=2, ensure_ascii=False)
        print(f"JSON: {json_file}")

        # 汇总统计
        print(f"\n汇总:")
        print(f"  未覆盖信号总数: {len(uncovered_signals)}")
        print(f"  高风险未覆盖:   {len(uncovered_detail)}")
        if len(uncovered_detail) > 0:
            print(f"\n建议:")
            print(f"  1. 为以上 {len(uncovered_detail)} 个高风险信号优先添加 SVA assertion")
            print(f"  2. 关键数据路径建议同时添加 CoverGroup 覆盖点")
            print(f"  3. 参考 docs/verification_coverage_analysis.md 了解更多")
        else:
            print(f"\n✅ 所有高风险信号已覆盖，继续用 sva-align 检查时序一致性")
    else:
        print("✅ 所有分析信号已覆盖 (或有 SVA 或有 CoverGroup)")

    print()
    print("=" * 70)
    print("工作流完成")
    print("=" * 70)


if __name__ == '__main__':
    main()