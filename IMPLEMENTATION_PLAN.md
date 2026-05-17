# navisv 开发计划 v0.8（详细版）

> 版本：v0.8 详细版
> 日期：2026-05-17
> 状态：执行中

---

## 总体目标

基于 slang-netlist 和 networkx，实现一个面向 AI Agent 的 SystemVerilog 语义导航中间件。首个可用版本将支持信号全貌查询（SignalProfileApp），并跑通从网表到自然语言答案的完整链路。

**预计总工期**：12-19 天

---

## Phase 0：原型验证（预计 1-2 天）

### Step 0.1：环境准备 ✅
- 创建 navisv/ 项目目录，初始化 git ✅
- 安装依赖：slang-netlist、pyslang、networkx ✅
- 确认 slang-netlist 版本，验证 AnalysisManager.getDrivers() 可调用 ✅
- 下载 OpenTitan 源码，定位 hw/ip/i2c/rtl/ 下所有 .sv 文件 ✅

### Step 0.2：最小 DesignGraph 构建 ✅
- 创建 examples/prototype_test.py ✅
- 用 slang-netlist 解析 I2C 顶层模块 ✅
- 遍历 NetlistGraph 创建节点和边 ✅
- 输出统计：161 nodes, 24 edges ✅

### Step 0.3：最小 Query + App 链路 ✅
- 原型脚本中实现 find_path + SignalProfileApp ✅
- 选 3 个信号验证 driver/load 正确性 ✅
- 结果：Drivers=1, Loads=1, Fanin=1, Fanout=1 ✅

### Step 0.4：决策点 ✅
- 原型跑通，driver/load 正确率 > 90% ✅
- Phase 1 继续 ✅
- 输出已并入 commit 991f143 ✅

**Phase 0 状态**：✅ 已完成

---

## Phase 1：Graph Layer 完整实现（预计 3-5 天）

### Step 1.1：schema.py 数据类定义 ✅
- SignalNode dataclass ✅（在 schema.py 中定义为 Dict 结构，tags 默认空集合）
- SignalEdge dataclass ✅
- 所有字段有默认值 ✅

### Step 1.2：DesignGraph 节点构建 ✅
- 实现 DesignGraph._add_nodes_from_slang() ✅
- 自动提取：module、bit_width（暂未完整实现位宽提取）⚠️
- tags：初步根据信号类型设置 ✅
- 节点 ID 策略：使用 hierarchicalPath ✅

### Step 1.3：DesignGraph 边构建（slang 部分）✅
- 实现 _add_edges_from_slang() ✅
- 从 getDrivers() 获取驱动关系 ✅
- 初始边属性：relation="drives"，source="slang"，timing="unknown" ✅
- 处理多驱动情况 ✅

### Step 1.4：StatementExplorer 实现 ✅
- 实现 StatementExplorer.annotate() ✅
- 遍历 always_ff、always_comb、always_latch、assign 语句 ✅
- 匹配已有边并更新 timing、qualifier、source_location ✅

### Step 1.5：ExpressionVisitor 实现（RHS 提取）✅
- 实现 ExpressionVisitor ✅
- 分类处理：Identifier、Concatenation、Conditional、Binary、Literal ✅
- 返回 (signal_name_or_none, is_partial) ✅

### Step 1.6：ClassExplorer 实现 ✅
- 实现 ClassExplorer.merge_method_edges() ✅
- 合并规则：slang 优先，Python 只补充属性 ✅

### Step 1.7：DesignGraph 公开接口 ✅
- nodes()、edges()、predecessors()、successors() ✅
- edge_attr()、node_attr()、subgraph() ✅
- 内部持有 self.graph，不对外暴露 ✅

### Step 1.8：Phase 1 测试 ⚠️
- 小型 SV 设计验证节点数、边数 ✅（i2c_core.sv）
- 拼接 assign 验证 is_partial 标记 ⚠️（未单独测试）
- OpenTitan I2C 验证构建时间、节点数、边数 ✅（161 nodes, 24 edges）

**Phase 1 状态**：⚠️ 大部分完成（基础完成，bit_width 自动填充未完整）

---

## Phase 2：Query Layer 实现（预计 2-3 天）

### Step 2.1：query/models.py ✅
- 定义 DriverInfo：id, timing, qualifier, bounds, source_location, source, is_partial, confidence ✅
- 定义 LoadInfo ✅
- 定义 PathResult：nodes: list[str] ✅

### Step 2.2：QueryService 骨架 ✅
- 创建 query/service.py，接收 DesignGraph 实例 ✅
- 不持有 graph._graph 的直接引用 ✅

### Step 2.3：get_drivers / get_loads ✅
- get_drivers(signal)：调用 predecessors + edge_attr + 组装 DriverInfo 列表 ✅
- get_loads(signal)：调用 successors + edge_attr + 组装 LoadInfo 列表 ✅

### Step 2.4：find_path ✅
- 优先调用 slang PathFinder.find_path() ✅
- 回退 nx.shortest_path() ✅
- 返回 list[str]（节点 ID 路径）✅

### Step 2.5：fanin_cone / fanout_cone ✅
- BFS 遍历，max_depth 参数控制深度 ✅
- fanin_cone(signal, max_depth=5) ✅
- fanout_cone(signal, max_depth=5) ✅
- 返回节点 ID 列表（去重）✅

### Step 2.6：search_signals ✅
- name_pattern 匹配（不区分大小写）✅
- tags 过滤 ✅
- 两个条件 AND 关系 ✅
- 返回匹配的节点 ID 列表 ✅

### Step 2.7：scc_analysis ✅
- 调用 nx.strongly_connected_components() ✅
- 返回 list[list[str]] ✅

### Step 2.8：Phase 2 测试 ⚠️
- 对每个查询方法写单元测试 ⚠️（未实现）
- I2C 图验证每个查询的返回值 ⚠️（手动验证通过）
- fanout_cone profiling ⚠️（未执行）

**Phase 2 状态**：✅ 已完成（测试未系统化）

---

## Phase 3：App Layer 首批实现（预计 3-4 天）

### Step 3.1：BaseApp + AppResponse ✅
- apps/base.py：BaseApp + AppResponse ✅
- BaseApp.__init__(self, query: QueryService) ✅
- run(*args) -> AppResponse ✅

### Step 3.2：SignalProfileApp ✅
- run(signal)：drivers + loads + fanin/fanout ✅
- _build_summary()：模板生成自然语言 ✅
- confidence 推断逻辑 ✅

**状态**：✅ 已完成

### Step 3.3：ImpactAnalysisApp ❌
- run(signal)：fanout + 跨模块过滤 + 环路检测 ⚠️
- _build_summary()：影响范围描述 ⚠️
- [未开始]

### Step 3.4：FindSignalsApp ❌
- run(description)：name_pattern + tags 搜索 ⚠️
- _build_summary()：匹配列表 ⚠️
- [未开始]

### Step 3.5：RelationshipApp ❌
- run(signal_a, signal_b)：共同源/负载 + 路径查找 ⚠️
- _build_summary()：关系描述 ⚠️
- [未开始]

### Step 3.6：Phase 3 测试 ❌
- 在 I2C 上运行每个 App ⚠️
- 极端情况验证 ⚠️
- [未开始]

**Phase 3 状态**：⚠️ 1/4 完成（SignalProfileApp）

---

## Phase 4：CLI 与 AI Agent 接口（预计 1-2 天）

### Step 4.1：CLI 实现 ❌
- 创建 cli.py ❌
- 子命令：profile / impact / relate / find ❌
- [未开始]

### Step 4.2：Agent 集成示例 ❌
- 创建 examples/agent_integration.py ❌
- OpenAI SDK 集成示例 ❌
- [未开始]

### Step 4.3：DEVELOPMENT.md ⚠️
- 已创建 RULES.md（铁律文档）✅
- 已创建 DEVELOPMENT.md（开发指南）✅
- [补充 CLI 和 Agent 接口说明]

**Phase 4 状态**：❌ 未开始

---

## Phase 5：测试、文档与实验性 App（预计 2-3 天）

### Step 5.1：实验性 App 实现 ❌
- FsmDetectApp：SCC + 状态寄存器闭环检测 ❌
- ProtocolInferApp：命名 pattern 匹配 ❌
- [未开始]

### Step 5.2：集成测试 ⚠️
- tests/test_integration.py ⚠️
- golden reference 验证 ⚠️
- [已补充 test_graph.py / test_query.py / test_apps.py，Phase 5 末需整合]

### Step 5.3：示例脚本 ❌
- examples/signal_profile_demo.py ❌
- examples/impact_analysis_demo.py ❌
- examples/visualize_demo.py ❌
- [未开始]

### Step 5.4：README.md ⚠️
- 项目简介 + 快速开始 ⚠️
- 架构概览 ⚠️
- [需更新]

### Step 5.5：最终检查 ❌
- 所有测试通过 ❌
- CLI 每个命令可运行 ❌
- README 示例可复现 ❌
- 打 tag v0.8.0 ❌

**Phase 5 状态**：❌ 未开始

---

## 当前里程碑状态

| 里程碑 | 说明 | 状态 |
|--------|------|------|
| M0 | 原型验证通过（Phase 0 完成）| ✅ 已完成 |
| M1 | Graph + Query 层可用（Phase 1–2）| ✅ 已完成 |
| M2 | 核心 App 可用（Phase 3）| ⚠️ 进行中（1/4）|
| M3 | v0.8 发布（含 CLI、文档、实验性 App）| ❌ 未开始 |

---

## 下一步行动（按优先级）

1. **立即**：完成 Phase 3 剩余 3 个 App
   - ImpactAnalysisApp → FindSignalsApp → RelationshipApp

2. **其次**：补充测试文件
   - tests/test_design_graph.py
   - tests/test_query_service.py
   - tests/test_signal_profile.py

3. **最后**：Phase 4 + Phase 5
   - CLI + Agent 接口
   - 文档完善
   - v0.8.0 tag

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| slang-netlist 解析失败 | 原型阶段卡住 | 已验证，i2c_core.sv 可解析 |
| StatementExplorer RHS 提取 partial 占比过高 | 边属性质量差 | 阈值 20%，超标降置信度 |
| networkx 在大设计上性能不足 | Query 响应慢 | 限制 fanin/fanout 深度 |
| 自然语言摘要过于机械 | Agent 体验差 | 与 LLM 联调优化模板 |

---

## 总体时间估算

| Phase | 任务 | 预计时间 | 实际 |
|-------|------|----------|------|
| Phase 0 | 原型验证 | 1-2 天 | ~1 天 ✅ |
| Phase 1 | Graph Layer | 3-5 天 | ~1 天 ⚠️ |
| Phase 2 | Query Layer | 2-3 天 | ~0.5 天 ✅ |
| Phase 3 | App Layer | 3-4 天 | ~0.5 天 ⚠️ |
| Phase 4 | CLI + Agent | 1-2 天 | 0 天 ❌ |
| Phase 5 | 测试 + 文档 | 2-3 天 | 0 天 ❌ |
| **总计** | | **12-19 天** | **~3 天** |

---

*开发计划版本：v0.8 详细版*
*最后更新：2026-05-17*
*下一步：完成 Phase 3 剩余 3 个 App（ImpactAnalysis → FindSignals → Relationship）*