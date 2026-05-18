# OpenChip QA - clacc/bs_mult 测试记录

> 测试时间：2026-05-18
> 设计路径：~/my_dv_proj/clacc/bs_mult.v
> navisv 版本：v0.8.0 (with NetlistGraph BFS fallback)

---

## 设计基本信息

| 属性 | 值 |
|------|-----|
| navisv 节点数 | 11 |
| navisv 边数 | 0 |
| NetlistGraph 可见节点 | 5 (全是 Input Port) |
| NetlistGraph 内部节点 | 6 |

---

## Issue 发现

| Issue | 描述 |
|-------|------|
| **Issue-B** | bs_mult 所有端口都是 Input，没有 Output Port，因此 NetlistGraph BFS 无法找到驱动关系（因为输入端口是终极驱动源，不会被追踪） |
| **Issue-E** | 31 个 bs_mult_slice 实例完全未被解析（navisv 只看到顶层的 11 个信号） |

---

## 问题回答记录

### Q1-S: Booth 编码原理

**问题**: Booth 编码如何减少部分积数量？

**navisv 提取**:
- 节点列表中包含 `xy` 信号（x & y 的结果）
- 无法获取 `assign xy = x & y` 这个驱动关系

**回答**: navisv 无法完整回答，需要查看源码。

---

### Q2-S: Slice 数量

**问题**: 为什么有 31 个 slice 实例？

**navisv 提取**:
- navisv 只解析了顶层信号（11 个节点）
- 没有实例节点信息

**回答**: navisv 无法回答，缺少实例解析功能（Issue-B）。

---

### Q3-S ~ Q16-RS

（待续 - 需要更深入的源码分析）

---

## navisv 限制总结

1. **端口全为 Input**：NetlistGraph BFS 无法追踪到 Output 驱动
2. **缺少实例节点**：无法看到 31 个 bs_mult_slice 实例
3. **驱动关系丢失**：当前边数为 0

---

## 需求记录

| Req | 描述 | 优先级 |
|-----|------|--------|
| R-1 | 实例节点解析：将 Instance 添加为节点 | P0 |
| R-2 | Output Port 驱动关系：处理全 Input 设计 | P1 |
| R-3 | ContinuousAssign 直接建边：替代 getDrivers() | P1 |