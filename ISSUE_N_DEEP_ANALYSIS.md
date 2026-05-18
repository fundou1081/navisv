# Issue-N 深调结论

> 调查时间：2026-05-18

---

## 核心发现

**darkriscv_de10nano 是一个"系统集成模块"，不是"功能逻辑模块"**

---

## 对比分析

### serv_alu（有路径）
```
o_cmp fan_in:
  [NodeKind.Port] o_cmp        ← self-loop
  [NodeKind.Assignment] ?      ← 中间赋值节点
  [NodeKind.Port] i_cmp_eq    ← ✅ Input Port 在 fan_in 中
```

**结论**：serv_alu 内部有从 Input Port 到 Output Port 的 NetlistGraph 路径

### darkriscv_de10nano（无路径）
```
CLK_VIDEO fan_in:
  [NodeKind.Port] CLK_VIDEO    ← self-loop
  [NodeKind.Assignment] ?      ← 赋值节点
  ❌ 没有 Input Port 在 fan_in 中
```

**结论**：darkriscv 的 Output Port 只连接到 Assignment，不连接到任何 Input Port

---

## 源码验证

darkriscv_de10nano 的输出赋值：
```verilog
assign CLK_VIDEO = clk_sys;      // 直接连线到另一个信号
assign VGA_SL = 0;               // 常量赋值
assign LED_USER = BLINK[24];     // 内部寄存器
```

**关键问题**：这些 Assignment 的 RHS（如 `clk_sys`）不是 Input Port！

- `clk_sys` 是子模块的输出，不是这个模块的输入
- `BLINK[24]` 是内部寄存器，也不是 Input Port

---

## 根因总结

| 项目 | 模块类型 | Input Ports | Output Ports | PathFinder |
|------|----------|------------|--------------|------------|
| serv_alu | 功能逻辑模块 | 直接驱动输出 | 被输入控制 | ✅ 有路径 |
| darkriscv | 系统集成模块 | 外部输入 | 外部输出 | ❌ 无路径 |

**darkriscv_de10nano 的结构**：
```
Input Ports ──┐
              ├──> 子模块实例化 ──> 输出到子模块
Input Ports ──┘              │
                            └──> Output Ports (通过连线赋值)
```

Input Ports 和 Output Ports 之间**没有直接的功能逻辑路径**，只有子模块连接。

---

## Issue-N 结论

**不是 PathFinder 的 bug，而是模块类型不匹配**

- PathFinder 适用于：**功能逻辑模块**（内部有组合逻辑/时序逻辑）
- PathFinder 不适用于：**系统集成模块**（只有子模块实例化和连线）

**解决方案**：
1. 区分模块类型，对集成模块使用其他分析方法
2. 或者只测试功能逻辑模块，跳过系统集成模块
3. 对集成模块，需要分析子模块实例化的连接关系（需要实现 R-9 跨实例追踪）

---

## 建议

在 navisv 中添加模块类型检测：
- 检测是否为"顶层集成模块"（通过实例化数量、端口复杂度等特征）
- 对这类模块，提示用户 PathFinder 不适用
- 或者自动切换到子模块实例化分析方法