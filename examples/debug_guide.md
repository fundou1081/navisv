# navisv Debug 实战指南

> 从 Agent 视角，如何用 navisv 工具组合解决复杂 RTL 问题

---

## 场景 1: "这个信号为什么是 X？"

**工具链**: DesignGraph + true_condition + ConstraintGraph

```python
from navisv import DesignDriver

dd = DesignDriver(['design.sv'])
dd.build()
dg = dd.design_graph

# Step 1: 路径追踪
result = dg.trace_full_path('top.src', 'top.data_out')
for node in result['path']:
    print(f"  {node['signal']}")

# Step 2: 看条件
for src, dst, data in dg.graph.in_edges('top.data_out', data=True):
    tc = data.get('true_condition', '')
    if tc:
        print(f"  {src} → {dst} 条件: {tc}")
```

**输出**: "data_out 来自 reg_data, 条件是 sel==0 且 rst_n 有效"

**实际验证**:
```
a → out_if 条件: !rst_n | !!rst_n && sel == 2'b0
b → out_if 条件: !rst_n | !!rst_n && !sel == 2'b0 && sel == 2'b1
c → out_if 条件: !rst_n | !!rst_n && !sel == 2'b0 && !sel == 2'b1
```

---

## 场景 2: "UVM testbench 的激励流程是什么？"

**工具链**: UVMTestbench + CallGraph

```python
dd = DesignDriver(['uvm_tb.sv'])
dd.build()
uvm = dd.uvm_tb
call = dd.call_graph

# 组件层级
for parent, children in uvm.get_hierarchy('my_env').items():
    print(f"{parent} → {children}")

# 端口连接
for conn in uvm.get_port_connections():
    print(f"{conn['source']} → {conn['target']}")

# 调用图
for path, calls in call._parser.calls.items():
    for c in calls:
        flags = []
        if c.is_randomize: flags.append('randomize')
        if c.is_constructor: flags.append('new')
        print(f"{path.split('.')[-1]} → {c.callee} {flags}")
```

**输出**: "test → env → agent → driver/monitor, driver 接收 write_sequence, 有 3 处 randomize"

**实际验证**:
```
axi_agent → [axi_driver, axi_monitor]
axi_agt.mon.ap → sb.axi_imp
wb_agt.mon.ap → sb.wb_imp
axi_agt.mon.ap → cov.imp
```

---

## 场景 3: "bin 定义合理吗？"

**工具链**: CovergroupAnalyzer

```python
dd = DesignDriver(['design.sv'])
dd.build()
cg = dd.covergroups

# bin-constraint 一致性
issues = cg.check_bin_constraint_consistency('pkg.pkt.length', 'pkt_cg', 'cp_length')
for issue in issues:
    print(f"⚠️ {issue['type']}: {issue['reason']}")

# 质量评估
report = cg.check_coverage_quality('pkg.pkt.length', 'pkt_cg', 'cp_length', signal_type='data')
for r in report:
    if r['type'] == 'warning':
        print(f"⚠️ {r['reason']}")
```

**输出**: "⚠️ dead_bin: bin [0:0] 被 constraint 排除, ⚠️ 缺少极值 bin"

**实际验证**:
```
⚠️ dead_bin: bin [101:200] 被 constraint 排除, 永远无法 hit
⚠️ dead_bin: bin [255:255] 被 constraint 排除, 永远无法 hit
⚠️ missing_illegal_bin: constraint 禁止的取值没有标 illegal_bins
```

---

## 场景 4: "这个 assertion 涉及哪些信号？"

**工具链**: SVAParser + SVAGenerator

```python
dd = DesignDriver(['design.sv'])
dd.build()
sva = dd.sva

# 提取 SVA
for a in sva.assertions:
    print(f"{a.kind}: {a.expression}")
    print(f"  clock: {a.clock}, signals: {a.signals}")
    if a.disable_condition:
        print(f"  disable iff ({a.disable_condition})")

# 生成补充 assertion
gen = dd.sva_generator
for prop in gen.generate_properties():
    print(f"  生成: {prop['body']}")
```

**输出**: "assert valid |-> ##1 ready, signals=[valid, ready], clock=clk"

**实际验证**:
```
Assert          valid |-> ##1 ready
Assume          valid |-> ##[1:3] ready
Assert          valid |-> data != 8'd0
  disable iff (!rst_n)
Restrict        data != 8'd255
```

---

## 场景 5: "FSM 状态转换对吗？"

**工具链**: DesignGraph + true_condition

```python
dd = DesignDriver(['fsm.sv'])
dd.build()
dg = dd.design_graph

# 看 next_state 的所有入边和条件
for src, dst, data in dg.graph.in_edges('top.next_state', data=True):
    tc = data.get('true_condition', '')
    if tc:
        print(f"  {src.split('.')[-1]} → next_state 条件: {tc}")
```

**输出**: "state → next_state 条件: state == IDLE && cmd == LOAD"

**实际验证**:
```
a → out_nested 条件: !rst_n | !!rst_n && sel[1] && sel[0]
b → out_nested 条件: !rst_n | !!rst_n && sel[1] && !sel[0]
c → out_nested 条件: !rst_n | !!rst_n && !sel[1]
```

---

## 工具组合速查

| 问题 | 工具 |
|------|------|
| 信号从哪来？ | `dg.trace_full_path()` |
| 什么条件下触发？ | `true_condition` 边属性 |
| 变量被什么约束？ | `cg.get_constraints_for_variable()` |
| bin 合理吗？ | `cg.check_bin_constraint_consistency()` |
| UVM 结构？ | `uvm.get_hierarchy()` / `get_port_connections()` |
| 调用流程？ | `call.get_calls_from()` / `to_mermaid()` |
| SVA 内容？ | `sva.assertions` |
