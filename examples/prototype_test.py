#!/usr/bin/env python3
"""
原型验证脚本 - 测试 DesignGraph + SignalProfileApp 完整链路
必须使用 /usr/bin/python3（Python 3.9）运行
"""
import sys

# 1. 先导入 networkx（避免被 slang install 的 ast.py 遮蔽）
import networkx as nx
print('networkx:', nx.__version__)

# 2. 添加 slang-netlist 路径
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')

# 3. 添加 navisv 路径
sys.path.insert(0, '/Users/fundou/my_dv_proj/navisv')

from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import SignalProfileApp

# Test with i2c_core.sv
RTL_FILE = '/Users/fundou/my_dv_proj/opentitan/hw/ip/i2c/rtl/i2c_core.sv'
print('Building DesignGraph...')
graph = DesignGraph([RTL_FILE])
print(f'DesignGraph: {graph}')

# Test QueryService
query = QueryService(graph)
print(f'Nodes: {len(graph.nodes())}, Edges: {len(graph.edges())}')

# Show some nodes
nodes = graph.nodes()
print(f'Sample nodes: {nodes[:5]}')

# Test SignalProfileApp
app = SignalProfileApp(query)
print('Testing SignalProfileApp...')

# Test with scl_i
result = app.run('i2c_core.scl_i')
print(f'Signal: {result.structured["signal"]}')
print(f'Drivers: {len(result.structured["drivers"])}')
print(f'Loads: {len(result.structured["loads"])}')
print(f'Fanin count: {result.structured["fanin_count"]}')
print(f'Fanout count: {result.structured["fanout_count"]}')
print(f'Summary: {result.summary}')
print(f'Confidence: {result.confidence}')

# Test with a non-existent signal
result2 = app.run('i2c_core.nonexistent_signal')
print(f'Non-existent signal confidence: {result2.confidence}')

print('ALL OK!')