# navisv 端到端工作流：RTL → Constraint → Coverage

本文档介绍如何用 navisv 构建 **RTL 信号 → 约束 → 覆盖** 的完整分析链路。

## 场景描述

在芯片验证中，一个典型的工作流是：

```
设计工程师写 RTL
    ↓
验证工程师写 constraint (随机化约束)
    ↓
验证工程师写 covergroup (覆盖率目标)
    ↓
问题：约束产生的值空间，是否被覆盖组完整覆盖？
```

navisv 将这三个环节打通，实现自动化分析。

## 架构

```
┌─────────────────────────────────────────────────────┐
│                    DesignDriver                      │
│  (统一入口: 编译 + 解析 + 构建)                       │
└──────────┬──────────┬──────────┬─────────────────────┘
           │          │          │
     ┌─────▼─────┐ ┌──▼──────┐ ┌▼──────────────┐
     │DesignGraph│ │Constraint│ │CoverGroup      │
     │           │ │Graph     │ │Analyzer        │
     │• 信号查询  │ │• 约束类   │ │• covergroup    │
     │• 路径追踪  │ │• 变量    │ │• coverpoint    │
     │• 时序分析  │ │• 约束    │ │• bins          │
     │• 条件覆盖  │ │• 关系    │ │• cross         │
     └─────┬─────┘ └──┬──────┘ └┬──────────────┘
           │          │          │
           └──────────┼──────────┘
                      │
              ┌───────▼───────┐
              │  交叉分析      │
              │  约束 vs 覆盖  │
              └───────────────┘
```

## 工作流详解

### Step 1: 从 RTL 信号出发

```python
dg = dd.design_graph

# 找到信号
paths = dg.resolve_signal_path('*data*')

# 分析驱动/负载
drivers = dg.get_drivers('top.data_in')  # 谁驱动这个信号？
loads = dg.get_loads('top.data_in')      # 这个信号驱动谁？

# Fan-in/Fan-out 分析
fanin = dg.get_fanin_cone('top.data_in', depth=3)   # 上游锥
fanout = dg.get_fanout_cone('top.data_in', depth=3)  # 下游锥
```

**输出示例：**
```
信号 'data_in':
  驱动: 0 个 (顶层输入)
  负载: 6 个 (pipeline_data, mode, ...)
  Fan-out: 4 个 (data_out, overflow, ...)
```

### Step 2: 路径追踪

```python
# 从输入到输出的完整路径
r = dg.trace_path('top.data_in', 'top.data_out')
print(f"status={r['success']} hops={len(r['path'])}")

# 路径上的信号
for p in r['path']:
    print(f"  {p['path']}")
```

**输出示例：**
```
data_in → data_out: success=True hops=5
  data_in
  pipeline_data
  pipeline_data
  data_out
  data_out
```

### Step 3: 约束分析

```python
cg = dd.constraint_graph

# 获取所有约束类
for cls in cg.get_classes():
    cls_name = cls['name']
    
    # 变量
    for v in cg.get_variables_in_class(cls_name):
        print(f"  {v['name']}: {v['type_str']} rand={v['rand_mode']}")
    
    # 约束
    for c in cg.get_constraints_in_class(cls_name):
        print(f"  {c['name']}: {c['constraint_body']}")
        if c['is_conditional']:
            print(f"    [条件约束]")
```

**输出示例：**
```
类 data_constraint:
  变量:
    data      bit[7:0]  rand=Rand
    op_mode   bit[1:0]  rand=Rand
  约束:
    c_data_range:  data inside {0:200}
    c_mode3_limit: if (op_mode == 2'b11) { data < 100 }  [条件]
    c_no_zero:     data != 0
```

### Step 4: 覆盖分析

```python
ca = dd._covergroup_analyzer

for cg_info in ca.get_covergroups():
    cg_name = cg_info['name']
    
    # Coverpoint 和 bins
    for cp in ca.get_coverpoints_by_cg(cg_name):
        bins = ca.get_bins(cg_name, cp['name'])
        for b in bins:
            print(f"  {b['name']}: {b['values']} [{b['kind']}]")
    
    # Cross
    for cx in ca.get_crosses(cg_name):
        print(f"  cross: {cx['targets']}")
```

**输出示例：**
```
CoverGroup cg_data:
  Coverpoint cp_data:
    bin low:      [1:50]    [Bins]
    bin mid:      [51:100]  [Bins]
    bin high:     [101:200] [Bins]
    bin extreme:  [201:255] [Bins]
    bin zero_val: [0:0]     [Bins]
  Coverpoint cp_mode:
    bin m0: [0:0]  bin m1: [1:1]  bin m2: [2:2]  bin m3: [3:3]
  Cross cx_data_mode: [cp_data, cp_mode]
```

### Step 5: 约束-覆盖交叉分析

这是核心价值——自动检查约束空间是否被覆盖：

```python
# 对每个约束变量
for v in cg.get_variables_in_class(cls_name):
    var_path = v['full_path']
    
    # 获取相关约束
    constraints = cg.get_constraints_for_variable(var_path)
    
    # 解析约束范围
    constraint_ranges = []
    for c in constraints:
        body = c['constraint_body']
        if 'inside' in body:
            # 解析 inside {lo:hi}
            lo, hi = parse_inside_range(body)
            constraint_ranges.append((lo, hi))
        if '!=' in body:
            # 解析 != value
            constraint_ranges.append((1, max_val))
    
    # 找匹配的 coverpoint
    for cp in coverpoints:
        if var_name in cp_name:
            bins = ca.get_bins(cg_name, cp_name)
            
            # 检查每个 bin 是否在约束范围内
            for b in bins:
                for lo, hi in b['values']:
                    if in_constraint_range(lo, hi, constraint_ranges):
                        print(f"✅ bin '{b['name']}': [{lo}:{hi}]")
                    else:
                        print(f"⬜ bin '{b['name']}': [{lo}:{hi}] (约束外)")
            
            # 检查约束范围是否完全覆盖
            merged = merge_covered_ranges(bins)
            if covers_all(merged, constraint_ranges):
                print(f"✅ 约束范围完全覆盖")
            else:
                print(f"❌ 约束范围未完全覆盖")
                print(f"   缺失区间: {find_gaps(merged, constraint_ranges)}")
```

**输出示例：**
```
变量 'data' (bit[7:0]):
  约束范围: [(0, 200)]
  条件约束: ["if (op_mode == 2'b11) { data < 100 }"]

  覆盖 cg_data.cp_data:
    ✅ bin 'low':      [1:50]
    ✅ bin 'mid':      [51:100]
    ✅ bin 'high':     [101:200]
    ✅ bin 'zero_val': [0:0]
  ⚠️ 约束外 bin:
    ⬜ bin 'extreme':  [201:255]

  ✅ 约束范围 [0:200] 完全覆盖
```

## 运行示例

```bash
cd ~/my_dv_proj/navisv
python3 examples/e2e_rtl_to_coverage.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `examples/e2e_rtl_to_coverage.sv` | 测试 SV 文件 (数据通路 + 约束 + 覆盖组) |
| `examples/e2e_rtl_to_coverage.py` | 端到端分析脚本 |

## 实际应用场景

### 场景 1: 验证完备性检查

验证工程师写了 constraint 和 covergroup，想知道：
- 约束产生的值空间是否被完整覆盖？
- 有哪些 bin 在约束范围外（不需要覆盖）？
- 有哪些约束范围没有被任何 bin 覆盖？

### 场景 2: 约束修改影响分析

修改了约束（扩大/缩小范围），需要知道：
- 哪些 bin 现在在约束外了？
- 需要新增哪些 bin 来覆盖新约束？

### 场景 3: 信号溯源

从一个寄存器出发，想知道：
- 数据从哪里来？（fan-in）
- 数据到哪里去？（fan-out）
- 中间经过了哪些条件逻辑？

## 扩展

此示例展示了基础流程。实际项目中可以扩展：

1. **多模块分析**：跨模块的约束-覆盖对齐
2. **条件约束细化**：解析 `if/else` 约束的分支范围
3. **Cross 覆盖分析**：检查交叉覆盖是否满足约束组合
4. **自动化报告**：生成 HTML/PDF 报告
5. **CI 集成**：在回归测试中自动检查覆盖完备性
