# navisv Code Review

> 日期: 2026-05-22
> 评审人: AI (资深程序员视角)
> 项目: 基于 slang-netlist 的 SystemVerilog 语义导航工具

---

## 整体评价

**定位清晰，踩点实用**。用 slang 做前端解析，用 networkx 做图查询，这个组合是对的。RTL 调试场景里，能直接问「信号 A 到信号 B 的路径是什么」确实有价值。

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | 7/10 | 方向对，但封装差 |
| 代码质量 | 5/10 | 缺类型、错误处理粗暴 |
| 功能完整性 | 7/10 | 覆盖核心场景 |
| 可维护性 | 5/10 | 内部实现泄漏严重 |
| 测试覆盖 | 5/10 | 有测试但依赖硬编码路径 |

---

## 问题清单

### 🔴 P0 - 必须修复（阻塞发布）

#### 1. 封装破损 - 内部实现泄漏
**文件**: `navisv/graph/design_graph.py`

```python
@property
def _signal_conditions(self) -> Dict[str, List[Dict]]:
    return self._graph_builder._signal_conditions  # 直接暴露内部引用
```

**问题**: `DesignGraph._signal_conditions` 直接返回 `_graph_builder._signal_conditions` 的引用，用户可以直接修改这个字典，绕过 GraphBuilder 的任何逻辑。

**影响**: 
- 数据一致性无法保证
- 用户可能直接修改后影响后续查询结果
- 违反 OOP 封装原则

**建议修复**:
```python
@property
def _signal_conditions(self) -> Dict[str, List[Dict]]:
    return copy.deepcopy(self._graph_builder._signal_conditions)

# 或直接提供公开方法
def get_signal_conditions(self, signal: str) -> List[Dict]:
    """获取信号的条件列表（返回副本）"""
    return copy.deepcopy(self._graph_builder._signal_conditions.get(signal, []))
```

---

#### 2. 多文件编译返回 0 节点
**文件**: `tests/test_navisv.py` / `navisv/drivers/slang_driver.py`

**问题**: 当传入多个 `.sv` 文件时，`design_graph.graph.nodes` 返回空，但测试改成了「只要不崩溃就行」掩盖了问题。

**根本原因**: 可能包括：
- 多个 `.sv` 文件之间有依赖但没被 slang 正确解析
- include 路径传递有问题
- 多文件场景下 slang 需要 `--top` 指定顶层模块

**建议**:
1. 调查 slang 对多文件的处理方式
2. 如果需要 `--top`，在 DesignDriver 或 SlangDriver 中自动推断
3. 添加错误提示：当节点为 0 时给出明确原因

---

### 🟠 P1 - 应该修复（影响体验）

#### 3. 字符串路径匹配脆弱
**文件**: `navisv/graph/design_graph.py` (trace_full_path 等方法)

```python
if signal in path  # 模糊匹配
```

**问题**: `signal in path` 会产生误匹配，比如 `clk` 会匹配到 `clk_presc`。

**建议修复**: 使用精确匹配或前缀匹配。

---

#### 4. 错误处理粗糙
**文件**: `navisv/drivers/slang_driver.py`

```python
try:
    with open(diag_json) as f:
        diag_data = json_module.load(f)
except (json_module.JSONDecodeError, IOError):
    pass  # 吞掉异常
```

**问题**: 异常被静默吞掉，用户看不到任何错误信息。

**建议修复**: 
- 底层工具报错 → 原样返回 `stderr`
- 解析层报错 → 返回结构化错误 + 建议

---

#### 5. 测试依赖硬编码路径
**文件**: `tests/test_navisv.py`

```python
TEST_SIGNAL_ATTRS = '/tmp/test_signal_attrs.sv'
```

**问题**: 测试文件路径写死，跨环境运行会失败。

**建议修复**:
```python
@pytest.fixture
def test_file(tmp_path):
    # 创建临时测试文件或复制测试文件
    ...

def test_single_file_build(self, test_file):
    ...
```

---

### 🟡 P2 - 改进建议（提升质量）

#### 6. 缺少类型注解
**问题**: 大量函数缺少类型提示，可读性差。

**建议**: 逐步添加类型注解，从公共 API 开始。

---

#### 7. Graph 是一次性构建
**问题**: `GraphBuilder.build()` 是一次性构建，后续不支持增量更新。

**建议**: 如需支持增量更新，考虑引入版本管理或脏标记机制。

---

## TODO Items

### P0 - 必须修复

- [x] **FIX: 封装 _signal_conditions**
  - [x] 改为 name mangling 存储 `__signal_conditions`
  - [x] 提供公开的 `get_signal_conditions(signal)` 方法
  - [x] `_signal_conditions` 访问发出废弃警告
  - [x] 验证修改后不影响现有功能 (43 tests passed)

- [x] **FIX: 多文件编译返回 0 节点**
  - [x] 实现方案 C: 多文件自动生成临时 filelist 调用 slang -F
  - [x] 添加测试 `test_compile_check_multi_files`
  - [x] 验证修改后不影响现有功能 (43 tests passed)

### P1 - 应该修复

- [ ] **IMPROVE: 路径精确匹配**
  - [ ] 模糊匹配改为前缀匹配或精确匹配
  - [ ] 添加单元测试验证匹配逻辑

- [x] **IMPROVE: 错误处理**
  - [x] 解析错误时返回结构化错误信息 (新增 `parse_error` 字段)
  - [x] 添加 logging 模块 (logger.warning)
  - [x] 吞掉的异常改为记录或返回警告 (43 tests passed)

- [x] **IMPROVE: 测试路径可配置**
  - [x] 使用 `pytest.fixture` + `tmp_path`
  - [x] 创建 conftest.py 定义 fixtures
  - [x] 添加注释说明推荐用法 (43 tests passed)

### P2 - 改进建议

- [ ] **ADD: 类型注解**
  - [ ] DesignGraph 公共方法加类型注解
  - [ ] GraphBuilder 公共方法加类型注解

- [ ] **ARCH: 增量更新支持** (可选)
  - [ ] 评估是否需要
  - [ ] 如需要，设计增量更新机制

---

## 附录：相关文件

| 文件 | 说明 |
|------|------|
| `navisv/graph/design_graph.py` | DesignGraph，核心查询 API |
| `navisv/graph/graph_builder.py` | GraphBuilder，图构建逻辑 |
| `navisv/drivers/slang_driver.py` | SlangDriver，slang 封装 |
| `tests/test_navisv.py` | pytest 测试套件 |