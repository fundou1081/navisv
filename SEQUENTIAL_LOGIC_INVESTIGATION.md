# 时序逻辑路径追踪调查

> 调查时间：2026-05-18
> navisv 版本：v0.8.0

---

## 问题

PathFinder 只能追踪组合逻辑路径，无法追踪时序逻辑路径（通过 always block 的路径）。

---

## 关键发现

### 1. PathFinder.find() vs get_comb_fan_in/fan_out

**发现**：PathFinder.find() 能找到路径，但 get_comb_fan_in/fan_out 无法追踪。

**含义**：PathFinder 可能使用不同的底层数据结构，不依赖 fan_in/fan_out 结构。

### 2. fan_in/fan_out 链在 Assignment 节点断裂

**观察**：
```
Input Port -> Assignment -> ??? -> Output Port
```

中间经过多个 Assignment，但它们的 fan_out 都指向另一个 Assignment，
形成一条长链。但最终无法到达 Output Port。

### 3. serv_decode 的时序逻辑

serv_decode 的输出端口在 always @(posedge clk) 中被赋值：
```verilog
always @(posedge clk) begin
    o_alu_sub <= co_alu_sub;
    o_alu_bool_op <= co_alu_bool_op;
    ...
end
```

PathFinder 在寄存器（always block）处停止追踪。

### 4. State 节点的连接

State 节点（如 `funct3`）可以连接到 Output Port：
```
State funct3 -> Output Port o_alu_rd_sel
```

但 Input Port 无法通过 fan_out 到达 State 节点（链在 Assignment 处断裂）。

---

## 根因

**PathFinder 是组合逻辑路径查找工具**，设计用于：
- 连续赋值（assign）
- 组合逻辑always block
- 运算符和数据流

**它不追踪**：
- 时序逻辑 always block（寄存器赋值 `<=`）
- 跨时钟域的路径
- 需要时间信息的路径

---

## 解决方案

### 方案 1: 接受限制

PathFinder 适用于组合逻辑模块：
- serv_alu（纯组合逻辑）：✅ 9 条边
- serv_decode（时序逻辑）：⚠️ 3 条边（只有组合输出）

### 方案 2: 结合多种方法

1. **PathFinder**：找组合逻辑路径
2. **BFS 通过 State**：找时序逻辑路径
3. **AnalysisManager.getDrivers()**：直接获取驱动关系

### 方案 3: 实现时序逻辑分析

需要：
1. 解析 always block 中的赋值语句
2. 识别寄存器（`<=`）和连线（`=`）
3. 建立从 Input 到寄存器输出的路径

---

## 当前状态

| 模块 | 类型 | PathFinder 边数 | 原因 |
|------|------|----------------|------|
| serv_alu | 组合逻辑 | 9 | ✅ 纯组合逻辑 |
| serv_decode | 时序逻辑 | 3 | ⚠️ 只有组合输出端口 |

---

## 建议

1. **保持当前 PathFinder 实现**：用于组合逻辑
2. **标记时序逻辑模块**：识别并提示用户
3. **调研时序逻辑分析**：
   - 检查 slang 的 Statement 相关 API
   - 或使用 ContinuousAssign 直接建边（R-3）
4. **或者接受限制**：PathFinder 只用于组合逻辑路径

---

## 后续行动

### 短期
- [ ] 评估方案 2/3 的实现复杂度
- [ ] 确定是否需要时序逻辑追踪功能

### 长期
- [ ] 实现时序逻辑分析（如果需要）
- [ ] 支持 always block 赋值解析