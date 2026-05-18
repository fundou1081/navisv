# verilog-axi (AXI Bus) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

| 指标 | 数值 |
|------|------|
| 文件数 | 55 (全部 rtl/*.v) |
| 测试文件 | 5 (限制) |
| 节点数 | 315 |
| 边数 | 57 |

### Instance 节点

```
axi_axil_adapter (def=axi_axil_adapter)
├── axi_axil_adapter.axi_axil_adapter_rd_inst (Instance)
└── axi_axil_adapter.axi_axil_adapter_wr_inst (Instance)
```

---

## Q1-S: AXI 基本架构

**问题**: AXI 总线的基本架构？

### navisv 分析

**navisv 可以列出 AXI 模块的 Instance 节点**：

| 信号 | 说明 |
|------|------|
| m_axil_arready | 地址读准备 |
| m_axil_awready | 地址写准备 |
| m_axil_bvalid | 写响应有效 |
| m_axil_rdata | 读数据 |
| clk | 时钟 |

### 回答

**navisv 可以确认**：
- AXI 协议信号包括 AR/AW/B/R 通道
- 通过 Instance 节点展示模块结构
- AXI- AXI-lite 适配器包含读写分离模块

---

## Q2-S: AXI-lite 适配器

**问题**: AXI 到 AXI-lite 适配器如何工作？

### navisv 分析

```bash
axi_axil_adapter
├── axi_axil_adapter_rd_inst (读实例)
└── axi_axil_adapter_wr_inst (写实例)
```

### 回答

**navisv 可以展示适配器结构**：
- `axi_axil_adapter_rd_inst`: 读通道转换
- `axi_axil_adapter_wr_inst`: 写通道转换

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: AXI 架构 | ✅ | Port/Instance 节点 |
| Q2-S: 适配器结构 | ✅ | Instance 层级 |

### 关键发现

1. **315 节点，57 边**：完整展示 AXI 模块结构
2. **axi_axil_adapter**: 包含读写分离实例
3. **AXI 信号**: 包括地址、数据、响应通道

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18