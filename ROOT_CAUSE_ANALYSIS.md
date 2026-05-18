# Issue 根因分析

> 分析时间：2026-05-18
> navisv 版本：v0.8.0

---

## 概述

12 个 Issue 可以归类为 **3 个根本原因**：

| 根本原因 | 影响的 Issue | 占比 |
|----------|-------------|------|
| **RC-1: navisv 只解析信号，不解析实例** | B, L, J | 25% |
| **RC-2: 过度依赖 slang getDrivers() / NetlistGraph** | C, D, E, F, H | 42% |
| **RC-3: 节点属性提取不完整** | G, R-4 | 17% |

---

## RC-1: navisv 只解析信号，不解析实例

### 问题代码

```python
# design_graph.py:99-104
for sym in body:
    kind_name = getattr(sym, 'kind', None)
    kind_name = kind_name.name if hasattr(kind_name, 'name') else str(kind_name) if kind_name else ''
    if kind_name not in ('Variable', 'Port', 'State', 'Net'):  # ❌ 没有 'Instance'
        continue
```

### 根因

**`body` 遍历时过滤掉了 Instance 类型**。slang 的 `Instance` 类型符号（如 `bs_mult_slice I0`, `serv_decode`）被完全忽略。

### 影响链

```
Instance 类型被过滤
    ↓
无法添加实例节点（R-1 未实现）
    ↓
无法解析子模块结构（Issue-B）
    ↓
大型顶层模块只能看到顶层信号（Issue-L）
    ↓
generate 语句中的条件实例化也无法处理（Issue-J）
```

### 对应的 Issue

- **Issue-B**: 实例未解析 → bs_mult 只能看到 11 个信号，缺少 31 个 bs_mult_slice 实例
- **Issue-L**: 大型模块可见性低 → CVA6 只有 10 个 Input Port 可被 NetlistGraph 追踪
- **Issue-J**: generate 未处理 → PRE_REGISTER 两种配置未体现

---

## RC-2: 过度依赖 slang getDrivers() / NetlistGraph

### 问题代码

```python
# design_graph.py:113-151 (_add_edges_from_slang)
def _add_edges_from_slang(self, nl) -> None:
    for node_id in list(self.graph.nodes()):
        sym = body.find(...)
        drivers = list(self._mgr.getDrivers(sym))  # ❌ 对 Net 类型返回 self-loop
        for drv in drivers:
            src_path = drv.path.rootSymbol.hierarchicalPath  # self-loop 时 src == dst
            if src_path == node_id:  # ❌ self-loop 被过滤
                continue
            ...
```

### 根因 1: getDrivers() 对 Net 类型返回 self-loop

**现象**：
```python
# 测试结果
result_add: driver=result_add (self=True)  # Net 类型信号
add_cy: driver=add_cy (self=True)         # Net 类型信号
```

**原因**：slang 的 `getDrivers()` 对**纯组合逻辑 Net 信号**（如 `assign result_add = i_rs1 + add_b`）返回 self-loop，因为它认为 Net 的驱动源是它自己（赋值语句本身）。

**这不是 navisv 的 bug，是 slang 分析粒度的限制**。

### 根因 2: NetlistGraph.find_nodes_regex() 只返回部分节点

**现象**：
```
serv_alu: NetlistGraph 内部 26 节点，find_nodes_regex 只返回 15 个
cva6: NetlistGraph 内部 11 节点，find_nodes_regex 只返回 10 个（全 Input）
```

**原因**：NetlistGraph 的 `find_nodes_regex()` 只返回 **Port 和 State** 节点，**内部的 Net/Assignment/Conditional 节点不可见**。

### 影响链

```
getDrivers() self-loop → 边数归零
    ↓
实现 NetlistGraph BFS fallback
    ↓
但 NetlistGraph 只返回 Port/State 节点
    ↓
内部 Net 信号（如 result_add）不在图中
    ↓
全 Input 设计（bs_mult）无法建边（Issue-D）
    ↓
部分信号（i_cmp_sig, result_slt）不在可见节点中（Issue-E, Issue-F, Issue-H）
```

### 对应的 Issue

- **Issue-C**: getDrivers() self-loop → 已用 BFS fallback 临时解决
- **Issue-D**: 全 Input 设计 → BFS 无法找到 Output 驱动终点
- **Issue-E**: i_cmp_sig 未出现 → 不在 NetlistGraph 可见节点中
- **Issue-F**: o_alu_sub 未出现 → 不在 NetlistGraph 可见节点中
- **Issue-H**: result_add 未作为节点 → 内部 Net 不在可见节点中

---

## RC-3: 节点属性提取不完整

### 问题代码

```python
# design_graph.py:106-111
self.graph.add_node(path,
    name=getattr(sym, 'name', '') or '',
    module=path.rsplit('.', 1)[0] if '.' in path else '',
    bit_width=(0, 0),      # ❌ 硬编码，未提取
    tags=set(),            # ❌ 空集合，未填充
    meta={})              # ❌ 空字典，未填充
```

### 根因

**节点创建时未提取可用属性**：
1. `bit_width` 硬编码为 `(0, 0)`
2. `tags` 永远是空集
3. `meta` 永远是空字典

### 影响

| 属性 | 当前值 | 应该提取的值 |
|------|--------|--------------|
| `bit_width` | `(0, 0)` | 从 signal 的 bit 范围提取 |
| `tags` | `set()` | `{port_input}`, `{port_output}`, `{state}`, `{net}` 等 |
| `meta['parameter']` | `{}` | `{W: 1, PRE_REGISTER: 1}` 等 |

### 对应的 Issue

- **Issue-G**: parameter 值无法提取 → `meta` 未填充
- **R-4**: 端口标签缺失 → `tags` 未填充

---

## 根因 → Issue 映射图

```
                    ┌─────────────────────────────────────────────┐
                    │           RC-1: 只解析信号不解析实例            │
                    │  ┌────────────────────────────────────────┐  │
                    │  │ kind_name not in ('Variable', 'Port',  │  │
                    │  │ 'State', 'Net')                         │  │
                    │  │            ↓                           │  │
                    │  │    body 遍历时过滤掉 Instance           │  │
                    │  └────────────────────────────────────────┘  │
                    └────────────────────┬──────────────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
        ┌───────────┐            ┌───────────┐            ┌───────────┐
        │  Issue-B  │            │  Issue-L  │            │  Issue-J  │
        │ 实例未解析│            │大型模块低 │            │generate未 │
        │           │            │可见性     │            │处理       │
        └───────────┘            └───────────┘            └───────────┘

                    ┌─────────────────────────────────────────────┐
                    │     RC-2: 过度依赖 getDrivers/NetlistGraph  │
                    │  ┌────────────────────────────────────────┐  │
                    │  │ getDrivers() → self-loop (Net类型)     │  │
                    │  │ find_nodes_regex() → 只返回Port/State   │  │
                    │  └────────────────────────────────────────┘  │
                    └────────────────────┬──────────────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
        ┌───────────┐            ┌───────────┐            ┌───────────┐
        │ Issue-C   │            │ Issue-D   │            │Issue-E/F/H│
        │ self-loop │            │全Input设计│            │信号缺失   │
        │ (BFS补救) │            │无法建边   │            │           │
        └───────────┘            └───────────┘            └───────────┘

                    ┌─────────────────────────────────────────────┐
                    │        RC-3: 节点属性提取不完整            │
                    │  ┌────────────────────────────────────────┐  │
                    │  │ bit_width=(0,0), tags=set(), meta={}   │  │
                    │  └────────────────────────────────────────┘  │
                    └────────────────────┬──────────────────────────┘
                                         │
                                 ┌───────┴───────┐
                                 ▼               ▼
                           ┌─────────┐     ┌─────────┐
                           │Issue-G  │     │ R-4     │
                           │parameter│     │端口标签 │
                           │无法提取 │     │缺失     │
                           └─────────┘     └─────────┘
```

---

## 修复策略

| 根本原因 | 修复方案 |
|---------|----------|
| **RC-1** | 在 `_add_nodes_from_slang()` 中添加 `Instance` 类型处理 |
| **RC-2** | 1) 保留 getDrivers() 结果（跨信号驱动）<br>2) 实现 ContinuousAssign 直接解析作为主要建边方式<br>3) 从 body 直接遍历所有 Net 类型，不依赖 NetlistGraph |
| **RC-3** | 1) 提取 signal bit_width<br>2) 根据 kind 添加 tags<br>3) 提取 parameter 值填充 meta |

---

## 验证方法

修复后，预期结果：

| 设计 | 修复前节点数 | 修复后节点数（预期） | 修复前边数 | 修复后边数（预期） |
|------|------------|---------------------|-----------|-------------------|
| bs_mult | 11 | 11 + 31 instances | 0 | > 30 |
| serv_alu | 24 | 24 + 内部Net | 12 | > 20 |
| serv_decode | 101 | 101 + instances | 17 | > 50 |
| cva6 | 253 | 253 + 数百 instances | 0 | > 100 |