# Issue 深入调查分析

> 生成时间：2026-05-18
> navisv 版本：v0.8.0

---

## Issue-M: PathFinder 边数异常减少

### 问题
- serv_decode: BFS 找到 17 条边，PathFinder 只找到 3 条边

### 根因
**PathFinder 只追踪组合逻辑路径，不追踪时序逻辑路径**

分析：
- serv_decode 的输出端口分为两类：

**1. 组合逻辑输出（PathFinder 可追踪）**：
```verilog
assign o_alu_rd_sel = i_wb_rdt ? ... : ...;  // 连续赋值
```
- PathFinder 可以找到 `i_wb_rdt -> o_alu_rd_sel`

**2. 时序逻辑输出（PathFinder 无法追踪）**：
```verilog
always @(posedge clk) begin
    o_alu_sub <= co_alu_sub;  // 寄存器赋值
end
```
- PathFinder 在寄存器处停止，无法追踪到输入
- 被遗漏的信号：`o_alu_sub`, `o_alu_bool_op`, `o_alu_cmp_eq`, `o_alu_cmp_sig` 等

### NetlistGraph 数据
- NetlistGraph 有 120 个节点，84 条边
- Input ports: 3 个（clk, i_wb_rdt, i_wb_en）
- Output ports: 44 个
- PathFinder 只连接了 1 个输出端口（o_alu_rd_sel）

### 结论
PathFinder 是**纯组合逻辑**路径查找工具，不追踪通过 always block 的时序路径。

### 解决方案

**方案 1**：结合 BFS + PathFinder
- PathFinder 处理组合逻辑路径
- BFS 处理时序逻辑路径（通过 State 节点）

**方案 2**：接受限制
- PathFinder 适用于组合逻辑模块
- 时序逻辑模块需要其他方法

**推荐**：方案 1，结合两者优势

---

## Issue-N: 多节点设计无边

### 问题
- darkriscv（76 节点）：0 条边
- tiny-gpu（42 节点）：0 条边

### darkriscv 调查

**NetlistGraph 信息**：
- 146 个节点，86 条边
- Input ports: 15 个
- Output ports: 40 个
- **Connected output ports: 0/40**

**节点类型统计**：
- NodeKind.Assignment: 47
- NodeKind.Constant: 39
- NodeKind.Port: 60
- **State 节点: 0**

**根因分析**：

darkriscv_de10nano 是一个**顶层模块**，包含：
1. 子模块实例化
2. 输出端口直接 assign 常量或简单组合逻辑

示例：
```verilog
assign CLK_VIDEO = clk_sys;           // 直接连线
assign VGA_SL = 0;                     // 常量赋值
assign LED_USER = BLINK[24];           // 简单组合逻辑
```

这些赋值不经过复杂的中间网络，PathFinder 可能无法正确关联输入到输出。

**可能的根因**：
1. PathFinder 在某些 Assignment 类型上查找失败
2. 模块内部的连线关系没有被正确追踪
3. 输入端口（如 clk_sys）没有被识别为输入

### tiny-gpu 调查

文件路径可能不正确，待进一步调查。

### 结论
Issue-N 的根因可能是：
1. 顶层模块没有复杂的内部逻辑
2. PathFinder 的路径查找算法对某些赋值类型不适用
3. 节点 ID 匹配问题

---

## Issue-O: picorv32 segfault

### 问题
- picorv32.v（3049 行）解析时产生 SIGSEGV

### 调查过程
1. ✅ Parse: 成功
2. ✅ Compilation: 成功
3. ✅ Analysis: 成功
4. ❌ NetlistGraph.build(): 崩溃

### 定位
- segfault 发生在 `nl.NetlistGraph()` 或 `sl_graph.build()` 调用时
- 不是 `runAnalysis()` 之后崩溃

### 可能原因
1. picorv32.v 有 slang-netlist 的解析 bug
2. 特定 SystemVerilog 语法导致崩溃
3. 文件过大或包含未处理的语法结构

### 建议
1. 使用更小的测试文件定位问题
2. 检查 picorv32.v 的特殊语法
3. 向 slang-netlist 报告 bug（如果是库的问题）

---

## 总结

| Issue | 根因 | 状态 |
|-------|------|------|
| Issue-M | PathFinder 只追踪组合逻辑，不追踪时序逻辑 | ✅ 已理解 |
| Issue-N | 顶层模块 + PathFinder 限制 | 🔍 待进一步调查 |
| Issue-O | slang-netlist 在特定文件上崩溃 | 🔍 待定位 |