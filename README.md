# navisv

> Semantic navigation middleware for AI debugging agents, built on slang-netlist.

navisv translates low-level netlist relationships into structured, debugging-oriented answers, enabling AI Agents to directly query and efficiently explore SystemVerilog designs.

## Architecture

```
User / AI Agent
     ↓
App Layer          ← Scenario apps: compose queries, generate natural language summaries
     ↓
Query Layer        ← Atomic queries: operate on DiGraph, return structured data
     ↓
Graph Layer        ← Data holder: networkx DiGraph is the only storage
     ↓
slang-netlist      ← Single source of truth: precise driver/load / path tracking
```

## Features

**App Layer**（生成自然语言摘要）：
| App | 说明 |
|-----|------|
| SignalProfileApp | 信号身份证 |
| ImpactAnalysisApp | 影响范围分析 |
| FindSignalsApp | 信号查找 |
| RelationshipApp | 关系分析 |
| FsmDetectApp | FSM 检测（实验性）|
| ProtocolInferApp | 协议推断（实验性）|

**Query Layer**（纯结构化数据）：
- `get_drivers` / `get_loads`：驱动源与负载
- `find_path`：路径查找
- `fanin_cone` / `fanout_cone`：逻辑锥
- `search_signals`：信号搜索
- `scc_analysis`：强连通分量

## Quick Start

**Python API**：
```python
from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import SignalProfileApp

# Build graph from SystemVerilog sources
graph = DesignGraph(["design.sv"])
query = QueryService(graph)
app = SignalProfileApp(query)
result = app.run("design.top.clk_i")
print(result.summary)
```

**CLI**：
```bash
/usr/bin/python3 cli.py profile <signal>   # 信号身份证
/usr/bin/python3 cli.py impact <signal>    # 影响范围分析
/usr/bin/python3 cli.py relate <a> <b>     # 关系分析
/usr/bin/python3 cli.py find [描述]        # 查找信号
/usr/bin/python3 cli.py --json ...         # 输出 JSON
/usr/bin/python3 cli.py fsm               # FSM 检测（实验性）
/usr/bin/python3 cli.py protocol         # 协议推断（实验性）
```

## Installation

```bash
# Required: Python 3.9 with slang-netlist
/usr/bin/python3 --version  # Should be 3.9.x

# Clone
git clone https://github.com/your-handle/navisv.git
cd navisv

# Run tests
/usr/bin/python3 -m pytest tests/ -v
```

## Key Design Principles (Iron Rules)

1. **slang-netlist is the single source of truth** — never rebuild driver/load logic
2. **networkx DiGraph is the only query interface** — no independent custom indexes
3. **Tags are sets, not enums** — signal attributes are additive
4. **Translate, don't judge** — only organize data; admit uncertainty when confidence is low
5. **Design output for Agents** — all interfaces return structured data + natural language summary
6. **Query Layer returns pure structured data** — no NL in query results
7. **App Layer is the only NL generation layer** — Query must stay clean

## Project Structure

```
navisv/
├── navisv/
│   ├── graph/           # Graph Layer: DesignGraph, StatementExplorer
│   ├── query/           # Query Layer: QueryService, models
│   └── apps/            # App Layer: SignalProfile, ImpactAnalysis, etc.
├── examples/            # Example scripts
├── tests/               # Test suite (pytest)
└── cli.py               # CLI tool
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Detailed architecture (v0.8)
- [DEVELOPMENT.md](DEVELOPMENT.md) — Development discipline and iron rules
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — Development plan and progress
- [RULES.md](RULES.md) — 25 iron rules

## Status

v0.8.0 预发布（M3 milestone）。

已验证：
- OpenTitan I2C 模块（161 nodes, 24 edges）
- 54 tests passed, 3 skipped
- 4 core apps + 2 experimental apps
- CLI fully functional