# slang-netlist 工具能力参考文档

> 本文档记录 slang 和 slang-netlist 的所有可用功能，供 navisv 实现时参考。

## 目录

1. [工具路径与版本](#1-工具路径与版本)
2. [slang 能力](#2-slang-能力)
3. [slang-netlist 能力](#3-slang-netlist-能力)
4. [TODO 功能](#4-todo-功能)
5. [使用示例](#5-使用示例)

---

## 1. 工具路径与版本

| 工具 | 路径 | 版本 |
|------|------|------|
| slang | `~/my_dv_proj/slang/slang` | 11.0.0+7ddf4059f |
| slang-netlist | `~/my_dv_proj/slang-netlist/build/tools/driver/slang-netlist` | 10.0.298+ad31b01a8 |

### 工具检查

```python
from navisv.drivers import SlangDriver, NetlistDriver

# 检查工具可用性
print(SlangDriver.check_available())   # True/False
print(NetlistDriver.check_available()) # True/False

# 获取版本
print(SlangDriver.get_version())       # slang version 11.0.0+...
print(NetlistDriver.get_version())     # slang-netlist version 10.0.298+...
```

---

## 2. slang 能力

### 2.1 基础输出

| 选项 | 输出 | 说明 |
|------|------|------|
| `--ast-json <file>` | AST JSON | 完整抽象语法树 |
| `--cst-json <file>` | CST JSON | 语法树（保留空白符） |
| `--diag-json <file>` | 诊断 JSON | 编译诊断信息 |
| `--ast-json-source-info` | 包含源码位置 | 文件/行/列信息 |
| `--ast-json-detailed-types` | 包含类型详情 | 详细类型推导 |
| `--ast-json-scope <path>` | 限定范围 | 只导出指定模块的 AST |

### 2.2 分析功能

| 选项 | 说明 |
|------|------|
| `--fan-in <name>` | 分析信号扇入 |
| `--fan-out <name>` | 分析信号扇出 |

### 2.3 编译选项

| 选项 | 说明 |
|------|------|
| `--std <ver>` | 语言版本 (1364-2005, 1800-2017, 1800-2023, latest) |
| `-I, --include-directory <dir>` | include 搜索路径 |
| `-D, --define <macro>=<value>` | 宏定义 |
| `--top <name>` | 指定顶层模块 |
| `-G <name>=<value>` | 参数覆盖 |

### 2.4 容错选项

| 选项 | 说明 |
|------|------|
| `--ignore-unknown-modules` | 忽略未知模块实例化 |
| `--allow-lib-module-redef` | 允许库文件重复定义 |
| `--lint-only` | 只做 lint，不完整 elaborate |
| `--relax-enum-conversions` | 允许隐式枚举转换 |

### 2.5 诊断选项

| 选项 | 说明 |
|------|------|
| `--diag-source` | 显示源码行 |
| `--diag-location` | 显示位置 |
| `--diag-column` | 显示列号 |
| `--diag-include-stack` | 显示 include 栈 |
| `--error-limit <n>` | 错误数量限制 |

---

## 3. slang-netlist 能力

### 3.1 输出格式

| 选项 | 输出 | 说明 |
|------|------|------|
| `--save-netlist <file>` | Netlist JSON | 节点+边的完整 netlist |
| `--load-netlist <file>` | - | 从 JSON 加载（跳过编译） |
| `--netlist-dot <file>` | DOT 格式 | Graphviz 可视化 |
| `--diag-json <file>` | 诊断 JSON | 编译诊断 |

### 3.2 分析报告

| 选项 | 说明 |
|------|------|
| `--report-registers` | 报告所有寄存器 | State 节点 |
| `--comb-loops` | 报告组合环路 | 检测反馈环 |
| `--fan-in <name>` | 扇入分析 | 驱动该信号的来源 |
| `--fan-out <name>` | 扇出分析 | 该信号驱动的目标 |
| `--from <name> --to <name>` | 路径跟踪 | 两点间路径 |
| `--find <pattern>` | 通配符查找 | 支持 * 和 ? |
| `--find-regex <pattern>` | 正则查找 | 正则表达式匹配 |

### 3.3 编译选项

与 slang 相同（见 2.3）

### 3.4 黑盒处理

| 选项 | 说明 |
|------|------|
| `--black-box <pattern>` | 将匹配的实例设为黑盒 | 排除其内部细节 |

### 3.5 性能选项

| 选项 | 说明 |
|------|------|
| `--stats` | 阶段耗时统计 | parsing/elaboration/analysis/netlist |
| `--stats-json` | JSON 格式统计 | 便于程序解析 |
| `-j, --threads <n>` | 并行线程数 | 加速大型设计 |

### 3.6 依赖生成

| 选项 | 输出 | 说明 |
|------|------|------|
| `--Mall, --all-deps <file>` | makefile 格式 | 所有文件依赖 |
| `--Minclude <file>` | include 文件 | 仅 include 文件 |
| `--Mmodule <file>` | 模块文件 | 仅源文件 |

---

## 4. TODO 功能

### 4.1 高优先级

- [ ] **缓存策略**
  - 文件 hash 比对
  - 修改时间检测
  - JSON 文件复用（--load-netlist）

- [ ] **报告生成器**
  - 组合多种报告
  - 寄存器列表
  - 组合环路
  - 节点清单
  - 诊断摘要

- [ ] **错误恢复**
  - --ignore-unknown-modules
  - --allow-lib-module-redef
  - --lint-only

### 4.2 中优先级

- [ ] **参数覆盖**
  - 大型设计常用参数
  - 配置化参数传递
  - 复杂类型参数（axi_pkg::axi_req_t）

- [ ] **依赖分析**
  - --Mall 生成依赖文件
  - 构建系统集成

- [ ] **DOT 可视化**
  - 转换为 SVG/PNG/PDF
  - Jupyter 集成

### 4.3 低优先级

- [ ] **多信号分析**
  - 批量 fan-in/fan-out
  - 批量 path-trace

- [ ] **正则查询**
  - --find-regex 高级用法
  - 批量节点查询

---

## 5. 使用示例

### 5.1 基础用法

```python
from navisv.drivers import SlangDriver, NetlistDriver

files = ['design.sv', 'pkg.sv']
driver = SlangDriver(files, include_dirs=['./include'])
result = driver.run()

if result['success']:
    print(f"AST: {result['ast_json']}")
    print(f"Errors: {result['error_count']}")
    print(f"Warnings: {result['warning_count']}")
```

### 5.2 完整分析流程

```python
from navisv.drivers import SlangDriver, NetlistDriver

files = ['design.sv']
driver = NetlistDriver(files)

# 1. 生成 netlist
netlist = driver.run()
print(f"Netlist edges: {netlist['success']}")

# 2. 报告寄存器
regs = driver.run_report_registers()
print(f"Registers: {regs['registers']}")

# 3. 检查组合环路
loops = driver.run_comb_loops()
print(f"Comb loops: {loops['count']}")

# 4. 扇入分析
fan_in = driver.run_fan_in('top.cpu.alu.result')
print(f"Fan-in: {fan_in['fan_in']}")

# 5. 查找节点
found = driver.run_find('*alu*')
print(f"Found: {found['nodes']}")

# 6. DOT 导出
dot = driver.run_dot('/tmp/design.dot')
```

### 5.3 带 scope 的 AST

```python
driver = SlangDriver(['design.sv'])

# 完整 AST
full = driver.run()
print(f"Full: {full['json_size']} bytes")  # 64196

# 限定范围（大幅减小）
alu_ast = driver.run(scope='top.alu_inst')
print(f"ALU: {alu_ast['json_size']} bytes")  # 17049
```

### 5.4 参数覆盖

```python
driver = SlangDriver(
    files=['cva6.sv'],
    params={
        'DATA_WIDTH': '64',
        'NUM_CORES': '4',
        'CVA6Cfg': 'config_pkg::cva6_cfg_empty'
    }
)
result = driver.run()
```

### 5.5 容错模式

```python
# 允许未知模块，只做 lint
driver = SlangDriver(
    files=['design.sv'],
    extra_args=['--ignore-unknown-modules', '--lint-only']
)
```

---

## 附录：JSON 输出格式

### slang --ast-json

```json
{
  "design": {
    "name": "$root",
    "kind": "Root",
    "members": [
      {
        "name": "top",
        "kind": "Instance",
        "body": {
          "name": "top",
          "kind": "InstanceBody",
          "members": [
            {"name": "clk", "kind": "Port", "direction": "In", ...},
            {"name": "data", "kind": "Net", ...}
          ]
        }
      }
    ]
  }
}
```

### slang-netlist --save-netlist

```json
{
  "edges": [
    {
      "source": 1,
      "target": 18,
      "symbol": {
        "path": "top.alu_inst.a",
        "location": {"line": 4, "column": 22}
      },
      "bounds": [0, 7],
      "edgeKind": "None"
    }
  ],
  "nodes": [
    {"id": 1, "name": "a", "kind": "Port"},
    ...
  ]
}
```