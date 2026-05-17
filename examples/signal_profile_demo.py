#!/usr/bin/env python3
# examples/signal_profile_demo.py - SignalProfileApp 演示
# navisv 架构 v0.8 - Phase 5

"""
演示 SignalProfileApp 在 OpenTitan I2C 模块上的输出。

运行：
    /usr/bin/python3 examples/signal_profile_demo.py
"""

import sys
import os

# 1. 先导入 networkx（避免被 slang 的 ast.py 遮蔽）
import networkx as _nx  # noqa: F401

# 2. 添加 slang-netlist 路径（必须在导入 navisv 前）
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')

# 3. navisv 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import SignalProfileApp

I2C = '/Users/fundou/my_dv_proj/opentitan/hw/ip/i2c/rtl/i2c_core.sv'

print("=" * 60)
print("SignalProfileApp 演示")
print("=" * 60)
print(f"设计：{I2C}\n")

graph = DesignGraph([I2C])
query = QueryService(graph)
app = SignalProfileApp(query)

# 演示查找信号并分析
test_signals = [
    'i2c_core.scl_i',
    'i2c_core.sda_i',
    'i2c_core.reg2hw',
    'i2c_core.hw2reg',
]

for sig in test_signals:
    if not graph.has_node(sig):
        print(f"⚠  信号不存在：{sig}\n")
        continue
    print(f"🔍 分析信号：{sig}")
    print("-" * 60)
    r = app.run(sig)
    print(r.summary)
    print(f"   置信度：{r.confidence}")
    print(f"   结构化数据：")
    s = r.structured
    print(f"     - drivers：{len(s['drivers'])} 个")
    print(f"     - loads：{len(s['loads'])} 个")
    print(f"     - fanin：{s['fanin_count']} 个信号")
    print(f"     - fanout：{s['fanout_count']} 个信号")
    print()


print("=" * 60)
print("演示完成")
print("=" * 60)