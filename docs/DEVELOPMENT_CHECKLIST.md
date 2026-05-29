# navisv 开发清单 (设计工程师视角)

> 优先级: P1 > P2 > P3
> 状态: 🟡 待开发 | ✅ 已完成 | 🔄 进行中

---

## P1 - 高优先 (直接影响日常使用)

### P1-1: uncertain 节点显式标记
- [x] `NodeAttr` 已有 `confidence` 字段，检查现状
- [x] `graphviz_exporter.py` 的 DOT/Mermaid 导出函数支持 `confidence` 参数
- [x] uncertain 节点用虚线边框 + "?" 标签
- [x] 测试: UART 项目 uncertain 节点正确显示
- [x] 更新 README 相关说明

### P1-2: 时钟/复位扇出统计
- [x] 新增 `ClockStatsAnalyzer` 类 → `navisv/graph/clock_stats.py`
- [x] 从 `timing='sequential'` 边识别时钟信号 (PosEdge)
- [x] 统计每个时钟驱动的寄存器数量
- [x] 新增 CLI: `navisv clock-stats <file>`
- [x] 输出表格: 时钟域 | 寄存器数 | 寄存器列表
- [x] 测试: UART (7时钟域, 54寄存器) / pipeline (1时钟域, 3寄存器)

### P1-3: CDC 路径列表
- [x] 基于 `RiskAnalyzer._reg_graph` 架构构建独立 `CDCAnalyzer`
- [x] 识别所有 `源时钟域 ≠ 目标时钟域` 的路径
- [x] 新增 CLI: `navisv cdc <file>`
- [x] 输出: CDC 路径表格 (src_reg → dst_reg | src_clock → dst_clock | hop)
- [x] 暂不加分级，先只列路径
- [x] 测试: UART (77条CDC) / pipeline (0条CDC)
- [x] 提交: `0a2571a`, `161d469`, `b771e6a`

---

## P2 - 中优先 (提升结果可信度)

### P2-1: 跨模块路径标注
- [x] 跨模块边检测: `_is_cross_module(src, dst)` 函数 (top-level module 不同)
- [x] DOT: cross-module 边 `style=dashed` + `label="... [X]"` + `penwidth=1.5`
- [x] Mermaid: cross-module 边使用 `-.-` 样式 + `[X]` 后缀
- [x] 模块边界节点 (depth>=4, kind=Port) 用 `doublebox` 形状 + 蓝色高亮
- [x] 测试: chipsonar 5条跨模块边正确标记, 27个模块边界节点

### P2-2: 约束 → Coverage 代码生成
- [ ] 从"文本建议"升级为"可直接运行的 covergroup 代码段"
- [ ] 代码段语法正确性验证 (可用 slang 检查)
- [ ] 新增 CLI: `navisv coverage-suggest <signal> --format code`
- [ ] 测试: 真实 constraint 提取

### P2-3: Risk 图加 confidence 标签
- [x] `export_risk_dot`: uncertain 节点 `doubleoctagon` + 橙色 + `F=0 T=0 ?` 标签
- [x] `export_risk_mermaid`: uncertain 节点 `?⚠️` 后缀 (通过 emit_group)
- [x] 测试: UART tx 模块 uncertain 节点在 DOT 和 Mermaid 中正确显示
- [x] 联动 P1-1 已有实现

### P2-4: 边层级/跳数标注
- [x] DOT: `seq-in` 边加 `penwidth=1.5` (视觉加粗表示寄存器跳)
- [x] DOT: 边标签显示条件信号名或时序类型 `(seq-in)/(seq-out)/(posedge)`
- [x] Mermaid: mermaid_edge 函数统一处理标签逻辑
- [x] 辅助函数: `_node_depth(node)` 返回 hierarchy 深度
- [x] 测试: chipsonar 边标签正确显示
- [x] 提交: `b771e6a` (与 P2-1 合并提交)

---

## P3 - 长期 (待定)

### P3-1: RTL diff (改动前后对比)
- [ ] 讨论需求: 代码 diff 还是网表 diff？
- [ ] 设计输入格式 (git diff / 两个文件目录)
- [ ] 输出: 影响范围变化清单

---

## 技术债务 (穿插在开发中处理)

- [ ] `ast_analyzer.py` 的 `NodeAttr` 类检查 — 是否所有场景都正确设置 `confidence`
- [ ] 清理 `TODO_IMPROVEMENTS.md` 里的已知问题
- [ ] 补充边界测试用例 (跨模块、参数化模块、嵌套 generate)
- [ ] 检查 239 个测试是否都真正通过

---

## 测试项目 (用于验证每个功能)

| 项目 | 路径 | 规模 | 用途 |
|------|------|------|------|
| UART | `/tmp/UART-Implementation/.../uart_controller.sv` | 229节点 | P1-1, P1-2, P1-3 |
| pipeline | `~/my_dv_proj/sv-trace/benchmarks/10_pipeline.sv` | 75节点 | P1-1, P1-3 |
| chipsonar | `~/my_dv_proj/chipsonar/large_design.sv` | 115节点 | P1-2, P2-4 |
| 多模块设计 | 待找或构造 | - | P2-1 |

---

## 开发顺序建议

```
第一轮 (1-2周):
  P1-3 → P1-2 → P1-1 (从 CDC 开始，因为设计工程师最需要)

第二轮 (2-3周):
  P2-3 → P2-4 → P2-2 → P2-1

第三轮:
  P3-1 (待讨论)
```

---

## 备注

- P2-3 与 P1-1 高度相关，建议 P1-1 完成后紧接着做
- P2-4 可以在 P1-3 (CDC) 完成后，顺手加上边层级标注
- P2-2 需要先确认"生成代码段"的需求优先级再开始