# OpenChip QA - serv/serv_top 测试记录

> 测试时间：2026-05-18
> 设计路径：~/my_dv_proj/serv/rtl/serv_top.v
> navisv 版本：v0.8.0 (with NetlistGraph BFS fallback)

---

## 设计基本信息

| 属性 | 值 |
|------|-----|
| navisv 节点数 | 124 |
| navisv 边数 | 0 |
| NetlistGraph 内部节点 | 25 |
| NetlistGraph 可见节点 | 15 (12 Input Port + 3 Output Port) |

---

## navisv 结果分析

### 为什么边数为 0？

**原因**：
1. NetlistGraph 内部有 25 个节点、9 条边，但 `find_nodes_regex` 只返回 15 个节点
2. 输出端口（o_ibus_cyc, o_ibus_adr, o_ext_rs2）的 fan_in 只包含 Assignment 节点（无 name），没有 Port/State 节点
3. 因此 BFS 无法找到终极 Input Port 驱动源

### NetlistGraph 可见节点

| 类型 | 数量 | 示例 |
|------|------|------|
| Input Port | 12 | clk, i_rst, i_ibus_rdt, i_rdata0, ... |
| Output Port | 3 | o_ibus_cyc, o_ibus_adr, o_ext_rs2 |

---

## Issue 发现

| Issue | 描述 | 影响 |
|-------|------|------|
| **Issue-K** | serv_top 内部信号驱动关系无法提取 | 边数为 0，无法回答任何问题 |

---

## 问题回答记录

### Q1-S: 参数配置

**问题**: serv_top 有哪些可配置参数？

**navisv 提取**: 无法提取 parameter 值

**回答**: navisv 无法回答此问题。源码显示有：
- WITH_CSR, W, B, PRE_REGISTER
- RESET_STRATEGY, RESET_PC
- DEBUG, MDU, COMPRESSED, ALIGN

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: parameter 无法提取

---

### Q2-S: 接口类型

**问题**: 处理器的外部接口有哪些？

**navisv 提取**: 未提取接口信号列表

**回答**: navisv 未能列出接口。源码显示有：
- RF Interface: o_rf_rreq, o_rf_wreq, o_wreg0/1, i_rdata0/1
- Instruction Bus: o_ibus_adr, o_ibus_cyc, i_ibus_rdt
- Data Bus: o_dbus_adr, o_dbus_dat, o_dbus_sel, o_dbus_we

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: 接口列表未提取

---

### Q3-S: 子模块连接

**问题**: 各子模块如何连接？

**navisv 提取**: 边数为 0，无法分析连接关系

**回答**: navisv 无法回答。源码显示：
- i_ibus_rdt → serv_decode → o_alu_*, o_mem_*, o_csr_*
- serv_ctrl → serv_alu → serv_rf_if → o_rf_*
- serv_mem_if → o_dbus_*

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: 子模块连接关系未提取（需要实例解析）

---

### Q4-S: 复位策略

**问题**: RESET_STRATEGY 参数的作用？

**navisv 提取**: 无法提取 parameter 值

**回答**: navisv 无法回答。RESET_STRATEGY="MINI" 使用最简复位策略。

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: parameter 无法提取

---

### Q5-C: Wishbone 总线信号

**问题**: Wishbone 总线信号有哪些？

**navisv 提取**: 边数为 0

**回答**: navisv 未能提取总线信号关系。源码显示：
- o_dbus_adr, o_dbus_dat, o_dbus_sel, o_dbus_we
- o_dbus_cyc, i_dbus_rdt

**来源**: VERIFICATION_QUESTIONS.md

**Issue**: 总线信号关系未提取

---

## navisv 限制总结

1. **顶层模块**：边数为 0，无法提取任何驱动关系
2. **parameter 无法提取**：所有配置参数未知
3. **实例连接未知**：子模块间的连接关系未体现
4. **内部信号复杂**：NetlistGraph 的可见节点有限

---

## 功能需求

| Req | 描述 | 优先级 |
|-----|------|--------|
| R-1 | 实例节点解析：识别 serv_decode, serv_alu 等实例 | P0 |
| R-5 | 提取 parameter 值 | P1 |
| R-9 | 处理模块间连接（跨实例信号追踪）| P2 |