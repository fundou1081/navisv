# SERV Decode (serv_decode.v) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 设计概览

| 指标 | 数值 |
|------|------|
| 节点数 | 56 |
| 边数 | 11 |
| Port | 47 |
| State | 8 |
| Instance | 1 |

### 节点列表

```
Instance:
  serv_decode (Instance)

State 节点:
  serv_decode.funct3
  serv_decode.imm25
  serv_decode.imm30
  serv_decode.opcode
  serv_decode.op20
  serv_decode.op21
  serv_decode.op22
  serv_decode.op26

Port 节点 (部分):
  serv_decode.clk
  serv_decode.i_wb_en
  serv_decode.i_wb_rdt
  serv_decode.o_alu_sub
  serv_decode.o_alu_rd_sel
  ... (共 47 个)
```

### 边列表

```
serv_decode.clk -> serv_decode.o_alu_rd_sel
serv_decode.i_wb_en -> serv_decode.funct3
serv_decode.i_wb_en -> serv_decode.o_alu_rd_sel
serv_decode.i_wb_rdt -> serv_decode.imm25
serv_decode.i_wb_rdt -> serv_decode.imm30
serv_decode.i_wb_rdt -> serv_decode.o_alu_rd_sel
serv_decode.i_wb_rdt -> serv_decode.op20
serv_decode.i_wb_rdt -> serv_decode.op21
serv_decode.i_wb_rdt -> serv_decode.op22
serv_decode.i_wb_rdt -> serv_decode.op26
serv_decode.i_wb_rdt -> serv_decode.opcode
```

---

## Q1-S: 指令格式

**问题**: RISC-V 指令如何分解？

### navisv 分析

```bash
# State 节点对应指令分解
serv_decode.funct3   -> bit[14:12]
serv_decode.opcode   -> bits[6:2]
serv_decode.op20     -> bit[20]
serv_decode.op21     -> bit[21]
serv_decode.op22     -> bit[22]
serv_decode.op26     -> bit[26]
serv_decode.imm25    -> bit[25]
serv_decode.imm30    -> bit[30]
```

### 边追踪

```
i_wb_rdt -> funct3   (通过 i_wb_en)
i_wb_rdt -> opcode   (直接)
i_wb_rdt -> op20     (直接)
...
```

### 回答

RISC-V 指令通过 State 节点分解：

| State 节点 | 指令位 | 说明 |
|------------|--------|------|
| funct3 | bits[14:12] | 3-bit funct3 |
| opcode | bits[6:2] | 5-bit opcode |
| op20 | bit[20] | 控制位 |
| op21 | bit[21] | 控制位 |
| op22 | bit[22] | 控制位 |
| op26 | bit[26] | 控制位 |
| imm25 | bit[25] | 立即数位 |
| imm30 | bit[30] | SUB vs ADD |

**navisv 发现**: i_wb_rdt 是这些 State 节点的驱动源。

---

## Q2-S: opcode 编码

**问题**: opcode 如何识别指令类型？

### navisv 分析

```bash
# opcode State 节点
serv_decode.opcode (State)
```

### 回答

**navisv 当前限制**: opcode 解码逻辑（如 `opcode[4]` 分类）需要理解表达式语义，navisv 主要追踪连接关系，不解析条件逻辑。

通过边追踪可以看到：
- `i_wb_rdt -> opcode` 路径存在
- 但 opcode 的解码逻辑（wire 定义）不在 navisv 追踪范围内

---

## Q4-S: o_alu_sub 信号

**问题**: 如何区分 ADD/SUB/SLT/SLTU？

### navisv 分析

```bash
# o_alu_sub 节点
serv_decode.o_alu_sub (Port)

# 边：o_alu_sub 无 driver（铁律26限制）
```

### 问题

**navisv 发现 Issue-F**: `o_alu_sub` 无边，无法追踪其驱动源。

这是因为：
1. `o_alu_sub` 同时有 `always @(*)` 阻塞赋值和 `always @(posedge clk)` 非阻塞赋值
2. 混合赋值导致 slang PathFinder 无法追踪

### 回答

**navisv 无法直接回答此问题**，原因：
1. `o_alu_sub` 在混合 always 块中赋值（铁律26限制）
2. 缺少从 `i_wb_rdt` 到 `o_alu_sub` 的边

---

## Q5-S: PRE_REGISTER 参数

**问题**: PRE_REGISTER 如何影响设计结构？

### navisv 分析

```bash
# State 节点数量
State: 8
  serv_decode.funct3
  serv_decode.imm25
  serv_decode.imm30
  serv_decode.opcode
  serv_decode.op20
  serv_decode.op21
  serv_decode.op22
  serv_decode.op26
```

### 回答

**navisv 当前限制**: parameter 提取不直接支持。

从节点结构可以看出：
- 8 个 State 节点对应 8 个寄存器（funct3, opcode, imm25, imm30, op20, op21, op22, op26）
- 这些 State 节点在 `PRE_REGISTER=1` 时被时钟驱动
- 在 `PRE_REGISTER=0` 时作为组合逻辑

---

## 边分析

### 驱动关系

```
i_wb_rdt -> [funct3, opcode, imm25, imm30, op20, op21, op22, op26]
         -> o_alu_rd_sel

i_wb_en -> funct3
        -> o_alu_rd_sel

clk -> o_alu_rd_sel
```

### 问题

**Issue-F**: `o_alu_sub`, `o_alu_cmp_eq`, `o_alu_bool_op` 等无驱动边。

这些信号在 always @(*) 和 always @(posedge clk) 中都有赋值，导致 PathFinder 无法追踪。

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 指令格式 | ✅ | State 节点映射正确 |
| Q2-S: opcode 编码 | ⚠️ | 需表达式语义理解 |
| Q4-S: o_alu_sub | ❌ | 混合 always 块限制 |

### 关键发现

1. **56 个节点，11 条边**
2. **8 个 State 节点对应指令分解**
3. **Issue-F: 多个输出信号无驱动边**（混合 always 块）
4. **PRE_REGISTER 参数无法直接提取**

### 铁律26限制

当信号在两个 always block 中赋值时，PathFinder 无法追踪：

```verilog
always @(*)    o_alu_sub = co_alu_sub;         // 阻塞
always @(posedge clk) o_alu_sub <= co_alu_sub;  // 非阻塞
```

`o_alu_sub`, `o_alu_cmp_eq`, `o_alu_bool_op` 等都属于此情况。

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18