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

## Key Design Principles (Iron Rules)

1. **slang-netlist is the single source of truth** — never rebuild driver/load logic
2. **networkx DiGraph is the only query interface** — no independent custom indexes
3. **Tags are sets, not enums** — signal attributes are additive, avoiding classification boundaries
4. **Translate, don't judge** — only organize data; admit uncertainty when confidence is low
5. **Design output for Agents** — all interfaces return structured data + natural language summary

## Quick Start

```python
from navisv.graph import DesignGraph
from navisv.query import QueryService
from navisv.apps import SignalProfileApp

# Build graph from SystemVerilog sources
graph = DesignGraph(["top.sv", "axi.sv"])

# Atomic queries (no natural language)
query = QueryService(graph)
drivers = query.get_drivers("top.axi.clk")

# Scenario apps (generates natural language summary)
profile_app = SignalProfileApp(query)
result = profile_app.run("top.axi.clk")
print(result.summary)  # "Signal top.axi.clk is driven by 1 source..."
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Detailed architecture (v0.8)
- [DEVELOPMENT.md](DEVELOPMENT.md) — Development discipline and iron rules
- [EXAMPLES_REVIEW.md](EXAMPLES_REVIEW.md) — slang-netlist examples review
- [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md) — Graph schema definition

## Status

Pre-production. Currently in prototype validation phase targeting OpenTitan I2C module.