# navisv

> 基于 slang 的 SystemVerilog 语义导航工具，为 AI Agent 提供 RTL 调试能力

navisv 将 RTL 设计转化为结构化查询，让 AI Agent 能够直接回答：
- 这个信号从哪来？到哪去？
- 这个变量被哪些约束限制？
- 这个 coverpoint 的 bin 定义合理吗？

## 快速上手

### 1. 安装依赖

```bash
# 前置条件: cmake, C++ 编译器
# macOS: xcode-select --install
# Ubuntu: apt install cmake g++

# Python 依赖
pip install networkx

# 编译 slang (SystemVerilog 前端)
git clone https://github.com/MikePopoloski/slang.git
cd slang && cmake -B build && cmake --build build -j$(nproc)
export NAVISV_SLANG_BIN=$(pwd)/slang  # 可执行文件在项目根目录

# 编译 slang-netlist (网表提取, DesignGraph 需要)
git clone https://github.com/MikePopoloski/slang-netlist.git
cd slang-netlist && cmake -B build && cmake --build build -j$(nproc)
export NAVISV_NETLIST_BIN=$(pwd)/build/tools/driver/slang-netlist
```

### 2. 5 分钟上手

```bash
# 信号路径追踪: 这个信号从哪来？
python3 cli.py trace design.sv top.src top.dst

# 约束查询: 这个变量被哪些约束限制？
python3 cli.py cvar design.sv pkg.Class.var

# covergroup 检查: bin 和 constraint 一致吗？
python3 cli.py cg-check design.sv pkg.Class.var cg_name cp_name

# 语法检查
python3 cli.py check design.sv
```

### 3. Python API (推荐 Agent 使用)

```python
from navisv import DesignDriver

dd = DesignDriver(['design.sv'])
dd.build()

# 信号路径
dg = dd.design_graph
dg.trace_full_path('top.src', 'top.dst')

# 约束查询
cg = dd.constraint_graph
cg.get_constraints_for_variable('pkg.Class.var')

# SVA 提取
sva = dd.sva
for a in sva.assertions:
    print(f'{a.kind}: {a.expression}')

# UVM 结构
uvm = dd.uvm_tb
uvm.get_port_connections()

# 调用图
call = dd.call_graph
call.to_mermaid()
```

## 能力总览

navisv 提供 9 大能力模块，覆盖 RTL 设计分析的完整链路：

## 功能一览

| 功能 | CLI 命令 | 说明 |
|------|----------|------|
| **信号路径追踪** | `trace` | 两点间完整路径，含时序和条件 |
| **信号分析** | `info` | fan-in/fan-out/条件列表 |
| **约束查询** | `cvar` / `ccons` / `crel` | 变量↔约束关系 |
| **CoverGroup 分析** | `cg-list` / `cg-check` / `cg-quality` | bins 一致性 + 质量评估 |
| **SVA 提取** | (Python API) | 从 AST 提取 assert/assume/cover/restrict |
| **UVM TB 结构** | (Python API) | 组件层级/Sequence/Port/config_db/plusargs |
| **调用图** | (Python API) | 函数调用图、fork、randomize 标记 |
| **SVA 生成** | (Python API) | 从信号关系生成 assert property |
| **编译检查** | `check` | 快速语法检查 |
| **时序分析** | `timing` / `fanout` | 时钟域/CDC 分析 |

---

## 实际效果示例

### 示例 1: 信号路径追踪

```bash
$ python3 cli.py trace uart_controller.sv uart_controller.s_apb_pwdata_i uart_controller.uart_tx.tx_fifo_data_i
```

```
✅ APB WDATA → TX FIFO    path=9  confidence=0.52

路径: s_apb_pwdata_i → apb_interface.s_apb_pwdata_i → ... → uart_tx.tx_fifo_data_i
```

Agent 用这个能力回答："这个 FIFO 数据是从 APB 总线的 pwdata 写入的"。

### 示例 2: 约束查询 (Q1)

```bash
$ python3 cli.py cvar tests/sv/realworld_ethernet.sv ethernet_pkg.packet.ipg
```

```
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

Agent 用这个能力回答："ipg 被 4 个约束限制，基类允许 10-50，子类分别覆盖为 10、1-10、0"。

### 示例 3: bin-constraint 一致性检查

```bash
$ python3 cli.py cg-check tests/sv/covergroup_constraint_check.sv \
    cg_check_pkg.dead_bin_cls.data dead_bin_cls.cg cp_data
```

```
data 的一致性检查:

  ⚠️  dead_bin: bin [101:200] 被 constraint 排除, 永远无法 hit
      range: [101:200]
  ⚠️  dead_bin: bin [255:255] 被 constraint 排除, 永远无法 hit
      range: [255:255]
  ⚠️  missing_illegal_bin: constraint 禁止的取值没有标 illegal_bins
      forbidden: [101:255]
```

Agent 用这个能力回答："你的 covergroup 有 3 个问题：2 个死 bin 永远不会 hit，还有 101-255 的值应该标 illegal_bins"。

### 示例 4: true_condition (条件追踪)

```bash
$ python3 cli.py --json trace true_condition.sv true_condition.a true_condition.out_if
```

边上带 `true_condition` 字段：

```json
{
  "src": "a", "dst": "out_if",
  "true_condition": "!!rst_n && sel == 2'b0"
}
```

Agent 用这个能力回答："信号 a 只在 `rst_n` 有效且 `sel==0` 时才会传递到 out_if"。

### 示例 5: covergroup 质量评估

```bash
$ python3 cli.py cg-quality tests/sv/covergroup_quality.sv \
    cg_quality_pkg.data_bad_cls.data data_bad_cls.cg cp_data -t data
```

```
data_bad_cls.data 的质量评估 (score=0.50):

  ⚠️  缺少极值 bin: 建议添加 bins zero = {0}
  ⚠️  缺少极值 bin: 建议添加 bins max = {255}
  ⚠️  bin 数量较少 (2), 建议细化范围划分
```

### 示例 6: 变量间约束关系 (Q3)

```bash
$ python3 cli.py crel tests/sv/realworld_ethernet.sv \
    ethernet_pkg.packet.mac_dst_addr ethernet_pkg.packet.mac_src_addr
```

```
变量关系:
  mac_dst_addr <-> mac_src_addr
  共享约束 (1):
    - C_bringup
```

### 示例 7: SVA 提取 (从 AST 直接解析)

```python
from navisv import DesignDriver

dd = DesignDriver(['design.sv'])
dd.build()
sva = dd.sva

for a in sva.assertions:
    print(f'{a.kind:15s} clk={a.clock} expr={a.expression}')
    if a.disable_condition:
        print(f'  disable iff ({a.disable_condition})')
```

```
Assert          clk=clk  expr: valid |-> ##1 ready
Assume          clk=clk  expr: valid |-> ##[1:3] ready
Assert          clk=clk  expr: valid |-> data != 8'd0
  disable iff (!rst_n)
Assert          clk=clk  prop=p_data_stable  expr: valid |-> ##1 $stable(data)
Restrict        clk=clk  expr: data != 8'hFF
```

Agent 用这个能力回答：“这个模块有哪些 assertion？涉及哪些信号？”

### 示例 8: 调用图 (UVM testbench 分析)

```python
cg = dd.call_graph

# 调用关系
for cls in ['my_pkg.my_seq']:
    for m in cg.get_methods(cls):
        calls = cg.get_calls_from(m['full_path'])
        for c in calls:
            flags = []
            if c['is_randomize']: flags.append('randomize')
            if c['is_constructor']: flags.append('new')
            if c['is_super']: flags.append('super')
            print(f'{m["name"]} -> {c["callee"]} {flags}')

# fork 块
for f in cg.get_forks('my_pkg.my_seq'):
    print(f'fork {[b["callee"] for b in f["branches"]]} {f["join_type"]}')

# 导出
print(cg.to_mermaid())
```

```
body -> body [super]
body -> do_tag []
do_send -> randomize [randomize]
run_phase -> new [new]
run_phase -> body []

fork ['task_a', 'task_b'] join_any
```

Agent 用这个能力回答：“这个 sequence 的执行流程是什么？哪里有 randomize？”

### 示例 9: 完整 UVM Testbench 分析 (真实 UVM 宏)

以 `tests/sv/uvm_full_test.sv` 为例，使用真实 `uvm_component_utils`、`uvm_config_db`、`$value$plusargs`：

```python
dd = DesignDriver(['uvm_full_test.sv'])
dd.build()
uvm = dd.uvm_tb

# 组件层级
for c in uvm.get_components():
    print(f'{c["name"]:20s} type={c["uvm_type"]}')

# config_db 配置流
for f in uvm.get_config_flows():
    print(f'{f["field"]:15s} {f["setter"]} -> {f["getter"]} = {f["value"]}')

# 端口连接
for conn in uvm.get_port_connections():
    print(f'{conn["source"]} -> {conn["target"]}')
```

```
=== 组件 ===
axi_driver       type=uvm_driver
axi_monitor      type=uvm_monitor
axi_scoreboard   type=uvm_scoreboard
axi_agent        type=uvm_agent
my_env           type=uvm_env

=== 层级 ===
axi_agent -> [drv, mon, sqr]
my_env    -> [agt, sb, cov]

=== config_db 配置流 ===
max_retries    my_test -> my_driver = 3
sample_count   my_test -> my_monitor = 100

=== plusargs ===
test:  VERBOSE         -> driver
value: RETRY=%d        -> max_retries

=== Port Connections ===
drv.seq_item_port -> sqr.seq_item_export
agt.mon.ap -> sb.imp
agt.mon.ap -> cov.imp
```

---

## API 参考

### DesignGraph (信号/路径)

```python
from navisv import DesignDriver

dd = DesignDriver(['design.sv'])
dd.build()
dg = dd.design_graph

# 路径追踪
result = dg.trace_full_path('top.src', 'top.dst')
print(result['path'])           # 路径节点
print(result['summary'])        # 置信度/时钟域/CDC

# 信号信息
info = dg.get_signal_info('top.clk')
print(info['drivers'])          # 驱动源
print(info['conditions'])       # 条件列表

# 寄存器列表
regs = dg.get_registers()
```

### ConstraintGraph (约束)

```python
cg = dd.constraint_graph

# Q1: 变量在哪些约束中
cons = cg.get_constraints_for_variable('pkg.Class.var', include_composition=True)
for c in cons:
    print(f'{c["class_name"]}::{c["constraint_name"]}')
    print(f'  body: {c["constraint_body"]}')
    print(f'  expr: {c["direct_exprs"]}')
    print(f'  bit:  {c["bit_range"]}')
    print(f'  cond: {c["is_conditional"]}')

# Q2: 约束影响哪些变量
vars = cg.get_variables_in_constraint('pkg.Class.constraint')

# Q3: 变量关系
rel = cg.get_constraint_relationship('pkg.Class.var_a', 'pkg.Class.var_b')
print(rel['shared_constraints'])
```

### CovergroupAnalyzer (覆盖)

```python
cg = dd.covergroups

# 列出 covergroup
for info in cg.get_covergroups():
    cps = cg.get_coverpoints(info['name'])
    for cp in cps:
        bins = cg.get_bins(info['name'], cp['name'])
        print(f'{cp["name"]}: {[b["name"] for b in bins]}')

# bin-constraint 一致性
issues = cg.check_bin_constraint_consistency('pkg.Class.var', 'cg_name', 'cp_name')
for issue in issues:
    print(f'{issue["type"]}: {issue["reason"]}')

# 质量评估
report = cg.check_coverage_quality('pkg.Class.var', 'cg_name', 'cp_name', signal_type='data')
```

### SVAParser (SVA 提取)

```python
sva = dd.sva

# 列出所有 assertion
for a in sva.assertions:
    print(f'{a.kind} clk={a.clock} expr={a.expression}')
    if a.disable_condition:
        print(f'  disable iff ({a.disable_condition})')

# 列出 property/sequence 定义
for name, prop in sva.properties.items():
    print(f'property {name}')
for name, seq in sva.sequences.items():
    print(f'sequence {name}')
```

### CallGraph (调用图)

```python
cg = dd.call_graph

# 方法列表 (含继承)
methods = cg.get_methods('pkg.my_class')

# 调用关系
calls = cg.get_calls_from('pkg.my_class.body')
for c in calls:
    print(f'{c["callee"]} super={c["is_super"]} randomize={c["is_randomize"]} new={c["is_constructor"]}')

# fork 块
forks = cg.get_forks('pkg.my_class')
for f in forks:
    print(f'fork {f["join_type"]}: {[b["callee"] for b in f["branches"]]}')

# 导出
dot = cg.to_dot()
mermaid = cg.to_mermaid()
```

---

## CLI 命令速查

```bash
# 信号分析
navisv info design.sv top.clk                    # 信号完整信息
navisv trace design.sv src dst                   # 路径追踪
navisv fanout design.sv top.clk                  # fan-out 分析
navisv timing design.sv                          # 时序报告

# 约束分析
navisv constraints design.sv                     # 列出所有 class/constraint
navisv constraints design.sv -v                  # 显示约束体内容
navisv cvar design.sv pkg.Class.var              # Q1: 变量在哪些约束中
navisv cvar -c design.sv pkg.Class.var           # Q1: 含组合穿透
navisv ccons design.sv pkg.Class.constraint      # Q2: 约束影响哪些变量
navisv crel design.sv pkg.Class.a pkg.Class.b    # Q3: 变量关系

# CoverGroup 分析
navisv cg-list design.sv                         # 列出 covergroup/coverpoint/bins
navisv cg-list design.sv -v                      # 显示 bins 详情
navisv cg-check design.sv var cg cp              # bin-constraint 一致性
navisv cg-quality design.sv var cg cp -t data    # 质量评估

# 编译检查
navisv check design.sv                           # 语法检查
navisv check -F filelist.f                       # filelist 检查

# 通用
navisv --json <command>                          # JSON 输出
```

---

## 架构

```
User / AI Agent
     ↓
DesignDriver          # 统一入口
     ↓
┌─────────────────────────────────────────┐
│  Parsers                                │
│    ├── ast_parser.py      (信号/条件)   │
│    ├── netlist_parser.py  (网表)        │
│    ├── constraint_parser.py (约束)      │
│    └── covergroup_parser.py (覆盖)      │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│  Graph Layer                            │
│    ├── design_graph.py    (信号/路径)   │
│    ├── constraint_graph.py (约束查询)   │
│    └── covergroup_analyzer.py (覆盖分析)│
└─────────────────────────────────────────┘
     ↓
slang / slang-netlist
```

### 图结构

**DesignGraph**: NetworkX MultiDiGraph
- 节点: Port / State / Net
- 边: drives / controls + `true_condition` + `edge_kind` + `condition`

**ConstraintGraph**: NetworkX MultiDiGraph
- 节点: Class / Variable / Constraint
- 边: has_var / has_constraint / binds / inherits / member_of

---

## 测试状态

| 测试集 | 数量 | 状态 |
|--------|------|------|
| ConstraintGraph | 43 | ✅ |
| CoverGroup 解析 | 33 | ✅ |
| bin-constraint 一致性 | 12 | ✅ |
| coverage 质量评估 | 9 | ✅ |
| true_condition | 9 | ✅ |
| SVA Parser | 17 | ✅ |
| SVA Generator | 6 | ✅ |
| CallGraph | 17 | ✅ |
| DesignGraph (UART) | 10/10 | ✅ |
| DesignGraph (benchmark) | 75/79 | ✅ (94%) |
| UVM config_db + plusargs | 17 | ✅ |
| UVM TB 静态结构 | 26 | ✅ |
| **总计** | **212** | ✅ |

### DesignGraph 路径追踪详情

| 测试集 | 通过率 | 说明 |
|--------|--------|------|
| UART (10 路径) | 10/10 (100%) | 含 FSM、组合逻辑、拼接表达式 |
| sv-trace benchmarks (79 路径) | 75/79 (94%) | 剩余 4 个是 pipeline 跨域路径 |

---

## 项目结构

```
navisv/
├── cli.py                          # CLI 入口
├── README.md                       # 本文件
├── FEATURE_PLAN.md                 # 功能规划
├── docs/
│   └── covergroup_design.md        # CoverGroup 设计方案
├── navisv/
│   ├── config.py                   # 配置
│   ├── drivers/
│   │   └── design_driver.py        # 统一入口
│   ├── parsers/
│   │   ├── ast_parser.py           # AST 解析
│   │   ├── netlist_parser.py       # 网表解析
│   │   ├── constraint_parser.py    # 约束解析
│   │   └── covergroup_parser.py    # 覆盖解析
│   └── graph/
│       ├── design_graph.py         # 信号/路径查询
│       ├── constraint_graph.py     # 约束查询
│       ├── covergroup_analyzer.py  # 覆盖分析
│       └── graph_builder.py        # 图构建 + true_condition
└── tests/
    ├── sv/                         # 测试用 SV 文件
    ├── test_constraint_graph.py    # 43 测试
    ├── test_covergroup.py          # 33 测试
    ├── test_cg_constraint_check.py # 12 测试
    ├── test_cg_quality.py          # 9 测试
    └── test_true_condition.py      # 9 测试
```

## 环境要求

- Python 3.9+
- networkx
- slang (编译好的二进制)
- slang-netlist (编译好的二进制)

## 许可证

MIT
