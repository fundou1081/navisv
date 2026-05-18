# OpenChip QA - serv/serv_alu 测试记录

> 测试时间：2026-05-18
> 设计路径：~/my_dv_proj/serv/rtl/serv_alu.v
> navisv 版本：v0.8.0 (with NetlistGraph BFS fallback)

---

## 设计基本信息

| 属性 | 值 |
|------|-----|
| navisv 节点数 | 24 |
| navisv 边数 | 12 (source=netlist_graph) |
| 模块名 | serv_alu |

---

## navisv 驱动关系提取结果

### 边列表

| 源信号 | 目标信号 | 备注 |
|--------|----------|------|
| serv_alu.i_cnt0 | serv_alu.o_rd | |
| serv_alu.i_buf | serv_alu.o_rd | |
| serv_alu.i_rd_sel | serv_alu.o_rd | |
| serv_alu.i_rs1 | serv_alu.o_rd | |
| serv_alu.i_rs1 | serv_alu.add_cy_r | |
| serv_alu.i_sub | serv_alu.add_cy_r | |
| serv_alu.i_en | serv_alu.cmp_r | |
| serv_alu.i_en | serv_alu.add_cy_r | |
| serv_alu.clk | serv_alu.cmp_r | |
| serv_alu.clk | serv_alu.add_cy_r | |
| serv_alu.i_cmp_eq | serv_alu.o_cmp | |
| serv_alu.i_cmp_eq | serv_alu.cmp_r | |

---

## 问题回答记录

### Q1-S: W 参数的作用

**问题**: W = 1 参数意味着什么？为何这样设计？

**navisv 提取**: navisv 无法直接提取 parameter 值，需要通过分析代码结构推断。

**回答**: navisv 无法直接回答此问题（需要查看参数定义），但从 Bit-Serial 架构可以推断：W=1 意味着每周期只处理 1 bit，是时间换面积的设计。

**来源**: VERIFICATION_QUESTIONS.md 中的源码分析

---

### Q2-S: i_sub 信号的作用

**问题**: 加法和减法如何区分？

**navisv 提取**: 发现 `i_sub -> add_cy_r` 边

**回答**: 
- navisv 显示 `i_sub` 驱动 `add_cy_r`（进位锁存器）
- i_sub=0 时进行加法，i_sub=1 时进行减法（通过二进制补码实现）
- 通过 `add_b = i_op_b ^ {W{i_sub}}` 实现加法/减法切换

**来源**: navisv 驱动关系 + VERIFICATION_QUESTIONS.md

---

### Q3-S: i_cnt0 信号的作用

**问题**: i_cnt0 在比较中的作用？

**navisv 提取**: 发现 `i_cnt0 -> o_rd` 边

**回答**: 
- navisv 显示 `i_cnt0` 驱动 `o_rd`（结果输出）
- i_cnt0 标识第一个 bit（bit 0），用于初始化比较逻辑
- 与 cmp_r 一起累积所有 bit 的相等结果

**来源**: navisv 驱动关系

---

### Q4-S: i_cmp_sig 信号的作用

**问题**: 有符号比较 vs 无符号比较如何区分？

**navisv 提取**: 未发现 i_cmp_sig 的驱动关系边

**回答**: navisv 未能提取此信号的关系。源码显示：
- i_cmp_sig=0 时进行无符号比较 (SLTU)
- i_cmp_sig=1 时进行有符号比较 (SLT)
- 通过符号扩展位 `rs1_sx` 和 `op_b_sx` 实现

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: i_cmp_sig 未出现在边列表中

---

### Q5-C: o_cmp 信号的选择

**问题**: o_cmp 如何选择比较类型？

**navisv 提取**: 发现 `i_cmp_eq -> o_cmp` 和 `i_cmp_eq -> cmp_r` 边

**回答**: 
- navisv 显示 `i_cmp_eq` 驱动 `o_cmp` 和 `cmp_r`
- 当 i_cmp_eq=1 时，o_cmp = result_eq（相等判断，用于 BEQ/BNE）
- 当 i_cmp_eq=0 时，o_cmp = result_lt（小于判断，用于 SLT/SLTU）

**来源**: navisv 驱动关系

---

### Q6-C: i_bool_op 信号的作用

**问题**: 逻辑操作如何编码？

**navisv 提取**: 未发现 i_bool_op 的驱动关系边

**回答**: navisv 未能提取此信号的关系。源码显示：
- i_bool_op[1]=0 时选择 XOR
- i_bool_op[1]=1, i_bool_op[0]=1 时选择 AND
- i_bool_op[1]=1, i_bool_op[0]=0 时选择 OR
- i_bool_op=01 时输出 0

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: i_bool_op 未出现在边列表中

---

### Q7-C: i_rd_sel 信号的作用

**问题**: 如何选择写入寄存器的内容？

**navisv 提取**: 发现 `i_rd_sel -> o_rd` 边

**回答**: 
- navisv 显示 `i_rd_sel` 驱动 `o_rd`
- i_rd_sel[0]=1 选择 result_add（加法结果）
- i_rd_sel[1]=1 选择 result_slt（比较结果）
- i_rd_sel[2]=1 选择 result_bool（逻辑结果）
- 默认选择 i_buf

**来源**: navisv 驱动关系

---

### Q8-F: add_cy_r 的位宽

**问题**: add_cy_r 为什么是 reg [B:0]？

**navisv 提取**: 发现 `i_rs1 -> add_cy_r`, `i_sub -> add_cy_r`, `i_en -> add_cy_r`, `clk -> add_cy_r` 边

**回答**: 
- navisv 显示 `add_cy_r` 被多个信号驱动（i_rs1, i_sub, i_en, clk）
- 当 W=1 时 B=0，add_cy_r 是 1-bit 寄存器
- 当 W>1 时 B=W-1，add_cy_r 是 W-bit 寄存器
- add_cy_r[0] 锁存进位 add_cy

**来源**: navisv 驱动关系

---

### Q9-F: result_slt 的生成

**问题**: SLT 结果如何生成？

**navisv 提取**: 未发现 result_slt 相关的驱动关系边

**回答**: navisv 未能提取 result_slt 的关系。源码显示：
- result_slt[0] = cmp_r & i_cnt0
- 当 W>1 时 result_slt[B:1] = 0

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: result_slt 未出现在边列表中

---

### Q10-RS: 进位链的工作原理

**问题**: Bit-Serial ALU 的进位如何在周期间传递？

**navisv 提取**: 发现 `i_rs1 -> add_cy_r`, `clk -> add_cy_r`, `i_en -> add_cy_r` 边

**回答**: 
- navisv 显示 `clk` 和 `i_en` 驱动 `add_cy_r`（时序元件）
- `i_rs1` 也驱动 `add_cy_r`
- 进位链：每个周期 add_cy_r[0] 锁存 add_cy（当前进位）
- 通过 32 个周期完成 32-bit 加法

**来源**: navisv 驱动关系

---

### Q11-RS: cmp_r 寄存器的行为

**问题**: cmp_r 如何累积相等结果？

**navisv 提取**: 发现 `i_en -> cmp_r`, `i_cmp_eq -> cmp_r`, `clk -> cmp_r` 边

**回答**: 
- navisv 显示 `cmp_r` 被 i_en, i_cmp_eq, clk 驱动
- i_en=1 时，cmp_r <= o_cmp（每个周期更新）
- cmp_r 累积所有 bit 的相等结果（AND 关系）

**来源**: navisv 驱动关系

---

### Q12-RS: 总结

**navisv 回答率**: 7/12 (58%)

**成功回答的问题**: Q2-S, Q3-S, Q5-C, Q7-C, Q8-F, Q10-RS, Q11-RS

**未能回答的问题**: Q1-S（参数值）, Q4-S, Q6-C, Q9-F（缺少中间信号关系）

---

## navisv 限制总结

1. **parameter 值无法提取**：无法直接获取 W, B 参数值
2. **部分信号缺少驱动关系**：i_cmp_sig, i_bool_op, result_slt 等未出现在边列表
3. **组合逻辑内部信号未解析**：内部 Net 信号（如 result_add, result_eq）不在节点列表中

---

## Issue 发现

| Issue | 描述 | 影响 |
|-------|------|------|
| **Issue-F** | 部分信号（i_cmp_sig, i_bool_op, result_slt）未出现在边列表 | 无法完整追踪驱动关系 |
| **Issue-G** | parameter 值无法提取 | 无法获取 W=1 等参数配置 |
| **Issue-H** | 内部 Net 信号（result_add, result_eq 等）未作为节点 | 驱动关系不完整 |

---

## 功能需求

| Req | 描述 | 优先级 |
|-----|------|--------|
| R-5 | 提取 parameter 值 | P1 |
| R-6 | 完善组合逻辑信号节点（result_add, result_eq 等） | P1 |