# navisv Covergroup 分析设计方案

> 日期: 2026-05-27
> 状态: ✅ 已完成 (Step 1-3)

---

## 痛点

### 痛点 1: bin 与 constraint 一致性
- coverage 中的 bin 定义是否与 constraint 约束一致？
- 是否存在漏定义 illegal bin 的情况？
- 有没有永远 hit 不到的 bin（被 constraint 排除但没有标 illegal）？
- 有没有 constraint 允许但没有对应 bin 的取值（遗漏覆盖）？

### 痛点 2: coverage 质量评估
- RTL 收集的 coverage，sample 条件是否合适？
- bin 定义是否能反映出信号特性：
  - **data 类信号**: 更关心数值范围、极值（0、max、边界值）
  - **control 类信号**: 更关心 cross、大小关系、特殊值（idle、error、default）
- 涉及的相关信号是否被联合覆盖（需要图来描述数据关系）

---

## 实现结果

### Step 1: CoverGroup 解析 ✅

**文件**: `navisv/parsers/covergroup_parser.py`

从 slang AST 提取 covergroup 定义，支持：
- CovergroupType / CovergroupBody
- Coverpoint + CoverageBin (bins/illegal_bins/ignore_bins)
- CoverCross + cross bins
- wildcard bins / default bin
- class 中的 covergroup（匿名 CovergroupType 从 ClassProperty 取名）
- 同一 class/module 多个 covergroup（full_path 去重）

**测试**: 33 个 (`test_covergroup.py`)

**关键数据结构**:
```python
CovergroupInfo:     name, full_path, location, coverpoints, crosses, options, sample_event
CoverpointInfo:     name, full_path, covergroup, bins, options
CrossInfo:          name, full_path, covergroup, targets, bins
BinInfo:            name, kind, values, is_wildcard, is_default, cross_select
```

### Step 2: bin-constraint 一致性检查 ✅

**文件**: `navisv/graph/covergroup_analyzer.py` (`check_bin_constraint_consistency`)

对比 coverpoint bins 与 ConstraintGraph 的约束范围：
- **死 bin 检测**: bin 范围被 constraint 排除 → 永远 hit 不到
- **遗漏 bin 检测**: constraint 允许的取值没有 bin 覆盖
- **illegal bin 缺失**: constraint 禁止的取值没有标 illegal_bins
- **部分重叠**: bin 范围与 constraint 部分重叠

**测试**: 12 个 (`test_cg_constraint_check.py`)

**约束范围解析**: 正则提取 `inside { lo:hi }`，支持多分支条件约束（合并所有分支的范围）

**输出示例**:
```
dead_bin_cls.data:
  ⚠️  dead_bin: bin [101:200] 被 constraint 排除, 永远无法 hit
  ⚠️  dead_bin: bin [255:255] 被 constraint 排除, 永远无法 hit
  ⚠️  missing_illegal_bin: constraint 禁止的取值没有标 illegal_bins
```

### Step 3: coverage 质量评估 ✅

**文件**: `navisv/graph/covergroup_analyzer.py` (`check_coverage_quality` / `check_cg_quality`)

评估 bin 策略是否合理：
- **data 类信号**: 检查是否有独立极值 bin (zero/max)、bin 粒度
- **control 类信号**: 检查是否有特殊值 bin、状态覆盖
- **covergroup 级别**: 检查是否有 cross 覆盖

**测试**: 9 个 (`test_cg_quality.py`)

**评分规则**:
- data: 缺 zero -0.2, 缺 max -0.2, bin 少于 3 -0.1
- control: 缺特殊值 bin -0.3, bin 不足 -0.3
- cg 级别: 多 cp 无 cross -0.3, cp 无 bins -0.3

**输出示例**:
```
差 data (score=0.5):
  ⚠️  缺少极值 bin: 建议添加 bins zero = {0}
  ⚠️  缺少极值 bin: 建议添加 bins max = {255}
  ⚠️  bin 数量较少 (2), 建议细化范围划分

差 ctrl (score=0.5):
  ⚠️  control 信号缺少特殊值 bin: 建议为每个状态值创建独立 bin
  ⚠️  control 信号 bin 数量不足 (1), 建议覆盖所有状态
```

---

## 数据流

```
SV 源文件
  │
  ├──slang──→ AST JSON
  │              │
  │              ├──→ ConstraintParser ──→ ConstraintGraph
  │              │
  │              ├──→ ASTParser ──→ DesignGraph
  │              │
  │              └──→ CovergroupParser ──→ CovergroupAnalyzer
  │                                          │
  │                                          ├── get_covergroups() / get_bins()
  │                                          ├── check_bin_constraint_consistency()
  │                                          └── check_coverage_quality() / check_cg_quality()
  │
  └──→ CLI
         ├── navisv cg-list <file>           # 列出 covergroup/coverpoint/bins
         ├── navisv cg-check <file> var cg cp  # bin-constraint 一致性
         └── navisv cg-quality <file> var cg cp  # coverage 质量评估
```

---

## slang AST 中 covergroup 的表示

已确认的 AST 结构：

```
CovergroupType (name=pkt_cg)
  └── CovergroupBody
        ├── ClassProperty (option, type_option)
        ├── Coverpoint (name=cp_length)
        │     ├── ClassProperty (option, type_option)
        │     ├── CoverageBin (name=zero, binsKind=Bins, values=[{0}])
        │     ├── CoverageBin (name=low,  binsKind=Bins, values=[{1:16}])
        │     └── CoverageBin (name=overflow, binsKind=IllegalBins, values=[{65:255}])
        ├── CoverCross (name=cx_mode_err)
        │     ├── targets: [cp_mode, cp_err]
        │     └── CoverCrossBody
        │           └── CoverageBin (name=mode0_err, binsKind=IllegalBins, crossSelect=...)
        └── CoverCross (name=cx_len_data)
              └── targets: [cp_length, cp_data]
```

关键字段：
- `CoverageBin.binsKind`: `Bins` / `IllegalBins` / `IgnoreBins`
- `CoverageBin.values`: 值列表 (IntegerLiteral 或 ValueRange)
- `CoverageBin.crossSelect`: cross 条件 (Condition + Binary + and/or)
- `CoverCross.targets`: 被 cross 的 coverpoint 列表
- `SignalEvent`: sample 事件 (`@(posedge clk)` 的 edge + expr)

---

## 待讨论问题

1. ~~covergroup 一般在 class 中还是 module 中？~~ → 两者都支持 ✅
2. ~~bins 的定义方式有哪些需要支持？~~ → 已支持固定范围、单值、wildcard、default ✅
3. ~~cross 的复杂度？~~ → 已支持 2 维 cross + 自定义 cross bins ✅
4. ~~coverage 质量评估的评分标准？~~ → 打分制 (扣分制) ✅
5. 关联信号覆盖的深度？→ 待做
