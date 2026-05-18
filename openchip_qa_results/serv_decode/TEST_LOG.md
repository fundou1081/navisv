# OpenChip QA - serv/serv_decode 测试记录

> 测试时间：2026-05-18
> 设计路径：~/my_dv_proj/serv/rtl/serv_decode.v
> navisv 版本：v0.8.0 (with NetlistGraph BFS fallback)

---

## 设计基本信息

| 属性 | 值 |
|------|-----|
| navisv 节点数 | 101 |
| navisv 边数 | 17 (source=netlist_graph) |
| 模块名 | serv_decode |

---

## navisv 驱动关系提取结果

### 边列表

| 源信号 | 目标信号 | 备注 |
|--------|----------|------|
| serv_decode.clk | serv_decode.opcode | |
| serv_decode.clk | serv_decode.funct3 | |
| serv_decode.clk | serv_decode.op20 | |
| serv_decode.clk | serv_decode.op21 | |
| serv_decode.clk | serv_decode.op22 | |
| serv_decode.clk | serv_decode.op26 | |
| serv_decode.clk | serv_decode.imm25 | |
| serv_decode.clk | serv_decode.imm30 | |
| serv_decode.i_wb_rdt | serv_decode.opcode | |
| serv_decode.i_wb_rdt | serv_decode.funct3 | |
| serv_decode.i_wb_rdt | serv_decode.op20 | |
| serv_decode.i_wb_rdt | serv_decode.op21 | |
| serv_decode.i_wb_rdt | serv_decode.op22 | |
| serv_decode.i_wb_rdt | serv_decode.op26 | |
| serv_decode.i_wb_rdt | serv_decode.imm25 | |
| serv_decode.i_wb_rdt | serv_decode.imm30 | |
| serv_decode.i_wb_en | serv_decode.funct3 | |

---

## 问题回答记录

### Q1-S: 指令格式

**问题**: RISC-V 指令如何分解？

**navisv 提取**: 发现 `i_wb_rdt -> opcode/funct3/op20/op21/op22/op26/imm25/imm30` 边

**回答**: 
- navisv 显示 `i_wb_rdt`（32-bit 指令输入）驱动所有分解信号
- opcode, funct3, op20, op21, op22, op26, imm25, imm30 都来自 i_wb_rdt
- 证明指令分解关系正确

**来源**: navisv 驱动关系

---

### Q2-S: opcode 编码

**问题**: opcode 如何识别指令类型？

**navisv 提取**: 发现 `i_wb_rdt -> opcode` 边，但未提取 opcode 的后续逻辑

**回答**: navisv 显示 opcode 来自 i_wb_rdt[6:2]，但 opcode 如何映射到指令类型需要查看源码。

**来源**: VERIFICATION_QUESTIONS.md

---

### Q3-S: funct3 解码

**问题**: funct3 如何区分同类指令？

**navisv 提取**: 发现 `i_wb_rdt -> funct3` 和 `i_wb_en -> funct3` 边

**回答**: navisv 显示 funct3 来自 i_wb_rdt[14:12]，且受 i_wb_en 控制（PRE_REGISTER 配置）

**来源**: navisv 驱动关系

---

### Q4-S: o_alu_sub 信号

**问题**: 如何区分 ADD/SUB/SLT/SLTU？

**navisv 提取**: 未发现 o_alu_sub 的驱动关系边

**回答**: navisv 未能提取 o_alu_sub 的关系。源码显示：
- `co_alu_sub = funct3[1] | funct3[0] | (opcode[3] & imm30) | opcode[4]`
- 多个信号组合决定

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: o_alu_sub 未出现在边列表中

---

### Q5-S: o_alu_cmp_eq 和 o_alu_cmp_sig

**问题**: 比较指令如何区分？

**navisv 提取**: 未发现 o_alu_cmp_eq 和 o_alu_cmp_sig 的驱动关系边

**回答**: navisv 未能提取这两个信号的关系。源码显示：
- `co_alu_cmp_eq = funct3[2:1] == 2'b00`
- `co_alu_cmp_sig = ~((funct3[0] & funct3[1]) | (funct3[1] & funct3[2]))`

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: 比较信号未出现在边列表中

---

### Q6-C: PRE_REGISTER 参数

**问题**: PRE_REGISTER=1 vs PRE_REGISTER=0 的区别？

**navisv 提取**: 未发现 PRE_REGISTER 参数

**回答**: navisv 无法提取 parameter 值。PRE_REGISTER 是 generate 条件：
- PRE_REGISTER=1：寄存器在输入侧
- PRE_REGISTER=0：寄存器在输出侧

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: parameter 无法提取

---

### Q7-C: o_alu_rd_sel 信号

**问题**: ALU 结果选择如何工作？

**navisv 提取**: 未发现 o_alu_rd_sel 的驱动关系边

**回答**: navisv 未能提取此信号的关系。源码显示：
- `co_alu_rd_sel[0] = (funct3 == 3'b000)` (ADD/SUB)
- `co_alu_rd_sel[1] = (funct3[2:1] == 2'b01)` (SLT)
- `co_alu_rd_sel[2] = funct3[2]` (逻辑操作)

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: o_alu_rd_sel 未出现在边列表中

---

## navisv 限制总结

1. **指令分解关系正确**：`i_wb_rdt -> opcode/funct3/op20...` ✅
2. **控制信号关系缺失**：o_alu_sub, o_alu_cmp_eq, o_alu_cmp_sig, o_alu_rd_sel 未提取
3. **parameter 无法提取**：PRE_REGISTER 值未知
4. **generate 语句未处理**：PRE_REGISTER 的两种配置路径未体现

---

## Issue 发现

| Issue | 描述 | 影响 |
|-------|------|------|
| **Issue-I** | 指令译码控制信号（o_alu_*）未出现在边列表 | 无法完整追踪译码逻辑 |
| **Issue-G** | parameter 值无法提取 | 无法获取 PRE_REGISTER 配置 |
| **Issue-J** | generate 语句未处理 | 两种配置路径未体现 |

---

## 功能需求

| Req | 描述 | 优先级 |
|-----|------|--------|
| R-5 | 提取 parameter 值 | P1 |
| R-7 | generate 语句处理 | P2 |
| R-8 | 组合逻辑信号驱动关系补全 | P1 |