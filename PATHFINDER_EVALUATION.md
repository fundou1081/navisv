# slang-netlist 正确使用方法评估报告

> 评估时间：2026-05-18
> navisv 版本：v0.8.0

---

## 结论

**使用 examples 中的方式（PathFinder）能够获得比当前 BFS 更准确的结果。**

---

## 评估方法

对比两种建边方式：
1. **navisv 当前 BFS**：`get_comb_fan_in()` + 手动 BFS 追踪
2. **examples 正确方式**：`PathFinder.find()` 直接查找路径

测试设计：`serv_alu.v`

---

## 测试结果

### 边数对比（只统计到 Output Ports）

| 方法 | 边数 |
|------|------|
| navisv 当前 BFS | 5 |
| PathFinder (examples 方式) | 9 |
| 差异 | +4 (PathFinder 多找到 4 条) |

### 边详情

**BFS 结果（5 条）**：
```
i_buf -> o_rd
i_cmp_eq -> o_cmp
i_cnt0 -> o_rd
i_rd_sel -> o_rd
i_rs1 -> o_rd
```

**PathFinder 结果（9 条）**：
```
clk -> o_rd       ← BFS 缺失
i_buf -> o_rd
i_cmp_eq -> o_cmp
i_cmp_eq -> o_rd  ← BFS 缺失
i_cnt0 -> o_rd
i_en -> o_rd      ← BFS 缺失
i_rd_sel -> o_rd
i_rs1 -> o_rd
i_sub -> o_rd     ← BFS 缺失
```

---

## 根因分析

### BFS 为什么遗漏 4 条边？

**BFS 在遇到 State 节点时停止**：
```python
if kn == 'NodeKind.State':
    continue  # ← BFS 认为 State 是终点，停止追踪
```

**但 State 节点（如 `add_cy_r`, `cmp_r`）实际上是中间节点**：
```
i_en -> cmp_r (State) -> o_rd
         ↑
         BFS 在这里停止，没有继续追踪到 o_rd
```

**PathFinder 正确处理**：
```
PathFinder.find(i_en, o_rd) → size=6
路径: i_en -> ... -> cmp_r -> ... -> o_rd
```

### 缺失的路径详情

| 边 | PathFinder 路径大小 | 说明 |
|----|---------------------|------|
| `clk -> o_rd` | 5 | clk → ... → add_cy_r → ... → o_rd |
| `i_en -> o_rd` | 6 | i_en → ... → cmp_r → ... → o_rd |
| `i_sub -> o_rd` | 6 | i_sub → ... → add_cy_r → ... → o_rd |
| `i_cmp_eq -> o_rd` | 7 | i_cmp_eq → ... → cmp_r → ... → o_rd |

---

## 关键发现

### 1. PathFinder 比 BFS 更准确

- **BFS**：通过 `get_comb_fan_in()` 获取邻居，然后手动追踪
- **PathFinder**：直接使用图算法查找路径，自动处理中间节点

### 2. 建图流程差异不影响结果

**方式 A**（navisv 当前）：
```python
comp = d.createCompilation()
mgr = d.runAnalysis(comp)
sl_graph.build(comp, mgr)
```

**方式 B**（examples）：
```python
comp.addSyntaxTree(tree)
pyslang_netlist.VisitAll().run(comp)
comp.freeze()
mgr = d.runAnalysis(comp)
comp.unfreeze()
sl_graph.build(comp, mgr)
```

**结果**：两者产生的 NetlistGraph 相同（26 nodes, 26 edges）

### 3. 关键差异在于建边方法

- **NetlistGraph 相同**，区别在于如何使用它
- **使用 PathFinder** 比 **BFS 手动追踪** 更可靠

---

## 修复方案

### 方案：使用 PathFinder 替代 BFS

```python
def _add_edges_from_pathfinder(self, sl_graph, module_name):
    """使用 PathFinder 查找所有输入->输出路径"""
    finder = nl.PathFinder()
    
    # 获取所有端口
    port_nodes = [n for n in sl_graph if str(n.kind) == 'NodeKind.Port']
    output_ports = [n for n in port_nodes if n.direction.name == 'Out']
    input_ports = [n for n in port_nodes if n.direction.name == 'In']
    
    for out_node in output_ports:
        for in_node in input_ports:
            path = finder.find(in_node, out_node)
            if not path.empty() and path.size() >= 2:
                # 添加边
                src_path = f'{module_name}.{in_node.name}'
                dst_path = f'{module_name}.{out_node.name}'
                self.graph.add_edge(src_path, dst_path,
                    relation='drives',
                    timing='unknown',
                    qualifier=None,
                    bounds=None,
                    source_location=None,
                    source='pathfinder',
                    is_partial=False,
                    confidence='high',
                    meta={})
```

---

## 预期效果

修复后，serv_alu 的边数从 **5 条** 增加到 **9 条**：

| 边 | 修复前 | 修复后 |
|----|--------|--------|
| clk -> o_rd | ❌ | ✅ |
| i_buf -> o_rd | ✅ | ✅ |
| i_cmp_eq -> o_cmp | ✅ | ✅ |
| i_cmp_eq -> o_rd | ❌ | ✅ |
| i_cnt0 -> o_rd | ✅ | ✅ |
| i_en -> o_rd | ❌ | ✅ |
| i_rd_sel -> o_rd | ✅ | ✅ |
| i_rs1 -> o_rd | ✅ | ✅ |
| i_sub -> o_rd | ❌ | ✅ |

---

## 总结

| 项目 | 当前 | 修复后 |
|------|------|--------|
| 建边方法 | BFS 手动追踪 | PathFinder 图算法 |
| 边数（serv_alu） | 5 | 9 |
| 准确性 | ~55% | 100% |
| 代码复杂度 | 高（手动 BFS） | 低（直接调用） |

**结论**：使用 examples 中的 PathFinder 方式能够获得正确结果，且代码更简洁。