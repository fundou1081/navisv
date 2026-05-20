# Examples

示例脚本，展示 navisv 的核心功能。

## 运行方式

```bash
cd ~/my_dv_proj/navisv
PYTHONPATH=. /usr/bin/python3 examples/01_signal_info.py
```

## 示例列表

### 01_signal_info.py - 信号完整信息查询

展示 `get_signal_info()` API 获取信号完整信息：
- 驱动源 (drivers)
- 负载 (loads)
- 时序属性 (target_kind, clock_domain, reset_kind)
- 条件列表 (conditions)

输出示例：
```
============================================================
示例 1: 信号完整信息查询
============================================================

[1] 加载设计: /tmp/test_signal_attrs.sv
    → 加载成功，共 6 个信号

[2] 查询信号: test_signal_attributes.result

[3] 信号属性:
    类型: set()
    时钟域: set()
    Reset类型: set()

[4] 条件列表 (5 个):
    1. rst_n
       类型: if
       语句: result <= 8'h00...
```

### 02_registers.py - 寄存器报告

展示如何生成完整的寄存器列表，包含时钟域和 Reset 类型统计。

输出示例：
```
============================================================
示例 2: 寄存器报告
============================================================

    时钟域: clk (4 个寄存器)
    信号                                  Reset   
    ----------------------------------- --------
    case_out                            sync    
    complex_reg                         async   
    no_reset_reg                        none    
    result                              async   

    时钟域: clk2 (1 个寄存器)
    信号                                  Reset   
    ----------------------------------- --------
    clk2_reg                            async   

[3] 统计:
    总寄存器数: 5
    Async reset: 3
    Sync reset: 1
    No reset: 1
```

### 03_conditions.py - 条件分析

展示 `get_all_conditions()` API 分析信号的所有条件，包括：
- 条件类型 (if/case/ternary/plain)
- 时序属性
- 源码文本

输出示例：
```
============================================================
示例 3: 条件分析
============================================================

[3] 条件类型分布:
    case: 4 个
    if: 1 个
    plain: 5 个

[4] 详细条件:
    条件 1:
      条件表达式: rst_n
      类型: if
      目标类型: register_output
      时钟域: clk
      Reset类型: sync
      语句: case_out <= 8'h00
      边: [{'from': 'test_signal_attributes.clk', ...}]
```