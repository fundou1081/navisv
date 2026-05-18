# navisv 项目纪律（铁律）

**适用项目**：navisv（构建在 slang-netlist 之上的语义导航中间件）
**版本**：v0.7
**日期**：2026-05-17
**关联文档**：`ARCHITECTURE.md`（架构设计）、`DEVELOPMENT.md`（开发指南）

> **TDD 视角说明**：本文件中的每条铁律都是"需求"，必须同时伴随可执行的自动化测试。无法被自动化测试验证的铁律必须加强描述，划入"手动审查"范围，并标注下次自动化截止日期。

---

## 状态标注

| 状态 | 说明 | 触发校验 |
|------|------|---------|
| [A] | 自动化测试已覆盖 | CI 强制执行 |
| [M] | 仅手工审查 | 人工审查 |
| [TBD] | 待补充自动化测试 | 应在实现前补齐 |

---

## 一、核心铁律（不可妥协）

### 铁律 1：slang-netlist 唯一数据源 [A]

**必须**：所有硬件语义（driver/load/路径/时序）必须且仅通过 slang-netlist 提取

**严禁**：
- 直接正则分析 SV 源码
- 在 navisv 层重新实现 driver/load 逻辑
- 用字符串匹配代替网表查询

**原理**：slang-netlist 已经正确处理了 SV 的拼接赋值、位选择、多驱动等复杂语义，重复实现必然引入错误。

**自动化测试**：
```python
# tests/test_discipline/test_no_regex_in_analysis_files.py
def test_no_regex_in_analysis_files():
    for f in glob("navisv/**/*.py"):
        tree = ast.parse(open(f).read())
        imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == 're']
        assert len(imports) == 0, f"{f} 导入了 re 模块"
```

---

### 铁律 2：networkx DiGraph 是唯一查询接口 [A]

**必须**：`DesignGraph.graph`（`nx.DiGraph`）是 navisv 内部唯一的数据结构

**严禁**：
- 维护 `DiGraph` 之外的任何自定义索引字典（如 `_driver_index`、`_node_dict`）
- Phase 1 为高频查询预先计算并缓存结果
- 创建双层存储（一个 dict + 一个 networkx 视图）

**Phase 1 策略**：直接调用 networkx API，无缓存。如果 profiling 显示高频调用成为瓶颈，Phase 2 再针对性加缓存。

**自动化测试**：
```python
# tests/test_discipline/test_no_custom_indexes.py
def test_no_custom_indexes():
    for f in glob("navisv/graph/*.py"):
        content = open(f).read()
        forbidden = ["_driver_index", "_node_dict", "_edge_cache", "_edge_index"]
        for kw in forbidden:
            assert kw not in content, f"{f} 包含被禁止的自定义索引: {kw}"
```

---

### 铁律 3：slang 是拓扑权威，Python 可用 PathFinder 创建边 [A]

**必须**：
- `source="slang"` 的边是最权威的拓扑关系，Python 层不能覆盖其核心属性（relation、timing）
- Python 层可以使用 PathFinder 结果创建边（`source="pathfinder"`），confidence 为 'high'
- 如果 `source="slang"` 的边已存在，Python 不能改变其 relation、timing 等核心属性

**合并逻辑**：
```python
# ClassExplorer 的合并原则
if graph.has_edge(src, dst):
    existing = graph.edges[src, dst]
    if existing.get("source") == "slang":
        # slang 拓扑优先，只补充 Python 独有的字段
        if not existing.get("source_location") and info.get("source_location"):
            existing["source_location"] = info["source_location"]
    else:
        existing.update(info)
else:
    graph.add_edge(src, dst, **info, source="python", confidence="medium")
```

**自动化测试**：
```python
def test_python_cannot_override_slang_topology():
    content = open("navisv/graph/class_explorer.py").read()
    assert "existing['relation']" not in content or "slang" not in content
```

---

### 铁律 4：回归测试不通过不能 commit [A]

**必须**：所有回归测试必须通过才能 commit，CI 强制门控

**严禁**：跳过测试、临时注释掉失败测试、用 `--no-test` 构建

**自动化测试**：
```python
# tests/test_discipline/test_ci_gate.py
def test_ci_gate_regression():
    result = subprocess.run(["pytest", "-q", "--tb=short"], capture_output=True)
    assert result.returncode == 0
```

---

### 铁律 5：禁止以快速方式打补丁通过测试 [A]

**必须**：测试失败时必须找到根本原因并正确修复，禁止用打补丁方式绕过

**禁止行为**：
```python
# ❌ 临时补丁
if not result:
    return default_result

# ❌ 注释掉失败测试
# def test_that_fails():
#     pass
```

**自动化测试**：
```python
def test_no_commented_tests():
    for f in glob("tests/**/*.py"):
        for i, line in enumerate(open(f).read().split('\n')):
            if line.strip().startswith('#') and 'def test_' in line:
                raise AssertionError(f"{f}:{i+1} 包含被注释掉的测试")
```

---

### 铁律 6：先了解全貌，再规划，再确认，后执行 [A]

**必须**：任何代码改动前，按以下顺序执行：

**步骤 1（了解全貌）**：阅读 `ARCHITECTURE.md`（v0.8）理解分层架构 + 铁律

**步骤 2（规划理想方案）**：评估改动影响范围，确认与项目愿景一致

**步骤 3（用户确认）**：将方案和 trade-off 呈现给用户，等待明确确认后再执行

**步骤 4（执行）**：按确认方案实现，实现后与规划对比

**禁止**：
- ❌ 拿到需求就写代码，不读文档
- ❌ 用"简单方案"破坏架构完整性
- ❌ 不与用户确认就自行决定 scope 或优先级

---

### 铁律 7：需求理解优先序 [M]

**Level 1**：阅读 `ARCHITECTURE.md` 理解项目全貌

**Level 2**：查阅 slang-netlist 源码注释、pyslang API 文档

**Level 3**：主动向用户索要信息，明确说明不确定点

**手动审查清单**：
- [ ] 任务开始前是否已完整阅读架构文档？
- [ ] 实现中遇到不明确的点是否先查阅文档而非猜测？
- [ ] 无法确认的假设是否主动向用户确认？

---

## 二、实现质量

### 铁律 8：先写测试再写实现 [A]

**必须**：实现任何新 App 前必须先写好金标准测试

**流程**：人工推导 → 写测试 → 实现 → 对比 → 提交

**自动化测试**：
```python
def test_no_app_impl_without_golden():
    for app_file in glob("navisv/apps/*.py"):
        if not app_file.endswith("base.py") and "class " in open(app_file).read():
            golden = app_file.replace(".py", "_golden.txt")
            assert exists(golden), f"{app_file} 有实现但无对应 golden 文件"
```

---

### 铁律 9：金标准测试必须覆盖 Corner Case [A]

**必须**：每个 App 的金标准测试必须包含空输入、Corner Case、多驱动场景

**自动化测试**：
```python
def test_golden_cover_corner_cases():
    for app in ["signal_profile", "impact_analysis", "relationship"]:
        golden = f"navisv/apps/{app}_golden.txt"
        assert exists(golden)
        content = open(golden).read()
        assert "nonexistent" in content or "empty" in content
```

---

### 铁律 10：置信度不可信则不输出 [A]

**必须**：无法解析时必须显式返回 `confidence: "uncertain"`，严禁静默跳过

**自动化测试**：
```python
def test_error_must_set_uncertain():
    result = signal_profile_app.run("nonexistent_signal")
    assert result.confidence == "uncertain"
```

---

### 铁律 11：返回必须有 confidence 标注 [A]

**必须**：`confidence` 必须是 `"high"` / `"medium"` / `"uncertain"` 之一

**自动化测试**：
```python
def test_confidence_values_valid():
    result = signal_profile_app.run("top.clk")
    assert result.confidence in ["high", "medium", "uncertain"]
```

---

## 三、Query Layer 约束

### 铁律 12：Query Layer 只返回结构化数据 [A]

**必须**：
- QueryService 的所有方法返回纯结构化数据（`list[DriverInfo]` / `list[str]` 等）
- **不**返回包含 `summary` 的对象
- 不生成任何自然语言文本

**禁止**：
```python
# ❌ 错误：QueryService 返回带 summary
class QueryService:
    def get_drivers(self, signal):
        return AppResponse(structured=..., summary="...")  # 禁止！
```

**自动化测试**：
```python
def test_query_service_no_summary():
    content = open("navisv/query/service.py").read()
    assert "summary" not in content
    assert "AppResponse" not in content
```

---

### 铁律 13：Query Layer 是 App Layer 的唯一数据通道 [A]

**必须**：App 只能通过 QueryService 获取数据，不能直接调用 DesignGraph

**禁止**：
```python
# ❌ 错误：App 直接持有 DesignGraph
class MyApp:
    def __init__(self):
        self.graph = DesignGraph(...)  # 禁止！

# ✅ 正确：App 持有 QueryService
class MyApp:
    def __init__(self, query: QueryService):
        self.query = query
```

**自动化测试**：
```python
def test_apps_no_direct_graph_access():
    for app_file in glob("navisv/apps/*.py"):
        content = open(app_file).read()
        assert "DesignGraph" not in content or "QueryService" in content
        assert ".graph.predecessors" not in content
        assert ".graph.successors" not in content
```

---

## 四、Graph Layer 约束

### 铁律 14：DesignGraph 禁止暴露内部 DiGraph [A]

**必须**：
- `self.graph`（`nx.DiGraph`）是内部属性，不公开访问
- 所有查询必须通过 DesignGraph 的最小公开接口
- `subgraph()` 是 Query Layer 内部算法使用，不暴露给 App

**禁止**：
```python
# ❌ 错误
result = app.query.graph.predecessors(signal)

# ✅ 正确
result = app.query.get_drivers(signal)
```

**自动化测试**：
```python
def test_design_graph_no_public_graph():
    content = open("navisv/graph/design_graph.py").read()
    assert "return self.graph" not in content
```

---

### 铁律 15：StatementExplorer 是边注释者，不是边构建者 [A]

**必须**：
- StatementExplorer 的角色是**注释**已存在的边（补充 timing/qualifier/source_location）
- 边本身由 slang getDrivers() 创建
- StatementExplorer 不调用 `graph.add_edge()`

**自动化测试**：
```python
def test_statement_explorer_no_add_edge():
    content = open("navisv/graph/statement_explorer.py").read()
    assert "add_edge" not in content or "# ClassExplorer" in content
```

---

### 铁律 16：annotators/ 是可选模块，核心构建流程不依赖 [A]

**必须**：
- `DesignGraph._build()` 不调用任何 annotators
- `enable_annotators=False` 时也能正常构建
- annotators 失败不能导致 `_build()` 失败

**自动化测试**：
```python
def test_annotators_optional():
    graph = DesignGraph(["top.sv"], enable_annotators=False)
    assert len(graph.nodes()) > 0
```

---

## 五、App Layer 约束

### 铁律 17：App Layer 是唯一生成自然语言的层 [A]

**必须**：
- 任何面向用户的自然语言摘要必须由 App 层生成
- 不可下沉到 Query Layer 或 Graph Layer 生成 summary

**自动化测试**：
```python
def test_only_apps_generate_summary():
    for f in glob("navisv/**/*.py"):
        if f.startswith("navisv/graph/") or f.startswith("navisv/query/"):
            content = open(f).read()
            assert "summary = " not in content
```

---

### 铁律 18：App 原子化 [A]

**必须**：一个 App 对应一个实现文件，实现一个用户场景

**自动化测试**：
```python
def test_one_app_per_file():
    for f in glob("navisv/apps/*.py"):
        if f.endswith("base.py"):
            continue
        classes = [n.name for n in ast.walk(ast.parse(open(f).read()))
                   if isinstance(n, ast.ClassDef) and not n.name.startswith('_')]
        assert len(classes) <= 1, f"{f} 包含多个 App 类"
```

---

### 铁律 19：实验性 App 必须标记 experimental [A]

**必须**：FsmDetectApp / ProtocolInferApp 等实验性 App 必须返回 `experimental=True`

**自动化测试**：
```python
def test_experimental_app_has_flag():
    content = open("navisv/apps/fsm_detect.py").read()
    assert "experimental=True" in content or "experimental: bool = True" in content
```

---

## 六、架构约束

### 铁律 20：Visitor 模式处理语法节点 [A]

**必须**：对 pyslang SyntaxNode 的遍历必须使用 Visitor 模式，禁止 if-elif 链

**自动化测试**：
```python
def test_no_if_elif_kind_chain():
    for f in glob("navisv/**/*.py"):
        lines = open(f).read().split('\n')
        for i, line in enumerate(lines):
            if re.search(r'if\s+.*["\']kind', line):
                for j in range(i+1, min(i+10, len(lines))):
                    if 'elif' in lines[j] and 'kind' in lines[j]:
                        raise AssertionError(f"{f}:{i+1} 使用 if-elif kind 链")
```

---

### 铁律 21：强断言原则 [A]

**禁止**：
```python
# ❌ 弱断言
assert len(result) >= 0
assert result is not None
```

**必须**：
```python
# ✅ 强断言
assert len(result.drivers) == 2
assert "top.clk" in [d.id for d in result.drivers]
```

**自动化测试**：
```python
def test_no_weak_assertions():
    for f in glob("tests/**/test_*.py"):
        content = open(f).read()
        for bad in ["assertTrue(len(result) >= 0)", "assertIsNotNone(result)"]:
            assert bad not in content
```

---

### 铁律 22：负面测试原则 [A]

**必须**：每个 App 必须有对应的负面测试

**自动化测试**：
```python
@pytest.mark.parametrize("app", ALL_APPS)
def test_signal_not_found_returns_uncertain(app):
    result = app.run("nonexistent_signal_xyz")
    assert result.confidence == "uncertain"
```

---

## 七、项目协作

### 铁律 23：支持管道化组合 [A]

**必须**：App 输出可以被下一个 App 或 Query 调用消费

**自动化测试**：
```python
def test_apps_composable():
    profile = signal_profile_app.run("top.data")
    assert profile.structured is not None
```

---

### 铁律 24：每个新 App 必须提供调用示例 [M]

**手动审查清单**：
- [ ] docstring 包含至少一个使用示例？
- [ ] examples/ 目录包含对应脚本？

---

### 铁律 25：文档与代码同步更新 [M]

**手动审查清单**：
- [ ] 新增 App → `ARCHITECTURE.md` 的 App 清单已更新？
- [ ] 新增铁律 → 本文件已更新？

---

## 八、禁止模式汇总

**P0 铁律（不可妥协）**：
- ❌ 禁止直接正则分析 SV 源码（铁律 1）
- ❌ 禁止维护 DiGraph 之外的自定义索引（铁律 2）
- ❌ 禁止 Python 层覆盖 slang 拓扑（铁律 3）
- ❌ 禁止跳过或注释回归测试（铁律 4、5）
- ❌ 禁止未确认就实现（铁律 6）

**P1 质量（Query Layer）**：
- ❌ Query Layer 返回带 summary 的对象（铁律 12）
- ❌ App 直接调用 DesignGraph 而非通过 QueryService（铁律 13）

**P2 架构（Graph/App Layer）**：
- ❌ DesignGraph 暴露内部 DiGraph（铁律 14）
- ❌ StatementExplorer 调用 add_edge（铁律 15）
- ❌ 核心构建流程依赖 annotators（铁律 16）
- ❌ App 之外的其他层生成 summary（铁律 17）

---

## 九、铁律自动化覆盖度汇总

| 铁律 | 覆盖状态 | 自动化测试文件 | 重要度 |
|------|----------|---------------|--------|
| 1 | [A] | `test_no_regex_in_analysis_files.py` | P0 |
| 2 | [A] | `test_no_custom_indexes.py` | P0 |
| 3 | [A] | `test_slang_authority.py` | P0 |
| 4 | [A] | CI gate `pytest exit-code == 0` | P0 |
| 5 | [A] | `test_no_commented_tests.py` | P0 |
| 6 | [A] | `test_no_rush_commit_without_design_review.py` | P0 |
| 7 | [M] | 手工审查清单 | P0 |
| 8 | [A] | `test_no_app_impl_without_golden.py` | P1 |
| 9 | [A] | `test_golden_cover_corner_cases.py` | P1 |
| 10 | [A] | `test_error_must_set_uncertain.py` | P1 |
| 11 | [A] | `test_confidence_values.py` | P1 |
| 12 | [A] | `test_query_service_no_summary.py` | P1 |
| 13 | [A] | `test_apps_no_direct_graph_access.py` | P1 |
| 14 | [A] | `test_design_graph_no_public_graph.py` | P1 |
| 15 | [A] | `test_statement_explorer_no_add_edge.py` | P2 |
| 16 | [A] | `test_annotators_optional.py` | P2 |
| 17 | [A] | `test_only_apps_generate_summary.py` | P2 |
| 18 | [A] | `test_one_app_per_file.py` | P2 |
| 19 | [A] | `test_experimental_app_has_flag.py` | P2 |
| 20 | [A] | `test_visitor_pattern.py` | P2 |
| 21 | [A] | `test_strong_assertions.py` | P2 |
| 22 | [A] | `test_negative_cases.py` | P2 |
| 23 | [A] | `test_apps_composable.py` | P3 |
| 24 | [M] | `test_agent_examples.py`（TBD）| P3 |
| 25 | [M] | CI doc diff 检测（TBD）| P3 |

**当前状态**：
- [A] 已自动化：23 条
- [M] 纯手工审查：2 条
- [TBD] 尚未实现：0 条

---

## 十、新 App / 模块提交流核

**P0 门控（自动化 CI 检查，失败即阻断）**：
- [ ] 铁律 1: 无正则源码分析？
- [ ] 铁律 2: 无自定义索引？Phase 1 无缓存？
- [ ] 铁律 3: Python 不覆盖 slang 拓扑？
- [ ] 铁律 4: 回归测试全部通过？
- [ ] 铁律 5: 无临时补丁或被注释的测试？
- [ ] 铁律 6: 是否经过用户确认的规划方案？

**P1 门控（自动化 CI 检查）**：
- [ ] 铁律 8: 先有金标准测试？
- [ ] 铁律 9: 金标准覆盖 Corner Case？
- [ ] 铁律 10: 解析失败时返回 uncertain？
- [ ] 铁律 12: Query Layer 不返回带 summary 的对象？
- [ ] 铁律 13: App 通过 QueryService 获取数据？

**P2 架构检查（CI 检查）**：
- [ ] 铁律 14: DesignGraph 不暴露内部 DiGraph？
- [ ] 铁律 15: StatementExplorer 不调用 add_edge？
- [ ] 铁律 16: 核心构建流程不依赖 annotators？
- [ ] 铁律 17: 只有 App 层生成 summary？
- [ ] 铁律 18: 一个文件一个 App？

**P3 协作检查（人工审查）**：
- [ ] 铁律 24: 提供 Agent 调用示例？
- [ ] 铁律 25: 文档已同步更新？

---

## 十一、slang-netlist 限制声明（新增）


### 铁律 26：PathFinder 时序追踪限制 [M]

**描述**：当同一信号在两个 always block 中赋值时，PathFinder 可能无法追踪到该路径。

**原因**：这是 slang-netlist 的设计限制，不是实现 bug。

**示例**：
```verilog
always @(posedge clk)
    b = a;           // combinational style =
always_ff @(posedge clk)
    b <= a;          // sequential style <=
// PathFinder 报告 a -> b 不可达，但时序路径确实存在
```

**处理方式**：
- 在设计阶段避免一个信号在多个 always block 中赋值
- 向用户说明此限制

---

### 铁律 27：组合逻辑中间信号透明性 [M]

**描述**：组合逻辑中间信号（wire/assign）在图中是"透明"的。


**表现**：
- Path 会穿过它们
- 它们不是 Named Node（无法 `graph.lookup("mod.wire_name")`）
- 只能作为路径中间节点，不能直接查询 driver

**示例**：
```verilog
wire w = a & b;
assign out = w | c;
// w 是透明节点，a -> out 路径存在，但无法单独查询 w 的 driver
```

---


### 铁律 28：Python 绑定限制 [M]

**描述**：部分 slang-netlist C++ API 未暴露到 Python 绑定。

**受限 API**：
- `PathFinder.find_comb()` — 纯组合路径查找（遇 State 停止）
- `graph.getSensitivity()` — 获取 State 的 clock/reset 信号
- `graph.get_comb_fan_in/out()` — 组合扇入/扇出


**处理方式**：
- 使用 networkx BFS 作为 fallback
- 或扩展 Python 绑定直接调用 C++


---

*RULES.md 版本：v0.7*
*修改：2026-05-18*
*下次审查：2026-07-01*