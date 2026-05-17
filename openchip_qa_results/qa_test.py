#!/usr/bin/env python3
# openchip_qa_results/qa_test.py - OpenChip QA 测试脚本
# 用 navisv 回答来自 openchip-qa 的问题

"""
用法：
    /usr/bin/python3 openchip_qa_results/qa_test.py [项目名] [模块名]

示例：
    /usr/bin/python3 openchip_qa_results/qa_test.py clacc bs_mult
"""

import sys
import os

# ---- 解决 slang ast.py 与 stdlib ast 的冲突 ----
import networkx as _nx  # noqa: F401

# ---- slang-netlist 路径 ----
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')

# ---- navisv 路径 ----
NAVISV = '/Users/fundou/my_dv_proj/navisv'
sys.path.insert(0, NAVISV)

from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import SignalProfileApp, ImpactAnalysisApp, FindSignalsApp


def test_design(design_path: str, module_name: str = None):
    """测试一个设计"""
    print("=" * 60)
    print(f"测试设计：{design_path}")
    if module_name:
        print(f"关注模块：{module_name}")
    print("=" * 60)

    graph = DesignGraph([design_path])
    print(f"图：{graph}")
    query = QueryService(graph)
    app = SignalProfileApp(query)
    impact = ImpactAnalysisApp(query)
    finder = FindSignalsApp(query)

    print(f"\n节点数：{len(graph.nodes())}")
    print(f"边数：{len(graph.edges())}")

    # 列出所有模块
    modules = {}
    for node_id in graph.nodes():
        mod = graph.node_attr(node_id).get('module', 'unknown')
        if mod not in modules:
            modules[mod] = []
        modules[mod].append(node_id)

    print(f"\n模块数：{len(modules)}")
    for mod, nodes in sorted(modules.items()):
        print(f"  {mod}: {len(nodes)} 个节点")

    # 查找特定模块
    if module_name:
        if module_name in modules:
            print(f"\n--- {module_name} 详细信息 ---")
            signals = modules[module_name]
            print(f"节点数：{len(signals)}")
            
            # 查找端口信号
            ports = [s for s in signals if graph.node_attr(s).get('tags')]
            if ports:
                print(f"端口：{len(ports)} 个")
            
            # 列出部分信号
            print("部分信号：")
            for sig in signals[:10]:
                attrs = graph.node_attr(sig)
                name = attrs.get('name', '')
                tags = attrs.get('tags', set())
                print(f"  {sig}: name={name}, tags={tags}")

            # 分析前几个信号
            print("\n信号分析：")
            for sig in signals[:3]:
                r = app.run(sig)
                print(f"\n  {sig}:")
                print(f"    {r.summary}")
                print(f"    confidence={r.confidence}")
        else:
            print(f"\n模块 {module_name} 不在图中")

    # 如果是 bs_mult，查找相关信号
    if 'bs_mult' in module_name.lower() if module_name else 'bs_mult' in design_path.lower():
        # 查找信号
        result = finder.run(description='slice')
        if result.structured['total_found'] > 0:
            print(f"\n--- 找到 slice 相关信号 ---")
            for s in result.structured['signals'][:5]:
                print(f"  {s['id']}: {s['name']} ({s['module']})")

    print()
    return graph, query, app


if __name__ == '__main__':
    import os

    # 默认测试 clacc/bs_mult
    if len(sys.argv) > 1:
        project = sys.argv[1]
    else:
        project = 'clacc'

    project_paths = {
        'clacc': '/Users/fundou/my_dv_proj/clacc/bs_mult.v',
        'clacc_fifo': '/Users/fundou/my_dv_proj/clacc/dual_clock_fifo.v',
        'serv': '/Users/fundou/my_dv_proj/serv/serv_decode.v',
    }

    path = project_paths.get(project, project)
    if not os.path.exists(path):
        print(f"文件不存在：{path}")
        sys.exit(1)

    test_design(path, module_name=None)