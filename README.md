# navisv

> 基于 slang-netlist 的 SystemVerilog 语义导航工具

navisv 将底层网表关系转化为面向调试的结构化答案，让 AI Agent 能够直接查询和高效探索 SystemVerilog 设计。

## 功能特性

### 核心功能
- **信号分析**: 获取信号的驱动源 (fan-in)、负载 (fan-out)、条件列表
- **路径追踪**: 完整的两点间路径追踪，包含节点、边、时序信息
- **时序属性**: 自动识别 clock_domain、reset_kind、target_kind
- **FSM 建模**: 完整的状态机路径建模 (case 选择变量 → 数据信号边)

### 时序分析
- **Fan-out 时序**: 获取信号驱动的所有负载，标注时钟域和 CDC 风险
- **Timing Report**: 生成完整时序报告，按时钟域分组，显示 CDC 风险路径
- **条件覆盖率**: 分析信号的所有条件组合，检测冗余和死代码

### 可视化与导出
- **DOT 导出**: 导出图到 DOT 格式，支持子图过滤和样式配置
- **SVG 导出**: 调用 Graphviz 生成 SVG 可视化图片

### 批量操作
- **批量信号查询**: 一次分析多个信号，批量获取 fan-in/fan-out/conditions
- **批量路径追踪**: 一次追踪多条路径，返回所有路径的详细信息

### 高级分析
- **路径置信度**: 评估路径追踪的完整性 (0-1 分值)
- **CDC 检测**: 自动识别跨时钟域路径
- **条件冗余检测**: 识别重复的条件-语句对

### Class Constraint 分析
- **约束查询**: 变量在哪些 class 的哪些 constraint 中 (Q1)
- **约束影响**: constraint 能影响哪些变量 (Q2)
- **变量关系**: 两个变量之间是否存在约束关系 (Q3)
- **多层继承**: 自动追溯继承链上的约束
- **组合穿透**: 跨 class instance 的约束追踪 (如 `pkt.length`)
- **位精确度**: 识别部分位约束 (如 `ctrl_word[15:12]`)
- **条件约束**: 识别 if/else 条件分支，返回完整条件上下文
- **foreach 约束**: 正确处理 foreach 循环内的约束
- **solve...before**: 识别求解顺序约束

### CoverGroup 分析
- **CoverGroup 解析**: 从 AST 提取 covergroup/coverpoint/bins/cross 定义
- **bin-constraint 一致性**: 检测死 bin、遗漏 bin、missing illegal bin
- **coverage 质量评估**: data 类看极值粒度、control 类看特殊值和 cross

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

# 路径追踪
result = dg.trace_full_path('top.src', 'top.dst')
print(f"路径: {result['path']}")
print(f"置信度: {result['summary']['path_confidence']['score']}")

# Fan-out 时序分析
loads = dg.get_loads_with_timing('top.clk')
for l in loads:
    print(f"  → {l['signal']} [{l['timing']['clock_domain']}]")

# 条件覆盖率分析
coverage = dg.get_condition_coverage('top.signal')
print(f"条件数: {coverage['total_conditions']}")
print(f"警告: {coverage['warnings']}")

# Timing Report
report = dg.generate_timing_report(format='text')
print(report['report_text'])

# DOT 导出
dot = dg.export_to_dot(subgraph='top.module_a.*')
with open('module_a.dot', 'w') as f:
    f.write(dot)

# 批量信号查询
batch = dg.get_signals_info_batch(['top.sig1', 'top.sig2'])
print(f"分析了 {batch['summary']['total_signals']} 个信号")

# 批量路径追踪
paths = dg.trace_paths_batch([
    ('top.a', 'top.b'),
    ('top.c', 'top.d')
])
print(f"成功: {paths['summary']['successful_paths']}/{paths['summary']['total_paths']}")
```

### CLI

```bash
# 获取信号信息
/usr/bin/python3 cli.py info design.sv top.clk

# 列出所有寄存器
/usr/bin/python3 cli.py registers design.sv

# 检查工具状态
/usr/bin/python3 cli.py tools

# 路径追踪
/usr/bin/python3 cli.py trace design.sv top.src top.dst

# 批量路径追踪
/usr/bin/python3 cli.py batch-trace design.sv top.a->top.b top.c->top.d

# 时序报告
/usr/bin/python3 cli.py timing design.sv
/usr/bin/python3 cli.py timing design.sv --format markdown

# Fan-out 时序分析
/usr/bin/python3 cli.py fanout design.sv top.clk

# 条件覆盖率
/usr/bin/python3 cli.py coverage design.sv top.signal
/usr/bin/python3 cli.py coverage design.sv  # 批量分析

# DOT 导出
/usr/bin/python3 cli.py dot design.sv -o output.dot
/usr/bin/python3 cli.py dot design.sv --subgraph "module.*" -o module.dot

# Fan-in 锥分析
/usr/bin/python3 cli.py fanin-cone design.sv top.target --depth 5

# 编译检查（语法检查）
/usr/bin/python3 cli.py check design.sv
/usr/bin/python3 cli.py check file1.sv file2.sv
/usr/bin/python3 cli.py check -F filelist.f  # 使用 filelist
/usr/bin/python3 cli.py check -F filelist.f --std 1800-2023

# JSON 输出
/usr/bin/python3 cli.py --json trace design.sv top.a top.b

# Class Constraint 分析
/usr/bin/python3 cli.py constraints design.sv                  # 列出所有 class 和 constraint
/usr/bin/python3 cli.py constraints design.sv -v               # 显示约束体内容
/usr/bin/python3 cli.py cvar design.sv pkg.Class.var           # Q1: 变量在哪些 constraint 中
/usr/bin/python3 cli.py cvar -c design.sv pkg.Class.var        # Q1: 含组合穿透
/usr/bin/python3 cli.py ccons design.sv pkg.Class.constraint   # Q2: 约束影响哪些变量
/usr/bin/python3 cli.py crel design.sv pkg.Class.var1 pkg.Class.var2  # Q3: 变量关系

# CoverGroup 分析
/usr/bin/python3 cli.py cg-list design.sv                              # 列出 covergroup/coverpoint/bins
/usr/bin/python3 cli.py cg-check design.sv pkg.Class.var cg cp         # bin-constraint 一致性
/usr/bin/python3 cli.py cg-quality design.sv cg                        # covergroup 质量评估
/usr/bin/python3 cli.py cg-quality design.sv pkg.Class.var cg cp -t data  # coverpoint 质量评估
```

### CLI 命令与 API 对应表

| CLI 命令 | 底层 API | 说明 |
|----------|----------|------|
| `info` | `get_signal_info` | 获取信号完整信息 (drivers/loads/conditions) |
| `registers` | `get_registers` | 报告所有寄存器及其时钟域 |
| `ast` | - | 生成 AST JSON |
| `tools` | - | 检查依赖工具 |
| `check` | `SlangDriver.compile_check` | 快速检查源码编译状态（支持 filelist） |
| `trace` | `trace_full_path` | 两点间路径追踪 |
| `batch-trace` | `trace_paths_batch` | 批量追踪多条路径 |
| `timing` | `generate_timing_report` | 生成完整时序报告 |
| `fanout` | `get_loads_with_timing` | Fan-out 时序分析 |
| `coverage` | `get_condition_coverage` / `analyze_condition_coverage` | 条件覆盖率分析 |
| `dot` | `export_to_dot` | 导出为 DOT 格式 |
| `fanin-cone` | `get_fanin_cone` | Fan-in 锥分析 |
| `constraints` | `ConstraintGraph.get_classes` | 列出所有 class 和 constraint |
| `cvar` | `ConstraintGraph.get_constraints_for_variable` | Q1: 变量在哪些 constraint 中 |
| `ccons` | `ConstraintGraph.get_variables_in_constraint` | Q2: 约束影响哪些变量 |
| `crel` | `ConstraintGraph.get_constraint_relationship` | Q3: 两变量间的约束关系 |
| `cg-list` | `CovergroupAnalyzer.get_covergroups` | 列出所有 covergroup/coverpoint/bins |
| `cg-check` | `CovergroupAnalyzer.check_bin_constraint_consistency` | bin-constraint 一致性检查 |
| `cg-quality` | `CovergroupAnalyzer.check_coverage_quality` / `check_cg_quality` | coverage 质量评估 |

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

### navisv constraints

```bash
$ /usr/bin/python3 cli.py constraints tests/sv/realworld_ethernet.sv

类 (8):
  packet
    变量 (7):
      mac_dst_addr         Rand   [48b]
      payload              Rand   [8b]
      ipg                  Rand   [32b]
    约束 (3):
      C_proper_sop_eop_marks
      C_payload_size
      C_ipg
  packet_bringup
    继承: packet_bringup -> packet
    约束 (4):
      C_bringup
      C_proper_sop_eop_marks
      C_payload_size
      C_ipg
  ethernet_env
    变量 (3):
      pkt                  Rand   -> packet
      wb_item              Rand   -> wishbone_item
```

### navisv cvar

```bash
$ /usr/bin/python3 cli.py cvar tests/sv/realworld_ethernet.sv ethernet_pkg.packet.ipg

变量 ipg 的约束 (4):

  packet::C_ipg
    expr: ipg inside { 10:50 }

  packet_bringup::C_bringup
    expr: ipg == 10

  packet_small_ipg::C_ipg
    expr: ipg inside { 1:10 }

  packet_zero_ipg::C_ipg
    expr: ipg == 0
```

```bash
# 位精确度
$ /usr/bin/python3 cli.py cvar tests/sv/constraint_conditional.sv constraint_conditional_pkg.bit_precision_packet.ctrl_word

变量 ctrl_word 的约束 (3):

  bit_precision_packet::c_ctrl_high [15:12]
    expr: ctrl_word[15:12] inside { 4'b1, 4'b10, 4'b11 }

  bit_precision_packet::c_ctrl_low [7:0]
    expr: ctrl_word[7:0] == addr

  bit_precision_packet::c_ctrl_flag [8:8]
    expr: ctrl_word[8] == 1'b1
```

```bash
# foreach + if 约束
$ /usr/bin/python3 cli.py cvar tests/sv/constraint_foreach_if_solve.sv foreach_if_solve_pkg.foreach_if_basic.data

变量 data 的约束 (1):

  foreach_if_basic::c_foreach_if
    context: foreach (...[i]) { if (mode == 0) { data[i] inside { 0:127 } } else { data[i] inside { 128:255 } } }
    expr: if (mode == 0) { data[i] inside { 0:127 } } else { data[i] inside { 128:255 } }
```

### navisv ccons

```bash
$ /usr/bin/python3 cli.py ccons tests/sv/realworld_ethernet.sv ethernet_pkg.packet_bringup.C_bringup

约束 C_bringup 影响的变量 (5):
  mac_dst_addr
  mac_src_addr
  ether_type
  payload
  ipg
```

### navisv crel

```bash
$ /usr/bin/python3 cli.py crel tests/sv/realworld_ethernet.sv ethernet_pkg.packet.mac_dst_addr ethernet_pkg.packet.mac_src_addr

变量关系:
  mac_dst_addr <-> mac_src_addr
  共享约束 (1):
    - C_bringup
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
│    ├── netlist_parser.py       │
│    └── constraint_parser.py    │  ← class/constraint 解析
└────────────────────────────────┘
     ↓
┌────────────────────────────────┐
│  Graph Layer                   │  ← NetworkX 图构建
│    ├── graph_builder.py       │
│    ├── design_graph.py         │  ← 信号/路径/时序
│    └── constraint_graph.py     │  ← class/constraint 查询
└────────────────────────────────┘
     ↓
slang / slang-netlist            # 单一数据源
```

### 核心模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 配置层 | `navisv/config.py` | 工具路径、环境变量 |
| 驱动层 | `navisv/drivers/` | DesignDriver/SlangDriver/NetlistDriver |
| 解析层 | `navisv/parsers/` | AST/Netlist/Constraint/CoverGroup 解析 |
| 图层 | `navisv/graph/` | DesignGraph + ConstraintGraph + CovergroupAnalyzer |

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
├── tests/
│   ├── conftest.py          # pytest fixtures
│   ├── test_navisv.py       # DesignGraph 测试
│   ├── test_constraint_graph.py  # ConstraintGraph 测试 (43 个)
│   ├── test_covergroup.py       # CoverGroup 解析测试 (33 个)
│   ├── test_cg_constraint_check.py  # bin-constraint 一致性测试 (12 个)
│   ├── test_cg_quality.py       # coverage 质量评估测试 (9 个)
│   └── sv/                  # 测试用 SV 文件
│       ├── constraint_basic.sv
│       ├── constraint_conditional.sv
│       ├── constraint_edge.sv
│       ├── constraint_foreach_solve.sv
│       ├── constraint_foreach_if_solve.sv
│       └── realworld_ethernet.sv
└── navisv/
    ├── config.py            # 配置层
    ├── drivers/
    │   ├── design_driver.py  # 统一入口 (含 ConstraintGraph 构建)
    │   ├── slang_driver.py
    │   └── netlist_driver.py
    ├── graph/
    │   ├── design_graph.py   # DesignGraph (信号/路径/时序)
    │   ├── constraint_graph.py  # ConstraintGraph (class/constraint)
    │   ├── covergroup_analyzer.py  # CovergroupAnalyzer (coverage 分析)
    │   └── graph_builder.py
    └── parsers/
        ├── ast_parser.py
        ├── netlist_parser.py
        ├── constraint_parser.py  # class/constraint 解析
        └── covergroup_parser.py  # covergroup/bins 解析
```

## 环境要求

- Python 3.9+
- slang (编译好的二进制)
- slang-netlist (编译好的二进制)
## API 参考

### DesignGraph 核心方法

#### 信号分析
| 方法 | 说明 |
|------|------|
| `get_signal_info(signal, source)` | 获取信号完整信息 (drivers/loads/conditions) |
| `get_signals_info_batch(signals, source)` | 批量获取多个信号的信息 |
| `get_all_conditions(signal)` | 获取信号的所有条件 |

#### 路径追踪
| 方法 | 说明 |
|------|------|
| `trace_full_path(src, dst)` | 完整路径追踪 (含时序、条件、置信度) |
| `trace_paths_batch(path_specs)` | 批量追踪多条路径 |
| `get_path(src, dst)` | 获取两点间的节点列表 |

#### 时序分析
| 方法 | 说明 |
|------|------|
| `get_loads_with_timing(signal)` | 获取信号的 fan-out，标注时钟域和 CDC |
| `generate_timing_report(format)` | 生成时序报告 (text/markdown/json) |
| `get_fanin_cone(signal, depth, timing)` | 获取信号 fan-in 锥 |
| `get_fanout_cone(signal, depth, timing)` | 获取信号 fan-out 锥 |

#### 条件分析
| 方法 | 说明 |
|------|------|
| `get_condition_coverage(signal)` | 单信号条件覆盖率分析 |
| `analyze_condition_coverage(signals)` | 批量分析信号条件覆盖率 |

#### 可视化
| 方法 | 说明 |
|------|------|
| `export_to_dot(file_path, subgraph, include_timing, include_conditions)` | 导出 DOT 格式 |
| `export_to_svg(file_path, subgraph, include_timing, include_conditions)` | 导出 SVG 格式 |

### ConstraintGraph 核心方法

> 通过 `dd.constraint_graph` 获取，基于 slang AST 解析 class/constraint 结构。

#### 类与约束查询
| 方法 | 说明 |
|------|------|
| `get_classes()` | 获取所有类 |
| `get_variables_in_class(class_path)` | 获取类的所有变量 (含继承) |
| `get_constraints_in_class(class_path)` | 获取类的所有约束 (含继承) |
| `get_inheritance_chain(class_path)` | 获取继承链 |

#### Q1: 变量在哪些 constraint 中
| 方法 | 说明 |
|------|------|
| `get_constraints_for_variable(var_path, include_composition, max_depth)` | 变量在哪些约束中 |

返回每条约束的 `constraint_name`、`class_name`、`constraint_body`、`direct_expr`、`context`、`bit_range`、`is_conditional`、`access_path`。

#### Q2: 约束影响哪些变量
| 方法 | 说明 |
|------|------|
| `get_variables_in_constraint(constraint_path)` | 约束引用了哪些变量 |

#### Q3: 变量间约束关系
| 方法 | 说明 |
|------|------|
| `get_constraint_relationship(var_a_path, var_b_path)` | 两变量间的共享约束 |

#### 返回结构

```python
# get_constraints_for_variable 返回示例
[
  {
    'constraint_name': 'C_ipg',
    'constraint_path': 'ethernet_pkg.packet.C_ipg',
    'class_name': 'ethernet_pkg.packet',
    'constraint_body': 'ipg inside { 10:50 }',
    'direct_exprs': ['ipg inside { 10:50 }'],
    'bit_range': None,            # 全宽; [15,12] 表示部分位
    'is_conditional': False,
    'condition': '',
    'context': '',                 # 条件约束时包含完整 if/else 上下文
    'access_path': '',             # 组合穿透时如 'pkt.length'
  },
  ...
]
```

#### SlangDriver 编译检查
| 方法 | 说明 |
|------|------|
| `compile_check(files, ...)` | 快速语法检查（支持 files 或 filelist） |
| `check_available()` | 检查 slang 是否可用 |
| `get_version()` | 获取 slang 版本 |

### CovergroupAnalyzer 核心方法

> 通过 `dd.covergroups` 获取，基于 slang AST 解析 covergroup/coverpoint/bins 结构。

#### 查询
| 方法 | 说明 |
|------|------|
| `get_covergroups()` | 列出所有 covergroup |
| `get_coverpoints(cg_name)` | 获取 covergroup 的 coverpoint 列表 |
| `get_bins(cg_name, cp_name)` | 获取 coverpoint 的 bins |
| `get_crosses(cg_name)` | 获取 cross 覆盖 |

#### bin-constraint 一致性检查
| 方法 | 说明 |
|------|------|
| `check_bin_constraint_consistency(var_path, cg_name, cp_name)` | 检查 bins 与 constraint 是否一致 |

返回问题列表，类型：
- `dead_bin`: bin 范围被 constraint 排除，永远无法 hit
- `missing_bin`: constraint 允许但无 bin 覆盖
- `missing_illegal_bin`: constraint 禁止但没标 illegal_bins

#### coverage 质量评估
| 方法 | 说明 |
|------|------|
| `check_coverage_quality(var_path, cg_name, cp_name, signal_type)` | coverpoint 级别质量评估 |
| `check_cg_quality(cg_name)` | covergroup 级别综合评估 |

`signal_type`:
- `data`: 检查极值 bin (zero/max)、bin 粒度
- `control`: 检查特殊值 bin、状态覆盖

返回报告列表，类型：`info` / `warning` / `score`

### compile_check 参数说明

```python
SlangDriver.compile_check(
    files=None,              # 源文件列表
    include_dirs=None,       # include 目录
    defines=None,           # 宏定义
    std='1800-2017',         # 语言标准
    top=None,                # 顶层模块
    ignore_unknown_modules=False,  # 忽略未知模块
    filelist=None,           # filelist 文件路径 (-F 选项)
    filelist_includes=None,  # filelist 内相对 include 目录
)
```

### compile_check 返回值

```python
{
    'success': True,           # 是否通过编译检查
    'returncode': 0,           # slang 返回码
    'error_count': 0,         # 错误数
    'warning_count': 0,       # 警告数
    'errors': [                # 错误详情列表
        {'file': 'file.sv', 'line': 68, 'column': 22, 'message': '...'},
        ...
    ],
    'warnings': [...],         # 警告详情列表
    'diagnostics': [...],      # 原始诊断信息
    'stdout': '',              # slang 标准输出
    'stderr': '',              # slang 标准错误
}
```

### 返回结构示例

#### trace_full_path 返回
```python
{
    'from': 'src_signal',
    'to': 'dst_signal',
    'success': True,
    'path': [
        {'signal': '...', 'location': 'file:line', 'timing': {...}, 'is_register': True},
        ...
    ],
    'summary': {
        'reset_safe': True,
        'cross_clock': False,
        'register_count': 2,
        'clocks': ['uart_clk_i'],
        'path_confidence': {'score': 0.85, 'details': {...}}
    }
}
```

#### get_loads_with_timing 返回
```python
[
    {
        'signal': 'load_name',
        'timing': {'clock_domain': 'clk', 'reset_kind': 'sync', 'target_kind': 'register_output'},
        'relation': 'drives',
        'cross_clock': False,
        'async_path': False
    },
    ...
]
```

#### generate_timing_report 返回
```python
{
    'summary': {'total_signals': 229, 'clock_domains': 4, 'registers': 47, 'cross_clock_paths': 2},
    'clock_domains': {'clk_i': {'signals': [...], 'registers': [...], 'reset_kind': 'sync'}, ...},
    'cross_clock_paths': [{'source': 'sig1', 'target': 'sig2', 'source_clock': 'clk1', 'target_clock': 'clk2'}, ...],
    'report_text': '...'  # format='text' 时
}
```

## 测试结果

使用 UART-Implementation 开源项目测试 (7 个模块, 229 节点, 311 边):

| 功能 | 状态 | 说明 |
|------|------|------|
| 路径追踪 | ✅ 3/3 通过 | 包括跨时钟域路径 |
| 时序属性 | ✅ 100% | 50 个信号全部有时序信息 |
| 条件覆盖 | ✅ 141 条 | 检测到 2 个冗余、16 个死代码风险 |
| CDC 检测 | ✅ 2 条 | 正确识别 APB 时钟域跨越 |
| DOT 导出 | ✅ | 599 行 DOT (uart_tx 子图) |

### ConstraintGraph 测试 (43 个)

| 分类 | 测试数 | 说明 |
|------|--------|------|
| 基础类 | 6 | 变量属性、约束绑定、Q1 查询 |
| 多层继承 | 5 | 3 层继承链、继承约束追溯 |
| 组合关系 | 4 | class instance、access_path |
| 深层组合 | 3 | 3 层穿透 (top_env -> wrapper -> eth_packet) |
| 位精确度 | 5 | RangeSelect、ElementSelect |
| 条件约束 | 6 | if/else、条件上下文、direct_expr |
| 边界场景 | 8 | 无约束变量、同名覆盖、randc、soft、4 层继承 |
| 变量关系 | 6 | Q3 共享约束、跨类关系 |

### CoverGroup 测试 (54 个)

| 分类 | 测试数 | 说明 |
|------|--------|------|
| CoverGroup 解析 | 33 | coverpoint/bins/cross/wildcard/default/option/class |
| bin-constraint 一致性 | 12 | 死 bin/遗漏 bin/missing illegal/条件约束/部分重叠 |
| coverage 质量评估 | 9 | data 极值/control 特殊值/cross/评分 |

开源项目验证:

| 项目 | 类 | 变量 | 约束 | 状态 |
|------|----|------|------|------|
| ethernet_10ge_mac_SV_UVM_tb | 8 | 13 | 11 | ✅ |
| sv-tests 18.5.2 (继承) | 2 | 2 | 2 | ✅ |
| sv-tests 18.5.7 (if-else) | 1 | 3 | 3 | ✅ |
| sv-tests 18.5.14.1 (soft) | 2 | 1 | 3 | ✅ |

## 许可证

MIT

---

## 架构详解：语义 AST 与 Netlist 协作

### navisv cg-list

```bash
$ /usr/bin/python3 cli.py cg-list tests/sv/realworld_ethernet.sv

类 (8):
  packet
    变量 (7):
      mac_dst_addr         Rand   [48b]
      payload              Rand   [8b]
```

### navisv cg-check

```bash
$ /usr/bin/python3 cli.py cg-check tests/sv/covergroup_constraint_check.sv cg_check_pkg.dead_bin_cls.data dead_bin_cls.cg cp_data

dead_bin_cls.data 的一致性检查:

  ⚠️  dead_bin: bin [101:200] 被 constraint 排除, 永远无法 hit
  ⚠️  dead_bin: bin [255:255] 被 constraint 排除, 永远无法 hit
  ⚠️  missing_illegal_bin: constraint 禁止的取值没有标 illegal_bins
```

### navisv cg-quality

```bash
$ /usr/bin/python3 cli.py cg-quality tests/sv/covergroup_quality.sv cg_quality_pkg.data_bad_cls.data data_bad_cls.cg cp_data --type data

data_bad_cls.data 的质量评估 (score=0.50):

  ⚠️  缺少极值 bin: 建议添加 bins zero = {0}
  ⚠️  缺少极值 bin: 建议添加 bins max = {255}
  ⚠️  bin 数量较少 (2), 建议细化范围划分
```

## 架构详解：语义 AST 与 Netlist 协作

### 设计理念

navisv 采用**双数据源协作**策略，结合 **slang AST** 的语义信息和 **slang-netlist** 的结构信息，生成完整的 design graph。

```
slang (AST)                    slang-netlist (Netlist)
     │                              │
     │  语法树                       │  网表
     │  - 模块层次                   │  - 节点/边
     │  - 条件语句 (if/case)         │  - Port/State
     │  - 时序上下文 (always 块)     │  - Assignment
     │  - 符号映射                   │  - Timing/EdgeKind
     │                              │
     └──────────┬───────────────────┘
                │
                ▼
     ┌─────────────────────┐
     │     GraphBuilder   │
     │                     │
     │  1. 添加 Named Nodes │ ← Netlist 提供节点结构
     │  2. 分析 AST 条件   │ ← AST 提供语义信息
     │  3. 添加边          │ ← Netlist 提供边结构
     │  4. 丰富边属性      │ ← AST 补充条件
     │  5. 推断时序分类   │ ← AST 时序上下文
     │  6. 计算 bit_mapping │ ← Netlist bounds
     └─────────────────────┘
                │
                ▼
        DesignGraph (Graph)
```

### slang AST 提供的数据

**来源**: `slang --ast-json ast.json design.sv`

**数据类型**:
| 数据 | 说明 | 用途 |
|------|------|------|
| **模块层次** | `module.path` 如 `uart_controller.uart_tx` | 构建完整路径 |
| **条件语句** | `if/case/ternary` 结构 | 提取 `condition`、`kind`、`statement` |
| **时序上下文** | `ProceduralBlock` + `Timed` (clock/reset) | 推断 `clock_domain`、`reset_kind` |
| **符号映射** | `symbol="id name"` | 从信号 ID 映射到名称 |
| **源码位置** | `source_line_start`、`source_column_start` | 提取 `statement` 文本 |

**关键处理**:

```python
# 1. 分析条件语句，建立 signal -> conditions 映射
def _traverse_with_timing(node, timing_ctx):
    if node.kind == 'ProceduralBlock':
        new_timing = _extract_timing_from_block(node)  # 提取 always @(posedge clk) 的 clock/reset
        for child in node.children:
            _traverse_with_timing(child, timing_ctx=new_timing)
    
    elif node.kind == 'Case':
        case_var = _extract_expr_path(node.attributes.get('expr', {}))  # 提取 case 选择变量
        for item in node.attributes.get('items', []):
            condition = f"{case_var} == {case_value}"
            _extract_assignments_from_stmt(condition, 'case', stmt, timing_ctx)
    
    elif node.kind == 'Conditional':
        _analyze_conditional(node, timing_ctx)

# 2. 提取 timing context
def _extract_timing_from_block(node):
    # 从 Timed 节点提取: @posedge clk, if (!rst_n)
    for child in node.children:
        if child.kind == 'Timed':
            clock = _extract_clock_from_timed(child)
            reset = _extract_reset_from_timed(child)
            return {'clock': clock, 'reset': reset}
```

### slang-netlist 提供的数据

**来源**: `slang-netlist --output netlist.json design.sv`

**数据类型**:
| 数据 | 说明 | 用途 |
|------|------|------|
| **节点** | `Port`、`State`、`Net`、`Assignment` | 构建图的顶点 |
| **边** | `source → target` 带 `edge_kind`、`timing` | 构建图的边 |
| **路径** | 完整信号路径 `module.signal` | 节点/边的标识 |
| **位宽** | `bounds` (msb, lsb) | 计算 `bit_width` |
| **方向** | `input/output/inout` | 标记 Port 方向 |

**关键处理**:

```python
# 1. 添加 Named Nodes (Port + State)
for state in netlist.get_registers():  # State 节点
    attr = NodeAttr(name=state.name, path=state.path, kind='State', 
                    bit_width=state.bounds, timing='sequential')
    self._add_node(state.path, attr)

for port in netlist.get_ports():  # Port 节点
    attr = NodeAttr(name=port.name, path=port.path, kind='Port',
                    direction=port.direction, timing='combinational')
    self._add_node(port.path, attr)

# 2. 从 Netlist 添加边
for edge in netlist.edges:
    src_path = src_node.path
    tgt_path = tgt_node.path
    attr = EdgeAttr(edge_kind=edge.edge_kind, bounds=edge.bounds)
    self.graph.add_edge(src_path, tgt_path, **attr.to_dict())
```

### 协作模式

#### 1. 节点构建：Netlist 提供结构，AST 补充属性

```
Netlist State 节点 ──────→ Graph 节点
    path/name/kind/bounds          继承 + timing='sequential'
    
Netlist Port 节点 ──────→ Graph 节点
    path/name/direction/bounds     继承 + timing='combinational'
```

#### 2. 边构建：Netlist 提供边结构

```
Netlist Edge (source → target) ──→ Graph Edge
    edge_kind/timing/bounds            继承
    + condition (来自 AST 补充)
```

**特殊处理 - Assignment 节点**:

Netlist 中 `Assignment` 节点没有 `path`，需要从边信息推断：

```python
# 如果 Assignment 是连续赋值的中间节点
if tgt_node.kind == 'Assignment' and not tgt_node.path:
    # 从出边 symbol 获取目标路径
    asn_info = assignment_edges_info.get(tgt_node.id)
    if asn_info['out']:
        tgt_path = asn_info['out'][0][0]
```

#### 3. 条件信息：AST 提供语义，Netlist 提供位置

```
AST CaseStatement                AST Conditional
    condition='curr_state'  ──────→ _signal_conditions[signal]
    kind='case'                   location (from AST)

Netlist Edge                      + condition_kind/condition_signals
    condition (补充)              + statement (从源文件读取)
```

#### 4. 时序推断：AST 时序上下文 + Netlist 边类型

```
AST ProceduralBlock               AST Timed
    always @(posedge clk)    ───→ clock_domain = 'uart_clk_i'
    if (!rst_n)             ───→ reset_kind = 'async'

Netlist Edge                      Graph Edge
    edge_kind='PosEdge'          timing='sequential'
```

### 数据流向

```
1. DesignDriver.__init__()
   └─→ SlangDriver.generate_ast()
   └─→ NetlistDriver.generate_netlist()

2. GraphBuilder.__init__(ast_parser, netlist_parser)
   └─→ _build_symbol_map()  # 建立 symbol -> path 映射

3. GraphBuilder.build()
   │
   ├─→ _add_named_nodes()           # Netlist → Graph 节点
   │      State: path, kind, bounds
   │      Port: path, kind, direction, bounds
   │      Net: placeholder 信号
   │
   ├─→ _analyze_ast_conditions()      # AST → _signal_conditions
   │      遍历模块，提取 if/case/ternary
   │      从 ProceduralBlock 提取 clock/reset
   │      建立 signal → [conditions] 映射
   │
   ├─→ _add_edges()                   # Netlist edges → Graph edges
   │      source → target (带 edge_kind/timing)
   │
   ├─→ _enrich_edges_with_conditions()  # 补充 AST 条件
   │      从 _signal_conditions 补充
   │
   ├─→ _classify_timing()             # 推断 timing 类型
   │      sequential / combinational
   │
   └─→ _calculate_bit_mapping()       # 计算 bit 映射

4. DesignGraph(_signal_conditions)
   └─→ 可查询: trace_full_path, get_loads_with_timing, 
              generate_timing_report, get_condition_coverage
```

### 关键数据结构

#### _signal_conditions

```python
{
    'module.signal': [
        {
            'condition': 'curr_state == S_DATA',  # 条件表达式
            'kind': 'case',                        # if/case/plain/ternary
            'statement': 'data <= tx_fifo_data_i',  # 赋值语句
            'clock_domain': 'uart_clk_i',          # 时钟域
            'reset_kind': 'sync',                  # reset 类型
            'target_kind': 'register_output',      # register_output/combinational
            'location': {'file': 'uart_tx.sv', 'line': 224, 'column': 13},
            'source': 'ast'                         # 数据来源
        },
        ...
    ]
}
```

#### _node_attrs

```python
{
    'module.signal': NodeAttr(
        name='signal',
        path='module.signal',
        kind='State',         # Port/State/Net
        bit_width=(7, 0),      # [7:0]
        timing='sequential',   # sequential/combinational
        module='module',
        location={...}
    )
}
```

#### Graph Edge

```python
Graph.add_edge(
    'module.src_signal',           # source
    'module.dst_signal',           # target
    relation='drives',              # drives/controls
    timing='sequential',            # sequential/combinational/sequential_input/sequential_output
    edge_kind='PosEdge',           # PosEdge/NegEdge/None
    condition='curr_state',         # 来自 AST
    condition_kind='case'          # if/case/plain/ternary
)
```

### FSM 路径建模特殊处理

FSM 的 `case(curr_state)` 语句中，数据赋值（如 `data = tx_fifo_data_i`）与状态选择变量（如 `curr_state`）相关，但不直接连接。需要建立 **case 选择变量 → 目标信号** 的边：

```python
# 在 _extract_assignments_from_expr 中
if cond_kind == 'case' and condition:
    # 从 condition 提取 case 选择变量
    case_var = condition.split('==')[0].strip()  # 'curr_state'
    
    if case_var in self._node_attrs:
        self.graph.add_edge(
            case_var, target_path,
            relation='controls',    # 不同于 'drives'
            timing='combinational',
            condition=condition    # 如 'curr_state == S_DATA'
        )
```

这使得 `trace_full_path('curr_state', 'data')` 可以找到直接路径。

### 置信度评分

路径置信度基于四个维度：

```python
score = (
    0.40 * node_match_score +      # 路径节点匹配度
    0.30 * edge_completeness_score +  # 边完整性 (condition + timing)
    0.15 * module_boundary_score +    # 模块边界损失
    0.15 * clock_consistency_score    # 时钟一致性
)
```

### 限制与已知问题

1. **AST 解析失败**: 如果 slang 返回非零退出码，部分语义信息可能丢失
2. **Netlist 边界**: 对于某些复杂赋值，可能无法正确建立边
3. **符号冲突**: 同名信号在不同模块可能冲突（通过完整路径解决）
4. **Timing 推断**: 只支持 `always @(posedge clk)` 和 `always @(negedge clk)`，不支持多时钟

---

## 架构详解：ConstraintGraph

### 设计理念

ConstraintGraph 从 slang AST 中提取 class/constraint 结构，回答三个核心问题：

1. **Q1**: 变量在哪些 class 的哪些 constraint 中？
2. **Q2**: constraint 能影响哪些变量？
3. **Q3**: 两个变量之间是否存在约束关系？

### 数据流

```
slang AST JSON
     │
     ▼
ConstraintParser (parsers/constraint_parser.py)
     │  遍历 ClassType → ClassProperty / ConstraintBlock
     │  提取: 类、变量、约束、继承、组合
     │
     ▼
ConstraintGraph (graph/constraint_graph.py)
     │  构建 NetworkX MultiDiGraph
     │  节点: Class / Variable / Constraint
     │  边: has_var / has_constraint / binds / inherits / member_of
     │
     └──→ 查询 API
```

### 节点与边

| 节点 | 属性 | 说明 |
|------|------|------|
| Class | name, full_path, is_abstract | class 定义 |
| Variable | name, type_str, rand_mode, msb/lsb/bit_width, type_class | class 变量 |
| Constraint | name, expr_count, has_soft, is_conditional, constraint_body | 约束块 |

| 边 | 方向 | 说明 |
|------|------|------|
| has_var | Class → Variable | 类拥有变量 |
| has_constraint | Class → Constraint | 类拥有约束 |
| binds | Constraint → Variable | 约束引用变量 (带 access_path, bit_range, context) |
| inherits | Class → Class | 继承关系 |
| member_of | Variable → Class | 变量类型是另一个类 |

### 继承处理

slang 对继承变量使用不同地址。Parser 通过 `_addr_to_owning_classes` 跟踪所有拥有同名变量的类。查询时 `_normalize_var_path` 将变量规范化为约束实际引用的路径。

```
base_packet.length ←inherits─ mid_packet.length ←inherits─ eth_packet.length
  (addr A)              (addr B)                 (addr C)

约束引用 addr A (原始定义)
→ _normalize_var_path('eth_packet.length') → 'base_packet.length'
→ _find_all_var_paths → [base_packet.length, mid_packet.length, eth_packet.length]
```

### 组合穿透

当约束引用跨类实例的变量时（如 `pkt.length`），Parser 通过 `MemberAccess` 节点提取：

```
AST MemberAccess:
  value: NamedValue (symbol='pkt', type='eth_packet')
  member: 'length'
→ access_path='pkt.length', target_class='eth_packet'
```

查询时 `include_composition=True` 会查找所有通过 access_path 引用的约束。

### 位精确度

AST 中的 `RangeSelect` 和 `ElementSelect` 节点提供位选择信息：

```
RangeSelect: ctrl_word[15:12] → bit_range=[15, 12]
ElementSelect: ctrl_word[8]   → bit_range=[8, 8]
循环变量: data[i]            → bit_range=['i', 'i']
```

### 条件约束与上下文

遍历约束表达式树时，维护 `parent_context` 和 `current_expr_str`：

- 进入 `Conditional` 节点 → 构建 `if (cond) { body } else { body }` 上下文
- 进入 `Foreach` 节点 → 构建 `foreach (...[i]) { body }` 上下文
- 进入 `Expression` 节点 → 捕获表达式文本作为 `direct_expr`
- 找到 `NamedValue` 引用 → 使用 `current_expr_str` 作为 `direct_expr`

### 实现文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `parsers/constraint_parser.py` | ~700 | AST 解析: 类/变量/约束提取 |
| `graph/constraint_graph.py` | ~300 | NetworkX 图构建 + 查询 API |
| `tests/test_constraint_graph.py` | ~500 | 43 个金标准测试 |

