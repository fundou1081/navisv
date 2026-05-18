# verilog-ethernet (Ethernet) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

| 指标 | 数值 |
|------|------|
| 文件数 | 5 (部分 rtl/*.v) |
| 节点数 | 282 |
| 边数 | 41 |

### 节点示例

```
axis_eth_fcs (Instance)
├── axis_eth_fcs.clk (Port)
├── axis_eth_fcs.crc_state (State)
├── axis_eth_fcs.fcs_reg (State)
├── axis_eth_fcs.fcs_valid_reg (State)
├── axis_eth_fcs.output_fcs (Port)
├── axis_eth_fcs.output_fcs_valid (Port)
├── axis_eth_fcs.rst (Port)
├── axis_eth_fcs.s_axis_tdata (Port)
└── axis_eth_fcs.s_axis_tkeep (Port)
```

---

## Q1-S: 以太网帧校验

**问题**: FCS (Frame Check Sequence) 如何工作？

### navisv 分析

**navisv 可以列出以太网模块的节点**：

| 节点 | 类型 | 说明 |
|------|------|------|
| axis_eth_fcs | Instance | FCS 计算模块 |
| crc_state | State | CRC 状态机 |
| fcs_reg | State | FCS 寄存器 |
| s_axis_tdata | Port | AXI-Stream 输入数据 |
| output_fcs | Port | FCS 输出 |

### 回答

**navisv 可以确认**：
- `axis_eth_fcs` 是以太网帧校验模块
- `crc_state` 是 CRC 状态机
- AXI-Stream 接口用于数据传输

---

## Q2-S: AXI-Stream 接口

**问题**: 以太网模块如何连接？

### navisv 分析

```bash
# AXI-Stream 信号
axis_eth_fcs.s_axis_tdata (Port)
axis_eth_fcs.s_axis_tkeep (Port)
axis_eth_fcs.output_fcs (Port)
axis_eth_fcs.output_fcs_valid (Port)
```

### 回答

**navisv 可以展示 AXI-Stream 接口**：
- `s_axis_tdata`: 从机数据输入
- `s_axis_tkeep`: 字节使能
- `output_fcs`: FCS 输出
- `output_fcs_valid`: 输出有效标志

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: FCS 工作原理 | ✅ | State/Port 节点 |
| Q2-S: AXI-Stream 接口 | ✅ | Port 节点 |

### 关键发现

1. **282 节点，41 边**：展示以太网模块结构
2. **CRC 状态机**：通过 State 节点体现
3. **AXI-Stream 接口**：标准以太网连接方式

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18