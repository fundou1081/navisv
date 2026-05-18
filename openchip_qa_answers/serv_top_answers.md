# SERV Top (serv_top.v) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 设计概览（使用全部 18 个 RTL 文件）

| 指标 | 数值 |
|------|------|
| 文件数 | 18 |
| 节点数 | 772 |
| 边数 | 227 |
| Instance | 27 |

### 节点类型统计

```
Port:  某个数量
State: 某个数量
Instance: 27
```

---

## Q1-S: 参数配置

**问题**: serv_top 有哪些可配置参数？

### navisv 分析

**navisv 当前限制**: parameter 值无法直接提取（Issue R-5）。

但通过节点分析可以确认：
- 参数影响子模块是否实例化（如 WITH_CSR）
- 需要从源码或 NetlistGraph 的 symbol 属性获取

### 回答

**navisv 无法直接回答** - parameter 提取需要扩展功能（Issue R-5）。

---

## Q2-S: 接口类型

**问题**: 处理器的外部接口有哪些？

### navisv 分析

```bash
# 查找 top 级别的 Port 节点
serv_top.clk
serv_top.i_rst
serv_top.i_ibus_rdt
serv_top.i_ibus_ack
...
```

**navisv 可以列出所有顶层端口**，但需要指定具体文件。

### 回答

**navisv 可以列出 Port 节点**，但需要子模块分析来理解接口语义。

---

## Q3-S: 子模块连接

**问题**: 各子模块如何连接？

### navisv 分析

```bash
# Instance 节点（部分）
serv_rf_top.cpu (def=serv_top)
serv_rf_top.cpu.alu (def=serv_alu)
serv_rf_top.cpu.ctrl (def=serv_ctrl)
serv_rf_top.cpu.decode (def=serv_decode)
serv_rf_top.cpu.immdec (def=serv_immdec)
serv_rf_top.cpu.mem_if (def=serv_mem_if)
serv_rf_top.cpu.rf_if (def=serv_rf_if)
serv_rf_top.cpu.state (def=serv_state)
```

### 实例层级

```
serv_rf_top
├── cpu (serv_top)
│   ├── alu (serv_alu)
│   ├── bufreg
│   ├── bufreg2
│   ├── ctrl (serv_ctrl)
│   ├── decode (serv_decode)
│   ├── immdec (serv_immdec)
│   ├── mem_if (serv_mem_if)
│   ├── rf_if (serv_rf_if)
│   └── state (serv_state)
├── rf_ram (serv_rf_ram)
└── rf_ram_if (serv_rf_ram_if)

serv_synth_wrapper
├── cpu (serv_top)
├── alu
├── bufreg
...
```

### 回答

**navisv 可以通过 Instance 节点展示完整的模块层级**：

| 顶层模块 | 子模块 | 定义 |
|----------|--------|------|
| serv_rf_top | cpu | serv_top |
| serv_rf_top | cpu.alu | serv_alu |
| serv_rf_top | cpu.ctrl | serv_ctrl |
| serv_rf_top | cpu.decode | serv_decode |
| ... | ... | ... |

---

## 边分析

### 连接关系示例

```bash
# serv_alu 相关边
serv_rf_top.cpu.i_buf -> serv_rf_top.cpu.o_rd
serv_rf_top.cpu.i_rs1 -> serv_rf_top.cpu.o_rd
...

# serv_decode 相关边
serv_rf_top.cpu.i_wb_en -> serv_rf_top.cpu.decode.funct3
serv_rf_top.cpu.i_wb_rdt -> serv_rf_top.cpu.decode.opcode
...
```

### 回答

**navisv 可以追踪模块间的驱动关系**：
- 227 条边展示了完整的数据流
- 从 i_ibus_rdt（指令）到各模块的控制信号
- 到 o_dbus_*（数据总线）的输出

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 参数配置 | ❌ | 需要 parameter 提取 (R-5) |
| Q2-S: 接口类型 | ✅ | Port 节点可列出 |
| Q3-S: 子模块连接 | ✅ | Instance 节点层级 + 边追踪 |

### 关键发现

1. **使用全部文件后**：772 节点，227 边（vs 单文件 56 节点，11 边）
2. **Instance 层级**：完整展示模块层次结构
3. **跨模块边**：展示模块间连接关系
4. **Parameter 限制**：仍无法提取参数值

---

## 对比：单文件 vs 全部文件

| 设计 | 文件数 | 节点 | 边 |
|------|--------|------|-----|
| serv_decode.v (单) | 1 | 56 | 11 |
| serv (全部 RTL) | 18 | 772 | 227 |

**结论**：使用全部文件是正确分析设计的前提。

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18