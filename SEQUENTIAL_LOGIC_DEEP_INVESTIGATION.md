# slang-netlist 时序逻辑追踪 - 深入源码分析

## 核心发现

### 1. PathFinder 只能追踪到一个输出端口

| 输出端口 | 可达性 |
|----------|--------|
| o_alu_rd_sel | ✅ 3个输入可达 |
| 其他43个输出端口 | ❌ 全部不可达 |

### 2. fan_in 链的致命缺陷

**o_alu_rd_sel 的 driver fan_in:**
```
Assignment ID=102 fan_in:
  - ID=102 (self-loop)
  - ID=58, ID=57, ID=56 (partial assign fan_in)
    └── 这些最终连接到 funct3 State 节点
```

**o_alu_sub 的 driver fan_in:**
```
Assignment ID=98 fan_in:
  - ID=98 (self-loop only!)
    └── 无法继续追踪到底层信号
```

### 3. 两个信号的代码结构对比

```verilog
// o_alu_sub 相关代码
wire co_alu_sub = funct3[1] | funct3[0] | (opcode[3] & imm30) | opcode[4];
// always block
o_alu_sub = co_alu_sub;  // line 277
o_alu_sub <= co_alu_sub;  // line 338 (非阻塞)

// o_alu_rd_sel 相关代码
wire [2:0] co_alu_rd_sel;
assign co_alu_rd_sel[0] = (funct3 == 3'b000);  // 多行 partial assign
assign co_alu_rd_sel[1] = (funct3[2:1] == 2'b01);
assign co_alu_rd_sel[2] = funct3[2];
// always block
o_alu_rd_sel = co_alu_rd_sel;  // line 281
o_alu_rd_sel <= co_alu_rd_sel; // line 342
```

**关键差异：** `co_alu_rd_sel` 有多个 partial assign，而 `co_alu_sub` 只有一个连续赋值。

### 4. fan_in 链结构分析

**o_alu_rd_sel:**
```
o_alu_rd_sel (Port ID=28)
  └── fan_in: [ID=28, ID=102, ID=56, ID=57, ID=58]
       ├── ID=28 (Port self-loop) → ID=102
       ├── ID=102 (Assignment) → ID=58,56,57
       └── ID=56,57,58 (partial assigns) → funct3 State
```

**o_alu_sub:**
```
o_alu_sub (Port ID=24)
  └── fan_in: [ID=24, ID=98]
       ├── ID=24 (Port self-loop) → ID=98
       └── ID=98 (Assignment) → ID=98 (self-loop dead end!)
```

### 5. State 节点的特殊性

**funct3 State 节点的 fan_out 包含 Output Port:**
```
State funct3 fan_out (4):
  -> funct3 (self)
  -> Assignment (partial)
  -> Assignment (ID=102)
  -> o_alu_rd_sel (Port!)
```

**其他 State 节点只有 self-loop:**
```
State op21 fan_out (1):
  -> op21 (self only)
```

### 6. getDrivers() 返回的都是 Assignment 节点

| 信号 | Driver | Fan_in | Fan_out |
|------|--------|--------|---------|
| o_alu_sub | Assignment ID=98 | [98 self] | [98 self] |
| o_alu_rd_sel | Assignment ID=102 | [102,58,57,56,102] | [102, o_alu_rd_sel] |

### 7. 问题根源推断

**NetlistBuilder 处理流程：**

1. **连续赋值处理** (`co_alu_sub = ...`):
   - `handleContinuousAssign()` 为 `co_alu_sub` 创建 Assignment 节点
   - 但 `hookupOutputPort()` 可能因为某种原因跳过了这个连接

2. **时序逻辑处理** (`o_alu_sub = co_alu_sub`):
   - 创建 State 节点（用于存储状态）
   - 时钟边连接到 State
   - 数据边从 `co_alu_sub` 的 driver 连接到 State

3. **问题所在:**
   - `co_alu_sub` 的 driver 没有正确连接到 `o_alu_sub` 的 driver
   - fan_in 链在 Assignment 节点断裂，只剩下 self-loop

**可能的原因：**
- `co_alu_sub` 是单行连续赋值，与多行 partial assign 处理方式不同
- `hookupOutputPort()` 的 `portBackRef->getNextBackreference() != nullptr` 检查跳过了某些信号
- DataFlowAnalysis 在处理简单的 `=` 赋值时没有正确建立边

### 8. 源码关键位置

**NetlistBuilder.cpp:**
```cpp
// handleContinuousAssign - 处理连续赋值
void NetlistBuilder::handleContinuousAssign(...) {
  // DataFlowAnalysis 追踪驱动关系
  mergeDrivers(dfa->getEvalContext(), dfa->valueTracker,
               dfa->getState().valueDrivers);
}

// hookupOutputPort - 端口连接
void NetlistBuilder::hookupOutputPort(...) {
  if (portBackRef->getNextBackreference() != nullptr) {
    DEBUG_PRINT("Ignoring symbol with multiple port back refs");
    return;  // ← 可能跳过某些信号
  }
  // 添加驱动边
  addDependency(*driver.node, *portNode, symRef, bounds);
}
```

**DataFlowAnalysis.cpp:**
```cpp
// addDriversToNode - 添加驱动边
// 这里决定了是否正确建立边
```

## 结论

1. **PathFinder.find() 只能追踪组合逻辑路径**，会跳过 State 节点
2. **时序逻辑路径追踪失败的根本原因**是 fan_in 链在 Assignment 节点断裂
3. **只有 `o_alu_rd_sel` 成功**是因为 `co_alu_rd_sel` 的多行 partial assign 形成了特殊的图结构
4. **这不是功能 bug，而是设计限制** - PathFinder 本就不是为时序逻辑设计的

## 建议的替代方案

1. **直接分析 AST** - 不依赖 NetlistGraph，手动追踪 always block 赋值链
2. **修改 NetlistBuilder** - 增强时序逻辑的边连接
3. **接受限制** - 使用其他工具进行时序逻辑分析