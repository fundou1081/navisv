#!/usr/bin/env python3
# qa_test_results/run_qa.py - OpenChip QA 测试脚本 v2
# 
# 用法：
#   /usr/bin/python3 run_qa.py <design_dir> <top_module> [files...]
#
# 示例：
#   /usr/bin/python3 run_qa.py ../serv/rtl serv_decode
#   /usr/bin/python3 run_qa.py ../clacc bs_mult ../clacc/*.v
#   /usr/bin/python3 run_qa.py ../darkriscv/rtl darkriscv ../darkriscv/rtl/*.v

import sys
import os

# ---- 解决 slang ast.py 与 stdlib ast 的冲突 ----
import networkx as _nx  # noqa: F401

# ---- slang-netlist 路径 ----
SLANG_PATH = '/Users/fundou/my_dv_proj/slang-netlist/install'
sys.path.insert(0, SLANG_PATH)
sys.path.insert(0, os.path.join(SLANG_PATH, 'lib'))

# ---- navisv 路径 ----
NAVISV = '/Users/fundou/my_dv_proj/navisv'
sys.path.insert(0, NAVISV)

from navisv.graph import DesignGraph
from navisv.query import QueryService


def run_qa_test(files: list, top_module: str = None):
    """
    运行 QA 测试
    
    Args:
        files: 设计文件列表（第一个是顶层）
        top_module: 顶层模块名（可选）
    """
    print("=" * 70)
    print(f"OpenChip QA 测试")
    print("=" * 70)
    print(f"顶层文件: {files[0]}")
    if top_module:
        print(f"关注模块: {top_module}")
    print(f"文件数量: {len(files)}")
    print("=" * 70)
    
    # 构建图
    print("\n[1/5] 构建 DesignGraph...")
    try:
        graph = DesignGraph(files, enable_annotators=False)
    except Exception as e:
        print(f"ERROR: 构建失败 - {e}")
        return None
    
    nodes = len(graph.nodes())
    edges = len(graph.edges())
    
    print(f"  节点数: {nodes}")
    print(f"  边数: {edges}")
    
    # 节点类型统计
    print("\n[2/5] 节点类型统计...")
    kind_counts = {}
    instance_nodes = []
    port_nodes = []
    state_nodes = []
    
    for n in graph.nodes():
        kind = graph.get_node_kind(n)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        
        if kind == 'Instance':
            instance_nodes.append(n)
        elif kind == 'Port':
            port_nodes.append(n)
        elif kind == 'State':
            state_nodes.append(n)
    
    print(f"  Port: {len(port_nodes)}")
    print(f"  State: {len(state_nodes)}")
    print(f"  Instance: {len(instance_nodes)}")
    
    # 实例统计
    print("\n[3/5] 实例详情...")
    instantiated = []
    uninstantiated = []
    for n in instance_nodes:
        tags = graph.node_attr(n).get('tags', set())
        if 'uninstantiated' in tags:
            uninstantiated.append(n)
        else:
            instantiated.append(n)
    
    print(f"  已实例化: {len(instantiated)}")
    print(f"  未实例化: {len(uninstantiated)}")
    
    if uninstantiated:
        print(f"  ⚠️  未实例化模块（缺少依赖文件）:")
        for n in uninstantiated[:10]:
            print(f"    - {n}")
        if len(uninstantiated) > 10:
            print(f"    ... 还有 {len(uninstantiated) - 10} 个")
    
    # 边统计
    print("\n[4/5] 边详情...")
    edge_sources = {}
    for src, dst in graph.edges():
        attrs = graph.edge_attr(src, dst)
        source = attrs.get('source', 'unknown')
        edge_sources[source] = edge_sources.get(source, 0) + 1
    
    for src, cnt in sorted(edge_sources.items()):
        print(f"  {src}: {cnt}")
    
    # 查询 API 测试
    print("\n[5/5] 查询 API 测试...")
    query = QueryService(graph)
    
    api_results = {}
    
    # 测试 get_drivers
    if port_nodes:
        test_node = port_nodes[-1]
        print(f"  测试节点: {test_node}")
        
        # get_drivers
        try:
            drivers = query.get_drivers(test_node)
            api_results['get_drivers'] = {
                'input': test_node,
                'count': len(drivers),
                'success': True
            }
            print(f"  get_drivers: {len(drivers)} 个驱动")
        except Exception as e:
            api_results['get_drivers'] = {'success': False, 'error': str(e)}
            print(f"  get_drivers: ERROR - {e}")
        
        # get_loads
        try:
            loads = query.get_loads(test_node)
            api_results['get_loads'] = {
                'input': test_node,
                'count': len(loads),
                'success': True
            }
            print(f"  get_loads: {len(loads)} 个负载")
        except Exception as e:
            api_results['get_loads'] = {'success': False, 'error': str(e)}
            print(f"  get_loads: ERROR - {e}")
        
        # find_path
        if edges > 0:
            # 找一个有边的节点
            for src, dst in graph.edges():
                if src != dst:
                    try:
                        path = query.find_path(src, dst)
                        api_results['find_path'] = {
                            'src': src,
                            'dst': dst,
                            'length': len(path) if path else 0,
                            'success': True
                        }
                        print(f"  find_path: {src} -> {dst} ({len(path) if path else 0} 步)")
                        break
                    except Exception as e:
                        pass
    
    # 生成结果摘要
    print("\n" + "=" * 70)
    print("测试结果摘要")
    print("=" * 70)
    
    status = "✅ PASS" if nodes > 0 and edges > 0 else "⚠️ REVIEW"
    if nodes == 0:
        status = "❌ FAIL"
    
    print(f"状态: {status}")
    print(f"节点: {nodes}, 边: {edges}")
    print(f"实例: {len(instantiated)} 已实例化, {len(uninstantiated)} 未实例化")
    
    return {
        'files': files,
        'top_module': top_module,
        'nodes': nodes,
        'edges': edges,
        'ports': len(port_nodes),
        'states': len(state_nodes),
        'instances': len(instance_nodes),
        'instantiated': len(instantiated),
        'uninstantiated': len(uninstantiated),
        'uninstantiated_list': uninstantiated[:20],  # 限制数量
        'edge_sources': edge_sources,
        'api_results': api_results,
        'status': status
    }


def generate_markdown(results: dict, output_path: str = None):
    """生成 Markdown 格式的测试报告"""
    
    md = []
    md.append("# OpenChip QA 测试结果")
    md.append("")
    md.append(f"**日期**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"**工具**: navisv")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 测试汇总")
    md.append("")
    md.append("| 设计 | 文件数 | 节点 | 边 | 实例 | 未实例化 | 状态 |")
    md.append("|------|---------|------|-----|-------|----------|------|")
    
    # 单个结果的情况
    if 'nodes' in results:
        files_count = len(results.get('files', []))
        files_str = results.get('files', [''])[0] if files_count > 0 else ''
        design_name = os.path.basename(os.path.dirname(files_str)) if files_str else 'unknown'
        
        md.append(f"| {design_name} | {files_count} | {results['nodes']} | {results['edges']} | "
                 f"{results['instances']} | {results['uninstantiated']} | {results['status']} |")
    
    md.append("")
    md.append("---")
    md.append("")
    
    # 详细结果
    if 'nodes' in results:
        md.append("## 详细结果")
        md.append("")
        md.append(f"**顶层文件**: `{results['files'][0] if results['files'] else 'N/A'}`")
        md.append("")
        md.append("### 节点统计")
        md.append("")
        md.append(f"- 总节点数: {results['nodes']}")
        md.append(f"- Port: {results['ports']}")
        md.append(f"- State: {results['states']}")
        md.append(f"- Instance: {results['instances']}")
        md.append("")
        
        md.append("### 实例详情")
        md.append("")
        md.append(f"- 已实例化: {results['instantiated']}")
        md.append(f"- 未实例化: {results['uninstantiated']}")
        if results['uninstantiated_list']:
            md.append("")
            md.append("**未实例化模块（可能缺少依赖文件）**:")
            for inst in results['uninstantiated_list']:
                md.append(f"- `{inst}`")
        md.append("")
        
        md.append("### 边详情")
        md.append("")
        if results.get('edge_sources'):
            for src, cnt in sorted(results['edge_sources'].items()):
                md.append(f"- {src}: {cnt}")
        else:
            md.append("无")
        md.append("")
        
        md.append("### API 测试")
        md.append("")
        if results.get('api_results'):
            for api, result in results['api_results'].items():
                if result.get('success'):
                    md.append(f"- **{api}**: ✅ 成功 ({result.get('count', result.get('length', 'N/A'))})")
                else:
                    md.append(f"- **{api}**: ❌ 失败 - {result.get('error', 'unknown')}")
        else:
            md.append("未测试")
        md.append("")
    
    result_md = "\n".join(md)
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(result_md)
        print(f"\nMarkdown 报告已保存到: {output_path}")
    
    return result_md


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  /usr/bin/python3 run_qa.py <files...>")
        print("")
        print("示例:")
        print("  /usr/bin/python3 run_qa.py ../serv/rtl/serv_decode.v")
        print("  /usr/bin/python3 run_qa.py ../clacc/bs_mult.v ../clacc/*.v")
        print("  /usr/bin/python3 run_qa.py ../darkriscv/rtl/darkriscv.v ../darkriscv/rtl/*.v")
        sys.exit(1)
    
    # 从命令行参数获取文件列表
    files = sys.argv[1:]
    
    # 确定顶层模块
    top_module = None
    if len(files) > 1:
        # 如果有多个文件，尝试从文件名推断顶层模块
        top_file = files[0]
        top_module = os.path.basename(top_file).replace('.v', '').replace('.sv', '')
    
    # 运行测试
    results = run_qa_test(files, top_module)
    
    if results:
        # 生成 Markdown 报告
        design_name = results['files'][0].split('/')[-2] if results['files'] else 'unknown'
        output_dir = os.path.dirname(__file__)
        output_path = os.path.join(output_dir, f"qa_report_{design_name}.md")
        generate_markdown(results, output_path)