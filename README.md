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

## CLI 输出示例

### navisv info

```bash
$ /usr/bin/python3 cli.py info /tmp/test_signal_attrs.sv test_signal_attributes.result

============================================================
信号: test_signal_attributes.result
============================================================

  驱动源 (1):
    - unknown

  负载 (1):
    - unknown

  条件 (5):
    - [if] rst_n → result <= 8'h00
    - [if] test_signal_attributes.enable → result <= a + b
    - [if] !test_signal_attributes.enable → result <= 8'h00
    - [plain]  → result <= 8'h00
    - [plain]  → result <= a + b
```

### navisv registers

```bash
$ /usr/bin/python3 cli.py registers /tmp/test_signal_attrs.sv

寄存器列表 (5 个):

  信号                                  时钟         Reset   
  ----------------------------------- ---------- --------
  case_out                            clk        sync    
  clk2_reg                            clk2       async   
  complex_reg                         clk        async   
  no_reset_reg                        clk        none    
  result                              clk        async   

  统计: async=3, sync=1, no_reset=1
```

### navisv tools

```bash
$ /usr/bin/python3 cli.py tools

工具路径:
  SLANG_BIN: /Users/fundou/my_dv_proj/slang/slang
  NETLIST_BIN: /Users/fundou/my_dv_proj/slang-netlist/build/tools/driver/slang-netlist

状态: ✅ 所有工具可用
```

### navisv --json

```bash
$ /usr/bin/python3 cli.py --json info /tmp/test_signal_attrs.sv test_signal_attributes.result

{
  "signal": "test_signal_attributes.result",
  "drivers": [
    {"path": "test_signal_attributes.result", "location": "...test_signal_attrs.sv:13:22"}
  ],
  "loads": [...],
  "conditions": [
    {
      "condition": "rst_n",
      "statement": "result <= 8'h00",
      "if_expression": "if (rst_n) result <= 8'h00;",
      "kind": "if",
      "edges": [{"from": "test_signal_attributes.clk", "edge_kind": "PosEdge"}],
      "target_kind": "register_output",
      "clock_domain": "clk",
      "reset_kind": "async"
    }
  ]
}
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

## 项目结构

```
navisv/
├── FEATURE_PLAN.md          # P2/P3 功能规划
├── README.md                # 本文件
├── cli.py                   # 命令行入口
├── examples/                # 示例代码
│   ├── 01_signal_info.py
│   ├── 02_registers.py
│   └── 03_conditions.py
└── navisv/
    ├── config.py            # 配置层
    ├── drivers/
    ├── graph/
    └── parsers/
```

## 环境要求

- Python 3.9+
- slang (编译好的二进制)
- slang-netlist (编译好的二进制)