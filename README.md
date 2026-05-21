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

## 许可证

MIT

---

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

