# OpenTitan (Security Chip) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

| 指标 | 数值 |
|------|------|
| 文件数 | 5 (prim/rtl/*.sv) |
| 节点数 | 55 |
| 边数 | 14 |

### 节点示例

```
prim_alert_sender (Instance)
├── prim_alert_sender.alert_ack_o (Port)
├── prim_alert_sender.alert_req_i (Port)
├── prim_alert_sender.alert_rx_i (Port)
├── prim_alert_sender.alert_set_q (State)
├── prim_alert_sender.alert_state_o (Port)
├── prim_alert_sender.alert_test_i (Port)
├── prim_alert_sender.alert_test_set_q (State)
├── prim_alert_sender.clk_i (Port)
├── prim_alert_sender.ping_set_q (State)
└── ...
```

---

## Q1-S: OpenTitan 基本架构

**问题**: OpenTitan 安全芯片的基本架构？

### navisv 分析

**navisv 可以列出 OpenTitan 模块的节点**：

| 模块 | 说明 |
|------|------|
| prim_alert_sender | Alert 发送器 |
| alert_set_q | Alert 状态寄存器 |
| alert_rx_i | Alert 接收输入 |
| clk_i | 时钟输入 |

### 回答

**navisv 可以确认**：
- OpenTitan 基于 prim 模块库
- prim_alert_sender 处理安全 Alert 信号
- 包含状态机（State）和端口（Port）

---

## Q2-S: Alert 机制

**问题**: OpenTitan 的 Alert 机制如何工作？

### navisv 分析

```bash
# Alert 相关信号
prim_alert_sender.alert_req_i (Port)      # Alert 请求输入
prim_alert_sender.alert_rx_i (Port)       # Alert 接收输入
prim_alert_sender.alert_set_q (State)      # Alert 状态
prim_alert_sender.alert_ack_o (Port)       # Alert 确认输出
```

### 回答

**navisv 可以展示 Alert 信号连接**：
- `alert_req_i`: Alert 请求输入
- `alert_rx_i`: Alert 接收（来自其他模块）
- `alert_set_q`: Alert 状态寄存器
- `alert_ack_o`: Alert 确认输出

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 基本架构 | ✅ | Instance 节点 |
| Q2-S: Alert 机制 | ✅ | Port/State 节点 |

### 关键发现

1. **55 节点，14 边**：展示 OpenTitan prim 模块
2. **prim_alert_sender**: 安全 Alert 处理模块
3. **Alert 协议**：请求-确认握手机制

---

## Issue 收集

| Issue | 描述 | 来源 |
|-------|------|------|
| - | OpenTitan 结构复杂，需要更多文件 | Q1-Q2 |

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18