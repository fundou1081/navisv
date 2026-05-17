# navisv 开发指南

**适用项目**：navisv（构建在 slang-netlist 之上的语义导航中间件）
**版本**：v0.6
**日期**：2026-05-17
**关联文档**：
- `ARCHITECTURE.md`（架构设计 v0.8）
- `RULES.md`（项目纪律/铁律，25 条规则）

---

## 一、项目概述

navisv 是一个面向 AI 调试 Agent 的语义导航中间件，基于 slang-netlist 提供结构化的硬件设计查询能力。

**目标**：将低层网表关系转化为面向调试场景的结构化答案，让 AI Agent 能直接提问并沿着明确的路径高效探索。

### 核心分层架构

```
User / AI Agent
     ↓
App Layer          ← 场景应用：SignalProfileApp / ImpactAnalysisApp 等
     ↓
Query Layer        ← 原子查询：QueryService（get_drivers / fanin_cone 等）
     ↓
Graph Layer        ← 数据持有：DesignGraph（networkx DiGraph 唯一存储）
     ↓
slang-netlist      ← 唯一数据来源
```

### 首批 App 清单

| App | 场景 | 核心查询组合 |
|-----|------|-------------|
| SignalProfileApp | "这个信号到底是怎么回事？" | get_drivers + get_loads + fanin_cone |
| ImpactAnalysisApp | "改了它会怎样？" | fanout_cone + 环路检测 |
| RelationshipApp | "A 和 B 有什么关系？" | find_path |
| FindSignalsApp | "和时钟门控相关的信号有哪些？" | search_signals |

---

## 二、环境准备

### 2.1 依赖

- Python 3.9+（slang-netlist 的 `.so` 文件编译于 Python 3.9）
- networkx >= 3.0
- pyslang（系统已安装）

### 2.2 验证 slang-netlist 可用

```python
import sys
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')

from pyslang import driver as sl_driver
import pyslang_netlist as nl

d = sl_driver.Driver()
d.addStandardArgs()
d.sourceLoader.addFiles("your/design.sv")
d.parseAllSources()
comp = d.createCompilation()
mgr = d.runAnalysis(comp)
graph = nl.NetlistGraph()
graph.build(comp, mgr)
print(f'Graph: {graph.num_nodes()} nodes, {graph.num_edges()} edges')
```

### 2.3 项目结构

```
navisv/
├── graph/                    # Graph Layer
│   ├── design_graph.py        # ★ 核心：DesignGraph
│   ├── statement_explorer.py # 边属性注释
│   ├── class_explorer.py     # class 边补充
│   └── schema.py             # DriverInfo / LoadInfo / SignalNode
│
├── query/                    # Query Layer
│   ├── service.py            # QueryService（7 个原子查询）
│   └── models.py             # 数据模型
│
├── apps/                     # App Layer
│   ├── base.py               # BaseApp + AppResponse
│   ├── signal_profile.py     # SignalProfileApp
│   └── ...
│
├── annotators/               # 可选标注
├── examples/                 # 示例脚本
├── tests/                    # 测试
└── docs/
    ├── ARCHITECTURE.md       # 架构文档
    ├── RULES.md              # 项目纪律（铁律）
    └── DEVELOPMENT.md        # 本文档
```

---

## 三、开发流程

### 3.1 每次开发前

1. **阅读架构文档**：确认要改动的模块在 `ARCHITECTURE.md` 中的位置
2. **确认铁律**：改动涉及的功能是否违反 `RULES.md` 中的铁律
3. **规划方案**：按铁律 6（先了解全貌，再规划，再确认，后执行）执行

### 3.2 实现新 App 的步骤

**示例：实现 SignalProfileApp**

1. **写金标准测试**（铁律 8）
   ```python
   # tests/test_apps/test_signal_profile.py
   def test_signal_profile_basic():
       # 期望输出结构 + confidence + summary 非空
       result = SignalProfileApp(query).run("top.clk")
       assert result.confidence in ["high", "medium", "uncertain"]
       assert len(result.summary) > 10
   ```

2. **实现 App**（铁律 17：App 是唯一生成 summary 的层）
   ```python
   # apps/signal_profile.py
   class SignalProfileApp:
       def __init__(self, query: QueryService):
           self.query = query
       
       def run(self, signal: str) -> AppResponse:
           drivers = self.query.get_drivers(signal)
           loads = self.query.get_loads(signal)
           summary = f"信号 {signal} 被 {len(drivers)} 个源驱动..."
           return AppResponse(
               structured={"drivers": drivers, "loads": loads},
               summary=summary,
               confidence="high"
           )
   ```

3. **运行测试**：`pytest tests/test_apps/test_signal_profile.py`

4. **验证 CI 门控**：`pytest -q` 全部通过才能 commit

### 3.3 实现新 Graph/Query 组件的步骤

1. **确认接口**：参考 `ARCHITECTURE.md` 中的接口定义
2. **实现**：遵循铁律 12（Query 只返回结构化数据）、铁律 14（不暴露 DiGraph）
3. **测试**：确保 CI 门控通过

---

## 四、测试

### 4.1 测试目录结构

```
tests/
├── test_discipline/    # 铁律自动化测试（23 条）
├── test_graph/         # Graph Layer 单元测试
├── test_query/         # Query Layer 单元测试
└── test_apps/          # App Layer 测试 + golden 文件
```

### 4.2 运行测试

```bash
# 所有测试
pytest -q

# 只运行 discipline 测试
pytest tests/test_discipline/ -v

# 只运行某个 App 测试
pytest tests/test_apps/test_signal_profile.py -v
```

### 4.3 golden 文件

每个 App 需要对应一个 `golden` 文件，记录已知输入输出的标准答案：

```
apps/
├── signal_profile.py
└── signal_profile_golden.txt
```

golden 文件格式：
```
# 输入: top.clk
# 期望: confidence=high, drivers>=1
top.clk
```

---

## 五、提交规范

### 5.1 commit 消息格式

```
<type>: <short description>

<optional body>

<optional footer>
```

类型：
- `feat`: 新功能（新增 App）
- `fix`: 修复 bug
- `refactor`: 重构（不改变功能）
- `docs`: 文档更新
- `test`: 测试相关
- `chore`: 其他

### 5.2 P0 提交门控

每次 commit 前自检（铁律 1-6）：

- [ ] 无正则源码分析（铁律 1）
- [ ] 无自定义索引（铁律 2）
- [ ] Python 不覆盖 slang 拓扑（铁律 3）
- [ ] `pytest -q` 全部通过（铁律 4）
- [ ] 无临时补丁（铁律 5）
- [ ] 方案已获确认（铁律 6）

---

## 六、遇到问题

### 6.1 铁律冲突

如果需求与铁律冲突，先讨论再实现，不要绕过铁律。铁律是架构的锚点，破坏铁律会让架构腐化。

### 6.2 需要新增铁律

提出 → 讨论 → 确认 → 更新 `RULES.md` → 更新 `ARCHITECTURE.md`（如涉及架构变更）

### 6.3 性能问题

不要预判瓶颈。等 profiling 数据出来后，再针对性优化（Phase 2）。

---

*开发指南版本：v0.6*
*修改：2026-05-17*