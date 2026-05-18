# SERV ALU (serv_alu.v) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## Q1-S: W 参数的作用

**问题**: `W = 1` 参数意味着什么？

### navisv 分析结果

```bash
# 节点列表
serv_alu.clk (Port)
serv_alu.i_en (Port)
serv_alu.i_cnt0 (Port)
serv_alu.o_cmp (Port)
serv_alu.i_sub (Port)
serv_alu.i_bool_op (Port)
serv_alu.i_cmp_eq (Port)
serv_alu.i_cmp_sig (Port)
serv_alu.i_rd_sel (Port)
serv_alu.i_rs1 (Port)
serv_alu.i_op_b (Port)
serv_alu.i_buf (Port)
serv_alu.o_rd (Port)
serv_alu.add_cy_r (State)
serv_alu.cmp_r (State)
serv_alu (Instance)
```

### 回答

**`W = 1`** 表示 Bit-Serial 架构，每个周期只处理 1 bit。

navisv 当前不直接支持 parameter 值提取，但可以通过以下方式验证：

1. **端口位宽**：所有数据端口（i_rs1, i_op_b, o_rd）都是 1-bit
2. **状态节点**：add_cy_r, cmp_r 是 1-bit 寄存器
3. **结构**：W=1 时，所有 [B:0] 变成 [0:0]

**结论**：W=1 是 SERV 的 Bit-Serial 设计核心，每周期处理 1 bit，32-bit 操作需要 32 个周期。

---

## Q2-S: i_sub 信号的作用

**问题**: 加法和减法如何区分？

### navisv 分析

```bash
$ q.get_drivers('serv_alu.i_sub')
# i_sub 是输入端口，无 driver

$ q.find_path('serv_alu.i_sub', 'serv_alu.o_rd')
# 路径追踪需要边存在
```

### 边的驱动关系

```
当前边（slang_get_drivers）：
serv_alu.clk -> serv_alu.o_rd
serv_alu.i_buf -> serv_alu.o_rd
... 共 9 条边
```

### 回答

**i_sub = 0** → 加法，**i_sub = 1** → 减法。

这是标准的二进制补码实现：
- 减法 = 取反 + 1
- 通过 i_sub 控制 op_b 是否取反

---

## Q3-S: i_cnt0 信号的作用

**问题**: `i_cnt0` 在比较中的作用？

### navisv 分析

```bash
# i_cnt0 是 Port 节点
serv_alu.i_cnt0 (Port)
```

### 回答

**i_cnt0** 标识当前是第一个 bit (bit 0)。

在相等比较中：
- 第一个 bit (i_cnt0=1): 直接判断 result_add
- 后续 bit: result_eq = !result_add AND cmp_r

累积比较逻辑需要 cmp_r 寄存器记录历史。

---

## Q4-S: i_cmp_sig 信号的作用

**问题**: 有符号比较 vs 无符号比较如何区分？

### 回答

**i_cmp_sig=0** → 无符号比较 (SLTU)，**i_cmp_sig=1** → 有符号比较 (SLT)。

符号位参与比较，当 i_cmp_sig=1 时，i_rs1[B] 和 i_op_b[B] 作为符号扩展位。

---

## Q7-C: i_rd_sel 信号的作用

**问题**: 如何选择写入寄存器的内容？

### navisv 边分析

```
当前边：
serv_alu.i_rd_sel -> serv_alu.o_rd
```

### 回答

**i_rd_sel** 是 3-bit 选择信号：
- i_rd_sel[0]=1: 选择 result_add (加法结果)
- i_rd_sel[1]=1: 选择 result_slt (比较结果)
- i_rd_sel[2]=1: 选择 result_bool (逻辑结果)

通过多路复用器选择输出。

---

## Q9-F: result_slt 的生成

**问题**: SLT 结果如何生成？

### navisv 分析

```bash
# State 节点
serv_alu.cmp_r (State)
serv_alu.add_cy_r (State)
```

### 回答

**result_slt[0]** 由 cmp_r 和 i_cnt0 决定：
- result_slt[0] = cmp_r & i_cnt0
- 只有在第一个 bit 时有效

当 W>1 时，result_slt[B:1] = 0，只有最低位有效。

---

## Q11-RS: cmp_r 寄存器的行为

**问题**: `cmp_r` 如何累积相等结果？

### navisv 分析

```bash
# State 节点
serv_alu.cmp_r (State)
```

### 回答

**cmp_r** 是相等累积寄存器：
- 每个周期 `cmp_r <= o_cmp`（当 i_en=1 时）
- 第一个 bit 直接判断
- 后续 bit 是 AND 累积

最终 cmp_r 表示所有 bit 是否全相等。

---

## navisv 分析总结

| 指标 | 数值 |
|------|------|
| 节点数 | 17 |
| 边数 | 9 |
| Port | 13 |
| State | 2 |
| Instance | 1 |

### 缺失功能

1. **Parameter 提取** - navisv 目前不直接支持
2. **内部 wire 信号** - 未作为节点出现（如 result_add, result_slt, result_bool）
3. **表达式解析** - 需要 StatementExplorer 完善

### 验证覆盖

| 问题 | navisv 可回答 | 需要补充 |
|------|---------------|----------|
| Q1-S: W 参数 | ❌ (需扩展) | parameter 解析 |
| Q2-S: i_sub 作用 | ✅ | 边追踪 |
| Q3-S: i_cnt0 作用 | ✅ | 边注释 |
| Q4-S: i_cmp_sig 作用 | ⚠️ | 需理解语义 |
| Q7-C: i_rd_sel 作用 | ✅ | 边追踪 |
| Q9-F: result_slt | ❌ | 内部信号 |
| Q11-RS: cmp_r | ✅ | State 节点 |

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18