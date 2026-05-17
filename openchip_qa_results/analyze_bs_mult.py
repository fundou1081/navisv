#!/usr/bin/env python3
"""OpenChip QA 测试 - bs_mult 分析"""
import sys, os

# CRITICAL: import networkx FIRST (caches stdlib ast)
import networkx as _nx

# THEN add slang paths
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')
sys.path.insert(0, '/Users/fundou/my_dv_proj/navisv')

from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import SignalProfileApp

path = '/Users/fundou/my_dv_proj/clacc/bs_mult.v'
print(f"Building graph for {path}...")
graph = DesignGraph([path])
print(f"Graph: {graph}")
query = QueryService(graph)
app = SignalProfileApp(query)

print(f"\nNodes ({len(graph.nodes())}):")
for n in graph.nodes():
    a = graph.node_attr(n)
    print(f"  {n}: name={a.get('name','')}, tags={a.get('tags',set())}")

print(f"\nEdges ({len(graph.edges())}):")
for s, d in graph.edges():
    a = graph.edge_attr(s, d)
    print(f"  {s} -> {d}: rel={a.get('relation')}, timing={a.get('timing')}")

print("\n=== Signal Profiles ===")
for n in graph.nodes():
    r = app.run(n)
    print(f"\n{n}:")
    print(f"  drivers: {[d.id for d in r.structured['drivers']]}")
    print(f"  loads: {[l.id for l in r.structured['loads']]}")
    print(f"  summary: {r.summary}")
    print(f"  confidence: {r.confidence}")