# navisv

> 基于 slang-netlist 的 SystemVerilog 语义导航工具

navisv 将底层网表关系转化为面向调试的结构化答案，让 AI Agent 能够直接查询和高效探索 SystemVerilog 设计。

## 功能特性

- **信号分析**: 获取信号的驱动源、负载、条件列表
- **时序属性**: 自动识别 clock_domain、reset_kind、target_kind
- **寄存器报告**: 列出所有寄存器及其时序属性
- **条件覆盖**: 分析信号的所有条件组合

## 快速开始

### Python API

```python
from navisv import DesignDriver

# 构建设计图
dd = DesignDriver(['design.sv'])
dd.build()
dg = dd.design_graph

# 获取信号完整信息
info = dg.get_signal_info('top.clk', source='both')
print(info)

# 获取信号的所有条件
conds = dg.get_all_conditions('top.data_out')
for c in conds:
    print(f"  条件: {c['condition']}, 类型: {c['kind']}")
```

### CLI

```bash
# 获取信号信息
/usr/bin/python3 cli.py info design.sv top.clk

# 列出所有寄存器
/usr/bin/python3 cli.py registers design.sv

# 检查工具状态
/usr/bin/python3 cli.py tools

# JSON 输出
/usr/bin/python3 cli.py --json info design.sv top.clk
```

## 架构

```
User / AI Agent
     ↓
DesignDriver          # 统一入口，调用 slang 生成 AST/Netlist
     ↓
┌────────────────────────────────┐
│  Parsers                       │  ← AST/Netlist JSON 解析
│    ├── ast_parser.py           │
│    └── netlist_parser.py       │
└────────────────────────────────┘
     ↓
┌────────────────────────────────┐
│  Graph Layer                   │  ← NetworkX 图构建
│    ├── graph_builder.py       │
│    └── design_graph.py         │
└────────────────────────────────┘
     ↓
slang / slang-netlist            # 单一数据源
```

### 核心模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 配置层 | `navisv/config.py` | 工具路径、环境变量 |
| 驱动层 | `navisv/drivers/` | DesignDriver/SlangDriver/NetlistDriver |
| 解析层 | `navisv/parsers/` | AST/Netlist JSON 解析 |
| 图层 | `navisv/graph/` | 图构建、查询 API |

## 配置

依赖工具路径通过环境变量配置：

```bash
export NAVISV_SLANG_BIN=~/my_dv_proj/slang/slang
export NAVISV_NETLIST_BIN=~/my_dv_proj/slang-netlist/build/tools/driver/slang-netlist
export NAVISV_CACHE_DIR=~/.cache/navisv
```

或使用 Python：

```python
from navisv.config import SLANG_BIN, NETLIST_BIN
print(SLANG_BIN)  # 当前路径
```

## 项目结构

```
navisv/
├── FEATURE_PLAN.md          # P2/P3 功能规划
├── README.md                # 本文件
├── cli.py                   # 命令行入口
├── navisv/
│   ├── __init__.py
│   ├── config.py            # 配置层
│   ├── drivers/
│   │   ├── design_driver.py  # 统一入口
│   │   ├── slang_driver.py   # AST 生成
│   │   └── netlist_driver.py # Netlist 生成
│   ├── graph/
│   │   ├── design_graph.py  # 查询 API
│   │   └── graph_builder.py # 图构建
│   └── parsers/
│       ├── ast_parser.py    # AST 解析
│       └── netlist_parser.py # Netlist 解析
└── docs/
    ├── DRIVER_CAPABILITIES.md
    └── ...
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `navisv info <file> <signal>` | 获取信号完整信息 |
| `navisv conditions <file> <signal>` | 获取信号的所有条件 |
| `navisv registers <files...>` | 列出所有寄存器 |
| `navisv ast <file>` | 生成 AST JSON |
| `navisv analyze <files...>` | 完整分析 |
| `navisv tools` | 检查依赖工具 |

## 环境要求

- Python 3.9+
- slang (编译好的二进制)
- slang-netlist (编译好的二进制)

## 开发

```bash
# 检查工具
/usr/bin/python3 cli.py tools --check

# 运行测试
/usr/bin/python3 -m pytest navisv/tests/ -v
```